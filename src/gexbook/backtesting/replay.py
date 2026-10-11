"""Replay and paper mode share the exact event-by-event decision pipeline."""

from collections import Counter
from hashlib import sha256
import json

from gexbook.models import Result, Snapshot, Event, jsonable, timestamp
from gexbook.config import Config
from gexbook.bookmap.flow import OrderFlow
from gexbook.strategy.engine import Strategy
from gexbook.risk.manager import RiskManager
from gexbook.execution.paper import PaperBroker


def validate_history(events: list[Event], snapshots: list[Snapshot]) -> None:
    """Validate original ordering before a split can conceal corrupt chronology."""
    if not events:
        raise ValueError("No events to replay")
    if events[0].kind != "reset":
        raise ValueError("Replay history must begin with a reset and book rebuild")
    if any(current.ts < previous.ts for previous, current in zip(events, events[1:])):
        raise ValueError("Out-of-order timestamp in original replay history")
    if len({s.id for s in snapshots}) != len(snapshots):
        raise ValueError("Duplicate snapshot IDs make provenance ambiguous")
    if len({s.available_at for s in snapshots}) != len(snapshots):
        raise ValueError("Snapshots with identical availability timestamps are ambiguous")


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
        self.coverage = {
            "trade_events": 0,
            "with_gex_snapshot": 0,
            "with_reliable_order_flow": 0,
            "with_both": 0,
        }
        self.unreliable_reasons = Counter()
        self.event_digest = sha256()
        self.event_count = 0
        self.first_event_at = None
        self.warmup_count = 0
        self.warmup_digest = sha256()
        self.split_at = None

    @staticmethod
    def event_bytes(event):
        return (json.dumps(jsonable(event), sort_keys=True, separators=(",", ":")) + "\n").encode()

    def warmup(self, event):
        self.flow.apply(event)
        self.warmup_digest.update(self.event_bytes(event))
        self.warmup_count += 1

    def coverage_report(self):
        """Event counts, not elapsed-time coverage or strategy success probabilities."""
        return {
            **self.coverage,
            "without_gex_snapshot": self.coverage["trade_events"]
            - self.coverage["with_gex_snapshot"],
            "unreliable_order_flow_reasons": dict(self.unreliable_reasons),
            "basis": "Trade events processed in this segment; warmup prefix excluded",
            "limitation": "Coverage does not establish feed completeness, entitlements or a trading edge",
        }

    def snapshot_at(self, ts):
        eligible = [s for s in self.snapshots if s.available_at <= ts < s.valid_until]
        return max(eligible, key=lambda s: s.available_at) if eligible else None

    def step(self, event: Event):
        self.flow.apply(event)
        self.event_digest.update(self.event_bytes(event))
        self.event_count += 1
        if self.first_event_at is None:
            self.first_event_at = event.ts
        self.last_event = event
        m = self.flow.metrics(event.ts)
        self.risk.roll_day(event.ts)
        snapshot = self.snapshot_at(event.ts)
        if event.kind in ("reset", "disconnect"):
            self.broker.pending = None
            self.strategy = Strategy(self.c)
        if event.kind == "trade":
            has_gex = snapshot is not None and bool(snapshot.levels)
            self.coverage["trade_events"] += 1
            self.coverage["with_gex_snapshot"] += int(has_gex)
            self.coverage["with_reliable_order_flow"] += int(m.reliable)
            self.coverage["with_both"] += int(has_gex and m.reliable)
            if not m.reliable:
                self.unreliable_reasons.update(set(m.reasons))
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
    validate_history(events, snapshots)
    engine = Engine(config, snapshots)
    for e in events:  # Preserve input order: sorting would conceal corrupted streams.
        engine.step(e)
    return finish_replay(engine)


def finish_replay(engine: Engine) -> Engine:
    """Use the same terminal-fill and unliquidated-position rules for every segment."""
    now = engine.last_event.ts
    m = engine.flow.metrics(now)
    engine.broker.pending = None
    if m.reliable:
        for p in list(engine.broker.positions):
            engine.broker.close(
                p, now, engine.broker.executable(m, -p.signal.side), "end_of_dataset"
            )
        engine.result.equity.append(
            {
                "ts": now,
                "equity": engine.c.balance + engine.risk.realized,
                "realized": engine.risk.realized,
                "open_positions": 0,
            }
        )
    if engine.broker.positions:
        engine.result.decisions.append(
            {
                "ts": now,
                "reason": "Dataset ended without fresh BBO; positions unliquidated",
            }
        )
    engine.result.trades = engine.broker.trades
    return engine


def out_of_sample(events, snapshots, config, split_at):
    """Fixed config, chronological split; no automatic optimization or model-selection claims."""
    validate_history(events, snapshots)
    split_at = timestamp(split_at)
    train = [e for e in events if e.ts < split_at]
    test = [e for e in events if e.ts >= split_at]
    if not train or not test:
        raise ValueError("Split needs nonempty chronological training and test segments")
    # Test gets book rebuild/reset and warmup from prefix, but no prefix trades/P&L.
    test_engine = Engine(config, snapshots)
    test_engine.split_at = split_at
    for e in train:
        test_engine.warmup(e)
    for e in test:
        test_engine.step(e)
    return replay(train, snapshots, config), finish_replay(test_engine)
