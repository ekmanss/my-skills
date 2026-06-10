# PBot-3 Reverse Engineering Patterns

Use these patterns when converting raw Polymarket address activity into a strategy replication document.

## Core Lessons From Prior PBot-3 Work

- Same market + same outcome + same rounded price + short timestamp gap should be merged into an inferred order. Default gap: `5s`.
- A market lifecycle can be two-sided even when each quote batch is usually single-sided. Report both:
  - `both_sides_market_rate`
  - `both_side_batch_rate`
- A PBot-style inventory strategy is not proven by profit alone. Require timing, ladder, q*, net inventory, and passive-execution evidence.
- q* is the breakeven probability of the current net side:
  - If `U > D`: `q*_up = (C - D) / (U - D)`
  - If `D > U`: `q*_down = (C - U) / (D - U)`
- Buying the eventual loser can still be rational if it was cheap optionality or reduced net exposure at the time. Do not label every loser-side order as a mistake.
- The alpha source cannot be recovered from trade CSV alone. Ex-post winner labels validate direction; they do not define a live signal.
- If orderbook data is absent, classify execution style by proxy only:
  - multi-fill same-price inferred orders support passive/limit behavior
  - no maker/taker flag means no per-fill proof
  - no unfilled/cancelled orders means quote density is under-observed

## Report Shape That Worked For PBot-3

Use this sequence:

1. Direct thesis and scope boundary.
2. Data inventory and evidence grades.
3. Aggregate performance by market family.
4. Inferred order construction.
5. Lifecycle timing and quote frequency.
6. One-sided versus both-sided batches.
7. Ladder rank, price offsets, and size allocation.
8. Market budget and cap inference.
9. Inventory ledger and q* math.
10. Direction/alpha inference and what remains unknowable.
11. Deterministic implementation spec.
12. Backtest, shadow, live gates, and kill switches.
13. Worked market example.
14. Unknowns and rewrite checklist.

## Common Traps

- Do not turn ex-post settlement into a live alpha rule.
- Do not claim fixed caps from medians; use quantile caps and call them soft/hard.
- Do not call size a Kelly function unless stake varies continuously with modeled edge and bankroll.
- Do not claim market orders just because a fill happened at a high price; compare against available orderbook when possible.
- Do not hide missing order IDs or maker/taker flags. State the exact inference boundary.
- Do not leave `dynamic_*`, `TBD`, `configurable`, or `roughly` in the final implementation spec. Convert them into formulas and defaults.
