"""Identify Barchart exports and their historical availability without fabricating timestamps."""

import csv
from dataclasses import dataclass
from datetime import date, datetime
import io
import re


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


@dataclass(frozen=True)
class SourceProfile:
    kind: str
    observed_on: date | None
    expires_on: date | None
    evidence: str

    @property
    def is_position_snapshot(self) -> bool:
        return self.kind != "options_flow"

    def current_session_errors(self, session_date: date) -> list[str]:
        errors = []
        if not self.is_position_snapshot:
            errors.append("Options-flow trade prints are not a unique-contract GEX snapshot")
        if self.observed_on is None:
            errors.append("Source observation date is unknown; cannot approve for current-session use")
        elif self.observed_on != session_date:
            errors.append(
                f"Options source was observed {self.observed_on}; current session is {session_date}"
            )
        if self.expires_on is not None and self.expires_on < session_date:
            errors.append(f"Source expiration {self.expires_on} is past the session date")
        return errors


def inspect_source(filename: str, text: str) -> SourceProfile:
    """Classify raw uploads using columns and a Barchart 'as of' footer, not upload time."""
    rows = csv.reader(io.StringIO(text.lstrip("\ufeff")))
    headers: set[str] = set()
    for row in rows:
        candidate = {_normalized(str(c)) for c in row}
        if "strike" in candidate or "leveltype" in candidate:
            headers = candidate
            break
    if not headers:
        kind = "unknown"
    elif {"symbol", "trade", "side", "size", "strike"} <= headers:
        kind = "options_flow"
    elif "netgammaexposure" in headers and "callgammaexposure" in headers:
        kind = "gamma_profile"
    elif "gamma" in headers and "type" in headers:
        kind = "volatility_greeks"
    elif "leveltype" in headers:
        kind = "manual_levels"
    else:
        kind = "option_chain"

    observed_on = None
    match = re.search(
        r"Downloaded\s+from\s+Barchart\.com\s+as\s+of\s+(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        date_text = match.group(1).replace("-", "/")
        try:
            observed_on = datetime.strptime(date_text, "%m/%d/%Y").date()
        except ValueError:
            pass

    expires_on = None
    expiry = re.search(r"exp-(\d{8}|\d{4}-\d{2}-\d{2})", filename, re.IGNORECASE)
    if expiry:
        value = expiry.group(1)
        try:
            expires_on = (
                datetime.strptime(value, "%Y%m%d").date()
                if len(value) == 8
                else date.fromisoformat(value)
            )
        except ValueError:
            pass
    return SourceProfile(kind, observed_on, expires_on, "Barchart footer" if match else "no verified as-of footer")
