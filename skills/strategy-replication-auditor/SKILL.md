---
name: strategy-replication-auditor
description: Audit pixel-level quantitative strategy replication documents against an "independent team with no prior context can reproduce it" standard. Use when reviewing strategy reverse-engineering docs, trading bot replication plans, quant execution specs, market-making strategy specs, backtest-to-live handoff docs, or Chinese prompts such as 策略复刻审核, 像素级复刻文档审查, 独立团队无上下文复现评分, 量化机构专家评审, 满分100打分并给详细改进建议.
---

# Strategy Replication Auditor

## Mission

Audit whether a strategy replication document removes implementation discretion for an independent team with no prior context. Treat "pixel-level replication" as a high bar: every trading decision must have a concrete what, how, why, default value, exception path, and validation proof.

The deliverable is a severity-ranked audit, a 100-point score, and precise rewrite recommendations. Do not stop at the user's example dimensions; review the full institutional quant handoff surface.

## Core Standard

Ask one controlling question:

```text
Could a competent but uninformed independent engineering/research team implement, replay, shadow, and safely launch the same strategy from this document alone?
```

Downgrade heavily when the document:

- Describes intuition without deterministic rules.
- Uses placeholder functions such as `dynamic_*`, `*_buffer`, `configurable`, `required`, `TBD`, or "roughly/around/near" without defaults.
- Depends on a probability/alpha model but omits labels, features, training, calibration, model artifact, or fallback rules.
- Cites performance without attribution, validation protocol, sensitivity tests, or regime boundaries.
- Gives risk concepts without hard thresholds and kill-switch actions.
- Says "replicate" while admitting missing order ids, cancels, queue position, maker/taker flags, L2, or hidden hedges without narrowing the claim.

## Workflow

1. **Read the document as the primary artifact.**
   - If the target is a local file, read headings and line-numbered passages.
   - If the document cites local supporting reports or specs, sample-read them when needed to check whether missing details are merely externalized.
   - Do not claim empirical truth unless you verified the underlying data. If only the document was reviewed, say the audit is about reproducibility and evidence sufficiency.

2. **Build a reconstruction map.**
   Extract the claimed strategy in this order:
   - Market and instrument.
   - Payoff mechanics and order types.
   - Data inputs and timing.
   - Alpha/fair value/probability model.
   - Decision loop and state machine.
   - Pricing and execution rules.
   - Sizing, inventory, budget, and capital scaling.
   - Risk controls and kill switches.
   - Backtest, replay, shadow, and live rollout gates.
   - Production operations, monitoring, reconciliation, governance, and compliance.

3. **Score with the rubric below.**
   Award points only for content that is concrete enough to implement. A named module, concept, or formula stub does not receive full credit unless its inputs, output, default behavior, and boundary cases are specified.

4. **Identify blockers before polishing.**
   Findings should focus on gaps that make two independent implementations diverge, make live trading unsafe, or make performance claims unverifiable.

5. **Give edit-level recommendations.**
   For each major gap, state the missing content and the replacement section/table/formula that should be added.

## 100-Point Rubric

| Dimension | Points | Full-credit requirement |
| --- | ---: | --- |
| Reproducibility boundary and scope | 7 | Defines exact strategy version, markets included/excluded, "replication" claim limits, assumptions, non-goals, and known unknowns. |
| Market mechanics, payoff, and order types | 8 | Explains product payoff, tick/lot/min-size rules, order side, order type, expiration, cancel semantics, settlement, fees, and maker/taker behavior in beginner-readable terms. |
| Data specification and time alignment | 8 | Lists every data source, schema, timezone, sampling frequency, lag assumptions, joins, missing-data handling, and data-health gates. |
| Alpha/probability model | 12 | Specifies features, labels, training window, model class, coefficients or training command, calibration, validation metrics, confidence/ambiguity handling, fallback when model is absent, and why it predicts edge. |
| Decision rules and state machine | 10 | Converts every tick/event into a unique action: no-op, quote, cancel, resize, rebalance, pause. Includes boundary cases and precedence when rules conflict. |
| Execution and microstructure | 10 | Gives price formula, ladder construction, queue/post-only behavior, refresh/TTL/cancel/reject handling, partial fills, stale book filters, latency assumptions, and no-chase rules. |
| Sizing, inventory, budget, and capital allocation | 10 | Defines exact size formula, rounding, max/min lots, q*/breakeven math, net caps, budget caps, weak-side rules, bankroll scaling, and examples. |
| Risk controls and kill switches | 10 | Provides hard thresholds and actions for drawdown, market loss, data lag, API errors, reconciliation gaps, exposure, correlation, regime drift, and unexplained losses. |
| Backtest, replay, and validation | 9 | Defines train/validation/test split, walk-forward protocol, fill model, fees, slippage/queue sensitivity, ablations, out-of-sample results, and pass/fail thresholds. |
| Shadow and live rollout gates | 5 | Defines dry-run outputs, minimum sample sizes, live sizing ramp, manual review gates, rollback conditions, and what must be true before real capital. |
| PnL attribution, economics, and capacity | 6 | Splits expected edge into alpha, execution improvement, inventory optionality, fees/rebates, adverse selection, costs, capacity, and ROI decay with scale. |
| Production operations, governance, compliance, and readability | 5 | Includes monitoring, alerts, reconciliation, restart recovery, config ownership, change control, credentials/security, venue/legal constraints, glossary, and worked examples. |

## Score Interpretation

- **90-100**: Independent team can implement and validate with minimal clarification.
- **75-89**: Strong technical spec; a team can implement but will make a few discretionary choices.
- **60-74**: Research-grade handoff; implementation will diverge unless authors fill key gaps.
- **45-59**: Concept/spec hybrid; useful direction, not a replication document.
- **Below 45**: Insufficient for independent reproduction.

Also provide separate optional lenses when useful:

```text
Professional research memo score:
Independent no-context reproduction score:
Beginner follow-the-doc score:
```

## Required Audit Checks

Run these checks even if the user only mentions a few examples:

- **What/how/why completeness**: For each major action, require what is done, how it is computed/executed, why it should create edge or reduce risk, and when not to do it.
- **Freedom-of-discretion test**: Mark every place where an implementer must invent a parameter, model, ranking rule, exception, or threshold.
- **Alpha dependency test**: If any gate uses probability or fair value, demand a model card and calibration evidence.
- **Execution realism test**: Separate observed fills from true orders; flag missing cancels, unfilled orders, queue priority, L2 depth, maker/taker flags, and latency.
- **Risk hardening test**: Convert "should pause" or "within cap" into exact cap, trigger, action, owner, and resume rule.
- **Validation integrity test**: Require out-of-sample, walk-forward, sensitivity, ablation, and shadow metrics. Flag any result that could be overfit to reverse-engineered fills.
- **Beginner usability test**: Require glossary, one-page plain-language mechanism, and at least one complete numeric market example from signal to final orders.

## Output Format

Use Chinese when the user writes Chinese unless they ask otherwise.

```markdown
## Verdict

**Score: X / 100**
**Status:** <one of: production-reproducible / strong but incomplete / research-grade only / not independently reproducible>
**Main reason:** <one sentence>

Optional lens scores:
- Professional quant memo: X / 100
- Independent no-context reproduction: X / 100
- Beginner executable clarity: X / 100

## Scorecard

| Dimension | Points | Score | Rationale |
| --- | ---: | ---: | --- |
| ... | ... | ... | ... |

## Blocking Gaps

List the highest-severity gaps first. For each:

### P0/P1: <title>
- **Where:** `<file>:<line or section>`
- **Problem:** <what is missing or ambiguous>
- **Why it blocks reproduction:** <how two teams would diverge or why live trading is unsafe>
- **Required fix:** <specific formula/table/model card/runbook/example to add>

## Detailed Improvement Plan

Group by:
1. Strategy definition and scope.
2. Data and alpha model.
3. Decision logic and execution.
4. Sizing, inventory, and risk.
5. Backtest, shadow, and production.
6. Beginner-readable examples.

## Minimal Rewrite Checklist

Provide a concrete checklist the document owner can apply before re-review.
```

Keep the final answer concise enough to read, but do not hide critical institutional dimensions. Avoid generic praise; focus on decision-changing gaps and actionable edits.
