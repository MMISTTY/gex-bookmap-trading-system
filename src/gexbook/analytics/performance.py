"""Cost-inclusive analytics, including marked-to-market drawdown."""

from collections import defaultdict
from statistics import mean
from gexbook.models import Result


def summary(result: Result):
    trades = result.trades
    wins = [t.net for t in trades if t.net > 0]
    losses = [t.net for t in trades if t.net < 0]
    peak, drawdown = None, 0.0
    for row in result.equity:
        value = row["equity"]
        peak = value if peak is None else max(peak, value)
        drawdown = max(drawdown, peak - value)
    return {
        "total_trades": len(trades),
        "win_rate": len(wins) / len(trades) if trades else 0,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "average_win": mean(wins) if wins else 0,
        "average_loss": mean(losses) if losses else 0,
        "net_profit": sum(t.net for t in trades),
        "maximum_drawdown": drawdown,
        "expectancy": mean(t.net for t in trades) if trades else 0,
        "average_duration_seconds": mean((t.exit_at - t.entry_at).total_seconds() for t in trades)
        if trades
        else 0,
        "open_positions_at_end": result.equity[-1]["open_positions"] if result.equity else 0,
        "label": result.label,
    }


def grouped(result: Result, field: str):
    if field not in ("level_kind", "confirmation", "side"):
        raise ValueError("Unsupported grouping")
    groups = defaultdict(list)
    for trade in result.trades:
        groups[str(getattr(trade, field))].append(trade)
    return {
        key: {
            "trades": len(ts),
            "net_profit": sum(t.net for t in ts),
            "win_rate": sum(t.net > 0 for t in ts) / len(ts),
        }
        for key, ts in groups.items()
    }
