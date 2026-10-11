"""Run a demo, replay normalized history, or poll a Bookmap capture file in paper mode."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from gexbook.config import Config
from gexbook.models import Snapshot, jsonable
from gexbook.bookmap.adapters import FileTail, read_events
from gexbook.bookmap.simulation import demo
from gexbook.backtesting.replay import Engine, replay, out_of_sample
from gexbook.analytics.performance import summary, grouped
from gexbook.storage.sqlite import Store


def export(engine, directory):
    p = Path(directory)
    p.mkdir(parents=True, exist_ok=True)
    result = engine.result
    report = {
        "summary": summary(result),
        "data_coverage": engine.coverage_report(),
        "by_level": grouped(result, "level_kind"),
        "by_confirmation": grouped(result, "confirmation"),
        "by_side": grouped(result, "side"),
    }
    for name, payload in [
        ("report", report),
        ("trades", result.trades),
        ("equity", result.equity),
        ("decisions", result.decisions),
    ]:
        (p / f"{name}.json").write_text(json.dumps(jsonable(payload), indent=2))
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description="GEX + Bookmap paper research; no live orders")
    parser.add_argument("command", choices=["demo", "replay", "tail", "inspect-capture"])
    parser.add_argument("--events")
    parser.add_argument("--snapshots")
    parser.add_argument(
        "--config",
        help="Explicit settings file; otherwise use ignored personal settings or tracked defaults",
    )
    parser.add_argument("--output", default="runtime/latest")
    parser.add_argument(
        "--split-at", help="ISO timezone-aware chronological out-of-sample boundary"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = Config.load(args.config) if args.config else Config.active()
    if args.command == "inspect-capture":
        from gexbook.bookmap.diagnostics import inspect_capture

        if not args.events:
            parser.error("--events is required for inspect-capture")
        report = inspect_capture(args.events, config)
        print(json.dumps(report, indent=2))
        # Structural validation only; freshness and entitlement remain separate fields.
        raise SystemExit(0 if report["capture_valid"] else 2)
    if args.command == "demo":
        events, snapshots = demo()
    else:
        if not args.events or not args.snapshots:
            parser.error("--events and --snapshots are required")
        snapshots = [Snapshot.from_dict(d) for d in json.loads(Path(args.snapshots).read_text())]
        if args.command == "replay":
            events = read_events(
                Path(args.events).read_text(), "csv" if args.events.endswith(".csv") else "jsonl"
            )
    if args.command == "tail":
        store = Store()
        engine, feed = Engine(config, snapshots, store), FileTail(args.events)
        control_id = None
        print(
            "PAPER ONLY: polling local capture. Connection remains unverified until valid events arrive."
        )
        try:
            while True:
                control_path = Path(args.output) / "control.json"
                if control_path.exists():
                    control = json.loads(control_path.read_text())
                    if control.get("id") != control_id:
                        if control.get("command") != "emergency":
                            raise ValueError("Unknown paper control command")
                        engine.broker.emergency_flatten()
                        control_id = control["id"]
                        store.audit(datetime.now(timezone.utc), "emergency_applied", control)
                for event in feed.poll():
                    engine.step(event)
                now = datetime.now(timezone.utc)
                metrics = engine.flow.metrics(now)
                if not metrics.reliable:
                    engine.broker.pending = None
                export_state = {
                    "as_of": now,
                    "source": engine.flow.source,
                    "metrics": metrics,
                    "risk": vars(engine.risk) | {"c": asdict(config)},
                    "positions": engine.broker.positions,
                    "trades": engine.broker.trades,
                    "decisions": engine.result.decisions[-40:],
                }
                p = Path(args.output)
                p.mkdir(parents=True, exist_ok=True)
                tmp = p / "state.tmp"
                tmp.write_text(json.dumps(jsonable(export_state), default=str))
                tmp.replace(p / "state.json")
                time.sleep(0.5)
        except KeyboardInterrupt:
            logging.info("Stopped. No real orders were placed.")
        finally:
            store.close()
    elif args.split_at:
        from gexbook.models import timestamp

        train, test = out_of_sample(events, snapshots, config, timestamp(args.split_at))
        export(train, str(Path(args.output) / "train"))
        export(test, str(Path(args.output) / "test"))
    else:
        export(replay(events, snapshots, config), args.output)


if __name__ == "__main__":
    main()
