"""One validated configuration shared by replay, live-file paper mode, and UI."""

from dataclasses import asdict, dataclass, fields
import json
from math import isfinite
from pathlib import Path
from datetime import time


@dataclass(frozen=True)
class Config:
    mode: str = "paper"
    market_symbol: str = "MNQ"
    balance: float = 10000.0
    risk_per_trade: float = 100.0
    daily_loss: float = 300.0
    max_contracts: int = 3
    max_positions: int = 1
    max_consecutive_losses: int = 3
    tick_size: float = 0.25
    tick_value: float = 0.50
    commission_per_side: float = 0.65
    slippage_ticks: int = 1
    min_rr: float = 1.5
    stop_points: float = 10.0
    target_points: float = 25.0
    breakeven_at: float = 0.0
    trailing_points: float = 0.0
    session_start: str = "08:30"
    session_end: str = "15:00"
    max_age_seconds: float = 5.0
    depth_max_age_seconds: float = 30.0
    window_seconds: float = 10.0
    min_window_seconds: float = 3.0
    min_trades: int = 4
    level_distance: float = 5.0
    confirm_points: float = 0.5
    min_liquidity: float = 20.0
    absorption_volume: float = 10.0
    absorption_range: float = 2.0
    delta_threshold: float = 10.0
    imbalance_threshold: float = 0.15
    breakout_seconds: float = 3.0
    liquidity_drop_ratio: float = 0.5
    cooldown_seconds: float = 30.0
    min_score: float = 0.65

    def __post_init__(self):
        if self.mode != "paper":
            raise ValueError("Only paper mode exists; live orders are not implemented")
        if self.market_symbol not in ("MNQ", "NQ"):
            raise ValueError("Only MNQ or NQ market data supported")
        if self.tick_size != 0.25 or self.tick_value != 0.50:
            raise ValueError("Execution is MNQ only: tick 0.25 points / $0.50")
        for f in fields(self):
            v = getattr(self, f.name)
            if isinstance(f.default, str):
                if not isinstance(v, str):
                    raise ValueError(f"{f.name} must be text")
                continue
            if type(v) not in (int, float):
                raise ValueError(f"{f.name} must be a number, not text or a boolean")
            if not isfinite(v) or v < 0:
                raise ValueError(f"{f.name} must be finite and nonnegative")
        for n in (
            "max_contracts",
            "max_positions",
            "max_consecutive_losses",
            "min_trades",
            "slippage_ticks",
        ):
            if type(getattr(self, n)) is not int:
                raise ValueError(f"{n} must be an integer")
        for n in (
            "balance",
            "risk_per_trade",
            "daily_loss",
            "max_contracts",
            "max_positions",
            "max_consecutive_losses",
            "stop_points",
            "target_points",
            "min_rr",
            "max_age_seconds",
            "depth_max_age_seconds",
            "window_seconds",
            "min_trades",
        ):
            if getattr(self, n) <= 0:
                raise ValueError(f"{n} must be positive")
        if not 0 <= self.min_score <= 1 or not 0 <= self.imbalance_threshold <= 1:
            raise ValueError("Score and imbalance must be in [0,1]")
        if not 0 < self.liquidity_drop_ratio < 1:
            raise ValueError("Liquidity drop ratio must be in (0,1)")
        if time.fromisoformat(self.session_start) >= time.fromisoformat(self.session_end):
            raise ValueError("This version requires a same-day daytime session")
        if self.min_window_seconds > self.window_seconds:
            raise ValueError("Warmup exceeds window")

    @classmethod
    def active(cls):
        """Prefer ignored personal settings; tracked defaults remain nonpersonal."""
        for path in (Path("runtime/paper-config.json"), Path("config/default.json")):
            if path.exists():
                return cls.load(path)
        return cls()

    @classmethod
    def load(cls, path: str | Path):
        return cls(**json.loads(Path(path).read_text()))

    def save(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(asdict(self), indent=2))
