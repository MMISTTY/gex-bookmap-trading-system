"""Independent vetoes and conservative sizing. Strategy scores cannot bypass this module."""

from dataclasses import dataclass
from math import floor, isfinite
from datetime import time
from zoneinfo import ZoneInfo
from gexbook.config import Config
from gexbook.models import Signal, Position, Trade
from gexbook.bookmap.flow import Metrics


@dataclass(frozen=True)
class Approval:
    quantity: int
    risk_per_contract: float
    rr: float
    reason: str

    @property
    def approved(self):
        return self.quantity > 0


class RiskManager:
    def __init__(self, config: Config):
        self.c = config
        self.realized = 0.0
        self.day_realized = 0.0
        self.losses = 0
        self.day = None
        self.locked = False
        self.manual_lock = False

    def roll_day(self, ts):
        day = ts.astimezone(ZoneInfo("America/Chicago")).date()
        if day != self.day:
            self.day, self.day_realized, self.losses, self.locked = day, 0.0, 0, False

    def in_session(self, ts):
        local = ts.astimezone(ZoneInfo("America/Chicago"))
        return local.weekday() < 5 and time.fromisoformat(
            self.c.session_start
        ) <= local.time().replace(tzinfo=None) < time.fromisoformat(self.c.session_end)

    def assess(
        self, signal: Signal, fill: float, metrics: Metrics, positions: list[Position], now
    ) -> Approval:
        self.roll_day(now)
        c = self.c

        def deny(reason):
            return Approval(0, 0, 0, reason)

        if c.mode != "paper" or c.market_symbol != "MNQ":
            return deny("MNQ execution quotes required; NQ proxy is analysis-only")
        if self.manual_lock or self.locked or self.day_realized <= -c.daily_loss:
            return deny("Daily or emergency lockout")
        if self.losses >= c.max_consecutive_losses:
            return deny("Consecutive-loss limit")
        if not self.in_session(now):
            return deny("Outside configured Chicago session")
        if not metrics.reliable or not 0 <= (now - signal.ts).total_seconds() <= c.max_age_seconds:
            return deny("Stale/disconnected/unreliable data or expired signal")
        if not 0 <= (now - metrics.ts).total_seconds() <= c.max_age_seconds:
            return deny("Stale/future risk quote timestamp")
        quotes = (metrics.bid, metrics.ask)
        if (
            any(q is None or not isfinite(q) or q <= 0 for q in quotes)
            or metrics.bid >= metrics.ask
        ):
            return deny("Missing/invalid/crossed executable quotes")
        if len(positions) >= c.max_positions:
            return deny("Open-position limit")
        if any(not isfinite(v) for v in (fill, signal.stop, signal.target)) or signal.side not in (
            1,
            -1,
        ):
            return deny("Invalid order geometry")
        if (
            not signal.side * (fill - signal.stop) > 0
            or not signal.side * (signal.target - fill) > 0
        ):
            return deny("Stop/target no longer bracket fill")
        dollars = c.tick_value / c.tick_size
        fees = 2 * c.commission_per_side
        stop_slip = c.slippage_ticks * c.tick_value
        risk = abs(fill - signal.stop) * dollars + stop_slip + fees
        reward = abs(signal.target - fill) * dollars - fees  # target is a limit, never improved
        rr = reward / risk
        if rr < c.min_rr:
            return deny("Net reward-to-risk below minimum after costs")
        committed = sum(
            max(0, p.signal.side * (p.entry - p.stop)) * dollars * p.quantity
            + (stop_slip + fees) * p.quantity
            for p in positions
        )
        remaining = c.daily_loss + self.day_realized - committed
        # Open stop risk is already committed capital, even before it is realized.
        balance = c.balance + self.realized - committed
        qty = min(
            c.max_contracts - sum(p.quantity for p in positions),
            floor(min(c.risk_per_trade, remaining, max(0, balance)) / risk),
        )
        if qty < 1:
            return deny("Insufficient per-trade/daily risk budget or contract capacity")
        return Approval(qty, risk, rr, "Approved by independent risk limits")

    def record(self, trade: Trade):
        self.roll_day(trade.exit_at)
        self.realized += trade.net
        self.day_realized += trade.net
        self.losses = self.losses + 1 if trade.net < 0 else 0
        if self.day_realized <= -self.c.daily_loss or self.losses >= self.c.max_consecutive_losses:
            self.locked = True

    def emergency(self):
        self.manual_lock = True

    def unlock(self, positions, metrics):
        if positions or not metrics.reliable:
            raise ValueError("Unlock requires no open positions and fresh reliable data")
        self.manual_lock = False
