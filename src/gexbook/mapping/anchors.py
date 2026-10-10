"""Approximate QQQ/futures coordinate mapping locked to a session reference."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from gexbook.models import Anchor, Level, timestamp, finite


def round_tick(price: float, tick: float = 0.25) -> float:
    return float(
        (Decimal(str(price)) / Decimal(str(tick))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        * Decimal(str(tick))
    )


def synchronized_anchor(
    session: str,
    qqq: float,
    mnq: float,
    qqq_at: datetime,
    mnq_at: datetime,
    locked_at: datetime,
    max_skew_seconds: float = 2,
) -> Anchor:
    q, m, lock = timestamp(qqq_at), timestamp(mnq_at), timestamp(locked_at)
    if abs((q - m).total_seconds()) > max_skew_seconds or max(q, m) > lock:
        raise ValueError("Reference quotes must be synchronized and known at lock time")
    if (lock - min(q, m)).total_seconds() > 60:
        raise ValueError("Reference quotes too old to lock (maximum 60 seconds)")
    finite(qqq, "QQQ reference", 0.000001)
    finite(mnq, "MNQ reference", 0.000001)
    return Anchor(session, lock, mnq / qqq, qqq, mnq, max(q, m), "synchronized_ratio")


def map_level(level: Level, anchor: Anchor) -> Level:
    if level.mnq_price is not None:
        return level
    return replace(level, mnq_price=round_tick(level.qqq_price * anchor.factor))


def override_level(level: Level, *, mnq_price: float, reason: str) -> Level:
    if not reason.strip():
        raise ValueError("Manual override requires a reason")
    return replace(
        level,
        mnq_price=round_tick(finite(mnq_price, "override", 0.000001)),
        override_reason=reason,
        provenance=level.provenance + "; manually overridden",
    )
