---
name: polymarket-updown-strategy-replicator
description: Analyze a Polymarket wallet or profile address and generate a pixel-level replication document for crypto Up/Down trading behavior. Use when a user gives a Polymarket address and asks to reverse engineer, reproduce, audit, or document its BTC/ETH/SOL/XRP/DOGE/BNB Up/Down strategy, especially with Chinese prompts such as 地址策略复刻, 像素级复刻, 交易历史分析, PBot 类策略反推, 最近一个月默认分析.
---

# Polymarket UpDown Strategy Replicator

## Purpose

Generate a source-backed, audit-ready strategy replication report from one Polymarket address. Default scope is the most recent 30 days of crypto Up/Down `TRADE` activity with settlement enrichment.

This skill builds on `$polymarket-address-activity` for complete address exports, then applies a PBot-3 style forensic workflow: inferred limit orders, quote batches, ladder ranks, lifecycle timing, two-sided inventory, q* breakeven math, side streaks, budget and sizing distributions, and a concrete implementation handoff.

## Quick Start

When the user provides only an address, run:

```bash
python3 /Users/hfer/temp/my-skills/skills/polymarket-updown-strategy-replicator/scripts/analyze_updown_strategy.py \
  --user 0x... \
  --days 30 \
  --export-chunk-hours 3 \
  --export-workers 4 \
  --export-limit 500 \
  --max-settlement-markets 5000 \
  --out-dir strategy-replication-audits
```

The script will:

1. Find and call `polymarket-address-activity/scripts/export_polymarket_activity.py` in raw chunks, then settlement-enrich the merged file.
2. Filter crypto Up/Down markets.
3. Infer orders and quote batches from short same-price consecutive fills.
4. Generate a Markdown replication report and machine-readable JSON summary.

If an enriched activity CSV already exists, skip export:

```bash
python3 /Users/hfer/temp/my-skills/skills/polymarket-updown-strategy-replicator/scripts/analyze_updown_strategy.py \
  --input /path/to/address_activity_with_settlements.csv \
  --out-dir strategy-replication-audits
```

If the CSV is a raw activity export without settlement fields, the analyzer will create an enriched copy first. For very large addresses, keep `--max-settlement-markets` capped and report the unresolved tail explicitly; use `--max-settlement-markets 0` only when full Gamma enrichment is practical.

## Required Workflow

1. **Export or load trades.** Prefer the bundled analyzer with `--user`; it delegates export to `$polymarket-address-activity`. Use `--input` only when the CSV is already settlement-enriched.
2. **Read the generated report.** Check the report path printed by the script. Do not answer from the JSON summary alone.
3. **Audit the report.** Use `$strategy-replication-auditor` on the generated Markdown report. The target quality gate for this project is `>=80 / 100`.
4. **Iterate if below 80.** Add missing exact defaults, worked examples, data-health caveats, or validation gates. Re-run quick validation after edits.

## Output Contract

The report must include these sections:

- Strategy boundary, address, time window, and non-goals.
- Data sources, schemas, timezone, filtering rules, and data-health counts.
- Market mechanics, payoff, settlement, fee and order-type assumptions.
- Observed performance by asset, interval, side, price band, and phase.
- Inferred order lifecycle: start, stop, frequency, multi-fill order rate.
- Batch and ladder structure: one-side versus both-side batches, rank sizes, price offsets.
- Inventory and q*: formulas, final net correctness, qstar margin, net caps.
- Direction and alpha inference: what can be inferred from fills, what requires underlying price path data, and the default model when kline/orderbook is available.
- Deterministic replication config with concrete numbers derived from the wallet sample.
- Execution rules, sizing rules, risk controls, backtest/shadow/live gates.
- One worked market example from first order to final inventory.
- Known unknowns and a minimal rewrite checklist aligned to `$strategy-replication-auditor`.

## Evidence Rules

- Treat trade rows as facts.
- Treat inferred orders as proxies, not real order IDs.
- If maker/taker flags, cancellations, unfilled orders, L2 depth, or queue position are missing, say so and narrow the claim.
- If the wallet has too few resolved crypto Up/Down markets, produce a partial report and state the minimum additional data needed.
- Do not infer a live alpha source from settlement labels alone. Use settlement labels only as ex-post validation unless underlying kline/orderbook was joined.

## References

Read these only when needed:

- `references/pbot3_reverse_engineering_patterns.md`: PBot-3 derived analysis patterns and common traps.
- `references/auditor_readiness_contract.md`: how to shape the report so `$strategy-replication-auditor` can score it above 80.

## Validation

After editing this skill, run:

```bash
python3 /Users/hfer/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  /Users/hfer/temp/my-skills/skills/polymarket-updown-strategy-replicator

python3 -m py_compile \
  /Users/hfer/temp/my-skills/skills/polymarket-updown-strategy-replicator/scripts/analyze_updown_strategy.py
```
