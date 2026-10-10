"""Local research dashboard. All execution controls are paper-only."""

from hashlib import sha256
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from gexbook.config import Config
from gexbook.models import Anchor, Level, Snapshot, jsonable, timestamp
from gexbook.gex.ingestion import parse_csv, derive_levels
from gexbook.gex.source import inspect_source
from gexbook.mapping.anchors import map_level, synchronized_anchor
from gexbook.storage.sqlite import Store
from gexbook.bookmap.adapters import read_events
from gexbook.bookmap.simulation import demo
from gexbook.backtesting.replay import replay, out_of_sample
from gexbook.analytics.performance import summary, grouped

PAGES = [
    "Overview",
    "GEX Levels",
    "Bookmap Order Flow",
    "Strategy Monitor",
    "Risk Management",
    "Backtesting",
    "Settings and Logs",
]


def table(items):
    rows = jsonable(items)
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.info("No data loaded.")


def load_config():
    return Config.active()


def main():
    st.set_page_config(page_title="GEX + Bookmap | Paper Research", layout="wide")
    st.title("GEX + Bookmap")
    st.caption("MNQ • America/Chicago • PAPER ONLY • Research system, no live-order connector")
    c = load_config()
    page = st.sidebar.radio("Workspace", PAGES)
    st.sidebar.warning("Bookmap connection and your data entitlements are not verified.")
    engine = st.session_state.get("engine")
    capture = None
    path = Path("runtime/latest/state.json")
    if path.exists():
        try:
            capture = json.loads(path.read_text())
            age = (datetime.now(timezone.utc) - timestamp(capture["as_of"])).total_seconds()
            if age > c.max_age_seconds:
                st.warning(
                    f"Capture process state is stale ({age:.1f}s). No new entries permitted."
                )
        except (ValueError, KeyError, OSError) as e:
            st.error(f"Capture state unavailable: {e}")
    store = Store()
    try:
        snapshots = store.snapshots()
        if page == "Overview":
            st.subheader("Account and session")
            st.metric("Configured paper balance", f"${c.balance:,.2f}")
            st.write(
                "Capture source:", capture["source"] if capture else "Disconnected / unavailable"
            )
            st.write("Saved GEX snapshots:", len(snapshots))
            st.write("Session window (Chicago):", c.session_start, "–", c.session_end)
            if capture:
                st.json(capture["metrics"])
            if engine:
                st.warning(engine.result.label)
                st.json(summary(engine.result))
        elif page == "GEX Levels":
            gex_page(store, snapshots)
        elif page == "Bookmap Order Flow":
            st.subheader("Normalized order flow")
            st.caption(
                "Depth additions/removals are net changes. Absorption and sweep flags are approximations; iceberg detection is unavailable."
            )
            if st.button("Load synthetic demonstration"):
                events, sample_snapshots = demo()
                st.session_state.engine = replay(events, sample_snapshots, c)
                st.rerun()
            if capture:
                st.json(capture["metrics"])
            elif engine:
                st.warning(engine.result.label)
                st.json(jsonable(engine.flow.metrics(engine.last_event.ts)))
                table(
                    [
                        {"side": side, "price": p, "size": size}
                        for side, book in [("bid", engine.flow.bids), ("ask", engine.flow.asks)]
                        for p, size in book.items()
                    ]
                )
            else:
                st.info(
                    "Start the documented local capture process, upload normalized history on Backtesting, or load the synthetic demonstration."
                )
        elif page == "Strategy Monitor":
            st.subheader("Signal explanations and rejected criteria")
            st.caption(
                "Score is a weighted checklist, not a probability of success. Risk vetoes override signals."
            )
            if capture:
                table(capture["decisions"])
            elif engine:
                table(engine.result.decisions[-100:])
            else:
                st.info("No strategy events processed.")
        elif page == "Risk Management":
            st.subheader("Independent paper risk controls")
            st.json(
                {
                    k: v
                    for k, v in asdict(c).items()
                    if k
                    in [
                        "balance",
                        "risk_per_trade",
                        "daily_loss",
                        "max_contracts",
                        "max_positions",
                        "max_consecutive_losses",
                        "min_rr",
                        "stop_points",
                        "target_points",
                        "commission_per_side",
                        "slippage_ticks",
                        "breakeven_at",
                        "trailing_points",
                    ]
                }
            )
            if capture:
                st.json(capture["risk"])
                table(capture["positions"])
            if st.button("Emergency paper lock and flatten"):
                if engine:
                    engine.broker.emergency_flatten()
                p = Path("runtime/latest/control.json")
                p.parent.mkdir(parents=True, exist_ok=True)
                tmp = p.with_suffix(".tmp")
                tmp.write_text(json.dumps({"id": str(uuid4()), "command": "emergency"}))
                tmp.replace(p)
                store.audit(datetime.now(timezone.utc), "emergency_requested", {"paper_only": True})
                st.success(
                    "Paper lock requested. Capture engine flattens only when a fresh executable quote is available. Restart requires deliberate operator action."
                )
            st.caption(
                "Demo replay has already finished. Emergency commands affect a running local tail process; this dashboard never controls a brokerage account."
            )
        elif page == "Backtesting":
            backtest_page(c)
        else:
            st.subheader("Configuration and audit")
            raw = st.text_area(
                "Paper configuration JSON", json.dumps(asdict(c), indent=2), height=450
            )
            if st.button("Validate and save configuration"):
                updated = Config(**json.loads(raw))
                updated.save("runtime/paper-config.json")
                store.audit(datetime.now(timezone.utc), "configuration_saved", asdict(updated))
                st.success("Validated. Restart capture process to apply settings.")
            table(store.logs())
    except Exception as e:
        st.error(f"{type(e).__name__}: {e}")
        store.audit(datetime.now(timezone.utc), "dashboard_error", {"error": str(e)})
    finally:
        store.close()


def gex_page(store, snapshots):
    st.subheader("Daily GEX import and locked mapping")
    st.caption(
        "QQQ and MNQ coordinates are approximate. The factor is locked per session; quotes do not continuously move levels."
    )
    upload = st.file_uploader("Options or levels CSV", type=["csv"])
    source_info = None
    if upload is not None:
        source_info = inspect_source(upload.name, upload.getvalue().decode("utf-8-sig"))
        st.caption(
            f"Detected file: {source_info.kind} • Barchart observed on: "
            f"{source_info.observed_on or 'unverified'} • "
            f"filename expiration: {source_info.expires_on or 'not supplied'}"
        )
        for warning in source_info.current_session_errors(
            datetime.now(ZoneInfo("America/Chicago")).date()
        ):
            st.warning("Not eligible as fresh current-session GEX: " + warning)
    spot = st.number_input("QQQ reference / calculation spot", min_value=0.01, value=500.0)
    assumption = st.selectbox(
        "Dealer-position assumption",
        ["unsigned", "calls_positive_puts_negative", "provided_signed"],
    )
    units = st.text_input("Imported GEX units (required for provided_signed)")
    if st.button("Validate and derive uploaded levels"):
        if upload is None:
            raise ValueError("Upload your CSV first; no options data is supplied automatically.")
        if not source_info.is_position_snapshot:
            raise ValueError(
                "Options-flow rows are trade prints, not a contract snapshot. "
                "Use a gamma-levels or volatility-Greeks CSV."
            )
        report = parse_csv(
            upload.getvalue().decode("utf-8-sig"),
            as_of=source_info.observed_on or datetime.now(ZoneInfo("America/Chicago")).date(),
        )
        levels, notes = derive_levels(report, spot, assumption, units)
        st.session_state.level_rows = jsonable(levels)
        st.session_state.gex_notes = report.warnings + list(notes)
        st.session_state.gex_source = upload.name
        st.session_state.gex_source_profile = source_info
        st.session_state.gex_source_digest = sha256(upload.getvalue()).hexdigest()
        store.audit(
            datetime.now(timezone.utc),
            "csv_import",
            {"filename": upload.name, "notes": st.session_state.gex_notes},
        )
    for note in st.session_state.get("gex_notes", []):
        st.warning(note)
    default = [
        {
            "id": "manual-1",
            "kind": "Put Wall",
            "qqq_price": None,
            "mnq_price": None,
            "importance": 1.0,
            "role": "support",
            "provenance": "manual",
            "metric": None,
            "approximate": True,
            "override_reason": "",
        }
    ]
    rows = st.data_editor(
        pd.DataFrame(st.session_state.get("level_rows", default)),
        num_rows="dynamic",
        key="level_editor",
        use_container_width=True,
    )
    st.caption(
        "Enter actual levels. For an imported coordinate override, add an override reason. Importance is a normalized concentration ranking or your explicit assessment."
    )
    session = st.text_input(
        "Session ID", datetime.now(ZoneInfo("America/Chicago")).date().isoformat()
    )
    method = st.radio("Anchor method", ["Manual factor", "Synchronized references"])
    factor = st.number_input("Manual conversion factor", min_value=0.000001, value=40.0)
    mnq = st.number_input("MNQ reference", min_value=0.25, value=20000.0)
    now_text = datetime.now(timezone.utc).isoformat()
    qtime = st.text_input("QQQ quote timestamp (with offset)", now_text)
    mtime = st.text_input("MNQ quote timestamp (with offset)", now_text)
    source = st.text_input("Level source", st.session_state.get("gex_source", "manual user levels"))
    if st.button("Map and save session snapshot"):
        # Historical files may be inspected but cannot silently become today's trade inputs.
        imported_profile = st.session_state.get("gex_source_profile")
        if upload is not None and (
            st.session_state.get("gex_source") != upload.name
            or st.session_state.get("gex_source_digest") != sha256(upload.getvalue()).hexdigest()
        ):
            raise ValueError("Revalidate the newly selected file before saving a snapshot")
        if imported_profile is not None:
            try:
                session_date = date.fromisoformat(session)
            except ValueError as exc:
                raise ValueError("Imported data requires an ISO session date (YYYY-MM-DD)") from exc
            today = datetime.now(ZoneInfo("America/Chicago")).date()
            if session_date != today:
                raise ValueError(
                    "Imported dashboard snapshots require today's Chicago session date"
                )
            problems = imported_profile.current_session_errors(today)
            if problems:
                raise ValueError(
                    "Cannot save an imported snapshot for this session: " + "; ".join(problems)
                )
        now = datetime.now(timezone.utc)
        # Existing anchors are reused unchanged, preserving the original lock timestamp.
        existing = next((s.anchor for s in snapshots if s.anchor.session == session), None)
        anchor = existing or (
            Anchor(session, now, factor)
            if method == "Manual factor"
            else synchronized_anchor(session, spot, mnq, timestamp(qtime), timestamp(mtime), now)
        )
        levels = []
        for row in rows.to_dict("records"):
            row = {k: (None if pd.isna(v) else v) for k, v in row.items()}
            for key in ["id", "kind", "role", "provenance", "override_reason"]:
                row[key] = row.get(key) or ("" if key == "override_reason" else "manual")
            if (
                row.get("qqq_price") is not None
                and row.get("mnq_price") is not None
                and row["provenance"] != "manual"
                and not row["override_reason"]
            ):
                raise ValueError("Imported MNQ overrides require an override reason.")
            levels.append(map_level(Level(**row), anchor))
        if not levels:
            raise ValueError("At least one real supplied level is required.")
        snap = Snapshot(
            str(uuid4()),
            now,
            now + timedelta(hours=16),
            tuple(levels),
            anchor,
            source,
            tuple(st.session_state.get("gex_notes", [])),
        )
        store.save_snapshot(snap)
        store.audit(now, "snapshot_saved", {"id": snap.id})
        st.success("Snapshot saved with a locked session anchor.")
        snapshots = store.snapshots()
    if snapshots:
        selected = st.selectbox(
            "Saved snapshot",
            snapshots,
            format_func=lambda s: f"{s.available_at.isoformat()} • {s.source}",
        )
        table(sorted(selected.levels, key=lambda level: -level.importance))
        chart = pd.DataFrame(
            [
                {"MNQ price": x.mnq_price, "Importance": x.importance, "Kind": x.kind}
                for x in selected.levels
            ]
        )
        st.scatter_chart(chart, x="MNQ price", y="Importance", color="Kind")
        st.json(jsonable(selected.anchor))
        st.download_button(
            "Download point-in-time snapshots",
            json.dumps(jsonable(snapshots), indent=2),
            "snapshots.json",
        )


def backtest_page(c):
    st.subheader("Event replay and chronological out-of-sample testing")
    event_file = st.file_uploader("Normalized event JSONL or CSV", type=["jsonl", "csv"])
    snapshot_file = st.file_uploader("Point-in-time snapshots JSON", type=["json"])
    split = st.text_input("Optional out-of-sample boundary (ISO timestamp with offset)")
    if st.button("Run uploaded history"):
        if event_file is None or snapshot_file is None:
            raise ValueError("Both event history and point-in-time snapshots are required.")
        events = read_events(
            event_file.getvalue().decode(), "csv" if event_file.name.endswith(".csv") else "jsonl"
        )
        snapshots = [Snapshot.from_dict(d) for d in json.loads(snapshot_file.getvalue())]
        engine = (
            out_of_sample(events, snapshots, c, timestamp(split))[1]
            if split
            else replay(events, snapshots, c)
        )
        st.session_state.engine = engine
    if st.button("Run synthetic verification example"):
        events, snapshots = demo()
        st.session_state.engine = replay(events, snapshots, c)
    engine = st.session_state.get("engine")
    if engine:
        st.warning(engine.result.label)
        st.json(summary(engine.result))
        if engine.result.equity:
            st.line_chart(pd.DataFrame(jsonable(engine.result.equity)).set_index("ts")["equity"])
        table(engine.result.trades)
        for field in ["level_kind", "confirmation", "side"]:
            st.write(field, grouped(engine.result, field))
        st.download_button(
            "Download trade explanations",
            json.dumps(jsonable(engine.result.trades), indent=2),
            "trades.json",
        )
    st.caption(
        "No queue-position or partial-fill reconstruction. Missing depth/aggressor data makes confirmation untestable. Demonstration results are not validated historical performance."
    )
