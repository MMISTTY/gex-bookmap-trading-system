# Reproducible portfolio demonstration

This is an engineering demonstration of a paper research system, not a claim of
profitable trading. No Bookmap login or market-data purchase is required for it.

## Five-minute walkthrough
1. Install the project as described in README and launch the local dashboard.
2. Open Backtesting and run the synthetic verification example. The simulation
   label must remain visible. Inspect the trade explanation and data coverage.
3. Open Strategy Monitor to compare proposed and rejected conditions. Explain
   why strategy checks cannot bypass the independent risk engine.
4. Open Bookmap Order Flow to inspect reconstructed depth and delta. Explain
   that absorption/sweeps are approximations and iceberg detection is unsupported.
5. Download the research report bundle from Backtesting. Inspect configuration,
   costed trades, equity, snapshots, coverage and the input-identity manifest.
6. In GEX Levels, show the CSV upload and manual draft controls. Do not present
   synthetic prices as actual current options positioning. Explain locked mapping.

## Engineering discussion points
- The same event pipeline runs paper replay and local capture processing.
- Input order is preserved; corruption is rejected before chronological splits.
- GEX snapshots have availability times and expiration bounds; future snapshots
  cannot influence earlier decisions.
- Stops can gap; stale quotes block fills, including emergency liquidation.
- Tests exercise data leakage, independent risk vetoes, source handling, mapping,
  dashboard workflows, and reproducible report exports.
- Resetting a draft clears imported rows instead of relabeling old data as fresh.

## Honest integration status
Normalized recordings and simulation are tested. Bookmap's live paid-feed access
requires provider approval; the owner's recognized add-on remains restricted.
No live brokerage connector exists. No real historical strategy performance has
been validated. Queue priority, partial fills, holiday calendars and robust
rolling optimization are future work, not implemented features.

## Reproduce the checks
```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m gexbook.cli demo --output runtime/portfolio-demo
```

Use only the committed synthetic fixtures for a public demonstration. Keep actual
options CSVs, account settings, runtime reports and provider data private. A report
bundle includes levels and paper settings; review it before sharing with recruiters.
