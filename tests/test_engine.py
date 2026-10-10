from dataclasses import replace
from datetime import timedelta
import pytest
from gexbook.models import Event, Signal, Position
from gexbook.config import Config
from gexbook.bookmap.simulation import demo
from gexbook.bookmap.flow import OrderFlow
from gexbook.bookmap.adapters import read_events, FileTail
from gexbook.backtesting.replay import replay, out_of_sample
from gexbook.analytics.performance import summary
from gexbook.risk.manager import RiskManager
from gexbook.execution.paper import PaperBroker


def reliable():
    events, snapshots = demo()
    f = OrderFlow(Config())
    for e in events[:39]:
        f.apply(e)
    m = f.metrics(events[38].ts)
    assert m.reliable
    return f, m, snapshots


def signal(m, side=1):
    return Signal(
        m.ts,
        side,
        "l",
        "Support",
        "rejection",
        m.price,
        m.price - side * 10,
        m.price + side * 25,
        1,
        {},
        "test",
        "s",
    )


def test_demo_replay_explains_trade_and_costs():
    e, s = demo()
    engine = replay(e, s, Config())
    result = engine.result
    assert len(result.trades) == 1
    t = result.trades[0]
    assert t.exit_at > t.entry_at and t.net == t.gross - t.fees
    assert t.fees > 0 and "recent_delta" in t.explanation
    assert t.quantity <= Config().max_contracts
    assert "SIMULATION" in result.label
    assert summary(result)["maximum_drawdown"] < 20


def test_future_snapshot_is_never_used():
    e, s = demo()
    future = replace(s[0], available_at=e[-1].ts + timedelta(seconds=1))
    assert not replay(e, [future], Config()).result.trades


def test_expired_snapshot_blocks_entry():
    e, s = demo()
    expired = replace(s[0], valid_until=e[0].ts)
    assert not replay(e, [expired], Config()).result.trades


def test_sequence_gap_and_time_regression_fail_closed():
    f, m, _ = reliable()
    with pytest.raises(ValueError, match="Sequence"):
        f.apply(Event(f.last_seq + 2, m.ts, "heartbeat", "MNQ", "simulation"))
    assert not f.metrics(m.ts).reliable
    f, m, _ = reliable()
    with pytest.raises(ValueError, match="timestamp"):
        f.apply(
            Event(f.last_seq + 1, m.ts - timedelta(seconds=1), "heartbeat", "MNQ", "simulation")
        )


def test_stale_heartbeat_does_not_refresh_trade_price():
    f, m, _ = reliable()
    later = m.ts + timedelta(seconds=10)
    f.apply(Event(f.last_seq + 1, later, "heartbeat", "MNQ", "simulation"))
    assert not f.metrics(later).reliable
    assert "stale/missing trade price" in f.metrics(later).reasons


def test_nq_cannot_be_used_for_mnq_execution():
    _, m, _ = reliable()
    risk = RiskManager(replace(Config(), market_symbol="NQ"))
    assert not risk.assess(signal(m), m.ask, m, [], m.ts).approved


def test_risk_budget_position_limit_and_net_rr():
    _, m, _ = reliable()
    c = replace(Config(), risk_per_trade=25)
    risk = RiskManager(c)
    a = risk.assess(signal(m), m.ask + 0.25, m, [], m.ts)
    assert a.quantity == 1 and a.quantity * a.risk_per_contract <= 25
    p = Position(signal(m), m.ts, m.ask, 1, m.price - 10, m.price + 25, 0.65)
    assert not risk.assess(signal(m), m.ask, m, [p], m.ts).approved
    assert not risk.assess(replace(signal(m), target=m.price + 1), m.ask, m, [], m.ts).approved


def test_emergency_disconnected_waits_for_real_quote():
    _, m, _ = reliable()
    c = Config()
    risk = RiskManager(c)
    b = PaperBroker(c, risk)
    b.propose(signal(m))
    b.enter_pending(m.ts, m, "s")
    assert b.positions
    b.emergency_flatten()
    b.on_market(m.ts, replace(m, reliable=False))
    assert b.positions and not b.trades
    b.on_market(m.ts, m)
    assert not b.positions and b.trades[0].reason == "emergency"
    assert risk.manual_lock


def test_stop_gap_fills_at_adverse_quote_and_fees():
    _, m, _ = reliable()
    c = Config()
    r = RiskManager(c)
    b = PaperBroker(c, r)
    b.propose(signal(m))
    b.enter_pending(m.ts, m, "s")
    stop = b.positions[0].stop
    gap = replace(m, bid=stop - 5, ask=stop - 4.5, price=stop - 4.75)
    t = b.on_market(m.ts, gap)[0]
    assert t.exit == stop - 5.25 and t.net < t.gross


def test_daily_loss_latch_and_day_reset():
    _, m, _ = reliable()
    c = replace(Config(), daily_loss=10)
    r = RiskManager(c)
    b = PaperBroker(c, r)
    b.propose(signal(m))
    a = b.enter_pending(m.ts, m, "s")
    assert a and not a.approved  # costed stop cannot fit remaining daily budget
    r.day_realized = -10
    assert not r.assess(signal(m), m.ask, m, [], m.ts).approved
    r.roll_day(m.ts + timedelta(days=1))
    assert r.day_realized == 0


@pytest.mark.parametrize(
    "change",
    [
        {"mode": "live"},
        {"tick_value": 5},
        {"max_contracts": 1.5},
        {"max_age_seconds": 0},
        {"balance": float("nan")},
    ],
)
def test_bad_config_rejected(change):
    with pytest.raises(ValueError):
        replace(Config(), **change)


def test_event_validation_and_file_tail(tmp_path):
    with pytest.raises(ValueError):
        read_events('{"seq":0,"ts":"2026-01-05T10:00:00","kind":"trade"}')
    p = tmp_path / "events.jsonl"
    text = '{"seq":0,"ts":"2026-01-05T15:00:00+00:00","kind":"reset","symbol":"MNQ","source":"recorded"}'
    p.write_text(text)
    tail = FileTail(str(p))
    assert not list(tail.poll())
    with p.open("a") as f:
        f.write("\n")
    assert len(list(tail.poll())) == 1


def test_oos_uses_only_test_period_for_trades():
    e, s = demo()
    train, test = out_of_sample(e, s, Config(), e[30].ts)
    assert all(t.entry_at >= e[30].ts for t in test.result.trades)
    assert not train.result.trades


def test_short_rejection_is_symmetric():
    events, snapshots = demo()
    mirrored = [
        replace(
            e,
            price=40000 - e.price if e.price else 0,
            side={"bid": "ask", "ask": "bid", "buy": "sell", "sell": "buy"}.get(e.side, e.side),
        )
        for e in events
    ]
    snapshot = replace(
        snapshots[0], levels=(replace(snapshots[0].levels[0], role="resistance", kind="Call Wall"),)
    )
    result = replay(mirrored, [snapshot], Config()).result
    assert len(result.trades) == 1 and result.trades[0].side == -1
    assert result.trades[0].net > 0


def test_breakout_requires_failed_liquidity_and_sustained_acceptance():
    from gexbook.backtesting.replay import Engine

    events, snapshots = demo()
    # Initial ask defense disappears as buyers establish acceptance above the wall.
    transformed = [
        replace(e, size=80 if e.ts <= events[23].ts else 5)
        if e.kind == "depth" and e.side == "ask" and e.size > 0
        else e
        for e in events
    ]
    snapshot = replace(snapshots[0], levels=(replace(snapshots[0].levels[0], role="resistance"),))
    engine = Engine(Config(), [snapshot])
    for e in transformed:
        engine.step(e)
    accepted = [d for d in engine.result.decisions if d.get("accepted")]
    assert accepted and all(d["confirmation"] == "breakout" for d in accepted)
    assert not engine.result.trades
    assert any(
        "Net reward-to-risk below minimum" in d.get("risk", "") for d in engine.result.decisions
    )
    assert "acceptance_seconds=3.0" in accepted[0]["reason"]
    # Disconnect/reset invalidates pre-disconnection defense and acceptance state.
    engine.step(
        Event(transformed[-1].seq + 1, transformed[-1].ts, "disconnect", "MNQ", "simulation")
    )
    assert not engine.strategy.baseline and not engine.strategy.accepted_since


def test_risk_revalidates_quote_timestamp_and_book_geometry():
    _, m, _ = reliable()
    r = RiskManager(Config())
    fresh_signal = replace(signal(m), ts=m.ts + timedelta(seconds=10))
    denied = r.assess(fresh_signal, m.ask, m, [], fresh_signal.ts)
    assert not denied.approved and "quote timestamp" in denied.reason
    for change in [{"bid": m.ask}, {"ask": None}, {"bid": float("nan")}, {"ask": -1}]:
        denied = r.assess(signal(m), m.ask, replace(m, **change), [], m.ts)
        assert not denied.approved and "executable quotes" in denied.reason


@pytest.mark.parametrize("seq", [True, 1.5, "1.5"])
def test_event_adapter_does_not_coerce_invalid_sequence(seq):
    import json

    e = {
        "seq": seq,
        "ts": "2026-01-05T15:00:00Z",
        "kind": "reset",
        "symbol": "MNQ",
        "source": "recorded",
    }
    with pytest.raises(ValueError, match="seq"):
        read_events(json.dumps(e))


def test_personal_settings_are_separate_from_tracked_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    defaults = Config()
    defaults.save("config/default.json")
    personal = replace(defaults, balance=4321)
    personal.save("runtime/paper-config.json")
    assert Config.active() == personal
    assert Config.load("config/default.json") == defaults


def test_breakout_confirmation_resets_when_directional_flow_fails():
    from gexbook.strategy.engine import Strategy

    f, m, snapshots = reliable()
    level = replace(snapshots[0].levels[0], role="resistance")
    snapshot = replace(snapshots[0], levels=(level,))
    strategy = Strategy(Config())
    strategy.active_snapshot = snapshot.id
    strategy.baseline[(level.id, -1)] = (80, m.ts)
    f.liquidity_near = lambda price, side: 80 if side == 1 else 5
    f.absorption = lambda price, side: False
    for seconds, delta, expected in [
        (0, 50, False),
        (2, -50, False),
        (3, 50, False),
        (6, 50, True),
    ]:
        now = m.ts + timedelta(seconds=seconds)
        f.metrics = lambda _, now=now, delta=delta: replace(
            m, ts=now, price=20001, recent_delta=delta, imbalance=0.8
        )
        proposed = strategy.evaluate(f, snapshot, now)
        assert bool(proposed) == expected
    assert proposed.confirmation == "breakout"


def test_old_liquidity_defense_cannot_confirm_new_breakout():
    from gexbook.strategy.engine import Strategy

    f, m, snapshots = reliable()
    level = replace(snapshots[0].levels[0], role="resistance")
    snapshot = replace(snapshots[0], levels=(level,))
    strategy = Strategy(Config())
    strategy.active_snapshot = snapshot.id
    strategy.baseline[(level.id, -1)] = (80, m.ts - timedelta(seconds=11))
    f.liquidity_near = lambda price, side: 80 if side == 1 else 5
    f.metrics = lambda _: replace(m, price=20001, recent_delta=50, imbalance=0.8)
    assert strategy.evaluate(f, snapshot, m.ts) is None
    assert strategy.baseline[(level.id, -1)][0] == 5
