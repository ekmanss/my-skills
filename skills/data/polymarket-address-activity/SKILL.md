---
name: polymarket-address-activity
description: Export complete Polymarket user activity for a wallet or profile address over a specified time range, especially TRADE rows, and optionally fetch Gamma market settlement results by eventSlug/slug. Use when the user asks to download, backfill, audit, or analyze Polymarket address trades, market outcomes, win/loss labels, or resolved settlement results for a time window.
---

# Polymarket Address Activity

Use this skill to produce reproducible address-level Polymarket activity exports with market settlement labels.

## Quick Start

Prefer the bundled script for real exports because the activity API has a hard offset cap and high-volume wallets require recursive time-window splitting.

```bash
python3 /path/to/polymarket-address-activity/scripts/export_polymarket_activity.py \
  --user 0x74a2b82f079e12bcc25cd0d479f17979fb62e32f \
  --start "2026-05-21 12:09:14" \
  --end "2026-05-28 12:09:14" \
  --timezone Asia/Shanghai \
  --out-dir trader-activitys/PBot-3 \
  --label PBot-3 \
  --settlements
```

If the user asks for "recent N days", use `--days N` instead of `--start/--end`.

```bash
python3 /path/to/polymarket-address-activity/scripts/export_polymarket_activity.py \
  --user 0x... \
  --days 7 \
  --out-dir trader-activitys/PBot-3 \
  --label PBot-3 \
  --settlements
```

## Workflow

1. Resolve the output directory from the user's request. Create it if needed.
2. Resolve the time window. Use explicit start/end when provided; otherwise use `--days`.
3. Run the script with `--settlements` unless the user only asks for raw activity.
4. Let the script split busy windows recursively when `/activity` reaches offset `3000`.
5. Report the generated CSV/JSON/metadata paths, row counts, unique market count, fetch errors, unresolved markets, and win/loss counts.

## Output Files

The script writes:

- Raw activity JSON/CSV plus metadata.
- Market settlements JSON/CSV when `--settlements` is used.
- Enriched activity JSON/CSV with `settlementStatus`, `winningOutcome`, `activityOutcomeResult`, `activityPayoutUSDC`, and `activityPnLUSDC`.

For trade exports, `activityOutcomeResult` is `WIN` when the row's `outcome` is one of the resolved winning outcomes, `LOSS` when the market resolved to another outcome, `OPEN` when the market is not closed, and `UNKNOWN` for fetch/parse problems.

## API Notes

Read [references/polymarket_activity_and_gamma.md](references/polymarket_activity_and_gamma.md) if you need to adjust parameters or debug API behavior.

Core rules:

- Data API endpoint: `https://data-api.polymarket.com/activity`
- Required activity parameter: `user=0x...`
- Use `type=TRADE` for trade-only exports.
- Use `limit=1000`, `sortBy=TIMESTAMP`, and `sortDirection=ASC`.
- Never assume offset pagination alone is complete for high-volume wallets; split the time range if a window fills offsets `0,1000,2000,3000`.
- Gamma endpoint: `https://gamma-api.polymarket.com/markets/slug/{eventSlug}`
- Settlement is resolved when `closed == true` and the parsed `outcomePrices` entry for an outcome equals `1`.

## Validation

After export, verify:

- JSON row count equals CSV data row count.
- All rows match the requested `proxyWallet` unless the user intentionally requested another activity type that can differ.
- `metadata.warnings` is empty, or report any capped one-second windows.
- Settlement `FETCH_ERROR`, `CLOSED_NO_PRICE_1`, and `CLOSED_UNPARSEABLE` counts are zero, or report them clearly.
