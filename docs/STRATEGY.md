# Measurable rules and defaults

Ten-second rolling flow, minimum three seconds warmup and four trades. Trade/event freshness: five seconds; depth freshness: thirty seconds. Top-five depth imbalance is `(B-A)/(B+A)`. Delta is buy minus sell; recent delta covers the newest half-window, earlier delta the remainder.

At each significant mapped level the strategy records recent proximity and observed bid/ask liquidity baselines. It evaluates both directions:

- Rejection: within five MNQ points; recovered/rejected by at least 0.5 point; matching support/resistance role; defending size at least 20; opposing volume at least 10 in at most a two-point range; directional recent delta at least 10 and stronger than earlier delta; signed imbalance at least 0.15.
- Breakout: same proximity/directional delta/imbalance requirements; opposing defense previously at least 20 and now at most 50% of observed baseline; acceptance at least 0.5 point beyond level for three continuous seconds while directional delta, imbalance and diminished opposing defense remain qualified. A failed flow gate resets the timer. Defense baselines expire after the ten-second rolling window. No assumption that negative GEX guarantees breakout.

Score weights: importance .10, distance .10, liquidity .15, absorption .15, delta .15, imbalance .10, confirmation .15, reliability .10. Importance contributes its normalized strength; other checks are Boolean. Required gates must all pass; rejection additionally requires absorption. Default minimum score .65; cooldown 30 seconds. Each recorded explanation includes measured delta, imbalance, liquidity, acceptance duration and failed gates. This score is not a probability.

Risk evaluates a proposed next-event fill independently. Stop distance plus adverse stop slippage and round-trip fees determines contract risk; net target reward after fees must satisfy 1.5 minimum reward/risk. Contract count is floored from the smallest of per-trade risk, remaining daily loss budget after open committed risk, and balance; position/contract/loss caps apply. Stop ten points, target 25 points by default. Adverse movement before fill may invalidate a previously proposed trade; this is tested.

Emergency locks new entries, cancels pending signals and requests flattening at the next reliable quote. Disconnect/reset clears signal acceptance and observed defense state. Configuration refuses live mode and non-MNQ tick economics. Change thresholds only through validated settings, and evaluate them out of sample with actual data before drawing conclusions.
