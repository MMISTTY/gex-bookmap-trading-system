"""Deterministic, visibly synthetic scenario for software validation only."""

from datetime import datetime, timedelta
from gexbook.models import Anchor, Level, Snapshot, Event


def demo():
    start = datetime.fromisoformat("2026-01-05T15:00:00+00:00")
    anchor = Anchor("SYNTHETIC-2026-01-05", start - timedelta(minutes=5), 40.0)
    snapshot = Snapshot(
        "synthetic-gex",
        start - timedelta(minutes=1),
        start + timedelta(hours=6),
        (
            Level(
                "support",
                "Put Wall",
                500,
                20000,
                role="support",
                provenance="SYNTHETIC FIXTURE; not observed options data",
            ),
            Level(
                "resistance",
                "Call Wall",
                501.5,
                20060,
                role="resistance",
                provenance="SYNTHETIC FIXTURE; not observed options data",
            ),
        ),
        anchor,
        "simulation",
        ("All prices, volume and levels are synthetic",),
    )
    events = []
    seq = 0

    def add(ts, kind, price=0, size=0, side=""):
        nonlocal seq
        events.append(Event(seq, ts, kind, "MNQ", "simulation", price, size, side))
        seq += 1

    add(start, "reset")
    old_bid, old_ask = None, None
    prices = [19999.75] * 5 + [
        20000,
        20000.25,
        20000.5,
        20000.75,
        20001,
        20002,
        20005,
        20010,
        20015,
        20020,
        20026,
        20030,
    ]
    for i, price in enumerate(prices):
        ts = start + timedelta(seconds=i + 1)
        if old_bid is not None:
            add(ts, "depth", old_bid, 0, "bid")
            add(ts, "depth", old_ask, 0, "ask")
        bid, ask = price - 0.25, price + 0.25
        add(ts, "depth", bid, 80, "bid")
        add(ts, "depth", ask, 15, "ask")
        add(ts, "trade", price, 5 if i < 5 else 20, "sell" if i < 5 else "buy")
        old_bid, old_ask = bid, ask
    return events, [snapshot]
