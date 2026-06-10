---
name: polymarket-updown-strategy-replicator
description: Analyze a Polymarket wallet or profile address and generate a pixel-level replication document for BTC Up/Down trading behavior only. Use when a user gives a Polymarket address and asks to reverse engineer, reproduce, audit, or document its BTC/Bitcoin Up/Down strategy, especially with Chinese prompts such as BTC updown 策略复刻, 地址策略复刻, 像素级复刻, 交易历史分析, PBot 类策略反推, 最近一个月默认分析.
---

# Polymarket BTC UpDown Strategy Replicator

## Purpose

Generate a source-backed, audit-ready strategy replication report from one Polymarket address. Default scope is the most recent 30 days of Polymarket BTC/Bitcoin Up/Down `TRADE` activity with settlement enrichment.

This skill builds on `$polymarket-address-activity` for complete address exports and settlement labels, then uses `$binance-spot-kline-history` for BTCUSDT kline context. It applies a PBot-3 style forensic workflow: inferred limit orders, quote batches, ladder ranks, lifecycle timing, two-sided inventory, q* breakeven math, side streaks, budget and sizing distributions, and a concrete implementation handoff.

The quality baseline is `trader-activitys/PBot-3/analysis_20260610/reports/pbot3_accumulation_strategy_pixel_replication_plan_20260610.md`. A generated report should be at least as clear and more self-contained than that template for a fresh address.

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
  --fetch-binance-klines \
  --out-dir strategy-replication-audits
```

The script will:

1. Find and call `polymarket-address-activity/scripts/export_polymarket_activity.py` in raw chunks, then settlement-enrich the merged file.
2. Fetch BTCUSDT klines through `skills/data/binance-spot-kline-history/scripts/fetch_binance_spot_klines.py` when `--fetch-binance-klines` is set, or load an existing `--binance-kline-csv`.
3. Filter BTC/Bitcoin Up/Down markets only.
4. Infer orders and quote batches from short same-price consecutive fills.
5. Generate a Markdown replication report and machine-readable JSON summary.

If an enriched activity CSV already exists, skip export:

```bash
python3 /Users/hfer/temp/my-skills/skills/polymarket-updown-strategy-replicator/scripts/analyze_updown_strategy.py \
  --input /path/to/address_activity_with_settlements.csv \
  --binance-kline-csv /path/to/BTCUSDT_1s.csv \
  --out-dir strategy-replication-audits
```

If the CSV is a raw activity export without settlement fields, the analyzer will create an enriched copy first. For very large addresses, keep `--max-settlement-markets` capped and report the unresolved tail explicitly; use `--max-settlement-markets 0` only when full Gamma enrichment is practical. Binance BTCUSDT 1s kline is used as a BTC-only cross-check / fallback for missing settlement labels and as the live-alpha data prerequisite; it does not replace Polymarket settlement labels when those labels are present.

## Required Workflow

1. **Export or load trades and settlement.** Prefer the bundled analyzer with `--user`; it delegates address activity to `$polymarket-address-activity`. Use `--input` only when the CSV is already settlement-enriched or when the analyzer is allowed to enrich it.
2. **Fetch or load BTCUSDT kline.** Use `$binance-spot-kline-history` directly or pass `--fetch-binance-klines` / `--binance-kline-csv`. Use `1s` for settlement cross-checks and alpha timing.
3. **Read the generated report.** Check the report path printed by the script. Do not answer from the JSON summary alone.
4. **Compare against the PBot-3 template.** Read `references/pbot3_accumulation_report_contract.md` when judging report completeness. The report must include dynamic q* anchors, final-net lock timing, with/against-current-advantage tables, Kelly diagnostics, lifecycle/batch/ladder evidence, interval live/shadow recommendations, and an implementation handoff.
5. **Audit the report.** Use `$strategy-replication-auditor` on the generated Markdown report. The target quality gate for this project is `>=85 / 100`.
6. **Iterate if below 85.** Add missing exact defaults, worked examples, data-health caveats, or validation gates. Re-run quick validation after edits.

## Output Contract

The report must include these sections:

- Strategy boundary, address, time window, and non-goals.
- Data sources, schemas, timezone, filtering rules, and data-health counts.
- Market mechanics, payoff, settlement, fee and order-type assumptions.
- Observed performance by BTC interval, side, price band, and phase.
- 5m/15m live/shadow/disabled recommendation derived from ROI, q* margin, and data coverage.
- Inferred order lifecycle: start, stop, frequency, multi-fill order rate.
- Batch and ladder structure: one-side versus both-side batches, rank sizes, price offsets.
- Inventory and q*: formulas, dynamic q* anchors, final net correctness, qstar margin, final-net lock timing, net caps.
- Direction and alpha inference: with/against-current-advantage tables from BTCUSDT kline, streaks, what can be inferred from fills, what requires BTCUSDT orderbook, and the default model when kline/orderbook is available.
- Size/Kelly diagnostic: price buckets, discrete lot evidence, correlation caveat, and verdict.
- Deterministic replication config with concrete numbers derived from the wallet sample.
- Execution rules, sizing rules, risk controls, backtest/shadow/live gates.
- One worked market example from first order to final inventory.
- Known unknowns and a minimal rewrite checklist aligned to `$strategy-replication-auditor`.

## Evidence Rules

- Treat trade rows as facts.
- Treat inferred orders as proxies, not real order IDs.
- If maker/taker flags, cancellations, unfilled orders, L2 depth, or queue position are missing, say so and narrow the claim.
- If the wallet has too few resolved BTC Up/Down markets, produce a partial report and state the minimum additional data needed.
- Do not infer a live alpha source from settlement labels alone. Use settlement labels only as ex-post validation unless BTCUSDT kline/orderbook was joined.

## References

Read these only when needed:

- `references/pbot3_reverse_engineering_patterns.md`: PBot-3 derived analysis patterns and common traps.
- `references/pbot3_accumulation_report_contract.md`: minimum structure to beat the 2026-06-10 PBot-3 pixel replication template.
- `references/auditor_readiness_contract.md`: how to shape the report so `$strategy-replication-auditor` can score it above 85.

## Validation

After editing this skill, run:

```bash
python3 /Users/hfer/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  /Users/hfer/temp/my-skills/skills/polymarket-updown-strategy-replicator

python3 -m py_compile \
  /Users/hfer/temp/my-skills/skills/polymarket-updown-strategy-replicator/scripts/analyze_updown_strategy.py
```
