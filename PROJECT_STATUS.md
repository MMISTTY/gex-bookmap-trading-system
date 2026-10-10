# Project status

Updated 2026-10-10 UTC. Paper research MVP published.

## Completed and verified
- Public repository: https://github.com/MMISTTY/gex-bookmap-trading-system
- Initial source published as b2f5f01; project pinned to MMISTTY profile.
- Removed accidental terminal-output file in 740e1c3.
- Final development checkpoint: 40 tests passed; Ruff checks and formatting passed.
- Streamlit server startup and HTTP health verified; seven dashboard pages implemented.
- Published initial commit shows successful GitHub checks.
- Barchart-style options and manual-level ingestion with explicit dealer-sign assumptions and missing-field diagnostics.
- Locked approximate QQQ-to-MNQ anchors, editable mapped levels, append-only SQLite snapshots.
- Normalized JSONL/CSV recordings, simulation and incremental local file-tail adapter.
- Depth, delta, CVD and documented absorption/sweep approximations.
- Explainable reversal and sustained-breakout rules; independent risk vetoes and costed paper fills.
- Shared event engine for replay and paper processing; chronological fixed-parameter out-of-sample split, analytics and trade explanations.
- README, architecture, data/strategy/backtest/Bookmap guides, MIT license, VS Code setup and CI.

## Architecture
Python 3.12+, Streamlit and SQLite. Modules under src/gexbook: gex, mapping, bookmap, strategy, risk, execution, backtesting, analytics, storage and dashboard. Point-in-time snapshots and validated events feed the same decision pipeline. No live-order connector exists.

## Safety and hardening
- Personal settings remain in ignored runtime/paper-config.json; public defaults remain unchanged.
- Chicago session dates; stale, future, disconnected, crossed or invalid quotes prevent entries.
- Integer event sequences, bounded defense observations and continuously qualifying breakout flow.
- Disconnect/reset clears strategy state. Risk limits override signals.
- Simulation fixtures are software tests, not historical performance or evidence of profitability.

## Integration status and remaining work
- Official Bookmap L1 Java depth/trade callbacks verified in documentation. Official Python API documentation excludes BookmapData/dxFeed support.
- Experimental Java capture source and build script exist, but have NOT been compiled, loaded or connected to the owner's installation.
- Next external gate: compile against the installed SDK and verify provider entitlements, units, initial book and reconnect behavior.
- No actual options or point-in-time historical order-flow data was supplied for this build. Real-data evaluation remains outstanding.
- MNQ economics configured as 0.25-point tick and $0.50/tick; NQ analysis cannot authorize MNQ fills.
- No known failing Python test at the verified checkpoint. Java compilation and actual Bookmap connectivity remain unverified.

## Continuation
Use the existing repository and preserve its history. Pull remote changes before editing. Keep private CSVs under data/private and runtime data out of commits. Do not reinitialize, force push, or rebuild completed phases. See AGENTS.md for stable instructions.

## Capture diagnostics checkpoint — 2026-10-10
- Added read-only `inspect-capture` CLI command: normalized schema, reset, continuity,
  source/symbol, capture-end reliability and separate wall-clock freshness diagnostics.
- No broker, execution, database or external connection is created by diagnostics.
- Official Bookmap guidance confirms restricted paid-feed activation requires review/signing;
  raw-data export in the existing bridge requires provider review. No bypass was added.
- Latest user setup context reports the add-on is recognized but MNQ activation is restricted;
  support approval was requested. This is not an independently verified live connection.
- Java changes made on the user's computer have not been synchronized or inspected here.
- Derived-only in-Bookmap processing is a possible future design, pending written clarification
  of permitted outputs; it is not implemented or represented as approved.
- Verification: 46 tests passed; Ruff lint and format checks passed.

## Phase 2 review — 2026-10-10
- Reviewed user commit 53d3c44: source classification, historical-date validation,
  options-flow rejection and gamma-weighted wall ranking. Baseline: 50 tests passed;
  two files failed the formatting gate.
- Fixed expired supplied GEX rows being retained before expiration filtering.
- Imported dashboard snapshots now require today's Chicago session date; backdating
  the label cannot turn historical data into a newly available trading snapshot.
- Upload content hashes require revalidation when same-name file contents change.
- Historical imports remain inspectable; unknown observation dates remain ineligible
  for current-session snapshots. A footer date does not establish intraday availability.
- Verification: 53 tests passed, including dashboard and expiry regressions; Ruff
  lint and formatting passed. No actual Bookmap connection or historical edge validated.
- Next external steps: apply this review patch, push from the authorized local checkout,
  supply current options data and await Bookmap/provider approval before live capture.
