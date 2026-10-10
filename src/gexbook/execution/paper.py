"""Paper market fills use BBO + adverse slippage; stops gap and targets do not improve."""

from gexbook.config import Config
from gexbook.models import Position, Signal, Trade
from gexbook.risk.manager import RiskManager
from gexbook.bookmap.flow import Metrics
from gexbook.mapping.anchors import round_tick


class PaperBroker:
    def __init__(self, config: Config, risk: RiskManager):
        self.c, self.risk = config, risk
        self.positions = []
        self.trades = []
        self.pending = None
        self.last_rejection = ""
        self.flatten_requested = False
        self.last_equity = config.balance

    def propose(self, signal: Signal):
        if self.pending is None and not self.risk.manual_lock:
            self.pending = signal

    def executable(self, metrics, side, entry=True):
        # Buy at ask, sell at bid, regardless of last traded price.
        quote = metrics.ask if side == 1 else metrics.bid
        if quote is None:
            raise ValueError("No executable quote")
        return round_tick(quote + side * self.c.slippage_ticks * self.c.tick_size)

    def enter_pending(self, now, metrics: Metrics, snapshot: str | None):
        if self.pending is None:
            return None
        s = self.pending
        self.pending = None
        if s.snapshot_id != snapshot:
            self.last_rejection = "Snapshot changed/expired before next-event fill"
            return None
        if metrics.bid is None or metrics.ask is None:
            self.last_rejection = "No executable BBO"
            return None
        fill = self.executable(metrics, s.side)
        approval = self.risk.assess(s, fill, metrics, self.positions, now)
        if not approval.approved:
            self.last_rejection = approval.reason
            return approval
        self.positions.append(
            Position(
                s,
                now,
                fill,
                approval.quantity,
                s.stop,
                s.target,
                self.c.commission_per_side * approval.quantity,
            )
        )
        return approval

    def close(self, p, now, exit_price, reason):
        dollars = self.c.tick_value / self.c.tick_size
        gross = (exit_price - p.entry) * p.signal.side * p.quantity * dollars
        fees = p.entry_fee + self.c.commission_per_side * p.quantity
        trade = Trade(
            p.entry_at,
            now,
            p.signal.side,
            p.quantity,
            p.entry,
            exit_price,
            gross,
            fees,
            gross - fees,
            reason,
            p.signal.level_kind,
            p.signal.confirmation,
            p.signal.explanation,
            p.signal.snapshot_id,
        )
        self.positions.remove(p)
        self.trades.append(trade)
        self.risk.record(trade)
        return trade

    def on_market(self, now, metrics: Metrics):
        if not metrics.reliable:
            return []  # No fabricated fill when disconnected: flatten waits for fresh BBO.
        c, closed = self.c, []
        for p in list(self.positions):
            side = p.signal.side
            quote = metrics.bid if side == 1 else metrics.ask
            if quote is None:
                continue
            reason = None
            if self.flatten_requested or not self.risk.in_session(now):
                reason = "emergency" if self.flatten_requested else "session_end"
            elif side * (quote - p.stop) <= 0:
                reason = "stop"
            elif side * (quote - p.target) >= 0:
                reason = "target"
            if reason:
                fill = p.target if reason == "target" else self.executable(metrics, -side)
                closed.append(self.close(p, now, fill, reason))
            else:
                favorable = side * (quote - p.entry)
                if c.breakeven_at > 0 and favorable >= c.breakeven_at:
                    # Entry price breakeven excludes fees, documented explicitly.
                    p.stop = max(p.stop, p.entry) if side == 1 else min(p.stop, p.entry)
                if c.trailing_points > 0 and favorable >= c.trailing_points:
                    trailing = round_tick(quote - side * c.trailing_points)
                    p.stop = max(p.stop, trailing) if side == 1 else min(p.stop, trailing)
        if not self.positions:
            self.flatten_requested = False
        return closed

    def emergency_flatten(self):
        self.risk.emergency()
        self.pending = None
        self.flatten_requested = True

    def equity(self, metrics):
        if not metrics.reliable:
            return self.last_equity
        unrealized = 0.0
        dollars = self.c.tick_value / self.c.tick_size
        for p in self.positions:
            quote = metrics.bid if p.signal.side == 1 else metrics.ask
            if quote is not None:
                unrealized += (quote - p.entry) * p.signal.side * p.quantity * dollars
                unrealized -= p.entry_fee + self.c.commission_per_side * p.quantity
        self.last_equity = self.c.balance + self.risk.realized + unrealized
        return self.last_equity
