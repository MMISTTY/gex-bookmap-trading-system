# Development instructions

Scope: GEX + Bookmap only. Python 3.12+, Streamlit, SQLite, MNQ paper execution.
No live-order implementation. No unrelated indicators or invented market data.
Use explicit GEX sign assumptions. Lock session mapping anchors. Reject stale, missing,
future, disconnected, and unsynchronized data. Keep simulation visibly labeled.
Maintain PROJECT_STATUS.md and commit meaningful working phases. Use focused tests after
changes and the full suite at integration checkpoints. Preserve existing working code.
Do not commit private data, account information, tokens, runtime databases, or secrets.
Do not enable paid usage or purchases. Avoid unnecessary agents, browser steps, and scans.
Use documented interfaces; record unverified integrations and limitations honestly.
