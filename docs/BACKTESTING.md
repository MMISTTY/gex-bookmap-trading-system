# Backtesting methodology

Replay uses the same event handlers, strategy and risk engine as paper file processing. At each event only the latest snapshot with `available_at <= event time < valid_until` is eligible. Levels or parameters selected from future results must not be supplied as if known historically.

A signal is proposed after a trade event; entry uses a subsequent trade event's fresh BBO, adverse slippage and a renewed risk check. Costs are charged on both sides. Stops gap to available quotes plus slippage. Targets receive no price improvement. At dataset end positions are liquidated at the last fresh executable quote with an explicit end-of-dataset reason; without one they remain open and are reported. Marked equity freezes when quotes are unreliable rather than inventing valuations.

The model does not reconstruct queue position, partial fills, venue latency, hidden orders or intra-event paths. A stale feed can leave a paper position open; this is a limitation, not risk-free execution. Estimated stopping risk can be exceeded by gaps. Holiday-calendar restrictions and production latency benchmarking are not implemented.

```bash
python -m gexbook.cli replay --events your-history.jsonl --snapshots your-point-in-time-snapshots.json --split-at 2026-01-05T15:00:08+00:00
```

The split is chronological and fixed-parameter. Prefix data initializes the test order book and rolling flow; prefix trades, P&L and strategy acceptance state are not copied into the test portfolio. Pick parameters using only the training segment, then freeze them before evaluating the test segment. This feature is not an optimization engine or rolling walk-forward search.

Missing order depth or aggressor sides cannot reconstruct liquidity/absorption/imbalance confirmations. Those inputs remain untestable. Toy synthetic fixtures verify behavior only. No supplied results are validated historical performance. Metrics describe the particular input dataset and execution assumptions, not probabilities of future success.

### Input integrity
Replay input must start with a reset followed by the required book rebuild. The
original event order is checked before an out-of-sample partition, so partitioning
cannot hide out-of-order timestamps. Equal event timestamps remain allowed;
normal sequence validation still applies. Snapshot IDs and availability timestamps
must each be unique: ambiguous inputs are rejected rather than resolved by file
order. Missing or expired GEX coverage continues to prevent entries.

### Data coverage report
The dashboard and CLI report count processed trade events with valid, nonempty
GEX snapshots, reliable order flow, and both inputs together. Missing GEX counts
and order-flow reliability reasons explain data limitations behind zero-trade runs.
Reason counts can overlap. Out-of-sample coverage excludes the warmup prefix.
These are event counts, not elapsed-time coverage, statistical confidence, proof
of feed completeness, or evidence of profitability. Risk and strategy criteria
can still reject events with both inputs available. The dashboard offers a JSON
download; CLI report.json includes data_coverage.


### Research bundles and reproducibility
Use **Download research report bundle** after a dashboard run. CLI exports the
same seven JSON files: manifest, configuration, snapshots, report, trades, equity,
and decisions. Keep the private original event file separately. The manifest
records normalized event hashes, event counts, time bounds, source, package
version, and separate warmup hash/count for out-of-sample runs. Configuration and
snapshot hashes identify the exact exported bytes. Hashes establish input identity,
not authenticity, feed completeness, or approval to redistribute data. Preserve
the Git commit alongside the bundle when comparing code versions.

Bundles include supplied GEX levels and paper account settings. Review before
sharing; neither raw options CSVs nor raw feed events are bundled. They remain
local until you deliberately download, copy or share them. Full and out-of-sample
replay share terminal liquidation handling; unavailable quotes leave positions
open with an explicit decision-log warning and no fabricated exit.
