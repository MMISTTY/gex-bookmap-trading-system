# Bookmap interface verification and capture

Official documentation inspected for this build:
- [Bookmap API overview](https://bookmap.com/knowledgebase/docs/API)
- [Python API](https://bookmap.com/knowledgebase/docs/Addons-Python-API)
- [Official Java examples](https://github.com/BookmapAPI/simple-demo), reference commit `aba12582fee5f59bbe6f4a0f609c8b99d56e91c2`
- [Official Python examples](https://github.com/BookmapAPI/python-api)
- [CME MNQ contract specifications](https://www.cmegroup.com/markets/equities/nasdaq/micro-e-mini-nasdaq-100.contractSpecs.html)

L1 Java add-ons receive depth, trades and SDK timestamps. The Python documentation says BookmapData and dxFeed are unsupported by its Python API, and Python replay is unavailable. Consequently this repository uses a Java capture candidate and a provider-neutral Python file adapter. A Global subscription does not establish your external API entitlement or provider compatibility; these have not been verified.

`bridge/.../Capture.java` follows the official `DataRecorder` callback signatures. It emits sequential normalized JSONL using SDK epoch-nanosecond timestamps. Depth integer prices are multiplied by `InstrumentInfo.pips`; trade prices are passed through as in the official recorder. Aggressor interpretation follows its `isBidAggressor` example. **You must validate units against the displayed MNQ contract before relying on capture.** The size divisor defaults to one for futures quantities and is explicitly configurable. The add-on does not infer a symbol from the alias: select the correct chart and configuration yourself. Metadata retains the SDK alias.

An asynchronous bounded queue isolates disk writes from callbacks. Overflow or writer failure stops capture instead of silently dropping events. Python freshness/sequence rules then veto entries. A reset is emitted at the first callback; reliable depth reconstruction depends on your Bookmap delivering full initialization callbacks. This behavior has not been checked in an installed Bookmap session. Reload into a new capture file after failures; do not splice partial books together.

## Restricted paid-feed approval gate

Bookmap's [official add-on guidance](https://github.com/BookmapAPI/ai-skills/blob/main/SKILL.md)
identifies the message "Most of the API modules are not allowed for this instrument"
as a restricted-instrument activation block. Paid live data can require Bookmap validation
and a signed add-on. Rebuilding a signed jar invalidates its signature.

The current capture design exports raw depth/trade events. Official guidance states that
market data should stay inside Bookmap for approval; this export design must therefore be
reviewed by Bookmap before use with restricted feeds. Do not add `@UnrestrictedData` as a
workaround: an annotation is not authorization. Do not change source labels or switch feeds
to evade an entitlement restriction.

A possible future architecture computes order-flow features inside Bookmap, then shares
only outputs explicitly permitted by the provider. It is **not implemented or approved**;
which fields may leave Bookmap must be established before building that transport.
Use the existing simulation or recordings you are authorized to process while approval
is pending. Never distribute private captures in GitHub issues or the public repository.

## Read-only capture diagnostics

Validate a closed capture or stable local copy before starting paper processing:

```bash
python -m gexbook.cli inspect-capture --events /absolute/path/capture.jsonl
# Reproducible synthetic example:
python -m gexbook.cli inspect-capture --events data/samples/SYNTHETIC-events.jsonl
```

JSON output distinguishes structural validity, quality at the last event and wall-clock
freshness. It checks schema, initial reset, symbol/source consistency, sequence continuity,
timestamps and existing order-book reliability rules. It reports event counts and explicit
failure reasons. It creates no broker, orders, database or report file. Exit code 0 means
structural validity only; code 2 means invalid/unreadable input. A historical file can pass
structural checks while correctly reporting stale data. A partial final JSON row fails;
retry on a closed copy rather than editing out missing data. Source labels are untrusted
metadata, not proof of live connectivity or authorization. Full initial depth, units and
aggressor semantics still require comparison against the approved provider feed.

## External setup gate

No JDK, installed Bookmap jars or desktop session was available during development. **The Java source is uncompiled and unverified.** These steps are a deployment checklist, not a claim of an established connection:

1. Confirm your installed Bookmap version, data provider, MNQ/NQ depth entitlement and L1 add-on support.
2. Obtain the official API jars matching that version. With a compatible JDK, run `BOOKMAP_LIB_DIR=/path/to/api-jars bash bridge/build.sh` (or the equivalent `javac`/`jar` commands on Windows).
3. Configure JVM properties through your installation's supported JVM configuration mechanism: `gexbook.symbol=MNQ`, `gexbook.directory=/absolute/local/path`, `gexbook.sizeDivisor=1`. Source defaults to `recorded`; set `gexbook.source=bookmap_bridge` only for verified live capture.
4. Load the resulting add-on through Bookmap's supported L1 add-on installation UI. SDK/version errors must be resolved before proceeding.
5. Verify prices, quantities, aggressor direction, timestamp freshness and complete initial depth against Bookmap. Use a new file for each attach. Do not relabel replay as live.
6. Run local paper processing:

```bash
python -m gexbook.cli tail --events /absolute/path/capture-TIMESTAMP.jsonl --snapshots /absolute/path/snapshots.json
```

The dashboard reads `runtime/latest/state.json` and sends a local paper emergency command through `control.json`. Restarting the tail process re-applies any retained emergency command, deliberately preserving lockout. Remove the control file only as a deliberate operator reset when flat and conditions are verified. No order API is called.

Historical fallback: translate your supported Bookmap export to [DATA.md](DATA.md), retaining original timestamps and depth/aggressor semantics. If your export lacks those fields, required conditions remain untestable. The repository does not claim a universal proprietary Bookmap-file converter or access to paid iceberg add-ons.
