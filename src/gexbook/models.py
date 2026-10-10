"""Validated domain objects. All persisted times are timezone-aware UTC."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from math import isfinite
from typing import Literal

UTC = timezone.utc


def timestamp(value: str | datetime) -> datetime:
    d = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if d.tzinfo is None:
        raise ValueError("Timezone offset is required; ambiguous local times are rejected")
    return d.astimezone(UTC)


def finite(value: float, name: str, minimum: float = 0) -> float:
    v = float(value)
    if not isfinite(v) or v < minimum:
        raise ValueError(f"{name} must be finite and >= {minimum}")
    return v


def jsonable(obj):
    if hasattr(obj, "__dataclass_fields__"):
        return jsonable(asdict(obj))
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    return obj


@dataclass(frozen=True)
class Level:
    id: str
    kind: str
    qqq_price: float | None
    mnq_price: float | None = None
    importance: float = 1.0
    role: Literal["support", "resistance", "neutral"] = "neutral"
    provenance: str = "manual"
    metric: float | None = None
    approximate: bool = False
    override_reason: str = ""

    def __post_init__(self):
        if not self.id or not self.kind:
            raise ValueError("Level id and kind are required")
        if self.qqq_price is None and self.mnq_price is None:
            raise ValueError("QQQ or MNQ coordinate required")
        for name in ["qqq_price", "mnq_price"]:
            if getattr(self, name) is not None:
                finite(getattr(self, name), name, 0.000001)
        finite(self.importance, "importance")
        if self.importance > 1 or self.role not in ("support", "resistance", "neutral"):
            raise ValueError("Invalid importance or role")
        if self.metric is not None and not isfinite(self.metric):
            raise ValueError("Nonfinite level metric")


@dataclass(frozen=True)
class Anchor:
    session: str
    locked_at: datetime
    factor: float
    qqq_reference: float | None = None
    mnq_reference: float | None = None
    reference_at: datetime | None = None
    method: str = "manual_factor"

    def __post_init__(self):
        object.__setattr__(self, "locked_at", timestamp(self.locked_at))
        finite(self.factor, "conversion factor", 0.000001)
        if self.reference_at is not None:
            object.__setattr__(self, "reference_at", timestamp(self.reference_at))
            if self.reference_at > self.locked_at:
                raise ValueError("Reference cannot be in the future relative to anchor")
        for name in ("qqq_reference", "mnq_reference"):
            if getattr(self, name) is not None:
                finite(getattr(self, name), name, 0.000001)


@dataclass(frozen=True)
class Snapshot:
    id: str
    available_at: datetime
    valid_until: datetime
    levels: tuple[Level, ...]
    anchor: Anchor
    source: str
    assumptions: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "available_at", timestamp(self.available_at))
        object.__setattr__(self, "valid_until", timestamp(self.valid_until))
        if self.valid_until <= self.available_at or self.anchor.locked_at > self.available_at:
            raise ValueError("Invalid snapshot timing")
        if len({level.id for level in self.levels}) != len(self.levels):
            raise ValueError("Duplicate level IDs")
        if any(level.mnq_price is None for level in self.levels):
            raise ValueError("All snapshot levels must have MNQ coordinates")

    @classmethod
    def from_dict(cls, d):
        d = dict(d)
        d["anchor"] = Anchor(**d["anchor"])
        d["levels"] = tuple(Level(**x) for x in d["levels"])
        d["assumptions"] = tuple(d.get("assumptions", []))
        return cls(**d)


@dataclass(frozen=True)
class Event:
    seq: int
    ts: datetime
    kind: Literal["depth", "trade", "heartbeat", "reset", "disconnect"]
    symbol: str
    source: Literal["simulation", "recorded", "bookmap_bridge"]
    price: float = 0
    size: float = 0
    side: str = ""

    def __post_init__(self):
        object.__setattr__(self, "ts", timestamp(self.ts))
        if self.kind not in ("depth", "trade", "heartbeat", "reset", "disconnect"):
            raise ValueError("Unsupported event kind")
        if self.source not in ("simulation", "recorded", "bookmap_bridge") or not self.symbol:
            raise ValueError("Invalid event source/symbol")
        if type(self.seq) is not int or self.seq < 0:
            raise ValueError("seq must be a nonnegative integer")
        finite(self.price, "price")
        finite(self.size, "size")
        if self.kind in ("depth", "trade") and self.price <= 0:
            raise ValueError("Market event requires positive price")
        if self.kind == "depth" and self.side not in ("bid", "ask"):
            raise ValueError("Depth side must be bid or ask")
        if self.kind == "trade" and (self.side not in ("buy", "sell") or self.size <= 0):
            raise ValueError("Trade requires positive size and known aggressor buy/sell")


@dataclass
class Signal:
    ts: datetime
    side: int
    level_id: str
    level_kind: str
    confirmation: str
    entry_reference: float
    stop: float
    target: float
    score: float
    checks: dict[str, bool]
    explanation: str
    snapshot_id: str


@dataclass
class Position:
    signal: Signal
    entry_at: datetime
    entry: float
    quantity: int
    stop: float
    target: float
    entry_fee: float


@dataclass
class Trade:
    entry_at: datetime
    exit_at: datetime
    side: int
    quantity: int
    entry: float
    exit: float
    gross: float
    fees: float
    net: float
    reason: str
    level_kind: str
    confirmation: str
    explanation: str
    snapshot_id: str


@dataclass
class Result:
    trades: list[Trade] = field(default_factory=list)
    equity: list[dict] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    label: str = "SIMULATION — NOT HISTORICAL PERFORMANCE"
