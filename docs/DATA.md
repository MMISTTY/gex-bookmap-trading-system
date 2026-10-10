# Data contracts

Options CSV may contain long rows (`Type,Strike,Open Int,Gamma,Expiration`) or wide rows (`Strike,Call Open Interest,Put Open Interest,Call Gamma,Put Gamma`). Supported aliases are defined centrally in `gex/ingestion.py`. Commas, currency signs, K/M/B suffixes and parentheses are normalized. Ambiguous columns, duplicate contracts, negative OI/gamma and nonfinite numbers are rejected. Expiration filtering requires the actual date; absent expiry is warned. One upload is processed at a time; combined files must preserve unique contracts and consistent units.

A manual levels file can use `Level Type,QQQ Price,MNQ Price,Role`. Roles are support/resistance/neutral. Explicit supplied flip/walls are preserved. Existing profiles use `Strike,Net GEX` and require a declared signed-data assumption and units to be ranked.

## Normalized event stream

JSONL has one event per line. CSV uses the same field names. An example reset:

```json
{"seq":0,"ts":"2026-01-05T15:00:00+00:00","kind":"reset","symbol":"MNQ","source":"recorded","price":0,"size":0,"side":""}
```

- `seq`: consecutive nonnegative integers; reset starts a newly reconstructed book.
- `ts`: timezone-aware ISO timestamp; preserve source chronology, never sort corruption away.
- `kind`: reset, depth, trade, heartbeat, disconnect.
- `symbol`: one configured instrument per engine; MNQ needed for execution.
- `source`: recorded, simulation, bookmap_bridge. Do not mix sources.
- `depth`: absolute size at price, bid/ask; zero deletes a level.
- `trade`: positive size/price and known aggressor buy/sell. Unknown sides cannot be fabricated.
- `heartbeat`: does not refresh trade/depth freshness.

First supply reset and a complete book, then enough recent trades for warmup. Missing sequence or timestamp regression invalidates state. A local file tail buffers incomplete lines and rejects file replacement/truncation; restart using a fully rebuilt stream.

Snapshot JSON is an array of `Snapshot` objects, downloadable from GEX Levels. Each records ID, availability, expiry, levels, locked anchor, source and assumptions. See the explicitly synthetic sample for an executable schema example. Runtime SQLite contains immutable anchors/snapshots and local audit records. Uploading a historical snapshot today does not establish that it was known historically; you must preserve its true original availability.

## Barchart historical import safety (Phase 2)

The GEX upload page identifies Barchart **gamma-levels** profiles, **volatility/Greeks**
contract rows, and **options-flow** trade prints. The last category is *not* a
unique-contract OI/GEX snapshot: repeated prints must not be deduplicated as if
they were separate open-interest observations. Upload a gamma-levels or Greeks
CSV for GEX calculations instead.

The source date is read from the Barchart `Downloaded ... as of` footer, when
present, and file expiration from a recognized `exp-YYYYMMDD` or
`exp-YYYY-MM-DD` filename segment. These are reported separately; neither
file modification time nor upload time proves historical data availability.
An imported snapshot cannot be saved as current-session input if its observed
date is unknown/different or its filename expiration is already past. These
checks prevent accidental use of old option-chain inputs as fresh signals; they
do **not** establish when during a historical day the data became available.
For rigorous historical backtesting, preserve the original availability time.

When contract gamma and open interest are complete on one side, a put/call wall
proxy ranks strikes by sum of **gamma × open interest** across the included
contracts. If any contract gamma is missing for that side, the model falls
back explicitly to an **open-interest-only wall proxy**. Both remain approximate
concentrations, not verified dealer holdings, and cannot establish a gamma flip.
Provided signed exposure columns require an explicitly declared unit convention
and cannot be treated as independently verified dealer inventories.

Historical CSVs are intentionally **not included** in the public repository.
Keep personal source files under ignored `data/private/`.

Dashboard saves of imported data require the actual current Chicago date, independently
of the editable session label. Historical files can be inspected but cannot be backdated
and saved with a fresh availability timestamp. Replacing an uploaded file, including
same-name replacements, requires revalidation. Expired supplied GEX rows are excluded
before profile aggregation. These checks validate metadata consistency, not the
truthfulness or intraday availability of a vendor footer.
