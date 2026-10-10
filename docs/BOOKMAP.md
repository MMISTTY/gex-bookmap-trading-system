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
