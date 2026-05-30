#!/usr/bin/env python3
"""Export Polymarket address activity and optional market settlements."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


DATA_API_URL = "https://data-api.polymarket.com/activity"
GAMMA_MARKET_BY_SLUG = "https://gamma-api.polymarket.com/markets/slug/{slug}"
DEFAULT_LIMIT = 1000
MAX_OFFSET = 3000
USER_AGENT = "codex-polymarket-address-activity/1.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export Polymarket activity by address and optionally enrich with Gamma market settlements."
    )
    parser.add_argument("--user", required=True, help="Polymarket profile/proxy wallet address, 0x + 40 hex chars.")
    parser.add_argument("--out-dir", required=True, help="Directory to write output files.")
    parser.add_argument("--label", default="", help="Human-readable filename prefix, e.g. PBot-3.")
    parser.add_argument("--timezone", default="Asia/Shanghai", help="Timezone for naive date strings and metadata.")
    parser.add_argument("--start", help="Start time, Unix seconds or ISO/local datetime string. Inclusive.")
    parser.add_argument("--end", help="End time, Unix seconds or ISO/local datetime string. Inclusive.")
    parser.add_argument("--days", type=float, help="Recent N days ending at now. Used when start/end are omitted.")
    parser.add_argument("--type", default="TRADE", help="Activity type filter, default TRADE. Use ALL for no type filter.")
    parser.add_argument("--side", choices=["BUY", "SELL", "buy", "sell"], help="Optional trade side filter.")
    parser.add_argument("--include-deposits-withdrawals", action="store_true", help="Set excludeDepositsWithdrawals=false.")
    parser.add_argument("--settlements", action="store_true", help="Fetch Gamma market settlements by eventSlug/slug.")
    parser.add_argument("--settlement-workers", type=int, default=16, help="Concurrent Gamma requests.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Activity API page size. Keep 1000 unless debugging.")
    parser.add_argument("--max-depth", type=int, default=32, help="Maximum recursive time-window split depth.")
    parser.add_argument("--dry-run", action="store_true", help="Print resolved configuration without calling APIs.")
    return parser.parse_args()


def validate_address(address: str) -> str:
    if not re.fullmatch(r"0x[a-fA-F0-9]{40}", address or ""):
        raise SystemExit(f"Invalid --user address: {address!r}")
    return address.lower()


def parse_time(value: str, tz: ZoneInfo) -> int:
    if re.fullmatch(r"\d+", value):
        return int(value)
    text = value.strip()
    if text.endswith("Z"):
        parsed = dt.datetime.fromisoformat(text[:-1] + "+00:00")
    else:
        parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return int(parsed.timestamp())


def resolve_window(args: argparse.Namespace, tz: ZoneInfo) -> tuple[int, int]:
    if args.start and args.end:
        start_ts = parse_time(args.start, tz)
        end_ts = parse_time(args.end, tz)
    elif args.days:
        end_ts = int(time.time())
        start_ts = end_ts - int(args.days * 24 * 3600)
    else:
        raise SystemExit("Provide either --start and --end, or --days.")
    if start_ts > end_ts:
        raise SystemExit("--start must be <= --end.")
    return start_ts, end_ts


def iso_utc(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def iso_local(ts: int, tz: ZoneInfo) -> str:
    return dt.datetime.fromtimestamp(ts, tz).isoformat()


def filename_time(ts: int, tz: ZoneInfo) -> str:
    return dt.datetime.fromtimestamp(ts, tz).strftime("%Y%m%d_%H%M%S")


def request_json(url: str, timeout: int = 30) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read())


class ActivityFetcher:
    def __init__(self, args: argparse.Namespace, user: str):
        self.args = args
        self.user = user
        self.requests_made: list[dict[str, Any]] = []
        self.warnings: list[str] = []

    def fetch_page(self, start: int, end: int, offset: int) -> list[dict[str, Any]]:
        params: dict[str, str] = {
            "user": self.user,
            "start": str(start),
            "end": str(end),
            "limit": str(self.args.limit),
            "offset": str(offset),
            "sortBy": "TIMESTAMP",
            "sortDirection": "ASC",
        }
        if self.args.type and self.args.type.upper() != "ALL":
            params["type"] = self.args.type
        if self.args.side:
            params["side"] = self.args.side.upper()
        if self.args.include_deposits_withdrawals:
            params["excludeDepositsWithdrawals"] = "false"
        url = DATA_API_URL + "?" + urllib.parse.urlencode(params)
        started = time.time()
        try:
            data = request_json(url)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Activity API HTTP {exc.code}: {body}") from exc
        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected activity response type: {type(data).__name__}")
        self.requests_made.append(
            {
                "start": start,
                "end": end,
                "offset": offset,
                "limit": self.args.limit,
                "count": len(data),
                "elapsed_ms": round((time.time() - started) * 1000),
            }
        )
        return data

    def fetch_window(self, start: int, end: int, depth: int = 0) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while offset <= MAX_OFFSET:
            page = self.fetch_page(start, end, offset)
            rows.extend(page)
            if len(page) < self.args.limit:
                return rows
            offset += self.args.limit

        if start >= end or depth >= self.args.max_depth:
            warning = (
                f"Window {start}-{end} ({iso_utc(start)} to {iso_utc(end)}) hit the activity offset cap; "
                "completeness cannot be proven."
            )
            self.warnings.append(warning)
            return rows

        mid = (start + end) // 2
        print(f"Window {iso_utc(start)}..{iso_utc(end)} hit offset cap; splitting at {iso_utc(mid)}", flush=True)
        return self.fetch_window(start, mid, depth + 1) + self.fetch_window(mid + 1, end, depth + 1)


def row_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("transactionHash", ""),
        row.get("asset", ""),
        row.get("timestamp"),
        row.get("type", ""),
        row.get("side", ""),
        row.get("price"),
        row.get("size"),
        row.get("usdcSize"),
        row.get("conditionId", ""),
        row.get("outcome", ""),
    )


def dedupe_and_sort(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        unique[row_key(row)] = row
    return sorted(unique.values(), key=lambda r: (r.get("timestamp", 0), r.get("transactionHash", ""), r.get("asset", "")))


def collect_fieldnames(rows: list[dict[str, Any]], extra: list[str] | None = None) -> list[str]:
    preferred = [
        "proxyWallet",
        "timestamp",
        "datetimeUtc",
        "datetimeLocal",
        "conditionId",
        "type",
        "side",
        "outcome",
        "outcomeIndex",
        "price",
        "size",
        "usdcSize",
        "transactionHash",
        "asset",
        "title",
        "slug",
        "eventSlug",
        "name",
        "pseudonym",
        "bio",
        "profileImage",
        "profileImageOptimized",
        "icon",
    ]
    fieldnames: list[str] = []
    seen: set[str] = set()
    for field in preferred + (extra or []):
        if field not in seen:
            fieldnames.append(field)
            seen.add(field)
    for row in rows:
        for field in row.keys():
            if field not in seen:
                fieldnames.append(field)
                seen.add(field)
    return fieldnames


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_activity_csv(path: Path, rows: list[dict[str, Any]], tz: ZoneInfo, extra_fields: list[str] | None = None) -> None:
    fieldnames = collect_fieldnames(rows, extra_fields)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            csv_row = dict(row)
            ts = row.get("timestamp")
            if isinstance(ts, int):
                csv_row["datetimeUtc"] = iso_utc(ts)
                csv_row["datetimeLocal"] = iso_local(ts, tz)
            writer.writerow(csv_row)


def parse_jsonish(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def price_to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def classify_market(data: dict[str, Any], slug: str) -> dict[str, Any]:
    outcomes = parse_jsonish(data.get("outcomes"))
    prices_raw = parse_jsonish(data.get("outcomePrices"))
    prices = [price_to_float(value) for value in prices_raw]
    closed = bool(data.get("closed"))
    winning: list[str] = []

    if closed and outcomes and len(outcomes) == len(prices):
        for outcome, price in zip(outcomes, prices):
            if not math.isnan(price) and abs(price - 1.0) <= 1e-9:
                winning.append(str(outcome))
        status = "RESOLVED" if winning else "CLOSED_NO_PRICE_1"
    elif closed:
        status = "CLOSED_UNPARSEABLE"
    else:
        status = "OPEN"

    return {
        "eventSlug": slug,
        "gammaMarketId": data.get("id"),
        "conditionId": data.get("conditionId"),
        "question": data.get("question"),
        "closed": closed,
        "settlementStatus": status,
        "winningOutcome": "|".join(winning),
        "winningOutcomeCount": len(winning),
        "outcomes": data.get("outcomes"),
        "outcomePrices": data.get("outcomePrices"),
        "endDate": data.get("endDate") or data.get("endDateIso"),
        "closedTime": data.get("closedTime"),
        "startDate": data.get("startDate") or data.get("startDateIso"),
        "lastTradePrice": data.get("lastTradePrice"),
        "volume": data.get("volume"),
        "volumeClob": data.get("volumeClob"),
        "active": data.get("active"),
        "archived": data.get("archived"),
        "apiError": "",
    }


def fetch_market(slug: str) -> dict[str, Any]:
    url = GAMMA_MARKET_BY_SLUG.format(slug=urllib.parse.quote(slug, safe=""))
    last_error = ""
    for attempt in range(5):
        try:
            data = request_json(url, timeout=25)
            if not isinstance(data, dict):
                raise RuntimeError(f"Unexpected Gamma response type: {type(data).__name__}")
            return classify_market(data, slug)
        except Exception as exc:  # noqa: BLE001 - keep retry details in output metadata.
            last_error = repr(exc)
            time.sleep(min(0.5 * (2**attempt), 5.0))
    return {
        "eventSlug": slug,
        "gammaMarketId": "",
        "conditionId": "",
        "question": "",
        "closed": "",
        "settlementStatus": "FETCH_ERROR",
        "winningOutcome": "",
        "winningOutcomeCount": 0,
        "outcomes": "",
        "outcomePrices": "",
        "endDate": "",
        "closedTime": "",
        "startDate": "",
        "lastTradePrice": "",
        "volume": "",
        "volumeClob": "",
        "active": "",
        "archived": "",
        "apiError": last_error,
    }


def fetch_settlements(slugs: list[str], workers: int) -> list[dict[str, Any]]:
    settlements: list[dict[str, Any]] = []
    started = time.time()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(fetch_market, slug): slug for slug in slugs}
        for count, future in enumerate(as_completed(futures), start=1):
            settlements.append(future.result())
            if count % 250 == 0 or count == len(slugs):
                print(f"Fetched {count}/{len(slugs)} Gamma markets in {time.time() - started:.1f}s", flush=True)
    return sorted(settlements, key=lambda row: row["eventSlug"])


def enrich_rows(rows: list[dict[str, Any]], settlements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_slug = {row["eventSlug"]: row for row in settlements}
    enriched: list[dict[str, Any]] = []
    for row in rows:
        slug = row.get("eventSlug") or row.get("slug") or ""
        settlement = by_slug.get(slug, {})
        winning = [value for value in (settlement.get("winningOutcome") or "").split("|") if value]
        status = settlement.get("settlementStatus") or "MISSING_SETTLEMENT"
        outcome = row.get("outcome")
        if status == "RESOLVED":
            result = "WIN" if outcome in winning else "LOSS"
        elif status == "OPEN":
            result = "OPEN"
        else:
            result = "UNKNOWN"

        payout = None
        pnl = None
        if str(row.get("side", "")).upper() == "BUY" and result in {"WIN", "LOSS"}:
            payout = float(row.get("size") or 0) if result == "WIN" else 0.0
            pnl = payout - float(row.get("usdcSize") or 0)

        new_row = dict(row)
        new_row.update(
            {
                "settlementStatus": status,
                "marketClosed": settlement.get("closed"),
                "winningOutcome": settlement.get("winningOutcome"),
                "activityOutcomeResult": result,
                "activityPayoutUSDC": payout,
                "activityPnLUSDC": pnl,
                "gammaMarketId": settlement.get("gammaMarketId"),
                "marketEndDate": settlement.get("endDate"),
                "marketClosedTime": settlement.get("closedTime"),
                "marketOutcomePrices": settlement.get("outcomePrices"),
            }
        )
        enriched.append(new_row)
    return enriched


def add_market_trade_aggregates(settlements: list[dict[str, Any]], rows: list[dict[str, Any]]) -> None:
    trade_counts = Counter((row.get("eventSlug") or row.get("slug") or "") for row in rows)
    usdc_by_slug: defaultdict[str, float] = defaultdict(float)
    size_by_slug: defaultdict[str, float] = defaultdict(float)
    win_counts: Counter[str] = Counter()
    loss_counts: Counter[str] = Counter()
    pnl_by_slug: defaultdict[str, float] = defaultdict(float)
    for row in rows:
        slug = row.get("eventSlug") or row.get("slug") or ""
        usdc_by_slug[slug] += float(row.get("usdcSize") or 0)
        size_by_slug[slug] += float(row.get("size") or 0)
        if row.get("activityOutcomeResult") == "WIN":
            win_counts[slug] += 1
        elif row.get("activityOutcomeResult") == "LOSS":
            loss_counts[slug] += 1
        if row.get("activityPnLUSDC") is not None:
            pnl_by_slug[slug] += float(row.get("activityPnLUSDC") or 0)
    for settlement in settlements:
        slug = settlement["eventSlug"]
        settlement["activityCount"] = trade_counts[slug]
        settlement["activityUsdcSize"] = round(usdc_by_slug[slug], 12)
        settlement["activitySize"] = round(size_by_slug[slug], 12)
        settlement["winActivityCount"] = win_counts[slug]
        settlement["lossActivityCount"] = loss_counts[slug]
        settlement["activityPnLUSDC"] = round(pnl_by_slug[slug], 12)


def write_settlement_csv(path: Path, settlements: list[dict[str, Any]]) -> None:
    fieldnames = [
        "eventSlug",
        "gammaMarketId",
        "conditionId",
        "question",
        "closed",
        "settlementStatus",
        "winningOutcome",
        "winningOutcomeCount",
        "outcomes",
        "outcomePrices",
        "endDate",
        "closedTime",
        "startDate",
        "lastTradePrice",
        "volume",
        "volumeClob",
        "active",
        "archived",
        "activityCount",
        "activityUsdcSize",
        "activitySize",
        "winActivityCount",
        "lossActivityCount",
        "activityPnLUSDC",
        "apiError",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(settlements)


def main() -> int:
    args = parse_args()
    if args.limit < 1 or args.limit > DEFAULT_LIMIT:
        raise SystemExit("--limit must be between 1 and 1000; larger values can cause incomplete offset paging.")
    user = validate_address(args.user)
    tz = ZoneInfo(args.timezone)
    start_ts, end_ts = resolve_window(args, tz)
    out_dir = Path(args.out_dir).expanduser().resolve()
    label = re.sub(r"[^A-Za-z0-9_.-]+", "-", args.label.strip()).strip("-") if args.label else "polymarket"
    prefix = f"{label}_{user}_activity_{filename_time(start_ts, tz)}_to_{filename_time(end_ts, tz)}"

    config = {
        "user": user,
        "start": start_ts,
        "end": end_ts,
        "startLocal": iso_local(start_ts, tz),
        "endLocal": iso_local(end_ts, tz),
        "outDir": str(out_dir),
        "type": args.type,
        "settlements": args.settlements,
    }
    if args.dry_run:
        print(json.dumps(config, ensure_ascii=False, indent=2))
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)

    fetcher = ActivityFetcher(args, user)
    raw_rows = fetcher.fetch_window(start_ts, end_ts)
    rows = dedupe_and_sort(raw_rows)

    activity_json = out_dir / f"{prefix}.json"
    activity_csv = out_dir / f"{prefix}.csv"
    activity_metadata = out_dir / f"{prefix}.metadata.json"
    write_json(activity_json, rows)
    write_activity_csv(activity_csv, rows, tz)

    summary: dict[str, Any] = {
        **config,
        "generatedAtLocal": dt.datetime.now(tz).isoformat(timespec="seconds"),
        "generatedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "rowCount": len(rows),
        "rawRowsBeforeDedupe": len(raw_rows),
        "deduplicatedRowsRemoved": len(raw_rows) - len(rows),
        "requestsMade": fetcher.requests_made,
        "warnings": fetcher.warnings,
        "aggregate": {
            "totalSize": round(sum(float(row.get("size") or 0) for row in rows), 12),
            "totalUsdcSize": round(sum(float(row.get("usdcSize") or 0) for row in rows), 12),
            "sideCounts": dict(Counter(str(row.get("side", "")) for row in rows)),
        },
        "files": {
            "activityJson": str(activity_json),
            "activityCsv": str(activity_csv),
            "activityMetadata": str(activity_metadata),
        },
    }

    if rows:
        first_ts = rows[0].get("timestamp")
        last_ts = rows[-1].get("timestamp")
        if isinstance(first_ts, int):
            summary["firstActivityUtc"] = iso_utc(first_ts)
        if isinstance(last_ts, int):
            summary["lastActivityUtc"] = iso_utc(last_ts)

    if args.settlements:
        slugs = sorted({row.get("eventSlug") or row.get("slug") for row in rows if row.get("eventSlug") or row.get("slug")})
        settlements = fetch_settlements(slugs, args.settlement_workers)
        enriched = enrich_rows(rows, settlements)
        add_market_trade_aggregates(settlements, enriched)

        settlement_prefix = f"{label}_market_settlements_{filename_time(start_ts, tz)}_to_{filename_time(end_ts, tz)}"
        settlement_json = out_dir / f"{settlement_prefix}.json"
        settlement_csv = out_dir / f"{settlement_prefix}.csv"
        enriched_json = out_dir / f"{prefix}_with_settlements.json"
        enriched_csv = out_dir / f"{prefix}_with_settlements.csv"

        write_json(settlement_json, settlements)
        write_settlement_csv(settlement_csv, settlements)
        write_json(enriched_json, enriched)
        write_activity_csv(
            enriched_csv,
            enriched,
            tz,
            extra_fields=[
                "settlementStatus",
                "marketClosed",
                "winningOutcome",
                "activityOutcomeResult",
                "activityPayoutUSDC",
                "activityPnLUSDC",
                "gammaMarketId",
                "marketEndDate",
                "marketClosedTime",
                "marketOutcomePrices",
            ],
        )

        status_counts = Counter(row.get("settlementStatus") for row in settlements)
        result_counts = Counter(row.get("activityOutcomeResult") for row in enriched)
        summary["settlements"] = {
            "uniqueMarketCount": len(slugs),
            "settlementStatusCounts": dict(status_counts),
            "activityResultCounts": dict(result_counts),
            "fetchErrorCount": status_counts.get("FETCH_ERROR", 0),
            "unresolvedOrUnparseableCount": sum(
                status_counts.get(key, 0) for key in ["CLOSED_NO_PRICE_1", "CLOSED_UNPARSEABLE"]
            ),
            "aggregateActivityPayoutUSDC": round(sum(float(row.get("activityPayoutUSDC") or 0) for row in enriched), 12),
            "aggregateActivityPnLUSDC": round(sum(float(row.get("activityPnLUSDC") or 0) for row in enriched), 12),
            "logic": "closed=true and outcomePrices price 1 marks the matching outcome as winning.",
        }
        summary["files"].update(
            {
                "marketSettlementsJson": str(settlement_json),
                "marketSettlementsCsv": str(settlement_csv),
                "enrichedActivityJson": str(enriched_json),
                "enrichedActivityCsv": str(enriched_csv),
            }
        )

    write_json(activity_metadata, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130)
