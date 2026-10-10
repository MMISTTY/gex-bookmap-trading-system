"""Replay and paper mode share the exact event-by-event decision pipeline."""

from gexbook.models import Result, Snapshot, Event
from gexbook.config import Config
from gexbook.bookmap.flow import OrderFlow
from gexbook.strategy.engine import Strategy
from gexbook.risk.manager import RiskManager
from gexbook.execution.paper import PaperBroker


class Engine:
    def __init__(self, config: Config, snapshots: list[Snapshot], store=None):
        self.c = config
        self.snapshots = sorted(snapshots, key=lambda s: s.available_at)
        self.flow = OrderFlow(config)
        self.strategy = Strategy(config)
        self.risk = RiskManager(config)
        self.broker = PaperBroker(config, self.risk)
        self.store = store
        self.result = Result()
        self.last_event = None

    def snapshot_at(self, ts):
        eligible = [s for s in self.snapshots if s.available_at <= ts < s.valid_until]
        return max(eligible, key=lambda s: s.available_at) if eligible else None

    def step(self, event: Event):
        self.flow.apply(event)
        self.last_event = event
        m = self.flow.metrics(event.ts)
        self.risk.roll_day(event.ts)
        snapshot = self.snapshot_at(event.ts)
        if event.kind in ("reset", "disconnect"):
            self.broker.pending = None
            self.strategy = Strategy(self.c)
        if event.kind == "trade":
            self.broker.on_market(event.ts, m)
            approval = self.broker.enter_pending(event.ts, m, snapshot.id if snapshot else None)
            if approval or self.broker.last_rejection:
                self.result.decisions.append(
                    {"ts": event.ts, "risk": self.broker.last_rejection or approval.reason}
                )
                self.broker.last_rejection = ""
            signal = self.strategy.evaluate(self.flow, snapshot, event.ts)
            self.result.decisions.extend(self.strategy.decisions)
            if signal:
                self.broker.propose(signal)
        else:
            self.broker.on_market(event.ts, m)
        self.result.trades = self.broker.trades
        self.result.equity.append(
            {
                "ts": event.ts,
                "equity": self.broker.equity(m),
                "realized": self.risk.realized,
                "open_positions": len(self.broker.positions),
            }
        )
        self.result.label = (
            "SIMULATION — NOT HISTORICAL PERFORMANCE"
            if event.source == "simulation"
            else "RECORDED/BRIDGE PAPER REPLAY — UNVALIDATED STRATEGY"
        )
        if self.store:
            self.store.audit(
                event.ts, "decision", self.result.decisions[-1:] or {"event": event.kind}
            )
        return m


def replay(events: list[Event], snapshots: list[Snapshot], config: Config) -> Engine:
    if not events:
        raise ValueError("No events to replay")
    engine = Engine(config, snapshots)
    for e in events:  # Preserve input order: sorting would conceal corrupted streams.
        engine.step(e)
    # Final valuation uses last known BBO, explicitly marked liquidation at end of dataset.
    m = engine.flow.metrics(events[-1].ts)
    if m.reliable:
        for p in list(engine.broker.positions):
            engine.broker.close(
                p, events[-1].ts, engine.broker.executable(m, -p.signal.side), "end_of_dataset"
            )
        engine.result.equity.append(
            {
                "ts": events[-1].ts,
                "equity": config.balance + engine.risk.realized,
                "realized": engine.risk.realized,
                "open_positions": 0,
            }
        )
    if engine.broker.positions:
        engine.result.decisions.append(
            {
                "ts": events[-1].ts,
                "reason": "Dataset ended without fresh BBO; positions unliquidated",
            }
        )
    return engine


def out_of_sample(events, snapshots, config, split_at):
    """Fixed config, chronological split; no automatic optimization or model-selection claims."""
    train = [e for e in events if e.ts < split_at]
    test = [e for e in events if e.ts >= split_at]
    if not train or not test:
        raise ValueError("Split needs nonempty chronological training and test segments")
    # Test gets book rebuild/reset and warmup from prefix, but no prefix trades/P&L.
    test_engine = Engine(config, snapshots)
    for e in train:
        test_engine.flow.apply(e)
    for e in test:
        test_engine.step(e)
    m = test_engine.flow.metrics(test[-1].ts)
    if m.reliable:
        for p in list(test_engine.broker.positions):
            test_engine.broker.close(
                p, test[-1].ts, test_engine.broker.executable(m, -p.signal.side), "end_of_dataset"
            )
        test_engine.result.equity.append(
            {
                "ts": test[-1].ts,
                "equity": config.balance + test_engine.risk.realized,
                "realized": test_engine.risk.realized,
                "open_positions": 0,
            }
        )
    test_engine.result.trades = test_engine.broker.trades
    return replay(train, snapshots, config), test_engine
