"""GEX location + measured order flow. Scores are diagnostics, never win probabilities."""

from gexbook.config import Config
from gexbook.models import Signal, Snapshot
from gexbook.bookmap.flow import OrderFlow
from gexbook.mapping.anchors import round_tick

WEIGHTS = {
    "importance": 0.10,
    "distance": 0.10,
    "liquidity": 0.15,
    "absorption": 0.15,
    "delta": 0.15,
    "imbalance": 0.10,
    "confirmation": 0.15,
    "reliability": 0.10,
}


class Strategy:
    def __init__(self, config: Config):
        self.c = config
        self.active_snapshot = None
        self.touched = {}
        self.baseline = {}
        self.accepted_since = {}
        self.last_signal_at = None
        self.decisions = []

    def evaluate(self, flow: OrderFlow, snapshot: Snapshot | None, now):
        m, c = flow.metrics(now), self.c
        self.decisions = []
        if not snapshot or not snapshot.available_at <= now < snapshot.valid_until:
            self.decisions.append(
                {"ts": now, "accepted": False, "reason": "No point-in-time valid GEX snapshot"}
            )
            return None
        if snapshot.id != self.active_snapshot:
            self.touched.clear()
            self.baseline.clear()
            self.accepted_since.clear()
            self.active_snapshot = snapshot.id
        if not m.reliable or m.price is None:
            self.decisions.append({"ts": now, "accepted": False, "reason": "; ".join(m.reasons)})
            return None
        if self.last_signal_at and (now - self.last_signal_at).total_seconds() < c.cooldown_seconds:
            return None
        proposals = []
        for level in snapshot.levels:
            price = level.mnq_price
            near = abs(m.price - price) <= c.level_distance
            for side in (1, -1):
                k = (level.id, side)
                previous = self.baseline.get(k)
                if previous and (now - previous[1]).total_seconds() > c.window_seconds:
                    self.baseline.pop(k)
                current_size = flow.liquidity_near(price, side)
                if near and current_size >= self.baseline.get(k, (0, now))[0]:
                    self.baseline[k] = (current_size, now)
            if near:
                self.touched[level.id] = now
            touched = (
                level.id in self.touched
                and (now - self.touched[level.id]).total_seconds() <= c.window_seconds
            )
            for side in (1, -1):
                for confirmation in ("rejection", "breakout"):
                    direction = side * (m.price - price)
                    role_ok = level.role == ("support" if side == 1 else "resistance")
                    current = flow.liquidity_near(
                        price, side if confirmation == "rejection" else -side
                    )
                    baseline = self.baseline.get((level.id, -side), (0, now))[0]
                    beyond = direction >= c.confirm_points
                    k = (level.id, side)
                    defend = current >= c.min_liquidity
                    fail = (
                        baseline >= c.min_liquidity and current <= baseline * c.liquidity_drop_ratio
                    )
                    absorption = flow.absorption(price, side)
                    delta = side * m.recent_delta >= c.delta_threshold
                    shift = side * (m.recent_delta - m.earlier_delta) > 0
                    imbalance = side * m.imbalance >= c.imbalance_threshold
                    # Breakout acceptance requires continuous price AND directional flow.
                    if confirmation == "breakout":
                        if beyond and delta and imbalance and fail:
                            self.accepted_since.setdefault(k, now)
                        else:
                            self.accepted_since.pop(k, None)
                    duration = (now - self.accepted_since.get(k, now)).total_seconds()
                    confirm = (
                        touched
                        and near
                        and beyond
                        and (
                            (role_ok and shift)
                            if confirmation == "rejection"
                            else duration >= c.breakout_seconds
                        )
                    )
                    checks = {
                        "importance": level.importance > 0,
                        "distance": near,
                        "liquidity": defend if confirmation == "rejection" else fail,
                        "absorption": absorption,
                        "delta": delta,
                        "imbalance": imbalance,
                        "confirmation": confirm,
                        "reliability": m.reliable,
                    }
                    score = sum(
                        WEIGHTS[x] * (level.importance if x == "importance" else checks[x])
                        for x in WEIGHTS
                    )
                    gates = (
                        "importance",
                        "distance",
                        "liquidity",
                        "delta",
                        "imbalance",
                        "confirmation",
                        "reliability",
                    )
                    if confirmation == "rejection":
                        gates += ("absorption",)
                    accepted = all(checks[x] for x in gates) and score >= c.min_score
                    explanation = (
                        f"{confirmation} at {level.kind} {price:.2f}; "
                        f"score={score:.2f}, recent_delta={m.recent_delta:.1f}, "
                        f"imbalance={m.imbalance:.3f}, liquidity={current:.1f}, "
                        f"acceptance_seconds={duration:.1f}; "
                        f"failed={','.join(x for x in gates if not checks[x]) or 'none'}; "
                        "absorption is a volume/price-stall approximation"
                    )
                    self.decisions.append(
                        {
                            "ts": now,
                            "level": level.id,
                            "side": side,
                            "confirmation": confirmation,
                            "score": score,
                            "checks": checks,
                            "accepted": accepted,
                            "reason": explanation,
                        }
                    )
                    if accepted:
                        proposals.append(
                            Signal(
                                now,
                                side,
                                level.id,
                                level.kind,
                                confirmation,
                                m.price,
                                round_tick(m.price - side * c.stop_points),
                                round_tick(m.price + side * c.target_points),
                                score,
                                checks,
                                explanation,
                                snapshot.id,
                            )
                        )
        if proposals:
            best = max(proposals, key=lambda s: s.score)
            self.last_signal_at = now
            return best
        return None
