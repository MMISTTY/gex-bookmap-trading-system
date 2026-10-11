"""Portable research reports; raw feed and options files are never bundled."""

from dataclasses import asdict
from hashlib import sha256
from importlib.metadata import version
from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile

from gexbook.analytics.performance import grouped, summary
from gexbook.models import jsonable


def encoded(value):
    return json.dumps(jsonable(value), indent=2, sort_keys=True, allow_nan=False).encode("utf-8")


def report_files(engine):
    snapshots = encoded(engine.snapshots)
    configuration = encoded(asdict(engine.c))
    manifest = {
        "schema_version": 1,
        "package_version": version("gex-bookmap-trading-system"),
        "mode": "paper",
        "source": engine.flow.source,
        "label": engine.result.label,
        "event_count": engine.event_count,
        "first_event_at": engine.first_event_at,
        "last_event_at": engine.last_event.ts if engine.last_event else None,
        "normalized_events_sha256": engine.event_digest.hexdigest(),
        "warmup_event_count": engine.warmup_count,
        "normalized_warmup_sha256": engine.warmup_digest.hexdigest(),
        "split_at": engine.split_at,
        "configuration_sha256": sha256(configuration).hexdigest(),
        "snapshots_sha256": sha256(snapshots).hexdigest(),
        "hash_definition": "Events: sorted-key compact UTF-8 JSON plus newline per event; config and snapshots: exact exported bytes",
        "limitations": [
            "Hashes identify normalized inputs; they do not verify vendor authenticity or entitlement.",
            "Retain original private inputs separately to reproduce a run.",
            "Contains supplied levels and paper settings; review before sharing.",
        ],
    }
    report = {
        "summary": summary(engine.result),
        "data_coverage": engine.coverage_report(),
        "by_level": grouped(engine.result, "level_kind"),
        "by_confirmation": grouped(engine.result, "confirmation"),
        "by_side": grouped(engine.result, "side"),
    }
    files = {"configuration.json": configuration, "snapshots.json": snapshots}
    for name, value in {
        "manifest": manifest,
        "report": report,
        "trades": engine.result.trades,
        "equity": engine.result.equity,
        "decisions": engine.result.decisions,
    }.items():
        files[name + ".json"] = encoded(value)
    return files


def report_bundle(engine):
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, content in report_files(engine).items():
            archive.writestr(name, content)
    return output.getvalue()
