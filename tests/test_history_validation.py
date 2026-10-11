from dataclasses import replace

import pytest

from gexbook.backtesting.replay import out_of_sample, replay
from gexbook.bookmap.simulation import demo
from gexbook.config import Config


def test_split_rejects_original_order_that_partitioning_would_hide():
    events, snapshots = demo()
    split = events[30].ts
    train = [e for e in events if e.ts < split]
    test = [e for e in events if e.ts >= split]
    corrupted = train[:1] + test + train[1:]
    with pytest.raises(ValueError, match="Out-of-order timestamp"):
        out_of_sample(corrupted, snapshots, Config(), split)


@pytest.mark.parametrize("mode", ["duplicate_id", "same_availability"])
def test_rejects_ambiguous_snapshot_selection(mode):
    events, snapshots = demo()
    original = snapshots[0]
    other = original if mode == "duplicate_id" else replace(original, id="other")
    with pytest.raises(ValueError, match="ambiguous"):
        replay(events, [original, other], Config())


def test_replay_requires_initial_book_reset():
    events, snapshots = demo()
    with pytest.raises(ValueError, match="begin with a reset"):
        replay(events[1:], snapshots, Config())


def test_coverage_explains_missing_gex_without_inventing_trades():
    events, _ = demo()
    engine = replay(events, [], Config())
    report = engine.coverage_report()
    assert report["trade_events"] == sum(e.kind == "trade" for e in events)
    assert report["with_gex_snapshot"] == report["with_both"] == 0
    assert report["without_gex_snapshot"] == report["trade_events"]
    assert not engine.result.trades


def test_coverage_counts_unreliable_flow_and_excludes_oos_warmup():
    events, snapshots = demo()
    engine = replay(events, snapshots, Config(max_age_seconds=0.000001))
    report = engine.coverage_report()
    assert report["unreliable_order_flow_reasons"]
    assert report["with_both"] <= report["with_reliable_order_flow"] <= report["trade_events"]
    split = events[30].ts
    _, test = out_of_sample(events, snapshots, Config(), split)
    assert test.coverage_report()["trade_events"] == sum(
        e.kind == "trade" and e.ts >= split for e in events
    )
