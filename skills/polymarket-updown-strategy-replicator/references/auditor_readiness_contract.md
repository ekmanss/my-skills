# Auditor Readiness Contract

The generated report should target `>=80 / 100` under `$strategy-replication-auditor`.

## Minimum Content For Each Rubric Area

Reproducibility boundary:

- Exact address, date window, generated timestamp, input CSV path, strategy version.
- Included assets and intervals.
- Explicit non-goals and unknowns.

Market mechanics:

- Up/Down payoff, settlement labels, BUY/SELL treatment, fee assumption, post-only/taker inference boundary.

Data specification:

- Source fields, timezone, crypto Up/Down filter, inferred-order gap, price rounding, missing data handling.

Alpha model:

- Distinguish observed ex-post edge from live alpha.
- Provide default live alpha model when kline/orderbook exists: features, labels, train window, calibration, fallback.

Decision rules:

- A state machine with no-op, quote, cancel, expand, trim, pause, and precedence rules.

Execution:

- Price formula, ladder offsets, refresh/TTL, post-only rejection handling, partial fills, stale data gates.

Sizing/inventory:

- Lot formula, rank multipliers, q* formula, net caps, budget caps, bankroll scaling, weak-side rules.

Risk:

- Hard drawdown, market loss, data lag, API error, reconciliation, exposure, and regime drift actions.

Validation:

- Train/validation/test split or when unavailable a clear historical-only limitation.
- Fill model, fee/slippage, sensitivity, pass/fail thresholds.

Shadow/live:

- Dry-run outputs, sample size gates, capital ramp, rollback.

PnL/economics:

- Split edge into direction, execution, optionality, fees, adverse selection, and capacity.

Operations/readability:

- Monitoring, alerting, restart recovery, config ownership, credentials, glossary, worked example.

## Self-Check Before Handoff

- No unexplained placeholders remain.
- Every numeric threshold has a value, formula, or sample-derived fallback.
- Every trading action has what/how/why/when-not.
- Every empirical claim names its denominator.
- At least one complete market example is present.
