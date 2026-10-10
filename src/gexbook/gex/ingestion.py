"""Barchart-style long/wide options and explicit levels; no inferred dealer inventory."""

from dataclasses import dataclass
from datetime import date
import csv
import io
import re
from math import isfinite
from collections import defaultdict
from gexbook.models import Level


class DataError(ValueError):
    pass


def key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


ALIASES = {
    "strike": ["strike", "strike price"],
    "type": ["type", "option type", "call/put", "cp"],
    "oi": ["open interest", "open int", "oi", "openint"],
    "volume": ["volume", "vol"],
    "gamma": ["gamma"],
    "iv": ["iv", "implied volatility", "imp vol"],
    "expiration": ["expiration", "expiry", "expiration date", "exp date", "exp"],
    "net_gex": ["net gex", "gex", "gamma exposure", "net gamma exposure"],
    "call_oi": ["call oi", "calls oi", "call open interest", "call open int"],
    "put_oi": ["put oi", "puts oi", "put open interest", "put open int"],
    "call_gamma": ["call gamma", "calls gamma"],
    "put_gamma": ["put gamma", "puts gamma"],
    "call_volume": ["call volume", "call vol"],
    "put_volume": ["put volume", "put vol"],
    "call_iv": ["call iv", "call implied volatility"],
    "put_iv": ["put iv", "put implied volatility"],
    "kind": ["level type", "level", "kind", "level name"],
    "price": ["price", "qqq price", "qqq level"],
    "mnq_price": ["mnq price", "mnq level"],
    "role": ["role"],
    "importance": ["importance", "rank score"],
}
REVERSE = {key(a): k for k, names in ALIASES.items() for a in names}
KINDS = {
    "callwall": "Call Wall",
    "putwall": "Put Wall",
    "gammaflip": "Gamma Flip",
    "gammapin": "Gamma Pin",
    "pinningzone": "Pinning Zone",
    "majorpositivegex": "Major Positive GEX",
    "majornegativegex": "Major Negative GEX",
    "support": "Support",
    "resistance": "Resistance",
}


def number(raw, *, nonnegative=False):
    if raw is None or str(raw).strip().lower() in ("", "-", "--", "n/a", "na", "null"):
        return None
    s = str(raw).strip().replace(",", "").replace("$", "")
    percent = s.endswith("%")
    if percent:
        s = s[:-1]
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = "-" + s[1:-1]
    multiplier = 1
    if s and s[-1].upper() in ("K", "M", "B"):
        multiplier = {"K": 1e3, "M": 1e6, "B": 1e9}[s[-1].upper()]
        s = s[:-1]
    try:
        v = float(s) * multiplier / (100 if percent else 1)
    except ValueError as exc:
        raise DataError(f"Invalid number: {raw!r}") from exc
    if not isfinite(v) or (nonnegative and v < 0):
        raise DataError(f"Invalid finite/nonnegative number: {raw!r}")
    return v


@dataclass(frozen=True)
class Contract:
    strike: float
    option_type: str
    oi: float | None
    gamma: float | None
    volume: float | None
    iv: float | None
    expiration: str | None


@dataclass
class ImportReport:
    contracts: list[Contract]
    profiles: dict[float, float]
    levels: list[Level]
    warnings: list[str]
    recognized_columns: list[str]


def parse_csv(text: str, as_of: date | None = None) -> ImportReport:
    """Header discovery tolerates preambles. Corrupt non-footer rows fail with row number."""
    rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    header_idx = next(
        (
            i
            for i, r in enumerate(rows)
            if any(
                key(c) in ("strike", "strikeprice", "leveltype", "kind") or key(c) in KINDS
                for c in r
            )
        ),
        None,
    )
    if header_idx is None:
        raise DataError("Missing recognized header: strike, level type, or named level columns")
    headers = [REVERSE.get(key(c), key(c)) for c in rows[header_idx]]
    if len(headers) != len(set(headers)):
        raise DataError("Duplicate normalized columns; use unambiguous call/put column names")
    contracts, profiles, levels, warnings = [], {}, [], []
    seen = set()
    for rownum, cells in enumerate(rows[header_idx + 1 :], header_idx + 2):
        if not cells or not any(c.strip() for c in cells):
            continue
        if cells[0].lower().startswith(("downloaded", "copyright", "total", "data as of")):
            continue
        if len(cells) != len(headers):
            raise DataError(f"Row {rownum}: expected {len(headers)} cells; found {len(cells)}")
        r = dict(zip(headers, cells))
        try:
            if "kind" in r:
                kind = KINDS.get(key(r["kind"]), r["kind"].strip())
                if not kind:
                    raise DataError("Missing level type")
                role = r.get("role", "").strip().lower() or (
                    "support"
                    if kind in ("Put Wall", "Support")
                    else "resistance"
                    if kind in ("Call Wall", "Resistance")
                    else "neutral"
                )
                levels.append(
                    Level(
                        f"import-{rownum}",
                        kind,
                        number(r.get("price")),
                        number(r.get("mnq_price")),
                        number(r.get("importance")) if r.get("importance") else 1.0,
                        role,
                        "provided level",
                    )
                )
                continue
            if "strike" not in r:
                for col in headers:
                    if col in KINDS and number(r[col]) is not None:
                        kind = KINDS[col]
                        levels.append(
                            Level(
                                f"import-{rownum}-{col}",
                                kind,
                                number(r[col]),
                                provenance="provided named level",
                            )
                        )
                continue
            strike = number(r["strike"], nonnegative=True)
            if not strike or strike <= 0:
                raise DataError("Missing or nonpositive strike")
            if r.get("net_gex", "").strip():
                if strike in profiles:
                    raise DataError("Duplicate strike in provided profile; aggregate explicitly")
                profiles[strike] = number(r["net_gex"])
            expiry = r.get("expiration", "").strip() or None
            if expiry:
                parsed = None
                for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
                    from datetime import datetime

                    try:
                        parsed = datetime.strptime(expiry, fmt).date()
                        break
                    except ValueError:
                        continue
                if parsed is None:
                    raise DataError("Unrecognized expiration date")
                expiry = parsed.isoformat()
                if as_of and parsed < as_of:
                    warnings.append(f"Excluded expired contract row {rownum}")
                    continue
            types = (
                [("call", "")]
                if key(r.get("type", "")) in ("call", "c")
                else ([("put", "")] if key(r.get("type", "")) in ("put", "p") else [])
            )
            if "type" in r and not types:
                raise DataError("Option type must be Call/C or Put/P")
            if not types:
                types = [
                    (t, t + "_")
                    for t in ("call", "put")
                    if any(t + "_" + f in r for f in ("oi", "gamma", "volume", "iv"))
                ]
            for option_type, prefix in types:
                identity = (strike, option_type, expiry)
                if identity in seen:
                    raise DataError("Duplicate contract strike/type/expiration")
                seen.add(identity)
                vals = [
                    number(r.get(prefix + f), nonnegative=True)
                    for f in ("oi", "gamma", "volume", "iv")
                ]
                if vals[0] is not None and not vals[0].is_integer():
                    raise DataError("Open interest must be whole contracts")
                contracts.append(Contract(strike, option_type, *vals, expiry))
        except (ValueError, TypeError) as exc:
            raise DataError(f"Row {rownum}: {exc}") from exc
    if not contracts and not profiles and not levels:
        raise DataError("No usable contracts, GEX profiles, or levels")
    if contracts and any(c.expiration is None for c in contracts):
        warnings.append("Expiration unavailable for some contracts; expiry filtering incomplete")
    return ImportReport(contracts, profiles, levels, warnings, headers)


def derive_levels(
    report: ImportReport, spot: float | None, assumption: str = "unsigned", gex_units: str = ""
) -> tuple[list[Level], list[str]]:
    """Returns supported levels and explicit limitations; gamma flip must be supplied."""
    if assumption not in ("unsigned", "calls_positive_puts_negative", "provided_signed"):
        raise DataError("Unknown dealer-position assumption")
    if spot is not None and (not isfinite(spot) or spot <= 0):
        raise DataError("Spot must be positive and finite")
    notes = list(report.warnings)
    levels = list(report.levels)
    unsigned, signed = defaultdict(float), defaultdict(float)
    for option_type, kind, role in [
        ("call", "Call Wall", "resistance"),
        ("put", "Put Wall", "support"),
    ]:
        selected = [c for c in report.contracts if c.option_type == option_type]
        if selected and all(c.oi is not None for c in selected):
            amounts = defaultdict(float)
            for c in selected:
                amounts[c.strike] += c.oi
            strike, amount = max(amounts.items(), key=lambda p: p[1])
            if amount > 0:
                levels.append(
                    Level(
                        f"{option_type}-wall",
                        kind,
                        strike,
                        importance=1,
                        role=role,
                        provenance="largest open-interest concentration; wall proxy",
                        metric=amount,
                        approximate=True,
                    )
                )
        elif selected:
            notes.append(f"{kind} unavailable: incomplete {option_type} open interest")
    enough = report.contracts and all(
        c.gamma is not None and c.oi is not None for c in report.contracts
    )
    if enough and spot is not None:
        for c in report.contracts:
            exposure = c.gamma * c.oi * 100 * spot**2 * 0.01
            unsigned[c.strike] += exposure
            if assumption == "calls_positive_puts_negative":
                signed[c.strike] += exposure * (1 if c.option_type == "call" else -1)
        notes.append("Unsigned GEX = gamma × OI × 100 × spot² × 0.01; USD per 1% QQQ move")
        if assumption == "calls_positive_puts_negative":
            notes.append(
                "MODEL ASSUMPTION: dealer exposure positive calls / negative puts; inventory unknown"
            )
    elif report.contracts:
        missing = []
        if spot is None:
            missing.append("QQQ reference spot")
        if any(c.gamma is None for c in report.contracts):
            missing.append("contract gamma")
        if any(c.oi is None for c in report.contracts):
            missing.append("open interest")
        notes.append("GEX calculation unavailable: missing " + ", ".join(missing))
    if report.profiles:
        if assumption != "provided_signed" or not gex_units.strip():
            notes.append(
                "Provided GEX profile not ranked: select provided_signed and declare its units"
            )
        else:
            signed = dict(report.profiles)
            notes.append(
                f"Provided signed GEX; units={gex_units}; provider methodology not independently verified"
            )
    if unsigned:
        largest = max(unsigned.values())
        for strike, value in sorted(unsigned.items(), key=lambda p: p[1], reverse=True)[:5]:
            if value <= 0:
                continue
            role = (
                "neutral"
                if spot is None or strike == spot
                else ("support" if strike < spot else "resistance")
            )
            levels.append(
                Level(
                    f"concentration-{strike}",
                    "Gamma Concentration",
                    strike,
                    importance=value / largest,
                    role=role,
                    provenance="unsigned gamma concentration; role inferred from location",
                    metric=value,
                    approximate=True,
                )
            )
    if signed:
        maximum = max(abs(v) for v in signed.values()) or 1
        for positive, kind in [(True, "Major Positive GEX"), (False, "Major Negative GEX")]:
            candidates = [(s, v) for s, v in signed.items() if (v > 0 if positive else v < 0)]
            if candidates:
                strike, val = max(candidates, key=lambda p: abs(p[1]))
                levels.append(
                    Level(
                        kind,
                        kind,
                        strike,
                        importance=abs(val) / maximum,
                        provenance=f"signed GEX: {assumption}",
                        metric=val,
                        approximate=assumption != "provided_signed",
                    )
                )
        positives = [(s, v) for s, v in signed.items() if v > 0]
        if positives:
            strike, val = max(positives, key=lambda p: p[1])
            levels.append(
                Level(
                    "pin-candidate",
                    "Gamma Pin Candidate",
                    strike,
                    importance=abs(val) / maximum,
                    provenance="largest positive concentration heuristic",
                    metric=val,
                    approximate=True,
                )
            )
    if not any(level.kind == "Gamma Flip" for level in levels):
        notes.append(
            "Gamma Flip unavailable: requires a supplied flip or re-priced spot-dependent gamma surface; strike sign changes are not a flip"
        )
    return sorted(levels, key=lambda level: level.importance, reverse=True), notes
