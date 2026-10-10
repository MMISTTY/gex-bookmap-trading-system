"""Read-only capture checks. Passing is not provider approval or live certification."""

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from gexbook.bookmap.adapters import read_events
from gexbook.bookmap.flow import OrderFlow
from gexbook.config import Config
from gexbook.models import jsonable, timestamp


def inspect_capture(path: str, config: Config, now: datetime | None = None) -> dict:
    """Inspect complete rows in a stable capture copy without constructing a broker.

    Schema/continuity failure stops at the first error. A final partial JSONL row
    is rejected deliberately: copy a closed capture or retry after the writer flushes.
    Historical quality is evaluated at the last event, freshness at wall clock.
    """
    report = {
        "schema_version": 1,
        "mode": "READ_ONLY_DIAGNOSTIC",
        "orders_enabled": False,
        "provider_authorization": "NOT_VERIFIED",
        "capture_valid": False,
        "event_count": 0,
        "errors": [],
        "limitations": [
            "Source labels are supplied by the file and do not authenticate a live feed.",
            "Full initial depth, price units and aggressor direction require provider comparison.",
            "No GEX snapshot, strategy performance or provider entitlement is certified.",
        ],
    }
    flow = OrderFlow(config)
    counts = Counter()
    try:
        p = Path(path)
        events = read_events(
            p.read_text(encoding="utf-8-sig"), "csv" if p.suffix.lower() == ".csv" else "jsonl"
        )
        if events[0].kind != "reset":
            raise ValueError("Capture must begin with reset; initial book is unknown")
        for event in events:
            flow.apply(event)
            counts[event.kind] += 1
            report["event_count"] += 1
        at_end = flow.metrics(events[-1].ts)
        current = flow.metrics(timestamp(now or datetime.now(timezone.utc)))
        report.update(
            capture_valid=True,
            source=flow.source,
            symbol=events[0].symbol,
            first_event_at=events[0].ts,
            last_event_at=events[-1].ts,
            metrics_at_capture_end=at_end,
            reliable_at_capture_end=at_end.reliable,
            fresh_and_reliable_now=current.reliable,
            current_reasons=current.reasons,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        report["errors"].append(str(exc))
    report["event_counts"] = dict(counts)
    return jsonable(report)
