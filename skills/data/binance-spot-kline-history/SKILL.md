---
name: binance-spot-kline-history
description: Fetch Binance spot cryptocurrency historical kline/candlestick records for a symbol, interval, and UTC time range. Use when a user asks to download, backfill, export, sync, or collect Binance spot klines such as BTCUSDT 1s/1m history, especially when archives should be preferred before REST API fallback or Chinese prompts mention 币安现货K线, 历史K线, 指定时间间隔, 月存档, 日存档, API补齐.
---

# Binance Spot Kline History

## Purpose

Fetch source-backed Binance spot kline history for a requested symbol, kline interval, and UTC time window. Prefer public archive ZIP files first, in this order:

1. Monthly archive files.
2. Daily archive files for ranges not covered by monthly archives.
3. Spot REST API only for the remaining uncovered gaps.

This mirrors the archive-first catch-up pattern from `sync_btcusdt_spot_1s_kline_incremental.service.ts`, but keeps the workflow reusable for any Binance spot symbol and supported kline interval.

## Quick Start

Use the bundled script by default:

```bash
python3 /Users/hfer/temp/my-skills/skills/data/binance-spot-kline-history/scripts/fetch_binance_spot_klines.py \
  --symbol BTCUSDT \
  --interval 1s \
  --start 2024-01-01T00:00:00Z \
  --end 2024-01-01T00:10:00Z \
  --out btcusdt_1s_20240101_0010.csv
```

The script writes CSV by default with normalized millisecond timestamps, ISO timestamps, OHLCV fields, trade counts, taker buy fields, and a `source` column (`archive_monthly`, `archive_daily`, or `api`).

Use JSON Lines when downstream code wants one record per line:

```bash
python3 /Users/hfer/temp/my-skills/skills/data/binance-spot-kline-history/scripts/fetch_binance_spot_klines.py \
  --symbol ETHUSDT \
  --interval 1m \
  --start 2024-06-01 \
  --end 2024-06-02 \
  --format jsonl \
  --out ethusdt_1m_20240601.jsonl
```

## Required Workflow

1. **Collect request parameters.** Require `symbol`, `interval`, `start`, and `end`. Treat `start` as inclusive and `end` as exclusive. Use UTC ISO timestamps or `YYYY-MM-DD` dates.
2. **Run the bundled script.** Do not hand-roll archive URLs unless the script needs a targeted patch. It already applies the monthly -> daily -> API priority and de-duplicates by `open_time`.
3. **Check the summary.** Confirm the printed source counts and uncovered/API segments. If REST API was used for a large gap, mention that the range was not fully covered by public archives.
4. **Inspect a sample when quality matters.** Read the first and last few rows, confirm `open_time_iso` boundaries, and verify the row count is plausible for the interval.
5. **Report limitations.** State API rate-limit failures, missing archive files, or partial current candles. By default the script excludes not-yet-closed API candles; use `--include-open` only when the user explicitly wants the latest forming candle.

## CLI Notes

- `--symbol`: uppercase spot symbol such as `BTCUSDT`.
- `--interval`: Binance spot interval: `1s`, `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`, `3d`, `1w`, or `1M`.
- `--start`, `--end`: UTC range. Dates like `2024-06-01` mean midnight UTC.
- `--cache-dir`: optional archive ZIP cache. Defaults to a `.binance-kline-cache` folder next to the output file.
- `--format`: `csv`, `json`, or `jsonl`.
- `--include-open`: include the latest not-yet-closed API candle if Binance returns it.
- `--max-api-pages`: safety valve for very large API fallback ranges.

## Evidence Rules

- Prefer archive records over API records when both exist for the same `open_time`.
- Normalize archive timestamps longer than 13 digits by truncating to milliseconds before filtering or writing output.
- Keep `source` in exported rows so later analysis can distinguish archive-backed records from API-filled gaps.
- Do not claim a range is complete if the script exits non-zero, hits `--max-api-pages`, or reports API failures.
- For huge `1s` ranges, expect archive files to be much more efficient than API fallback; narrow the range or increase `--max-api-pages` only after estimating the number of candles.

## Reference

Read `references/binance_kline_sources.md` only when you need URL formats, field definitions, or source caveats.

## Validation

After editing this skill, run:

```bash
python3 /Users/hfer/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  /Users/hfer/temp/my-skills/skills/data/binance-spot-kline-history

python3 -m py_compile \
  /Users/hfer/temp/my-skills/skills/data/binance-spot-kline-history/scripts/fetch_binance_spot_klines.py
```
