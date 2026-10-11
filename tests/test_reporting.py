from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile

from gexbook.analytics.reporting import report_bundle, report_files
from gexbook.backtesting.replay import replay, out_of_sample, Engine
from gexbook.bookmap.simulation import demo
from gexbook.config import Config
from gexbook.models import Event


def test_research_bundle_is_complete_and_input_hashes_are_reproducible():
    events, snapshots = demo()
    engine = replay(events, snapshots, Config())
    with ZipFile(BytesIO(report_bundle(engine))) as archive:
        assert set(archive.namelist()) == {
            "manifest.json",
            "configuration.json",
            "snapshots.json",
            "report.json",
            "trades.json",
            "equity.json",
            "decisions.json",
        }
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["event_count"] == len(events)
        assert (
            manifest["configuration_sha256"]
            == sha256(archive.read("configuration.json")).hexdigest()
        )
        assert manifest["snapshots_sha256"] == sha256(archive.read("snapshots.json")).hexdigest()
        assert (
            manifest["normalized_events_sha256"]
            == sha256(b"".join(Engine.event_bytes(e) for e in events)).hexdigest()
        )
        assert manifest["source"] == "simulation"
        assert "SIMULATION" in manifest["label"]
    repeated = replay(events, snapshots, Config())
    assert report_files(engine) == report_files(repeated)
    changed = replay(events, snapshots, replace(Config(), commission_per_side=0.7))
    assert report_files(engine)["configuration.json"] != report_files(changed)["configuration.json"]


def test_oos_report_identifies_warmup_and_test_inputs_separately():
    events, snapshots = demo()
    split = events[30].ts
    _, engine = out_of_sample(events, snapshots, Config(), split)
    manifest = json.loads(report_files(engine)["manifest.json"])
    assert manifest["warmup_event_count"] == sum(e.ts < split for e in events)
    assert manifest["event_count"] == sum(e.ts >= split for e in events)
    assert manifest["split_at"] == split.isoformat()
    assert (
        manifest["normalized_warmup_sha256"]
        == sha256(b"".join(Engine.event_bytes(e) for e in events if e.ts < split)).hexdigest()
    )


def test_oos_stale_end_reports_open_positions_without_fabricating_exit():
    events, snapshots = demo()
    probe = Engine(Config(), snapshots)
    for i, event in enumerate(events):
        probe.step(event)
        if probe.broker.positions:
            break
    else:
        raise AssertionError("Fixture must produce an open position")
    history = events[: i + 1]
    history.append(
        Event(event.seq + 1, event.ts + timedelta(seconds=30), "heartbeat", "MNQ", "simulation")
    )
    _, engine = out_of_sample(history, snapshots, Config(), events[30].ts)
    assert engine.broker.positions
    assert not engine.result.trades
    assert engine.result.equity[-1]["open_positions"] == len(engine.broker.positions)
    assert any("unliquidated" in d.get("reason", "") for d in engine.result.decisions)
    assert engine.broker.pending is None
