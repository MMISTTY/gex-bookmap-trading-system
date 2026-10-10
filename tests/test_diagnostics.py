import json
from datetime import timedelta

from gexbook.bookmap.diagnostics import inspect_capture
from gexbook.bookmap.simulation import demo
from gexbook.config import Config
from gexbook.models import jsonable


def capture(tmp_path, events):
    path = tmp_path / "capture.jsonl"
    path.write_text("\n".join(json.dumps(jsonable(e)) for e in events), encoding="utf-8")
    return str(path)


def test_historical_quality_is_not_live_authentication(tmp_path):
    events, _ = demo()
    report = inspect_capture(capture(tmp_path, events), Config(), events[-1].ts + timedelta(days=1))
    assert report["capture_valid"]
    assert report["event_count"] == len(events)
    assert report["source"] == "simulation"
    assert not report["fresh_and_reliable_now"]
    assert report["provider_authorization"] == "NOT_VERIFIED"
    assert report["orders_enabled"] is False
    assert "stale/future event stream" in report["current_reasons"]


def test_missing_reset_and_sequence_gap_fail(tmp_path):
    events, _ = demo()
    report = inspect_capture(capture(tmp_path, events[1:]), Config())
    assert not report["capture_valid"]
    assert "begin with reset" in report["errors"][0]
    report = inspect_capture(capture(tmp_path, events[:3] + events[4:]), Config())
    assert not report["capture_valid"]
    assert "Sequence gap" in report["errors"][0]


def test_missing_file_and_partial_json_are_reported(tmp_path):
    report = inspect_capture(str(tmp_path / "absent.jsonl"), Config())
    assert not report["capture_valid"] and report["errors"]
    path = tmp_path / "partial.jsonl"
    path.write_text('{"seq":', encoding="utf-8")
    report = inspect_capture(str(path), Config())
    assert not report["capture_valid"] and report["errors"]


def test_disconnect_cannot_be_reported_as_ready(tmp_path):
    from dataclasses import replace

    events, _ = demo()
    last = events[-1]
    events.append(replace(last, seq=last.seq + 1, kind="disconnect", side="", size=0))
    report = inspect_capture(capture(tmp_path, events), Config(), last.ts)
    assert report["capture_valid"]
    assert not report["reliable_at_capture_end"]
    assert not report["fresh_and_reliable_now"]


def test_cli_inspection_needs_no_snapshot_and_writes_nothing(tmp_path, monkeypatch, capsys):
    import sys
    import pytest
    from gexbook.cli import main

    events, _ = demo()
    path = capture(tmp_path, events)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["gexbook", "inspect-capture", "--events", path])
    with pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == 0
    assert json.loads(capsys.readouterr().out)["capture_valid"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["capture.jsonl"]


def test_cli_invalid_capture_returns_nonzero(tmp_path, monkeypatch, capsys):
    import sys
    import pytest
    from gexbook.cli import main

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["gexbook", "inspect-capture", "--events", "absent.jsonl"])
    with pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == 2
    assert not json.loads(capsys.readouterr().out)["capture_valid"]
