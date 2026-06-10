# PBot-3 Accumulation Report Contract

Use this contract when judging whether a generated BTC Up/Down replication report beats the local template:

`trader-activitys/PBot-3/analysis_20260610/reports/pbot3_accumulation_strategy_pixel_replication_plan_20260610.md`

## Minimum Sections

The report must include:

- A direct technical thesis, not just tables.
- Exact input path, address/window, generated time, settlement source, BTCUSDT kline source, and coverage.
- Evidence grades: facts, strong inference, weak inference, unknowns, and prohibited extrapolations.
- Interval recommendation: `primary_candidate`, `shadow_only`, or `disable_live`, derived from ROI, q* margin, sample size, and kline coverage.
- Lifecycle: first order, last-before-close, order gap, active span, and whether the strategy should avoid last-second chasing.
- Inferred order evidence: same price / same side / short gap multi-fill rate and its maker/post-only inference boundary.
- Batch evidence: market-level both-side rate versus batch-level both-side rate.
- Ladder evidence: rank cost share, median shares, price offsets, and deeper-level behavior.
- Size/Kelly diagnostic: price bucket table, discrete lot evidence, price-share correlation caveat, and a verdict that avoids claiming Kelly without modeled edge and bankroll.
- Inventory: q* formula, weighted q*, weighted net correctness, q* margin, dynamic q* anchors, and final-net lock timing.
- Direction alpha: BTCUSDT current advantage definition, with/against-current-advantage cost/ROI/win-rate table, and streak table.
- Weak-side rules: cheap optionality, q* improvement, inventory repair, ambiguity, and no chasing.
- Deterministic implementation handoff: config, event loop, candidate order model, risk gates, post-only behavior, shadow/live gates, and scorecard targets.
- Worked market example from first fill to final inventory, including q*, current advantage, and advantage relation.

## Must Be Better Than The Template By

- Computing the tables from the supplied address, not copying PBot-3 constants.
- Writing every derived CSV next to the report for auditability.
- Making kline absence explicit: if BTCUSDT kline is missing, alpha/advantage sections must downgrade to research-only.
- Separating Polymarket settlement labels from Binance kline fallback/cross-checks.
- Turning every live rule into a measurable gate or default value.
- Listing unknowns that block live replication: unfilled orders, cancellations, maker/taker proof, queue position, full orderbook, fees/rebates, hidden hedges, and account bankroll.

## Failure Conditions

Reject or iterate the report if it:

- Mentions non-BTC assets as in-scope.
- Claims true order IDs, cancellations, queue position, maker status, or live alpha source from activity CSV alone.
- Treats ex-post winner labels as the live signal.
- Uses a fixed market spend cap without quantile and bankroll scaling caveats.
- Calls sizing Kelly without a modeled probability edge and bankroll term.
- Omits q* anchors, final-net lock timing, with/against-current-advantage evidence, or the worked example.
