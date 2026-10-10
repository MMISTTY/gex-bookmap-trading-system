# Project status

## Completed
- Python 3.12 workspace inspected; Streamlit, pandas, pytest, and Ruff available.
- Domain models and validated paper-only configuration implemented.
- Official Bookmap L1/Python API documentation inspected.

## Verified external interfaces
- Bookmap L1 Java add-ons expose depth/trade callbacks.
- Official Python API page states BookmapData/dxFeed are unsupported by Python API.
- MNQ specification: 0.25-point tick, $0.50 tick value.
- GitHub account MMISTTY is connected; connector reads work, writes previously returned 403.
- Local Bookmap installation/data entitlement and live bridge are NOT verified.

## Architecture
src/gexbook: gex, mapping, bookmap, strategy, risk, execution, backtesting, analytics,
storage, dashboard. Frozen point-in-time snapshots feed an event-driven paper engine.

## Completed phase 2
- Barchart-style options/levels ingestion, explicit sign assumptions and missing-field reporting.
- Locked QQQ-to-MNQ mapping and append-only SQLite snapshots.
- Normalized JSONL/CSV replay and incremental file-tail adapter.
- Order-book, delta, CVD, concentration, absorption/sweep approximations.
- Explainable rejection/breakout rules, independent risk vetoes, costed paper fills.
- Point-in-time replay, fixed-config chronological out-of-sample split and analytics.
- 29 tests passed at phase checkpoint.

## Remaining
Java capture bridge, dashboard, integration tests, documentation, packaging and publication.

## Known blockers
No actual options or historical order-flow files provided for this build. No access to
user's VS Code or Bookmap process. Use explicitly synthetic fixtures for verification.

## Completed phase 3
- Seven-page Streamlit dashboard, editable GEX levels, local SQLite snapshots and JSON export.
- Normalized history upload, synthetic replay, equity/trade reviews, configuration validation.
- Local file-tail state and emergency paper controls; no brokerage connector.
- Experimental Java L1 capture source and SDK build script (NOT compiled or deployed).
- README, MIT license, data/strategy/backtest/Bookmap guides, VS Code configuration and CI.
- 32 tests passed; Ruff passed; Streamlit server HTTP health verified.
- Short rejection and sustained breakout tested; adverse breakout fills correctly vetoed by risk.
- Disconnect/reset now clears pre-disconnection strategy acceptance/defense state.

## Outstanding external gates
- Actual Bookmap SDK compilation, entitlement/provider checks and live depth initialization.
- Actual point-in-time options/order-flow data and out-of-sample performance validation.
- GitHub publication underway through authorized signed-in browser; connector write permissions blocked.

## Publication checkpoint
- Public repository created: MMISTTY/gex-bookmap-trading-system.
- New-repository Contents API write returned 403 (Resource not accessible by integration).
- Browser folder upload rejected; expanded source-tree publication blocked by write access.
- Complete tracked source archive and README prepared for browser upload as a usable fallback.
- 33 tests passed including dashboard manual save and session-anchor reuse.
- Browser multi-file upload did not complete and was interrupted. Repository verified EMPTY.
- Code has NOT been pushed or published. Downloadable source archive is the completed deliverable.

## Continued hardening
- Personal account configuration saves to ignored runtime/paper-config.json, preserving public defaults.
- Dashboard session dates and expiration filtering now use America/Chicago.
- Risk independently checks quote timestamp, finite/positive BBO and uncrossed geometry.
- Fractional/Boolean event sequences are rejected instead of coerced to integers.
- Breakout timers require continuous directional flow and diminished opposing defense.
- Observed defense baselines expire within the rolling window; zero-importance levels are vetoed.
- GitHub installation lookup returned no app installations; write authorization remains an external gate.
- Final hardening checkpoint: 40 tests passed; Ruff checks and formatting passed.
