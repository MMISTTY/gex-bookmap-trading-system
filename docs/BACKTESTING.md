# Backtesting methodology

Replay uses the same event handlers, strategy and risk engine as paper file processing. At each event only the latest snapshot with `available_at <= event time < valid_until` is eligible. Levels or parameters selected from future results must not be supplied as if known historically.

A signal is proposed after a trade event; entry uses a subsequent trade event's fresh BBO, adverse slippage and a renewed risk check. Costs are charged on both sides. Stops gap to available quotes plus slippage. Targets receive no price improvement. At dataset end positions are liquidated at the last fresh executable quote with an explicit end-of-dataset reason; without one they remain open and are reported. Marked equity freezes when quotes are unreliable rather than inventing valuations.

The model does not reconstruct queue position, partial fills, venue latency, hidden orders or intra-event paths. A stale feed can leave a paper position open; this is a limitation, not risk-free execution. Estimated stopping risk can be exceeded by gaps. Holiday-calendar restrictions and production latency benchmarking are not implemented.

```bash
python -m gexbook.cli replay --events your-history.jsonl --snapshots your-point-in-time-snapshots.json --split-at 2026-01-05T15:00:08+00:00
```

The split is chronological and fixed-parameter. Prefix data initializes the test order book and rolling flow; prefix trades, P&L and strategy acceptance state are not copied into the test portfolio. Pick parameters using only the training segment, then freeze them before evaluating the test segment. This feature is not an optimization engine or rolling walk-forward search.

Missing order depth or aggressor sides cannot reconstruct liquidity/absorption/imbalance confirmations. Those inputs remain untestable. Toy synthetic fixtures verify behavior only. No supplied results are validated historical performance. Metrics describe the particular input dataset and execution assumptions, not probabilities of future success.
