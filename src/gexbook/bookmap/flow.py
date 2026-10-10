"""Order-flow metrics calculated only from events already observed."""

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from gexbook.config import Config
from gexbook.models import Event


@dataclass(frozen=True)
class Metrics:
    ts: datetime
    price: float | None
    bid: float | None
    ask: float | None
    bid_liquidity: float
    ask_liquidity: float
    imbalance: float
    buy_volume: float
    sell_volume: float
    delta: float
    recent_delta: float
    earlier_delta: float
    cvd: float
    additions: float
    removals: float
    sweep_candidate: bool
    reliable: bool
    reasons: tuple[str, ...]


class OrderFlow:
    def __init__(self, config: Config):
        self.config = config
        self.bids, self.asks = {}, {}
        self.trades, self.changes = deque(), deque()
        self.last_seq = None
        self.last_ts = self.last_trade_at = self.last_depth_at = None
        self.price = None
        self.connected = False
        self.started_at = None
        self.cvd, self.day = 0.0, None
        self.source = None

    def apply(self, e: Event):
        if e.symbol != self.config.market_symbol:
            raise ValueError("Mixed or unexpected symbols; separate books are required")
        if self.source and e.source != self.source:
            raise ValueError("Cannot mix recorded, simulated, and bridge events in one engine")
        if self.last_ts and e.ts < self.last_ts:
            self.connected = False
            raise ValueError("Out-of-order timestamp; book state invalidated")
        if e.kind != "reset" and self.last_seq is not None and e.seq != self.last_seq + 1:
            self.connected = False
            raise ValueError("Sequence gap or duplicate; reset/rebuild required")
        self.source = e.source
        self.last_seq, self.last_ts = e.seq, e.ts
        local_day = e.ts.astimezone(ZoneInfo("America/Chicago")).date()
        if local_day != self.day:
            self.cvd, self.day = 0.0, local_day
        if e.kind == "reset":
            self.bids.clear()
            self.asks.clear()
            self.trades.clear()
            self.changes.clear()
            self.price = self.last_trade_at = self.last_depth_at = None
            self.started_at = e.ts
            self.connected = True
            return
        if e.kind == "disconnect":
            self.connected = False
            return
        if not self.connected:
            return
        if e.kind == "depth":
            book = self.bids if e.side == "bid" else self.asks
            old = book.get(e.price, 0)
            if e.size == 0:
                book.pop(e.price, None)
            else:
                book[e.price] = e.size
            self.changes.append((e.ts, e.side, e.price, e.size - old))
            self.last_depth_at = e.ts
        elif e.kind == "trade":
            self.trades.append(e)
            self.price, self.last_trade_at = e.price, e.ts
            self.cvd += e.size * (1 if e.side == "buy" else -1)
        self.prune(e.ts)

    def prune(self, now):
        while (
            self.trades and (now - self.trades[0].ts).total_seconds() > self.config.window_seconds
        ):
            self.trades.popleft()
        while (
            self.changes and (now - self.changes[0][0]).total_seconds() > self.config.window_seconds
        ):
            self.changes.popleft()

    def metrics(self, now: datetime) -> Metrics:
        self.prune(now)
        c = self.config
        reasons = []
        if not self.connected:
            reasons.append("disconnected or waiting for reset")
        if (
            self.last_ts is None
            or not 0 <= (now - self.last_ts).total_seconds() <= c.max_age_seconds
        ):
            reasons.append("stale/future event stream")
        if (
            self.last_trade_at is None
            or not 0 <= (now - self.last_trade_at).total_seconds() <= c.max_age_seconds
        ):
            reasons.append("stale/missing trade price")
        if (
            self.last_depth_at is None
            or not 0 <= (now - self.last_depth_at).total_seconds() <= c.depth_max_age_seconds
        ):
            reasons.append("stale/missing depth")
        bid, ask = max(self.bids, default=None), min(self.asks, default=None)
        if bid is None or ask is None or bid >= ask:
            reasons.append("missing/crossed order book")
        if (
            self.started_at is None
            or (now - self.started_at).total_seconds() < c.min_window_seconds
        ):
            reasons.append("warmup incomplete")
        if len(self.trades) < c.min_trades:
            reasons.append("insufficient recent trades")
        # Top five levels; quantities retain source instrument units.
        b = sum(self.bids[p] for p in sorted(self.bids, reverse=True)[:5])
        a = sum(self.asks[p] for p in sorted(self.asks)[:5])
        buy = sum(t.size for t in self.trades if t.side == "buy")
        sell = sum(t.size for t in self.trades if t.side == "sell")
        recent = sum(
            t.size * (1 if t.side == "buy" else -1)
            for t in self.trades
            if (now - t.ts).total_seconds() <= c.window_seconds / 2
        )
        delta = buy - sell
        prices = [t.price for t in self.trades]
        sweep = len(set(prices)) >= 3 and bool(prices) and max(prices) - min(prices) >= 1
        return Metrics(
            now,
            self.price,
            bid,
            ask,
            b,
            a,
            (b - a) / (b + a) if b + a else 0,
            buy,
            sell,
            delta,
            recent,
            delta - recent,
            self.cvd,
            sum(max(0, x[3]) for x in self.changes),
            sum(max(0, -x[3]) for x in self.changes),
            sweep,
            not reasons,
            tuple(reasons),
        )

    def absorption(self, level: float, side: int) -> bool:
        """Approximation: opposing aggressive volume trades in a narrow range near level."""
        adverse = [
            t
            for t in self.trades
            if t.side == ("sell" if side == 1 else "buy")
            and abs(t.price - level) <= self.config.level_distance
        ]
        return (
            bool(adverse)
            and sum(t.size for t in adverse) >= self.config.absorption_volume
            and (
                max(t.price for t in adverse) - min(t.price for t in adverse)
                <= self.config.absorption_range
            )
        )

    def liquidity_near(self, level: float, side: int) -> float:
        book = self.bids if side == 1 else self.asks
        return sum(size for p, size in book.items() if abs(p - level) <= self.config.level_distance)
