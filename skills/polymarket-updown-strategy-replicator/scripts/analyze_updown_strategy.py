#!/usr/bin/env python3
"""Analyze a Polymarket wallet's BTC Up/Down trades and write a replication report."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo


ASSET_ALIASES = {
    "btc": ("btc", "bitcoin"),
}
INTERVAL_SECONDS = {
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}
PHASE_BINS = [
    (0.00, 0.10, "0-10%"),
    (0.10, 0.20, "10-20%"),
    (0.20, 0.40, "20-40%"),
    (0.40, 0.60, "40-60%"),
    (0.60, 0.80, "60-80%"),
    (0.80, 0.95, "80-95%"),
    (0.95, 1.01, "95-100%"),
]
PRICE_BANDS = [
    (0.00, 0.25, "0-0.25"),
    (0.25, 0.40, "0.25-0.40"),
    (0.40, 0.47, "0.40-0.47"),
    (0.47, 0.49, "0.47-0.49"),
    (0.49, 0.51, "0.49-0.51"),
    (0.51, 0.65, "0.51-0.65"),
    (0.65, 0.85, "0.65-0.85"),
    (0.85, 1.01, "0.85-1.00"),
]
DEFAULT_ORDER_GAP_SEC = 5
DEFAULT_BATCH_GAP_SEC = 5
EPS = 1e-12
GAMMA_MARKET_BY_SLUG = "https://gamma-api.polymarket.com/markets/slug/{slug}"
USER_AGENT = "codex-polymarket-updown-strategy-replicator/1.0"


@dataclass
class Trade:
    row_id: int
    timestamp: int
    dt_utc: dt.datetime
    slug: str
    title: str
    asset: str
    interval: str
    market_start: int | None
    market_end: int | None
    outcome: str
    side: str
    price: float
    size: float
    usdc: float
    result: str
    winning_outcome: str
    payout: float | None
    pnl: float | None
    tx_hash: str
    btc_open: float | None
    btc_trade_close: float | None
    current_advantage: str
    advantage_relation: str
    raw: dict[str, Any]

    @property
    def price_level(self) -> float:
        return self.price

    @property
    def elapsed_sec(self) -> float | None:
        if self.market_start is None:
            return None
        return float(self.timestamp - self.market_start)

    @property
    def seconds_before_close(self) -> float | None:
        if self.market_end is None:
            return None
        return float(self.market_end - self.timestamp)

    @property
    def elapsed_frac(self) -> float | None:
        if self.market_start is None or self.market_end is None or self.market_end <= self.market_start:
            return None
        return (self.timestamp - self.market_start) / (self.market_end - self.market_start)


@dataclass
class InferredOrder:
    order_id: int
    market: str
    asset: str
    interval: str
    outcome: str
    side: str
    price_level: float
    first_ts: int
    last_ts: int
    fill_count: int
    shares: float
    cost: float
    payout: float
    pnl: float
    result_counts: Counter[str]
    winning_outcome: str
    market_start: int | None
    market_end: int | None
    current_advantage: str
    advantage_relation: str

    @property
    def duration_sec(self) -> int:
        return int(self.last_ts - self.first_ts)

    @property
    def avg_price(self) -> float:
        return safe_div(self.cost, self.shares)

    @property
    def elapsed_sec(self) -> float | None:
        if self.market_start is None:
            return None
        return float(self.first_ts - self.market_start)

    @property
    def seconds_before_close(self) -> float | None:
        if self.market_end is None:
            return None
        return float(self.market_end - self.last_ts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", help="Polymarket wallet/profile address. Required unless --input is given.")
    parser.add_argument("--input", help="Existing activity CSV, preferably *_with_settlements.csv.")
    parser.add_argument("--days", type=float, default=30.0, help="Recent N days when exporting. Default 30.")
    parser.add_argument("--start", help="Optional export start time.")
    parser.add_argument("--end", help="Optional export end time.")
    parser.add_argument("--timezone", default="Asia/Shanghai")
    parser.add_argument("--out-dir", default="strategy-replication-audits")
    parser.add_argument("--label", default="")
    parser.add_argument("--env-file", default="", help="Optional .env file for DATABASE_URL style settings.")
    parser.add_argument("--export-script", help="Path to export_polymarket_activity.py.")
    parser.add_argument(
        "--export-chunk-hours",
        type=float,
        default=6.0,
        help="Export recent/address data in external chunks before merging. Default 6 hours.",
    )
    parser.add_argument(
        "--export-workers",
        type=int,
        default=4,
        help="Concurrent raw export chunks. Settlement enrichment still runs after merge. Default 4.",
    )
    parser.add_argument(
        "--export-retries",
        type=int,
        default=3,
        help="Retries per raw export chunk before failing the run. Default 3.",
    )
    parser.add_argument(
        "--export-limit",
        type=int,
        default=500,
        help="Activity API page size passed to the exporter. Lower values reduce timeout risk. Default 500.",
    )
    parser.add_argument(
        "--max-settlement-markets",
        type=int,
        default=5000,
        help="Maximum unique BTC market slugs to enrich through Gamma, ranked by traded cost. Use 0 for all. Default 5000.",
    )
    parser.add_argument("--binance-kline-script", default="", help="Path to fetch_binance_spot_klines.py.")
    parser.add_argument("--binance-kline-csv", default="", help="Existing BTCUSDT kline CSV from binance-spot-kline-history.")
    parser.add_argument("--fetch-binance-klines", action="store_true", help="Fetch BTCUSDT klines for the activity window before enrichment.")
    parser.add_argument("--binance-kline-interval", default="1s", help="Binance kline interval. Default 1s.")
    parser.add_argument("--binance-kline-cache-dir", default="", help="Optional cache directory passed to the Binance kline fetcher.")
    parser.add_argument("--binance-max-api-pages", type=int, default=0, help="Optional --max-api-pages passed to the Binance kline fetcher.")
    parser.add_argument("--single-export", action="store_true", help="Disable external chunking and call exporter once.")
    parser.add_argument("--order-gap-sec", type=int, default=DEFAULT_ORDER_GAP_SEC)
    parser.add_argument("--batch-gap-sec", type=int, default=DEFAULT_BATCH_GAP_SEC)
    parser.add_argument("--price-decimals", type=int, default=3)
    parser.add_argument("--min-report-markets", type=int, default=10)
    parser.add_argument("--skip-export", action="store_true", help="Require --input and never call the activity exporter.")
    return parser.parse_args()


def safe_div(num: float, den: float) -> float:
    return float(num / den) if den else math.nan


def clean_float(value: Any, default: float = math.nan) -> float:
    try:
        if value in ("", None):
            return default
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def clean_int(value: Any) -> int | None:
    try:
        if value in ("", None):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def parse_datetime_to_ts(value: Any) -> int | None:
    if value in ("", None):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return int(float(text))
    try:
        if text.endswith("Z"):
            parsed = dt.datetime.fromisoformat(text[:-1] + "+00:00")
        else:
            parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return int(parsed.timestamp())


def percentile(values: Iterable[float], q: float) -> float:
    clean = sorted(v for v in values if v is not None and math.isfinite(float(v)))
    if not clean:
        return math.nan
    if len(clean) == 1:
        return float(clean[0])
    pos = (len(clean) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(clean[lo])
    weight = pos - lo
    return float(clean[lo] * (1 - weight) + clean[hi] * weight)


def median(values: Iterable[float]) -> float:
    clean = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return float(statistics.median(clean)) if clean else math.nan


def fmt_num(value: Any, digits: int = 2) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not math.isfinite(x):
        return "n/a"
    return f"{x:,.{digits}f}"


def fmt_int(value: Any) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not math.isfinite(x):
        return "n/a"
    return f"{int(round(x)):,}"


def fmt_pct(value: Any, digits: int = 2) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not math.isfinite(x):
        return "n/a"
    return f"{x * 100:.{digits}f}%"


def markdown_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]], max_rows: int = 30) -> str:
    if not rows:
        return "_No rows._"
    lines = [
        "| " + " | ".join(label for _, label in columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows[:max_rows]:
        cells: list[str] = []
        for key, _ in columns:
            value = row.get(key, "")
            if (
                key.endswith("_rate")
                or key.endswith("_share")
                or key.endswith("_frac")
                or key.endswith("_fraction")
                or key in {"roi", "cost_share", "order_share", "qstar_margin", "top_lot_order_share"}
            ):
                cells.append(fmt_pct(value))
            elif key.endswith("_cost") or key in {"cost", "pnl", "payout", "median_cost", "p95_cost", "p99_cost"}:
                cells.append(fmt_num(value))
            elif key.endswith("_shares") or key in {"shares", "median_shares", "p95_shares", "abs_net"}:
                cells.append(fmt_num(value))
            elif isinstance(value, float):
                cells.append(fmt_num(value, 4))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                fields.append(key)
                seen.add(key)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def infer_asset_and_interval(slug: str, title: str) -> tuple[str, str]:
    target = f"{slug} {title}".lower()
    asset = ""
    for canonical, aliases in ASSET_ALIASES.items():
        if any(re.search(rf"(^|[^a-z0-9]){re.escape(alias)}([^a-z0-9]|$)", target) for alias in aliases):
            asset = canonical.upper()
            break
    interval = ""
    match = re.search(r"(?<![a-z0-9])(5m|15m|1h|4h|1d)(?![a-z0-9])", target)
    if match:
        interval = match.group(1)
    elif re.search(r"\bup or down\b\s*-\s*[A-Za-z]+\s+\d{1,2},\s*\d{1,2}(?::\d{2})?\s*(?:AM|PM)\s*ET\b", title, re.IGNORECASE):
        interval = "1h"
    return asset, interval


def is_btc_updown(slug: str, title: str) -> bool:
    target = f"{slug} {title}".lower()
    has_asset = any(alias in target for aliases in ASSET_ALIASES.values() for alias in aliases)
    has_updown = (
        "updown" in target
        or "up-or-down" in target
        or "up or down" in target
        or (" up " in f" {target} " and " down " in f" {target} ")
        or "higher or lower" in target
    )
    return has_asset and has_updown


def slug_market_start(slug: str) -> int | None:
    match = re.search(r"-(\d{10})(?:$|[^0-9])", slug or "")
    return int(match.group(1)) if match else None


def canonical_outcome(value: str) -> str:
    text = str(value or "").strip()
    low = text.lower()
    if low in {"up", "yes", "higher"}:
        return "Up"
    if low in {"down", "no", "lower"}:
        return "Down"
    return text.title() if text else ""


def resolve_export_script(provided: str | None) -> Path:
    candidates: list[Path] = []
    if provided:
        candidates.append(Path(provided).expanduser())
    here = Path(__file__).resolve()
    candidates.extend(
        [
            here.parents[2] / "data/polymarket-address-activity/scripts/export_polymarket_activity.py",
            Path.home() / ".codex/skills/polymarket-address-activity/scripts/export_polymarket_activity.py",
            Path("/Users/hfer/temp/my-skills/skills/data/polymarket-address-activity/scripts/export_polymarket_activity.py"),
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SystemExit("Could not find export_polymarket_activity.py; pass --export-script or --input.")


def resolve_binance_kline_script(provided: str | None) -> Path | None:
    candidates: list[Path] = []
    if provided:
        candidates.append(Path(provided).expanduser())
    here = Path(__file__).resolve()
    candidates.extend(
        [
            here.parents[2] / "data/binance-spot-kline-history/scripts/fetch_binance_spot_klines.py",
            Path("/Users/hfer/temp/my-skills/skills/data/binance-spot-kline-history/scripts/fetch_binance_spot_klines.py"),
            Path.home() / ".codex/skills/binance-spot-kline-history/scripts/fetch_binance_spot_klines.py",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def parse_local_or_epoch(value: str, timezone: str) -> int:
    if re.fullmatch(r"\d+(\.\d+)?", str(value).strip()):
        return int(float(value))
    text = str(value).strip()
    if text.endswith("Z"):
        parsed = dt.datetime.fromisoformat(text[:-1] + "+00:00")
    else:
        parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone))
    return int(parsed.timestamp())


def resolve_export_window(args: argparse.Namespace) -> tuple[int, int]:
    if args.start and args.end:
        start = parse_local_or_epoch(args.start, args.timezone)
        end = parse_local_or_epoch(args.end, args.timezone)
    else:
        end = int(time.time())
        start = end - int(float(args.days) * 86400)
    if start > end:
        raise SystemExit("--start must be <= --end.")
    return start, end


def load_env_file(path_text: str) -> None:
    if not path_text:
        return
    path = Path(path_text).expanduser()
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def run_exporter(
    script: Path,
    args: argparse.Namespace,
    user: str,
    out_dir: Path,
    label: str,
    start: int,
    end: int,
    *,
    settlements: bool,
) -> Path | None:
    cmd = [
        sys.executable,
        str(script),
        "--user",
        user,
        "--out-dir",
        str(out_dir),
        "--label",
        label,
        "--timezone",
        args.timezone,
        "--start",
        str(start),
        "--end",
        str(end),
    ]
    if settlements:
        cmd.insert(cmd.index("--start"), "--settlements")
    if args.export_limit:
        cmd.extend(["--limit", str(int(args.export_limit))])
    print(
        f"Export chunk {label}: {dt.datetime.fromtimestamp(start, dt.timezone.utc).isoformat()} -> "
        f"{dt.datetime.fromtimestamp(end, dt.timezone.utc).isoformat()}",
        flush=True,
    )
    log_dir = out_dir / "_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    run: subprocess.CompletedProcess[str] | None = None
    attempts = max(1, int(args.export_retries))
    for attempt in range(1, attempts + 1):
        run = subprocess.run(cmd, text=True, capture_output=True, check=False)
        suffix = "" if attempt == attempts else f".attempt{attempt}"
        (log_dir / f"{label}{suffix}.stdout.txt").write_text(run.stdout, encoding="utf-8")
        (log_dir / f"{label}{suffix}.stderr.txt").write_text(run.stderr, encoding="utf-8")
        if run.returncode == 0:
            break
        if attempt < attempts:
            delay = min(2.0 * attempt, 10.0)
            print(f"Retrying export chunk {label} after exit {run.returncode}; attempt {attempt + 1}/{attempts}", flush=True)
            time.sleep(delay)
    if run is None or run.returncode != 0:
        if run is not None:
            sys.stderr.write(run.stdout)
            sys.stderr.write(run.stderr)
        raise SystemExit(f"Activity export chunk {label} failed after {attempts} attempts")
    if settlements:
        candidates = sorted(out_dir.glob(f"{label}_*_with_settlements.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    else:
        candidates = sorted(
            [
                p
                for p in out_dir.glob(f"{label}_*.csv")
                if "_with_settlements" not in p.name and "market_settlements" not in p.name
            ],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    if not candidates:
        pattern = "*_with_settlements.csv" if settlements else "*.csv"
        candidates = sorted(out_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def activity_row_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("transactionHash", ""),
        row.get("asset", ""),
        row.get("timestamp", ""),
        row.get("type", ""),
        row.get("side", ""),
        row.get("price", ""),
        row.get("size", ""),
        row.get("usdcSize", ""),
        row.get("conditionId", ""),
        row.get("outcome", ""),
    )


def merge_activity_csvs(paths: list[Path], output: Path) -> Path:
    fieldnames: list[str] = []
    seen_fields: set[str] = set()
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for path in paths:
        with path.open(newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for field in reader.fieldnames or []:
                if field not in seen_fields:
                    fieldnames.append(field)
                    seen_fields.add(field)
            for row in reader:
                unique[activity_row_key(row)] = row
    rows = sorted(unique.values(), key=lambda r: (clean_int(r.get("timestamp")) or 0, r.get("transactionHash", ""), r.get("asset", "")))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return output


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


def request_json(url: str, timeout: int = 25) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read())


def classify_gamma_market(data: dict[str, Any], slug: str) -> dict[str, Any]:
    outcomes = [str(x) for x in parse_jsonish(data.get("outcomes"))]
    prices = [clean_float(x, math.nan) for x in parse_jsonish(data.get("outcomePrices"))]
    closed = bool(data.get("closed"))
    winning: list[str] = []
    if closed and outcomes and len(outcomes) == len(prices):
        for outcome, price in zip(outcomes, prices):
            if math.isfinite(price) and abs(price - 1.0) <= 1e-9:
                winning.append(outcome)
        status = "RESOLVED" if winning else "CLOSED_NO_PRICE_1"
    elif closed:
        status = "CLOSED_UNPARSEABLE"
    else:
        status = "OPEN"
    return {
        "eventSlug": slug,
        "gammaMarketId": data.get("id", ""),
        "closed": closed,
        "settlementStatus": status,
        "winningOutcome": "|".join(winning),
        "outcomes": data.get("outcomes", ""),
        "outcomePrices": data.get("outcomePrices", ""),
        "endDate": data.get("endDate") or data.get("endDateIso") or "",
        "closedTime": data.get("closedTime") or "",
        "apiError": "",
    }


def fetch_gamma_market(slug: str) -> dict[str, Any]:
    url = GAMMA_MARKET_BY_SLUG.format(slug=urllib.parse.quote(slug, safe=""))
    last_error = ""
    for attempt in range(5):
        try:
            data = request_json(url)
            if not isinstance(data, dict):
                raise RuntimeError(f"Unexpected Gamma response type: {type(data).__name__}")
            return classify_gamma_market(data, slug)
        except Exception as exc:  # noqa: BLE001 - keep retry details in metadata.
            last_error = repr(exc)
            time.sleep(min(0.5 * (2**attempt), 5.0))
    return {
        "eventSlug": slug,
        "gammaMarketId": "",
        "closed": "",
        "settlementStatus": "FETCH_ERROR",
        "winningOutcome": "",
        "outcomes": "",
        "outcomePrices": "",
        "endDate": "",
        "closedTime": "",
        "apiError": last_error,
    }


def fetch_settlements_once(slugs: list[str], workers: int = 16) -> dict[str, dict[str, Any]]:
    settlements: dict[str, dict[str, Any]] = {}
    if not slugs:
        return settlements
    started = time.time()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        future_by_slug = {pool.submit(fetch_gamma_market, slug): slug for slug in slugs}
        for idx, future in enumerate(as_completed(future_by_slug), start=1):
            row = future.result()
            settlements[row["eventSlug"]] = row
            if idx % 250 == 0 or idx == len(slugs):
                print(f"Fetched {idx}/{len(slugs)} unique Gamma markets in {time.time() - started:.1f}s", flush=True)
    return settlements


def parse_btc_updown_window(row: dict[str, Any]) -> tuple[int, int] | None:
    slug = row.get("eventSlug") or row.get("slug") or ""
    title = row.get("title") or row.get("question") or row.get("name") or ""
    text = f"{slug} {title}".lower()
    if "btc" not in text and "bitcoin" not in text:
        return None
    if not is_btc_updown(slug, title):
        return None
    match = re.search(r"btc-updown-(5m|15m|1h|4h)-(\d{10})", slug)
    if match:
        interval = match.group(1)
        start = int(match.group(2))
        return start, start + INTERVAL_SECONDS[interval]

    title_match = re.search(
        r"bitcoin up or down\s*-\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s*ET",
        title,
        flags=re.IGNORECASE,
    )
    if not title_match:
        return None
    month_name, day_text, hour_text, minute_text, ampm = title_match.groups()
    month_lookup = {
        name.lower(): idx
        for idx, name in enumerate(
            ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
            start=1,
        )
    }
    month = month_lookup.get(month_name.lower())
    if not month:
        return None
    timestamp = clean_int(row.get("timestamp"))
    if timestamp is None:
        return None
    year = dt.datetime.fromtimestamp(timestamp, ZoneInfo("America/New_York")).year
    hour = int(hour_text)
    minute = int(minute_text or 0)
    if ampm.upper() == "PM" and hour != 12:
        hour += 12
    if ampm.upper() == "AM" and hour == 12:
        hour = 0
    start_dt = dt.datetime(year, month, int(day_text), hour, minute, tzinfo=ZoneInfo("America/New_York"))
    start = int(start_dt.timestamp())
    return start, start + 3600


def parse_title_updown_window(row: dict[str, Any]) -> tuple[int, int] | None:
    title = row.get("title") or row.get("question") or row.get("name") or ""
    title_match = re.search(
        r"\bup or down\b\s*-\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s*ET\b",
        title,
        flags=re.IGNORECASE,
    )
    if not title_match:
        return None
    month_name, day_text, hour_text, minute_text, ampm = title_match.groups()
    month_lookup = {
        name.lower(): idx
        for idx, name in enumerate(
            ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
            start=1,
        )
    }
    month = month_lookup.get(month_name.lower())
    timestamp = clean_int(row.get("timestamp"))
    if not month or timestamp is None:
        return None
    year = dt.datetime.fromtimestamp(timestamp, ZoneInfo("America/New_York")).year
    hour = int(hour_text)
    minute = int(minute_text or 0)
    if ampm.upper() == "PM" and hour != 12:
        hour += 12
    if ampm.upper() == "AM" and hour == 12:
        hour = 0
    start_dt = dt.datetime(year, month, int(day_text), hour, minute, tzinfo=ZoneInfo("America/New_York"))
    start = int(start_dt.timestamp())
    return start, start + 3600


def utc_arg(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def btc_kline_window(rows: list[dict[str, Any]]) -> tuple[int, int] | None:
    starts: list[int] = []
    ends: list[int] = []
    fallback_timestamps: list[int] = []
    for row in rows:
        timestamp = clean_int(row.get("timestamp")) or parse_datetime_to_ts(row.get("datetimeUtc"))
        if timestamp is not None:
            fallback_timestamps.append(timestamp)
        parsed = parse_btc_updown_window(row)
        if parsed:
            start, end = parsed
            starts.append(start)
            ends.append(end)
    if starts and ends:
        return max(0, min(starts) - 60), max(ends) + 60
    if fallback_timestamps:
        return max(0, min(fallback_timestamps) - 3600), max(fallback_timestamps) + 3600
    return None


def prepare_binance_kline_csv(activity_csv: Path, args: argparse.Namespace, out_dir: Path) -> Path | None:
    if args.binance_kline_csv:
        path = Path(args.binance_kline_csv).expanduser().resolve()
        if not path.exists():
            raise SystemExit(f"--binance-kline-csv does not exist: {path}")
        return path
    if not args.fetch_binance_klines:
        return None
    script = resolve_binance_kline_script(args.binance_kline_script)
    if script is None:
        raise SystemExit("Could not find fetch_binance_spot_klines.py; pass --binance-kline-script or --binance-kline-csv.")
    with activity_csv.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    window = btc_kline_window(rows)
    if window is None:
        print("Skipping Binance kline fetch because no BTC Up/Down window was found.", flush=True)
        return None
    start, end = window
    kline_dir = out_dir / "binance_klines"
    kline_dir.mkdir(parents=True, exist_ok=True)
    output = kline_dir / (
        f"BTCUSDT_{args.binance_kline_interval}_{dt.datetime.fromtimestamp(start, dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_"
        f"{dt.datetime.fromtimestamp(end, dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv"
    )
    cmd = [
        sys.executable,
        str(script),
        "--symbol",
        "BTCUSDT",
        "--interval",
        args.binance_kline_interval,
        "--start",
        utc_arg(start),
        "--end",
        utc_arg(end),
        "--out",
        str(output),
    ]
    if args.binance_kline_cache_dir:
        cmd.extend(["--cache-dir", str(Path(args.binance_kline_cache_dir).expanduser())])
    if args.binance_max_api_pages:
        cmd.extend(["--max-api-pages", str(args.binance_max_api_pages)])
    print(f"Fetching Binance BTCUSDT {args.binance_kline_interval} klines: {utc_arg(start)} -> {utc_arg(end)}", flush=True)
    run = subprocess.run(cmd, text=True, capture_output=True, check=False)
    log_dir = out_dir / "_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "binance_kline_fetch.stdout.txt").write_text(run.stdout, encoding="utf-8")
    (log_dir / "binance_kline_fetch.stderr.txt").write_text(run.stderr, encoding="utf-8")
    if run.returncode != 0:
        sys.stderr.write(run.stdout)
        sys.stderr.write(run.stderr)
        raise SystemExit(f"Binance kline fetch failed with exit {run.returncode}")
    return output


def load_binance_1s_candles(kline_csv: Path, timestamps: list[int]) -> dict[int, dict[str, float]]:
    if not kline_csv or not timestamps:
        return {}
    wanted = set(timestamps)
    candles: dict[int, dict[str, float]] = {}
    with kline_csv.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            open_time = clean_int(row.get("open_time"))
            if open_time is None:
                continue
            ts = open_time // 1000 if open_time > 10_000_000_000 else open_time
            if ts not in wanted:
                continue
            candles[ts] = {
                "open": clean_float(row.get("open"), math.nan),
                "close": clean_float(row.get("close"), math.nan),
            }
            if len(candles) >= len(wanted):
                break
    return candles


def classify_current_advantage(open_price: float, trade_price: float) -> str:
    if not math.isfinite(open_price) or not math.isfinite(trade_price):
        return "no_kline"
    if trade_price > open_price:
        return "Up"
    if trade_price < open_price:
        return "Down"
    return "Tie"


def advantage_relation_for_outcome(outcome: str, current_advantage: str) -> str:
    if current_advantage in {"", "no_kline"}:
        return "no_kline"
    if current_advantage == "Tie":
        return "tie"
    canonical = canonical_outcome(outcome)
    if canonical == current_advantage:
        return "with_current_advantage"
    if canonical in {"Up", "Down"}:
        return "against_current_advantage"
    return "unknown_outcome"


def binance_row_context(rows: list[dict[str, Any]], kline_csv: Path | None) -> dict[int, dict[str, Any]]:
    if kline_csv is None:
        return {}
    timestamps: list[int] = []
    row_windows: dict[int, tuple[int, int]] = {}
    row_trade_ts: dict[int, int] = {}
    for idx, row in enumerate(rows):
        slug = row.get("eventSlug") or row.get("slug") or ""
        title = row.get("title") or row.get("question") or row.get("name") or ""
        if not is_btc_updown(slug, title):
            continue
        window = parse_btc_updown_window(row)
        if window is not None:
            row_windows[idx] = window
            timestamps.extend([window[0], window[1] - 1])
        trade_ts = clean_int(row.get("timestamp")) or parse_datetime_to_ts(row.get("datetimeUtc"))
        if trade_ts is not None:
            row_trade_ts[idx] = trade_ts
            timestamps.append(trade_ts)
    candles = load_binance_1s_candles(kline_csv, timestamps)
    context: dict[int, dict[str, Any]] = {}
    for idx, trade_ts in row_trade_ts.items():
        window = row_windows.get(idx)
        if window is None:
            continue
        start, end = window
        open_candle = candles.get(start, {})
        close_candle = candles.get(end - 1, {})
        trade_candle = candles.get(trade_ts, {})
        btc_open = open_candle.get("open", math.nan)
        btc_close = close_candle.get("close", math.nan)
        btc_trade_close = trade_candle.get("close", math.nan)
        advantage = classify_current_advantage(btc_open, btc_trade_close)
        outcome = rows[idx].get("outcome") or ""
        context[idx] = {
            "btcOpen": "" if not math.isfinite(btc_open) else f"{btc_open:.12f}",
            "btcClose": "" if not math.isfinite(btc_close) else f"{btc_close:.12f}",
            "btcTradeClose": "" if not math.isfinite(btc_trade_close) else f"{btc_trade_close:.12f}",
            "currentAdvantage": advantage,
            "advantageRelation": advantage_relation_for_outcome(outcome, advantage),
        }
    return context


def binance_settle_btc_markets(rows: list[dict[str, Any]], kline_csv: Path | None) -> dict[str, dict[str, Any]]:
    if kline_csv is None:
        return {}
    windows: dict[str, tuple[int, int]] = {}
    for row in rows:
        slug = row.get("eventSlug") or row.get("slug") or ""
        if slug in windows:
            continue
        parsed = parse_btc_updown_window(row)
        if parsed:
            windows[slug] = parsed
    if not windows:
        return {}
    needed: list[int] = []
    for start, end in windows.values():
        needed.append(start)
        needed.append(end - 1)
    candles = load_binance_1s_candles(kline_csv, needed)
    settlements: dict[str, dict[str, Any]] = {}
    missing = 0
    for slug, (start, end) in windows.items():
        open_candle = candles.get(start)
        close_candle = candles.get(end - 1)
        if not open_candle or not close_candle:
            missing += 1
            continue
        open_price = open_candle.get("open", math.nan)
        close_price = close_candle.get("close", math.nan)
        if not math.isfinite(open_price) or not math.isfinite(close_price):
            missing += 1
            continue
        if close_price > open_price:
            winning = "Up"
        elif close_price < open_price:
            winning = "Down"
        else:
            winning = "Tie"
        settlements[slug] = {
            "eventSlug": slug,
            "gammaMarketId": "",
            "closed": True,
            "settlementStatus": "RESOLVED_BINANCE_BTC_KLINE",
            "winningOutcome": winning,
            "outcomes": json.dumps(["Up", "Down"]),
            "outcomePrices": json.dumps([1 if winning == "Up" else 0, 1 if winning == "Down" else 0]),
            "endDate": dt.datetime.fromtimestamp(end, dt.timezone.utc).isoformat(),
            "closedTime": "",
            "apiError": "",
            "btcOpen": open_price,
            "btcClose": close_price,
            "klineCsv": str(kline_csv),
        }
    print(
        f"Binance BTCUSDT kline resolved {len(settlements)}/{len(windows)} BTC Up/Down markets"
        + (f"; missing kline for {missing}" if missing else ""),
        flush=True,
    )
    return settlements


def enrich_activity_csv(
    raw_csv: Path,
    enriched_csv: Path,
    settlements_json: Path,
    max_settlement_markets: int = 0,
    binance_kline_csv: Path | None = None,
) -> Path:
    with raw_csv.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        base_fields = list(reader.fieldnames or [])
    binance_settlements = binance_settle_btc_markets(rows, binance_kline_csv)
    kline_context = binance_row_context(rows, binance_kline_csv)
    cost_by_slug: defaultdict[str, float] = defaultdict(float)
    for row in rows:
        slug = row.get("eventSlug") or row.get("slug") or ""
        title = row.get("title") or row.get("question") or row.get("name") or ""
        if slug and is_btc_updown(slug, title):
            cost_by_slug[slug] += clean_float(row.get("usdcSize"), 0.0)
    all_slugs = sorted(cost_by_slug)
    if max_settlement_markets and max_settlement_markets > 0 and len(all_slugs) > max_settlement_markets:
        ranked = sorted(all_slugs, key=lambda slug: (-cost_by_slug[slug], slug))
        slugs = ranked[:max_settlement_markets]
        skipped_slugs = set(ranked[max_settlement_markets:])
        print(
            f"Settlement enrichment capped to top {len(slugs)}/{len(all_slugs)} markets by cost; "
            f"skipped {len(skipped_slugs)} low-cost markets",
            flush=True,
        )
    else:
        slugs = all_slugs
        skipped_slugs = set()
    settlements = fetch_settlements_once(slugs)
    for slug, kline_settlement in binance_settlements.items():
        current_status = str(settlements.get(slug, {}).get("settlementStatus", ""))
        if slug not in settlements or current_status in {"", "OPEN", "FETCH_ERROR", "MISSING_SETTLEMENT", "SETTLEMENT_NOT_FETCHED"}:
            settlements[slug] = kline_settlement
    settlement_payload = {
        "fetched_market_count": len(slugs),
        "binance_btc_market_count": len(binance_settlements),
        "binance_kline_csv": str(binance_kline_csv or ""),
        "settled_market_count": len(settlements),
        "gamma_candidate_market_count": len(all_slugs),
        "skipped_market_count": len(skipped_slugs),
        "max_settlement_markets": max_settlement_markets,
        "settlements": list(settlements.values()),
    }
    settlements_json.write_text(json.dumps(settlement_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    extra_fields = [
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
        "btcOpen",
        "btcClose",
        "btcTradeClose",
        "currentAdvantage",
        "advantageRelation",
        "settlementKlineCsv",
    ]
    fieldnames = list(base_fields)
    for field in extra_fields:
        if field not in fieldnames:
            fieldnames.append(field)
    enriched_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        slug = row.get("eventSlug") or row.get("slug") or ""
        settlement = settlements.get(slug, {})
        row_context = kline_context.get(idx, {})
        winning = [value for value in str(settlement.get("winningOutcome") or "").split("|") if value]
        status = settlement.get("settlementStatus") or ("SETTLEMENT_NOT_FETCHED" if slug in skipped_slugs else "MISSING_SETTLEMENT")
        outcome = row.get("outcome")
        if str(status).startswith("RESOLVED"):
            result = "WIN" if outcome in winning else "LOSS"
        elif status == "OPEN":
            result = "OPEN"
        else:
            result = "UNKNOWN"
        payout = ""
        pnl = ""
        if str(row.get("side", "")).upper() == "BUY" and result in {"WIN", "LOSS"}:
            size = clean_float(row.get("size"), 0.0)
            cost = clean_float(row.get("usdcSize"), 0.0)
            payout_value = size if result == "WIN" else 0.0
            payout = f"{payout_value:.12f}"
            pnl = f"{(payout_value - cost):.12f}"
        enriched = dict(row)
        enriched.update(
            {
                "settlementStatus": status,
                "marketClosed": settlement.get("closed", ""),
                "winningOutcome": settlement.get("winningOutcome", ""),
                "activityOutcomeResult": result,
                "activityPayoutUSDC": payout,
                "activityPnLUSDC": pnl,
                "gammaMarketId": settlement.get("gammaMarketId", ""),
                "marketEndDate": settlement.get("endDate", ""),
                "marketClosedTime": settlement.get("closedTime", ""),
                "marketOutcomePrices": settlement.get("outcomePrices", ""),
                "btcOpen": settlement.get("btcOpen") or row_context.get("btcOpen", ""),
                "btcClose": settlement.get("btcClose") or row_context.get("btcClose", ""),
                "btcTradeClose": row_context.get("btcTradeClose", ""),
                "currentAdvantage": row_context.get("currentAdvantage", ""),
                "advantageRelation": row_context.get("advantageRelation", ""),
                "settlementKlineCsv": settlement.get("klineCsv", ""),
            }
        )
        enriched_rows.append(enriched)
    with enriched_csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(enriched_rows)
    return enriched_csv


def attach_binance_kline_fields(input_csv: Path, output_csv: Path, binance_kline_csv: Path | None) -> Path:
    if binance_kline_csv is None:
        return input_csv
    with input_csv.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        base_fields = list(reader.fieldnames or [])
    kline_settlements = binance_settle_btc_markets(rows, binance_kline_csv)
    kline_context = binance_row_context(rows, binance_kline_csv)
    if not kline_settlements and not kline_context:
        return input_csv
    extra_fields = [
        "settlementStatus",
        "winningOutcome",
        "activityOutcomeResult",
        "activityPayoutUSDC",
        "activityPnLUSDC",
        "marketEndDate",
        "btcOpen",
        "btcClose",
        "btcTradeClose",
        "currentAdvantage",
        "advantageRelation",
        "settlementKlineCsv",
    ]
    fieldnames = list(base_fields)
    for field in extra_fields:
        if field not in fieldnames:
            fieldnames.append(field)
    output_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        slug = row.get("eventSlug") or row.get("slug") or ""
        kline_settlement = kline_settlements.get(slug)
        row_context = kline_context.get(idx, {})
        if kline_settlement or row_context:
            row = dict(row)
            if not row.get("btcOpen"):
                row["btcOpen"] = (kline_settlement or {}).get("btcOpen", row_context.get("btcOpen", ""))
            if not row.get("btcClose"):
                row["btcClose"] = (kline_settlement or {}).get("btcClose", row_context.get("btcClose", ""))
            if not row.get("btcTradeClose"):
                row["btcTradeClose"] = row_context.get("btcTradeClose", "")
            if not row.get("currentAdvantage"):
                row["currentAdvantage"] = row_context.get("currentAdvantage", "")
            if not row.get("advantageRelation"):
                row["advantageRelation"] = row_context.get("advantageRelation", "")
            if not row.get("settlementKlineCsv"):
                row["settlementKlineCsv"] = (kline_settlement or {}).get("klineCsv", str(binance_kline_csv))
            status = str(row.get("settlementStatus") or "")
            if kline_settlement and status in {"", "OPEN", "FETCH_ERROR", "MISSING_SETTLEMENT", "SETTLEMENT_NOT_FETCHED"}:
                row["settlementStatus"] = kline_settlement.get("settlementStatus", status)
                row["winningOutcome"] = kline_settlement.get("winningOutcome", row.get("winningOutcome", ""))
                row["marketEndDate"] = kline_settlement.get("endDate", row.get("marketEndDate", ""))
                outcome = row.get("outcome")
                winning = [value for value in str(row.get("winningOutcome") or "").split("|") if value]
                result = "WIN" if outcome in winning else "LOSS"
                current_result = str(row.get("activityOutcomeResult") or row.get("tradeOutcomeResult") or "")
                if current_result in {"", "OPEN", "UNKNOWN"}:
                    row["activityOutcomeResult"] = result
                if str(row.get("side", "")).upper() == "BUY":
                    size = clean_float(row.get("size"), 0.0)
                    cost = clean_float(row.get("usdcSize"), 0.0)
                    payout_value = size if result == "WIN" else 0.0
                    if not row.get("activityPayoutUSDC"):
                        row["activityPayoutUSDC"] = f"{payout_value:.12f}"
                    if not row.get("activityPnLUSDC"):
                        row["activityPnLUSDC"] = f"{(payout_value - cost):.12f}"
        output_rows.append(row)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)
    return output_csv


def export_activity(args: argparse.Namespace, out_dir: Path, label: str) -> Path:
    if not args.user:
        raise SystemExit("Provide --user or --input.")
    script = resolve_export_script(args.export_script)
    user = args.user.lower()
    start, end = resolve_export_window(args)
    raw_dir = out_dir / "source_export"
    raw_dir.mkdir(parents=True, exist_ok=True)

    if args.single_export:
        result = run_exporter(script, args, user, raw_dir, label, start, end, settlements=True)
        if result is None:
            raise SystemExit(f"Activity export succeeded but no *_with_settlements.csv was found in {raw_dir}")
        binance_kline_csv = prepare_binance_kline_csv(result, args, out_dir)
        return attach_binance_kline_fields(result, out_dir / f"{label}_{user}_single_with_binance_kline.csv", binance_kline_csv)

    chunk_seconds = max(60, int(float(args.export_chunk_hours) * 3600))
    chunk_specs: list[tuple[int, int, str]] = []
    chunk_start = start
    idx = 1
    while chunk_start <= end:
        chunk_end = min(end, chunk_start + chunk_seconds - 1)
        chunk_specs.append((chunk_start, chunk_end, f"{label}_chunk{idx:03d}"))
        chunk_start = chunk_end + 1
        idx += 1

    chunk_paths: list[Path] = []
    workers = max(1, int(args.export_workers))
    if workers == 1 or len(chunk_specs) == 1:
        for chunk_start, chunk_end, chunk_label in chunk_specs:
            exported = run_exporter(script, args, user, raw_dir / chunk_label, chunk_label, chunk_start, chunk_end, settlements=False)
            if exported is not None:
                chunk_paths.append(exported)
    else:
        print(f"Exporting {len(chunk_specs)} raw chunks with {workers} workers", flush=True)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_by_label = {
                pool.submit(
                    run_exporter,
                    script,
                    args,
                    user,
                    raw_dir / chunk_label,
                    chunk_label,
                    chunk_start,
                    chunk_end,
                    settlements=False,
                ): chunk_label
                for chunk_start, chunk_end, chunk_label in chunk_specs
            }
            for idx, future in enumerate(as_completed(future_by_label), start=1):
                exported = future.result()
                if exported is not None:
                    chunk_paths.append(exported)
                print(f"Completed raw export chunk {idx}/{len(chunk_specs)}", flush=True)
    if not chunk_paths:
        raise SystemExit("Chunked export completed but produced no enriched CSV files.")
    merged_raw = out_dir / f"{label}_{user}_merged_activity.csv"
    merge_activity_csvs(chunk_paths, merged_raw)
    merged_enriched = out_dir / f"{label}_{user}_merged_with_settlements.csv"
    binance_kline_csv = prepare_binance_kline_csv(merged_raw, args, out_dir)
    return enrich_activity_csv(
        merged_raw,
        merged_enriched,
        out_dir / f"{label}_{user}_market_settlements.json",
        int(args.max_settlement_markets),
        binance_kline_csv,
    )


def has_settlement_columns(path: Path) -> bool:
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        fields = set(reader.fieldnames or [])
    return bool(fields & {"activityOutcomeResult", "tradeOutcomeResult", "activityPnLUSDC", "tradePnLUSDC"})


def load_trades(path: Path, price_decimals: int) -> tuple[list[Trade], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            rows.append(row)
    trades: list[Trade] = []
    for idx, row in enumerate(rows):
        row_type = str(row.get("type", "")).upper()
        if row_type and row_type != "TRADE":
            continue
        slug = row.get("eventSlug") or row.get("slug") or ""
        title = row.get("title") or row.get("question") or row.get("name") or ""
        if not is_btc_updown(slug, title):
            continue
        asset, interval = infer_asset_and_interval(slug, title)
        market_start = slug_market_start(slug)
        title_window = parse_title_updown_window(row)
        if market_start is None and title_window is not None:
            market_start = title_window[0]
        if (not interval or interval == "unknown") and title_window is not None:
            duration = title_window[1] - title_window[0]
            interval = next((key for key, seconds in INTERVAL_SECONDS.items() if seconds == duration), interval)
        market_end = None
        if market_start is not None and interval in INTERVAL_SECONDS:
            market_end = market_start + INTERVAL_SECONDS[interval]
        else:
            market_end = parse_datetime_to_ts(row.get("marketEndDate") or row.get("endDate"))
        timestamp = clean_int(row.get("timestamp")) or parse_datetime_to_ts(row.get("datetimeUtc"))
        if timestamp is None:
            continue
        price = round(clean_float(row.get("price"), 0.0), price_decimals)
        size = clean_float(row.get("size"), 0.0)
        usdc = clean_float(row.get("usdcSize"), 0.0)
        result = str(row.get("activityOutcomeResult") or row.get("tradeOutcomeResult") or "").upper()
        winning = canonical_outcome(row.get("winningOutcome") or row.get("winning_outcome") or "")
        payout_raw = row.get("activityPayoutUSDC") if "activityPayoutUSDC" in row else row.get("tradePayoutUSDC")
        pnl_raw = row.get("activityPnLUSDC") if "activityPnLUSDC" in row else row.get("tradePnLUSDC")
        payout = clean_float(payout_raw, math.nan)
        pnl = clean_float(pnl_raw, math.nan)
        btc_open = clean_float(row.get("btcOpen") or row.get("btc_market_open"), math.nan)
        btc_trade_close = clean_float(row.get("btcTradeClose") or row.get("btc_trade_close"), math.nan)
        current_advantage = canonical_outcome(row.get("currentAdvantage") or row.get("current_advantage_side") or "")
        advantage_relation = str(row.get("advantageRelation") or row.get("advantage_relation") or "no_kline")
        trades.append(
            Trade(
                row_id=idx,
                timestamp=timestamp,
                dt_utc=dt.datetime.fromtimestamp(timestamp, dt.timezone.utc),
                slug=slug,
                title=title,
                asset=asset or "UNKNOWN",
                interval=interval or "unknown",
                market_start=market_start,
                market_end=market_end,
                outcome=canonical_outcome(row.get("outcome") or ""),
                side=str(row.get("side") or "").upper(),
                price=price,
                size=size,
                usdc=usdc,
                result=result or "UNKNOWN",
                winning_outcome=winning,
                payout=None if math.isnan(payout) else payout,
                pnl=None if math.isnan(pnl) else pnl,
                tx_hash=row.get("transactionHash") or "",
                btc_open=None if math.isnan(btc_open) else btc_open,
                btc_trade_close=None if math.isnan(btc_trade_close) else btc_trade_close,
                current_advantage=current_advantage,
                advantage_relation=advantage_relation,
                raw=row,
            )
        )
    audit = {
        "input_csv": str(path),
        "input_rows": len(rows),
        "btc_updown_trade_rows": len(trades),
        "markets": len({t.slug for t in trades}),
        "assets": dict(Counter(t.asset for t in trades)),
        "intervals": dict(Counter(t.interval for t in trades)),
        "side_counts": dict(Counter(t.side for t in trades)),
        "result_counts": dict(Counter(t.result for t in trades)),
    }
    return sorted(trades, key=lambda t: (t.timestamp, t.slug, t.tx_hash, t.row_id)), audit


def infer_orders(trades: list[Trade], gap_sec: int) -> list[InferredOrder]:
    orders: list[InferredOrder] = []
    grouped = sorted(trades, key=lambda t: (t.slug, t.outcome, t.side, t.price_level, t.timestamp, t.row_id))
    current: list[Trade] = []
    prev_key: tuple[str, str, str, float] | None = None
    prev_ts: int | None = None

    def flush() -> None:
        if not current:
            return
        order_id = len(orders) + 1
        first = current[0]
        result_counts = Counter(t.result for t in current)
        relation_counts = Counter(t.advantage_relation or "no_kline" for t in current)
        advantage_counts = Counter(t.current_advantage or "no_kline" for t in current)
        payout = sum(t.payout or 0.0 for t in current)
        pnl = sum(t.pnl or 0.0 for t in current)
        orders.append(
            InferredOrder(
                order_id=order_id,
                market=first.slug,
                asset=first.asset,
                interval=first.interval,
                outcome=first.outcome,
                side=first.side,
                price_level=first.price_level,
                first_ts=min(t.timestamp for t in current),
                last_ts=max(t.timestamp for t in current),
                fill_count=len(current),
                shares=sum(t.size for t in current),
                cost=sum(t.usdc for t in current),
                payout=payout,
                pnl=pnl,
                result_counts=result_counts,
                winning_outcome=first.winning_outcome,
                market_start=first.market_start,
                market_end=first.market_end,
                current_advantage=advantage_counts.most_common(1)[0][0] if advantage_counts else "no_kline",
                advantage_relation=relation_counts.most_common(1)[0][0] if relation_counts else "no_kline",
            )
        )

    for trade in grouped:
        key = (trade.slug, trade.outcome, trade.side, trade.price_level)
        starts_new = prev_key is None or key != prev_key or prev_ts is None or trade.timestamp - prev_ts > gap_sec
        if starts_new:
            flush()
            current = [trade]
        else:
            current.append(trade)
        prev_key = key
        prev_ts = trade.timestamp
    flush()
    return sorted(orders, key=lambda o: (o.first_ts, o.market, o.order_id))


def qstar_for(up_shares: float, down_shares: float, cost: float) -> tuple[str, float, float]:
    if up_shares > down_shares:
        return "Up", up_shares - down_shares, safe_div(cost - down_shares, up_shares - down_shares)
    if down_shares > up_shares:
        return "Down", down_shares - up_shares, safe_div(cost - up_shares, down_shares - up_shares)
    return "Flat", 0.0, math.nan


def summarize_intervals(trades: list[Trade]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, group in groupby_many(trades, lambda t: (t.asset, t.interval)).items():
        asset, interval = key
        cost = sum(t.usdc for t in group)
        payout = sum(t.payout or 0.0 for t in group)
        pnl = sum(t.pnl or 0.0 for t in group)
        rows.append(
            {
                "asset": asset,
                "interval": interval,
                "markets": len({t.slug for t in group}),
                "fills": len(group),
                "cost": cost,
                "shares": sum(t.size for t in group),
                "payout": payout,
                "pnl": pnl,
                "roi": safe_div(pnl, cost),
                "avg_price": safe_div(cost, sum(t.size for t in group)),
                "resolved_rate": safe_div(sum(1 for t in group if t.result in {"WIN", "LOSS"}), len(group)),
            }
        )
    return sorted(rows, key=lambda r: (-r["cost"], r["asset"], r["interval"]))


def groupby_many(items: Iterable[Any], key_func) -> dict[Any, list[Any]]:
    groups: defaultdict[Any, list[Any]] = defaultdict(list)
    for item in items:
        groups[key_func(item)].append(item)
    return dict(groups)


def market_summaries(trades: list[Trade], orders: list[InferredOrder]) -> list[dict[str, Any]]:
    orders_by_market = groupby_many(orders, lambda o: o.market)
    rows: list[dict[str, Any]] = []
    for market, group in groupby_many(trades, lambda t: t.slug).items():
        buy_group = [t for t in group if t.side == "BUY"]
        cost = sum(t.usdc for t in buy_group)
        payout = sum(t.payout or 0.0 for t in buy_group)
        pnl = sum(t.pnl or 0.0 for t in buy_group)
        up = sum(t.size for t in buy_group if t.outcome == "Up")
        down = sum(t.size for t in buy_group if t.outcome == "Down")
        net_side, abs_net, qstar = qstar_for(up, down, cost)
        winning = next((t.winning_outcome for t in group if t.winning_outcome), "")
        market_orders = orders_by_market.get(market, [])
        first_elapsed = [o.elapsed_sec for o in market_orders if o.elapsed_sec is not None]
        last_before_close = [o.seconds_before_close for o in market_orders if o.seconds_before_close is not None]
        rows.append(
            {
                "market": market,
                "asset": group[0].asset,
                "interval": group[0].interval,
                "fills": len(group),
                "orders": len(market_orders),
                "cost": cost,
                "payout": payout,
                "pnl": pnl,
                "roi": safe_div(pnl, cost),
                "outcomes_traded": len({t.outcome for t in buy_group if t.outcome}),
                "both_sides": len({t.outcome for t in buy_group if t.outcome in {"Up", "Down"}}) >= 2,
                "up_shares": up,
                "down_shares": down,
                "net_side": net_side,
                "abs_net": abs_net,
                "qstar": qstar,
                "winning_outcome": winning,
                "net_correct": net_side == winning if winning and net_side in {"Up", "Down"} else None,
                "first_order_elapsed_sec": min(first_elapsed) if first_elapsed else math.nan,
                "last_order_seconds_before_close": min(last_before_close) if last_before_close else math.nan,
            }
        )
    return sorted(rows, key=lambda r: (-r["cost"], r["market"]))


def lifecycle_summary(markets: list[dict[str, Any]], orders: list[InferredOrder]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, group in groupby_many(markets, lambda r: (r["asset"], r["interval"])).items():
        asset, interval = key
        costs = [r["cost"] for r in group]
        abs_nets = [r["abs_net"] for r in group]
        qstars = [r["qstar"] for r in group if math.isfinite(float(r["qstar"]))]
        net_known = [r for r in group if r["net_correct"] is not None]
        net_weights = [r["abs_net"] for r in net_known]
        weighted_net_correct = safe_div(sum(r["abs_net"] for r in net_known if r["net_correct"]), sum(net_weights))
        weighted_qstar = weighted_average(qstars, [r["abs_net"] for r in group if math.isfinite(float(r["qstar"]))])
        interval_orders = [o for o in orders if o.asset == asset and o.interval == interval]
        gaps = order_gaps_by_market(interval_orders)
        first_elapsed = [r["first_order_elapsed_sec"] for r in group]
        last_before = [r["last_order_seconds_before_close"] for r in group]
        rows.append(
            {
                "asset": asset,
                "interval": interval,
                "markets": len(group),
                "orders": len(interval_orders),
                "fills": sum(r["fills"] for r in group),
                "both_sides_rate": safe_div(sum(1 for r in group if r["both_sides"]), len(group)),
                "net_correct_rate": safe_div(sum(1 for r in net_known if r["net_correct"]), len(net_known)),
                "weighted_net_correct_rate": weighted_net_correct,
                "weighted_qstar": weighted_qstar,
                "qstar_margin": weighted_net_correct - weighted_qstar,
                "median_first_order_elapsed_sec": median(first_elapsed),
                "median_last_order_seconds_before_close": median(last_before),
                "median_market_order_gap_sec": median(gaps),
                "median_cost": median(costs),
                "p95_cost": percentile(costs, 0.95),
                "p99_cost": percentile(costs, 0.99),
                "median_abs_net_shares": median(abs_nets),
                "p90_abs_net_shares": percentile(abs_nets, 0.90),
            }
        )
    return sorted(rows, key=lambda r: (-r["cost"] if "cost" in r else 0, r["asset"], r["interval"]))


def weighted_average(values: list[float], weights: list[float]) -> float:
    pairs = [(v, w) for v, w in zip(values, weights) if math.isfinite(float(v)) and math.isfinite(float(w)) and w > 0]
    if not pairs:
        return math.nan
    return sum(v * w for v, w in pairs) / sum(w for _, w in pairs)


def order_gaps_by_market(orders: list[InferredOrder]) -> list[float]:
    gaps: list[float] = []
    for _, group in groupby_many(orders, lambda o: o.market).items():
        seq = sorted(group, key=lambda o: o.first_ts)
        gaps.extend(seq[i].first_ts - seq[i - 1].first_ts for i in range(1, len(seq)))
    return gaps


def order_summary(orders: list[InferredOrder]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, group in groupby_many(orders, lambda o: (o.asset, o.interval)).items():
        asset, interval = key
        costs = [o.cost for o in group]
        shares = [o.shares for o in group]
        rows.append(
            {
                "asset": asset,
                "interval": interval,
                "orders": len(group),
                "fills": sum(o.fill_count for o in group),
                "markets": len({o.market for o in group}),
                "cost": sum(o.cost for o in group),
                "multi_fill_order_rate": safe_div(sum(1 for o in group if o.fill_count > 1), len(group)),
                "multi_fill_cost_rate": safe_div(sum(o.cost for o in group if o.fill_count > 1), sum(o.cost for o in group)),
                "median_fills_per_order": median([o.fill_count for o in group]),
                "p95_fills_per_order": percentile([o.fill_count for o in group], 0.95),
                "median_order_shares": median(shares),
                "p95_order_shares": percentile(shares, 0.95),
                "median_order_cost": median(costs),
                "p95_order_cost": percentile(costs, 0.95),
            }
        )
    return sorted(rows, key=lambda r: (-r["cost"], r["asset"], r["interval"]))


def batch_and_ladder(orders: list[InferredOrder], batch_gap_sec: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    batch_rows: list[dict[str, Any]] = []
    ladder_rows: list[dict[str, Any]] = []
    batch_id = 0
    for market, group in groupby_many(orders, lambda o: o.market).items():
        seq = sorted(group, key=lambda o: (o.first_ts, o.order_id))
        current: list[InferredOrder] = []
        prev_ts: int | None = None

        def flush() -> None:
            nonlocal batch_id
            if not current:
                return
            batch_id += 1
            outcomes = {o.outcome for o in current}
            prices = {o.price_level for o in current}
            cost = sum(o.cost for o in current)
            batch_rows.append(
                {
                    "batch_id": batch_id,
                    "market": market,
                    "asset": current[0].asset,
                    "interval": current[0].interval,
                    "orders": len(current),
                    "cost": cost,
                    "both_side_batch": len(outcomes & {"Up", "Down"}) >= 2,
                    "distinct_price_levels": len(prices),
                    "multi_order_batch": len(current) > 1,
                    "first_ts": min(o.first_ts for o in current),
                }
            )
            for outcome, side_orders in groupby_many(current, lambda o: o.outcome).items():
                ranked_prices = sorted({o.price_level for o in side_orders}, reverse=True)
                rank_by_price = {price: idx + 1 for idx, price in enumerate(ranked_prices)}
                for order in side_orders:
                    ladder_rows.append(
                        {
                            "batch_id": batch_id,
                            "market": market,
                            "asset": order.asset,
                            "interval": order.interval,
                            "outcome": outcome,
                            "rank": rank_by_price[order.price_level],
                            "price": order.price_level,
                            "shares": order.shares,
                            "cost": order.cost,
                        }
                    )

        for order in seq:
            if prev_ts is None or order.first_ts - prev_ts <= batch_gap_sec:
                current.append(order)
            else:
                flush()
                current = [order]
            prev_ts = order.first_ts
        flush()

    batch_summary_rows: list[dict[str, Any]] = []
    for key, group in groupby_many(batch_rows, lambda r: (r["asset"], r["interval"])).items():
        asset, interval = key
        cost = sum(r["cost"] for r in group)
        batch_summary_rows.append(
            {
                "asset": asset,
                "interval": interval,
                "batches": len(group),
                "markets": len({r["market"] for r in group}),
                "orders": sum(r["orders"] for r in group),
                "cost": cost,
                "both_side_batch_rate": safe_div(sum(1 for r in group if r["both_side_batch"]), len(group)),
                "both_side_cost_rate": safe_div(sum(r["cost"] for r in group if r["both_side_batch"]), cost),
                "multi_order_batch_rate": safe_div(sum(1 for r in group if r["multi_order_batch"]), len(group)),
                "median_orders_per_batch": median([r["orders"] for r in group]),
                "p90_distinct_price_levels": percentile([r["distinct_price_levels"] for r in group], 0.90),
            }
        )

    ladder_summary_rows: list[dict[str, Any]] = []
    for key, group in groupby_many(ladder_rows, lambda r: (r["asset"], r["interval"], rank_bucket(r["rank"]))).items():
        asset, interval, rank = key
        total_cost = sum(r["cost"] for r in ladder_rows if r["asset"] == asset and r["interval"] == interval)
        ladder_summary_rows.append(
            {
                "asset": asset,
                "interval": interval,
                "rank_bucket": rank,
                "side_price_levels": len(group),
                "cost": sum(r["cost"] for r in group),
                "shares": sum(r["shares"] for r in group),
                "median_shares": median([r["shares"] for r in group]),
                "cost_share": safe_div(sum(r["cost"] for r in group), total_cost),
            }
        )
    return (
        sorted(batch_summary_rows, key=lambda r: (-r["cost"], r["asset"], r["interval"])),
        sorted(ladder_summary_rows, key=lambda r: (r["asset"], r["interval"], str(r["rank_bucket"]))),
    )


def rank_bucket(rank: int) -> str:
    return "6+" if rank >= 6 else str(rank)


def price_band_summary(orders: list[InferredOrder]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, group in groupby_many(orders, lambda o: (o.asset, o.interval)).items():
        asset, interval = key
        for low, high, label in PRICE_BANDS:
            band = [o for o in group if low <= o.price_level < high]
            if not band:
                continue
            cost = sum(o.cost for o in band)
            rows.append(
                {
                    "asset": asset,
                    "interval": interval,
                    "price_band": label,
                    "orders": len(band),
                    "markets": len({o.market for o in band}),
                    "cost": cost,
                    "shares": sum(o.shares for o in band),
                    "pnl": sum(o.pnl for o in band),
                    "roi": safe_div(sum(o.pnl for o in band), cost),
                    "avg_order_cost": safe_div(cost, len(band)),
                    "avg_order_shares": safe_div(sum(o.shares for o in band), len(band)),
                    "avg_price": safe_div(cost, sum(o.shares for o in band)),
                }
            )
    return rows


def phase_summary(trades: list[Trade]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    usable = [t for t in trades if t.elapsed_frac is not None]
    for key, group in groupby_many(usable, lambda t: (t.asset, t.interval)).items():
        asset, interval = key
        for low, high, label in PHASE_BINS:
            phase = [t for t in group if low <= (t.elapsed_frac or -1) < high]
            if not phase:
                continue
            cost = sum(t.usdc for t in phase)
            rows.append(
                {
                    "asset": asset,
                    "interval": interval,
                    "phase": label,
                    "fills": len(phase),
                    "markets": len({t.slug for t in phase}),
                    "cost": cost,
                    "pnl": sum(t.pnl or 0.0 for t in phase),
                    "roi": safe_div(sum(t.pnl or 0.0 for t in phase), cost),
                    "winner_cost_rate": safe_div(sum(t.usdc for t in phase if t.result == "WIN"), cost),
                }
            )
    return rows


def sequence_summary(orders: list[InferredOrder]) -> list[dict[str, Any]]:
    transitions: Counter[tuple[str, str, str, str]] = Counter()
    costs: defaultdict[tuple[str, str, str, str], float] = defaultdict(float)
    for market, group in groupby_many(orders, lambda o: o.market).items():
        seq = sorted(group, key=lambda o: (o.first_ts, o.order_id))
        prev = None
        for order in seq:
            current = "unknown"
            if order.winning_outcome:
                current = "winner_proxy" if order.outcome == order.winning_outcome else "loser_proxy"
            if prev is not None:
                key = (order.asset, order.interval, prev, current)
                transitions[key] += 1
                costs[key] += order.cost
            prev = current
    rows: list[dict[str, Any]] = []
    totals: Counter[tuple[str, str, str]] = Counter()
    for asset, interval, prev, current in transitions:
        totals[(asset, interval, prev)] += transitions[(asset, interval, prev, current)]
    for key, count in transitions.items():
        asset, interval, prev, current = key
        rows.append(
            {
                "asset": asset,
                "interval": interval,
                "prev_expost": prev,
                "order_expost_side": current,
                "orders": count,
                "cost": costs[key],
                "order_share_from_prev": safe_div(count, totals[(asset, interval, prev)]),
            }
        )
    return sorted(rows, key=lambda r: (r["asset"], r["interval"], r["prev_expost"], r["order_expost_side"]))


def order_inventory_path(orders: list[InferredOrder]) -> list[dict[str, Any]]:
    up = down = cost = 0.0
    rows: list[dict[str, Any]] = []
    for idx, order in enumerate(sorted(orders, key=lambda o: (o.first_ts, o.order_id)), start=1):
        if order.side == "BUY":
            if order.outcome == "Up":
                up += order.shares
            elif order.outcome == "Down":
                down += order.shares
            cost += order.cost
        net_side, abs_net, qstar = qstar_for(up, down, cost)
        rows.append(
            {
                "idx": idx,
                "order": order,
                "up": up,
                "down": down,
                "cost": cost,
                "net_side": net_side,
                "abs_net": abs_net,
                "qstar": qstar,
            }
        )
    return rows


def qstar_anchor_summary(markets: list[dict[str, Any]], orders: list[InferredOrder]) -> list[dict[str, Any]]:
    market_by_slug = {row["market"]: row for row in markets}
    anchors = [
        ("after_first", 0.0),
        ("after_25pct_orders", 0.25),
        ("after_50pct_orders", 0.50),
        ("after_75pct_orders", 0.75),
        ("after_last", 1.0),
    ]
    raw_rows: list[dict[str, Any]] = []
    for market, group in groupby_many(orders, lambda o: o.market).items():
        path = order_inventory_path(group)
        if not path:
            continue
        market_row = market_by_slug.get(market, {})
        winning = market_row.get("winning_outcome", "")
        interval = market_row.get("interval") or path[0]["order"].interval
        for anchor, frac in anchors:
            idx = min(len(path) - 1, max(0, int(round((len(path) - 1) * frac))))
            row = path[idx]
            order = row["order"]
            net_side = row["net_side"]
            elapsed_frac = None
            if order.market_start is not None and order.market_end is not None and order.market_end > order.market_start:
                elapsed_frac = (order.first_ts - order.market_start) / (order.market_end - order.market_start)
            raw_rows.append(
                {
                    "interval": interval,
                    "anchor": anchor,
                    "market": market,
                    "qstar": row["qstar"],
                    "abs_net": row["abs_net"],
                    "cost": row["cost"],
                    "elapsed_frac": elapsed_frac if elapsed_frac is not None else math.nan,
                    "net_correct": net_side == winning if winning and net_side in {"Up", "Down"} else None,
                }
            )
    rows: list[dict[str, Any]] = []
    anchor_order = {name: idx for idx, (name, _) in enumerate(anchors)}
    for key, group in groupby_many(raw_rows, lambda r: (r["interval"], r["anchor"])).items():
        interval, anchor = key
        net_known = [r for r in group if r["net_correct"] is not None]
        rows.append(
            {
                "interval": interval,
                "anchor": anchor,
                "markets": len({r["market"] for r in group}),
                "median_qstar": median([r["qstar"] for r in group]),
                "median_abs_net_shares": median([r["abs_net"] for r in group]),
                "median_cost_so_far": median([r["cost"] for r in group]),
                "median_elapsed_frac": median([r["elapsed_frac"] for r in group]),
                "net_correct_rate": safe_div(sum(1 for r in net_known if r["net_correct"]), len(net_known)),
            }
        )
    return sorted(rows, key=lambda r: (r["interval"], anchor_order.get(r["anchor"], 99)))


def final_net_lock_summary(markets: list[dict[str, Any]], orders: list[InferredOrder]) -> list[dict[str, Any]]:
    raw_rows: list[dict[str, Any]] = []
    for market, group in groupby_many(orders, lambda o: o.market).items():
        path = order_inventory_path(group)
        if not path:
            continue
        final = path[-1]
        final_side = final["net_side"]
        if final_side not in {"Up", "Down"}:
            continue
        lock_idx = None
        for idx, row in enumerate(path):
            if row["net_side"] == final_side and all(later["net_side"] == final_side for later in path[idx:]):
                lock_idx = idx
                break
        if lock_idx is None:
            continue
        lock = path[lock_idx]
        order = lock["order"]
        elapsed_frac = math.nan
        if order.market_start is not None and order.market_end is not None and order.market_end > order.market_start:
            elapsed_frac = (order.first_ts - order.market_start) / (order.market_end - order.market_start)
        raw_rows.append(
            {
                "interval": order.interval,
                "market": market,
                "lock_elapsed_frac": elapsed_frac,
                "lock_cost_fraction": safe_div(lock["cost"], final["cost"]),
                "final_abs_net": final["abs_net"],
                "final_qstar": final["qstar"],
                "orders_before_lock": lock_idx + 1,
                "total_orders": len(path),
            }
        )
    rows: list[dict[str, Any]] = []
    order_markets = {market for market, _ in groupby_many(orders, lambda o: o.market).items()}
    for interval, group in groupby_many(raw_rows, lambda r: r["interval"]).items():
        interval_order_markets = {o.market for o in orders if o.interval == interval}
        rows.append(
            {
                "interval": interval,
                "markets": len(interval_order_markets),
                "locked_markets": len({r["market"] for r in group}),
                "lock_rate": safe_div(len({r["market"] for r in group}), len(interval_order_markets)),
                "median_lock_elapsed_frac": median([r["lock_elapsed_frac"] for r in group]),
                "median_lock_cost_fraction": median([r["lock_cost_fraction"] for r in group]),
                "median_orders_before_lock": median([r["orders_before_lock"] for r in group]),
                "median_final_abs_net": median([r["final_abs_net"] for r in group]),
                "median_final_qstar": median([r["final_qstar"] for r in group]),
            }
        )
    return sorted(rows, key=lambda r: r["interval"])


def advantage_summary(trades: list[Trade]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    interval_totals: defaultdict[str, float] = defaultdict(float)
    for trade in trades:
        interval_totals[trade.interval] += trade.usdc
    for key, group in groupby_many(trades, lambda t: (t.interval, t.advantage_relation or "no_kline")).items():
        interval, relation = key
        cost = sum(t.usdc for t in group)
        pnl = sum(t.pnl or 0.0 for t in group)
        resolved = [t for t in group if t.result in {"WIN", "LOSS"}]
        rows.append(
            {
                "interval": interval,
                "advantage_relation": relation,
                "fills": len(group),
                "markets": len({t.slug for t in group}),
                "cost": cost,
                "cost_share": safe_div(cost, interval_totals[interval]),
                "pnl": pnl,
                "roi": safe_div(pnl, cost),
                "win_rate": safe_div(sum(1 for t in resolved if t.result == "WIN"), len(resolved)),
            }
        )
    return sorted(rows, key=lambda r: (r["interval"], -r["cost"]))


def advantage_streak_summary(orders: list[InferredOrder]) -> list[dict[str, Any]]:
    streaks: list[dict[str, Any]] = []
    for market, group in groupby_many(orders, lambda o: o.market).items():
        seq = sorted(group, key=lambda o: (o.first_ts, o.order_id))
        prev = ""
        length = 0
        cost = 0.0

        def flush(relation: str, run_length: int, run_cost: float, interval: str) -> None:
            if relation:
                streaks.append({"market": market, "interval": interval, "relation": relation, "length": run_length, "cost": run_cost})

        for order in seq:
            relation = order.advantage_relation or "no_kline"
            if relation == prev:
                length += 1
                cost += order.cost
            else:
                if prev:
                    flush(prev, length, cost, order.interval)
                prev = relation
                length = 1
                cost = order.cost
        if prev and seq:
            flush(prev, length, cost, seq[-1].interval)
    rows: list[dict[str, Any]] = []
    for key, group in groupby_many(streaks, lambda r: (r["interval"], r["relation"])).items():
        interval, relation = key
        rows.append(
            {
                "interval": interval,
                "relation": relation,
                "streaks": len(group),
                "markets": len({r["market"] for r in group}),
                "median_streak_orders": median([r["length"] for r in group]),
                "p90_streak_orders": percentile([r["length"] for r in group], 0.90),
                "max_streak_orders": max((r["length"] for r in group), default=0),
                "cost": sum(r["cost"] for r in group),
            }
        )
    return sorted(rows, key=lambda r: (r["interval"], -r["cost"]))


def pearson(xs: list[float], ys: list[float]) -> float:
    pairs = [(x, y) for x, y in zip(xs, ys) if math.isfinite(float(x)) and math.isfinite(float(y))]
    if len(pairs) < 2:
        return math.nan
    x_values = [p[0] for p in pairs]
    y_values = [p[1] for p in pairs]
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)
    x_var = sum((x - x_mean) ** 2 for x in x_values)
    y_var = sum((y - y_mean) ** 2 for y in y_values)
    if x_var <= 0 or y_var <= 0:
        return math.nan
    cov = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    return cov / math.sqrt(x_var * y_var)


def size_price_diagnostic(orders: list[InferredOrder]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for interval, group in groupby_many(orders, lambda o: o.interval).items():
        costs = [o.cost for o in group]
        lots = [round(o.shares, 2) for o in group]
        lot_counts = Counter(lots)
        top_lot, top_count = lot_counts.most_common(1)[0] if lot_counts else (math.nan, 0)
        corr = pearson([o.price_level for o in group], [o.shares for o in group])
        if len(group) < 30:
            verdict = "insufficient_sample_for_kelly_test"
        elif not math.isfinite(corr) or abs(corr) < 0.35:
            verdict = "not_kelly_discrete_lot"
        else:
            verdict = "needs_edge_model_check"
        rows.append(
            {
                "interval": interval,
                "orders": len(group),
                "cost": sum(costs),
                "median_order_shares": median([o.shares for o in group]),
                "p95_order_shares": percentile([o.shares for o in group], 0.95),
                "distinct_lot_count": len(lot_counts),
                "top_lot_shares": top_lot,
                "top_lot_order_share": safe_div(top_count, len(group)),
                "price_share_corr": corr,
                "kelly_verdict": verdict,
            }
        )
    return sorted(rows, key=lambda r: (-r["cost"], r["interval"]))


def interval_mode_summary(interval_rows: list[dict[str, Any]], lifecycle_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lifecycle_by_interval = {row["interval"]: row for row in lifecycle_rows}
    rows: list[dict[str, Any]] = []
    for row in interval_rows:
        interval = row["interval"]
        lifecycle = lifecycle_by_interval.get(interval, {})
        roi = row.get("roi", math.nan)
        qstar_margin = lifecycle.get("qstar_margin", math.nan)
        both_rate = lifecycle.get("both_sides_rate", math.nan)
        if interval == "5m" and math.isfinite(roi) and roi > 0 and math.isfinite(qstar_margin) and qstar_margin >= 0:
            mode = "primary_candidate"
        elif math.isfinite(roi) and roi > 0:
            mode = "shadow_only_positive_pnl_unproven_qstar"
        else:
            mode = "disable_live_or_shadow_only"
        rows.append(
            {
                "interval": interval,
                "markets": row.get("markets", 0),
                "cost": row.get("cost", math.nan),
                "roi": roi,
                "qstar_margin": qstar_margin,
                "both_sides_rate": both_rate,
                "recommended_mode": mode,
            }
        )
    return rows


def choose_primary_segment(lifecycle: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not lifecycle:
        return None
    return max(lifecycle, key=lambda r: r.get("orders", 0))


def config_from_stats(primary: dict[str, Any] | None, order_rows: list[dict[str, Any]], ladder_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if primary is None:
        return {}
    matching_order = next(
        (r for r in order_rows if r["asset"] == primary["asset"] and r["interval"] == primary["interval"]),
        {},
    )
    rank_lots = []
    for rank in ["1", "2", "3", "4", "5", "6+"]:
        row = next(
            (
                r
                for r in ladder_rows
                if r["asset"] == primary["asset"] and r["interval"] == primary["interval"] and r["rank_bucket"] == rank
            ),
            None,
        )
        if row:
            rank_lots.append(round(row["median_shares"], 4))
    if not rank_lots:
        rank_lots = [round(matching_order.get("median_order_shares", 1.0) or 1.0, 4)]
    start_s = primary.get("median_first_order_elapsed_sec")
    stop_s = primary.get("median_last_order_seconds_before_close")
    gap_s = primary.get("median_market_order_gap_sec")
    return {
        "strategy_id": f"{primary['asset'].lower()}_{primary['interval']}_address_updown_replica_v1",
        "asset": primary["asset"],
        "interval": primary["interval"],
        "order_merge_gap_sec": DEFAULT_ORDER_GAP_SEC,
        "batch_gap_sec": DEFAULT_BATCH_GAP_SEC,
        "start_quote_after_open_sec": round(start_s, 3) if math.isfinite(float(start_s)) else 15,
        "stop_new_orders_before_close_sec": round(stop_s, 3) if math.isfinite(float(stop_s)) else 45,
        "quote_refresh_sec": round(gap_s, 3) if math.isfinite(float(gap_s)) else 5,
        "median_order_shares": round(matching_order.get("median_order_shares", math.nan), 4),
        "p95_order_shares": round(matching_order.get("p95_order_shares", math.nan), 4),
        "ladder_rank_lots": rank_lots,
        "market_budget_median": round(primary.get("median_cost", math.nan), 4),
        "market_budget_soft_cap": round(primary.get("p95_cost", math.nan), 4),
        "market_budget_hard_cap": round(primary.get("p99_cost", math.nan), 4),
        "abs_net_soft_cap": round(primary.get("median_abs_net_shares", math.nan), 4),
        "abs_net_hard_cap": round(primary.get("p90_abs_net_shares", math.nan), 4),
        "qstar_reference": round(primary.get("weighted_qstar", math.nan), 6),
    }


def worked_example(markets: list[dict[str, Any]], orders: list[InferredOrder]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    candidates = [m for m in markets if m["orders"] >= 3 and m["cost"] > 0]
    if not candidates:
        candidates = [m for m in markets if m["orders"] > 0]
    if not candidates:
        return None, []
    market = sorted(candidates, key=lambda r: (-r["cost"], r["market"]))[0]
    seq = [o for o in orders if o.market == market["market"]]
    seq = sorted(seq, key=lambda o: (o.first_ts, o.order_id))[:12]
    up = down = cost = 0.0
    rows: list[dict[str, Any]] = []
    for order in seq:
        if order.side == "BUY":
            if order.outcome == "Up":
                up += order.shares
            elif order.outcome == "Down":
                down += order.shares
            cost += order.cost
        net_side, abs_net, qstar = qstar_for(up, down, cost)
        rows.append(
            {
                "ts_utc": dt.datetime.fromtimestamp(order.first_ts, dt.timezone.utc).isoformat(),
                "outcome": order.outcome,
                "current_advantage": order.current_advantage,
                "advantage_relation": order.advantage_relation,
                "side": order.side,
                "price": order.price_level,
                "shares": order.shares,
                "cost": order.cost,
                "cum_up": up,
                "cum_down": down,
                "cum_cost": cost,
                "net_side": net_side,
                "abs_net": abs_net,
                "qstar": qstar,
            }
        )
    return market, rows


def generate_report(
    *,
    out_dir: Path,
    input_csv: Path,
    args: argparse.Namespace,
    trades: list[Trade],
    orders: list[InferredOrder],
    audit: dict[str, Any],
    interval_rows: list[dict[str, Any]],
    market_rows: list[dict[str, Any]],
    lifecycle_rows: list[dict[str, Any]],
    order_rows: list[dict[str, Any]],
    batch_rows: list[dict[str, Any]],
    ladder_rows: list[dict[str, Any]],
    price_rows: list[dict[str, Any]],
    phase_rows: list[dict[str, Any]],
    sequence_rows: list[dict[str, Any]],
    qstar_anchor_rows: list[dict[str, Any]],
    final_lock_rows: list[dict[str, Any]],
    advantage_rows: list[dict[str, Any]],
    advantage_streak_rows: list[dict[str, Any]],
    size_diagnostic_rows: list[dict[str, Any]],
    interval_mode_rows: list[dict[str, Any]],
) -> tuple[Path, dict[str, Any]]:
    generated = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    primary = choose_primary_segment(lifecycle_rows)
    config = config_from_stats(primary, order_rows, ladder_rows)
    example_market, example_rows = worked_example(market_rows, orders)
    resolved = [t for t in trades if t.result in {"WIN", "LOSS"}]
    total_cost = sum(t.usdc for t in trades)
    resolved_cost = sum(t.usdc for t in resolved)
    total_pnl = sum(t.pnl or 0.0 for t in resolved)
    buy_only = all(t.side == "BUY" for t in trades)
    both_sides_rate = safe_div(sum(1 for m in market_rows if m["both_sides"]), len(market_rows))
    net_known = [m for m in market_rows if m["net_correct"] is not None]
    net_correct = safe_div(sum(1 for m in net_known if m["net_correct"]), len(net_known))
    multi_fill_order_rate = safe_div(sum(1 for o in orders if o.fill_count > 1), len(orders))
    kline_trades = [t for t in trades if t.advantage_relation and t.advantage_relation != "no_kline"]
    advantage_coverage = safe_div(len(kline_trades), len(trades))
    primary_mode = next((r for r in interval_mode_rows if r.get("recommended_mode") == "primary_candidate"), interval_mode_rows[0] if interval_mode_rows else {})
    report_path = out_dir / "strategy_replication_report.md"
    min_data_warning = ""
    if len(market_rows) < args.min_report_markets:
        min_data_warning = (
            f"\n> 数据不足提示：样本只有 `{len(market_rows)}` 个 BTC Up/Down 市场，低于默认 `{args.min_report_markets}`。"
            "本报告仍给出复刻框架，但 live 策略不得上线，只能作为研究草案。\n"
        )

    lines: list[str] = []
    lines.append("# Polymarket BTC Up/Down 地址策略像素级复刻报告\n")
    lines.append("## 技术摘要\n")
    lines.append(
        f"- 地址：`{args.user or infer_user_from_rows(trades) or 'input-csv'}`\n"
        f"- 输入：`{input_csv}`\n"
        f"- 生成时间 UTC：`{generated}`\n"
        f"- 默认/实际窗口：`{args.days:g}` 天；若使用 `--input`，窗口以 CSV 为准。\n"
        f"- BTC Up/Down 成交行：`{len(trades):,}`；市场：`{len(market_rows):,}`；inferred orders：`{len(orders):,}`。\n"
        f"- 总成本：`{fmt_num(total_cost)}`；已结算/已拉取成本：`{fmt_num(resolved_cost)}`；"
        f"已标记 PnL：`{fmt_num(total_pnl)}`；resolved ROI：`{fmt_pct(safe_div(total_pnl, resolved_cost))}`。\n"
        f"- BUY-only：`{buy_only}`；market both-side rate：`{fmt_pct(both_sides_rate)}`；multi-fill order rate：`{fmt_pct(multi_fill_order_rate)}`；final net correct：`{fmt_pct(net_correct)}`。\n"
        f"- BTCUSDT 当前优势边覆盖率：`{fmt_pct(advantage_coverage)}`；推荐主模式：`{primary_mode.get('interval', 'n/a')}` / `{primary_mode.get('recommended_mode', 'n/a')}`。"
    )
    lines.append(min_data_warning)
    lines.append(
        "\n本报告的复刻边界是“从地址成交历史复刻可观察行为与可验证执行规则”。"
        "若没有订单 ID、撤单、未成交单、maker/taker 标记、队列位置和底层价格路径，本报告不会声称拿到了真实源码。"
        "它会把可确定事实、强推断、弱推断和 live 上线前必须补的数据分开。"
    )

    lines.append("\n## 证据范围与口径\n")
    lines.append(
        f"- 主输入：`{input_csv}`。\n"
        f"- settlement 口径：`activityOutcomeResult/tradeOutcomeResult` 与 `activityPnLUSDC/tradePnLUSDC`，resolved 成本覆盖 `{fmt_pct(safe_div(resolved_cost, total_cost))}`。\n"
        f"- BTCUSDT kline 口径：`btcOpen/btcTradeClose/currentAdvantage/advantageRelation`，当前优势边覆盖 `{fmt_pct(advantage_coverage)}`。\n"
        f"- inferred order 口径：同 market/outcome/side/rounded price，fill gap <= `{args.order_gap_sec}s`。\n"
        f"- quote batch 口径：同 market 内 inferred order first timestamp gap <= `{args.batch_gap_sec}s`。\n"
        "- 确定事实：成交行、价格、size、时间、side、settlement、PnL、BTC 当前优势边字段。\n"
        "- 强推断：限价挂单风格、微阶梯、双边库存、q* gate、顺/逆势候选池。\n"
        "- 不可直接确定：真实 order id、撤单、未成交单、maker/taker、队列位置、完整 L2、真实 alpha 系数、账户级 bankroll。"
    )

    lines.append("\n## 一页机制图\n")
    lines.append(
        "```text\n"
        "address trades -> BTC Up/Down filter -> Polymarket settlement labels\n"
        "       -> optional BTCUSDT 1s kline join from binance-spot-kline-history\n"
        "       -> inferred orders by same market/outcome/side/price within 5s\n"
        "       -> quote batches by market time gap within 5s\n"
        "       -> ladder ranks, lifecycle timing, budget, size lots\n"
        "       -> inventory ledger: Up shares, Down shares, C cost, q*\n"
        "       -> replication config + backtest/shadow/live gates\n"
        "```\n"
    )

    lines.append("## 数据来源与过滤规则\n")
    lines.append(
        f"- 原始 CSV 行数：`{audit['input_rows']:,}`。\n"
        f"- BTC Up/Down 过滤后行数：`{audit['btc_updown_trade_rows']:,}`。\n"
        f"- 过滤逻辑：slug/title 中必须出现 `btc` 或 `bitcoin`，并包含 `updown`、`up-or-down`、`up or down` 或等价描述。\n"
        f"- settlement 字段优先级：`activityOutcomeResult` / `tradeOutcomeResult`；PnL 字段优先级：`activityPnLUSDC` / `tradePnLUSDC`。\n"
        f"- settlement 结果优先来自 `polymarket-address-activity` / Gamma；若启用 Binance kline，BTCUSDT 1s 只用于补全未拉到或仍 open/missing 的 BTC 市场，并在 CSV 中写入 `btcOpen` / `btcClose` / `settlementKlineCsv`。\n"
        f"- 时间字段：优先 `timestamp` Unix 秒；显示统一使用 UTC。\n"
        f"- market_start：优先从 slug 末尾 10 位 Unix 秒解析；否则使用 market end 字段进行部分生命周期分析。\n"
        f"- inferred order：同 market + outcome + side + rounded price，连续 fill gap <= `{args.order_gap_sec}s`。\n"
        f"- quote batch：同 market 中 inferred order 的 first timestamp gap <= `{args.batch_gap_sec}s`。\n"
    )
    lines.append(
        markdown_table(
            [
                {"metric": "assets", "value": json.dumps(audit["assets"], ensure_ascii=False)},
                {"metric": "intervals", "value": json.dumps(audit["intervals"], ensure_ascii=False)},
                {"metric": "side_counts", "value": json.dumps(audit["side_counts"], ensure_ascii=False)},
                {"metric": "result_counts", "value": json.dumps(audit["result_counts"], ensure_ascii=False)},
            ],
            [("metric", "metric"), ("value", "value")],
        )
    )

    lines.append("\n## 市场机制、订单类型和费用假设\n")
    lines.append(
        "- Up/Down 市场是二元 payoff：买中结算边的 share 最终按 `1` 兑付，买错边按 `0` 兑付。\n"
        "- BUY 行的历史 PnL 使用 settlement enrichment 字段；SELL 行不强行按同一公式解释，报告会保留 side_counts。\n"
        "- 费用：若 CSV PnL 已含费用则以 CSV 为准；若 live 复刻需要估算，默认使用 `fee_rate = 0.07 * min(price, 1-price)` 的保守 Polymarket 费用近似，并在回放中做 `0x/0.5x/1x/2x` 敏感性。\n"
        "- maker/taker：CSV 没有逐笔 maker/taker 标记。若 multi-fill same-price 与低价阶梯明显，默认实现用 `post-only` 限价；若样本显示高价单笔或 SELL 多，应单独降级为未知执行风格。\n"
    )

    lines.append("\n## 总体表现与市场分布\n")
    lines.append(
        markdown_table(
            interval_rows,
            [
                ("asset", "asset"),
                ("interval", "interval"),
                ("markets", "markets"),
                ("fills", "fills"),
                ("cost", "cost"),
                ("pnl", "pnl"),
                ("roi", "roi"),
                ("avg_price", "avg_price"),
                ("resolved_rate", "resolved_rate"),
            ],
        )
    )
    lines.append("\n### 5m/15m 实盘范围判定\n")
    lines.append(
        markdown_table(
            interval_mode_rows,
            [
                ("interval", "interval"),
                ("markets", "markets"),
                ("cost", "cost"),
                ("roi", "roi"),
                ("qstar_margin", "qstar_margin"),
                ("both_sides_rate", "both_sides_rate"),
                ("recommended_mode", "recommended_mode"),
            ],
        )
    )
    lines.append(
        "\n判定规则：只有 ROI、q* margin、双边库存和样本量同时过关的 interval 才能成为主策略候选；"
        "其余 interval 即使短期盈利，也默认 `shadow_only`，不能把一个地址的历史收益直接外推成 live 参数。"
    )

    lines.append("\n## 生命周期、频率和库存质量\n")
    lines.append(
        markdown_table(
            lifecycle_rows,
            [
                ("asset", "asset"),
                ("interval", "interval"),
                ("markets", "markets"),
                ("orders", "orders"),
                ("both_sides_rate", "both_sides_rate"),
                ("net_correct_rate", "net_correct_rate"),
                ("weighted_net_correct_rate", "weighted_net_correct"),
                ("weighted_qstar", "weighted_qstar"),
                ("qstar_margin", "qstar_margin"),
                ("median_first_order_elapsed_sec", "first_s"),
                ("median_last_order_seconds_before_close", "last_before_close_s"),
                ("median_market_order_gap_sec", "gap_s"),
                ("median_cost", "median_cost"),
                ("p95_cost", "p95_cost"),
                ("median_abs_net_shares", "median_abs_net"),
                ("p90_abs_net_shares", "p90_abs_net"),
            ],
        )
    )

    lines.append("\n## inferred order 证据\n")
    lines.append(
        markdown_table(
            order_rows,
            [
                ("asset", "asset"),
                ("interval", "interval"),
                ("orders", "orders"),
                ("fills", "fills"),
                ("markets", "markets"),
                ("cost", "cost"),
                ("multi_fill_order_rate", "multi_fill_rate"),
                ("multi_fill_cost_rate", "multi_fill_cost"),
                ("median_fills_per_order", "median_fills"),
                ("p95_fills_per_order", "p95_fills"),
                ("median_order_shares", "median_shares"),
                ("p95_order_shares", "p95_shares"),
                ("median_order_cost", "median_order_cost"),
                ("p95_order_cost", "p95_order_cost"),
            ],
        )
    )
    lines.append(
        "\n解释：multi-fill same-price inferred order 越高，越支持限价挂单或挂单被连续打中的解释。"
        "但这仍不是订单 ID 级证明，因为 CSV 看不到未成交单和撤单。"
    )

    lines.append("\n## quote batch 和阶梯结构\n")
    lines.append(
        markdown_table(
            batch_rows,
            [
                ("asset", "asset"),
                ("interval", "interval"),
                ("batches", "batches"),
                ("markets", "markets"),
                ("orders", "orders"),
                ("cost", "cost"),
                ("both_side_batch_rate", "both_side_batch"),
                ("both_side_cost_rate", "both_side_cost"),
                ("multi_order_batch_rate", "multi_order_batch"),
                ("median_orders_per_batch", "median_orders_batch"),
                ("p90_distinct_price_levels", "p90_price_levels"),
            ],
        )
    )
    lines.append("\n阶梯 rank 中，BUY 价格最高为 rank 1，更低价格为更深阶梯。")
    lines.append(
        markdown_table(
            ladder_rows,
            [
                ("asset", "asset"),
                ("interval", "interval"),
                ("rank_bucket", "rank"),
                ("side_price_levels", "levels"),
                ("cost", "cost"),
                ("shares", "shares"),
                ("median_shares", "median_shares"),
                ("cost_share", "cost_share"),
            ],
        )
    )

    lines.append("\n## price band 与 size 是否像 Kelly\n")
    lines.append(
        markdown_table(
            price_rows,
            [
                ("asset", "asset"),
                ("interval", "interval"),
                ("price_band", "price_band"),
                ("orders", "orders"),
                ("markets", "markets"),
                ("cost", "cost"),
                ("shares", "shares"),
                ("pnl", "pnl"),
                ("roi", "roi"),
                ("avg_order_shares", "avg_order_shares"),
                ("avg_price", "avg_price"),
            ],
        )
    )
    lines.append(
        "\n判定规则：如果 shares 在价格桶间主要是离散 lot 且不随 edge 连续缩放，就不能称为 Kelly。"
        "复刻实现默认使用离散 lot + rank multiplier + q*/budget gate，而不是 `stake = bankroll * Kelly(p, price)`。"
    )
    lines.append("\n### Size/Kelly 诊断表\n")
    lines.append(
        markdown_table(
            size_diagnostic_rows,
            [
                ("interval", "interval"),
                ("orders", "orders"),
                ("cost", "cost"),
                ("median_order_shares", "median_shares"),
                ("p95_order_shares", "p95_shares"),
                ("distinct_lot_count", "distinct_lots"),
                ("top_lot_shares", "top_lot"),
                ("top_lot_order_share", "top_lot_order_share"),
                ("price_share_corr", "price_share_corr"),
                ("kelly_verdict", "verdict"),
            ],
        )
    )
    lines.append(
        "\n如果 `price_share_corr` 不强、`top_lot_order_share` 明显、且 median/p95 shares 呈离散档位，"
        "应实现为 `base_lot_shares -> rank_multiplier -> risk_multiplier`，而不是 Kelly 连续下注函数。"
    )

    lines.append("\n## 市场阶段收益\n")
    lines.append(
        markdown_table(
            phase_rows,
            [
                ("asset", "asset"),
                ("interval", "interval"),
                ("phase", "phase"),
                ("fills", "fills"),
                ("markets", "markets"),
                ("cost", "cost"),
                ("pnl", "pnl"),
                ("roi", "roi"),
                ("winner_cost_rate", "winner_cost_rate"),
            ],
        )
    )

    lines.append("\n## 序列：是否连续买强边或弱边\n")
    lines.append(
        markdown_table(
            sequence_rows,
            [
                ("asset", "asset"),
                ("interval", "interval"),
                ("prev_expost", "prev"),
                ("order_expost_side", "current"),
                ("orders", "orders"),
                ("cost", "cost"),
                ("order_share_from_prev", "share_from_prev"),
            ],
        )
    )
    lines.append(
        "\n`winner_proxy` / `loser_proxy` 是 ex-post 标签，只说明最终结果，不代表当时 live alpha。"
        "若连续 loser_proxy 很多，可能是弱边便宜 optionality、库存修复，也可能是错误 alpha；必须结合底层价格路径验证。"
    )

    lines.append("\n## q* 库存账本\n")
    lines.append(
        "设 `U` 为 Up shares，`D` 为 Down shares，`C` 为累计买入成本。\n\n"
        "```text\n"
        "if U > D: q*_up = (C - D) / (U - D)\n"
        "if D > U: q*_down = (C - U) / (D - U)\n"
        "if U == D: no directional q*, evaluate bundle cost and future optionality\n"
        "```\n\n"
        "每个候选订单必须先模拟成交后库存，再用 `p_side >= q*_after + required_margin` 判断是否扩大净风险。"
    )
    lines.append("\n### q* 动态锚点\n")
    lines.append(
        markdown_table(
            qstar_anchor_rows,
            [
                ("interval", "interval"),
                ("anchor", "anchor"),
                ("markets", "markets"),
                ("median_qstar", "median_qstar"),
                ("median_abs_net_shares", "median_abs_net"),
                ("median_cost_so_far", "median_cost_so_far"),
                ("median_elapsed_frac", "median_elapsed_frac"),
                ("net_correct_rate", "net_correct_rate"),
            ],
            max_rows=40,
        )
    )
    lines.append(
        "\n解释：如果 `after_first` 接近随机而 `after_last` 明显更好，说明方向 alpha 不是开盘一次性给定，"
        "而是在运行中由 BTC 路径、盘口和库存约束逐步形成。复刻时应控制 `qstar_after <= p_side - buffer`，不是追一个固定 q*。"
    )
    lines.append("\n### 最终净仓锁定时点\n")
    lines.append(
        markdown_table(
            final_lock_rows,
            [
                ("interval", "interval"),
                ("markets", "markets"),
                ("locked_markets", "locked_markets"),
                ("lock_rate", "lock_rate"),
                ("median_lock_elapsed_frac", "lock_elapsed_frac"),
                ("median_lock_cost_fraction", "lock_cost_fraction"),
                ("median_orders_before_lock", "orders_before_lock"),
                ("median_final_abs_net", "final_abs_net"),
                ("median_final_qstar", "final_qstar"),
            ],
        )
    )
    lines.append(
        "\n锁定含义：第一次出现最终净边并且之后不再切换。若锁定发生在市场中后段，说明前期更像建立可调整库存，"
        "而不是一开盘就单边押注。"
    )

    lines.append("\n## alpha 与方向来源\n")
    lines.append(
        "仅凭地址成交 CSV 不能直接恢复 live alpha。可确定的是最终净仓与结算边之间的关系，以及订单在生命周期中的偏向。"
        "若要从本报告上线策略，必须使用 BTCUSDT 1s kline/orderbook 训练或校准 fair value 模型。\n\n"
        "默认 live alpha 模型规格：\n\n"
        "```yaml\n"
        "label: market_winning_outcome_up\n"
        "training_window: rolling_45_days_before_trade_day\n"
        "validation_window: next_7_days_walk_forward\n"
        "sample_frequency: every_1s_or_5s_while_market_open\n"
        "model: logistic_regression_or_calibrated_gradient_boosting\n"
        "features:\n"
        "  - btc_market_family\n"
        "  - interval\n"
        "  - elapsed_frac\n"
        "  - seconds_remaining_sqrt\n"
        "  - ret_from_open_bps\n"
        "  - abs_ret_from_open_bps\n"
        "  - ret_1s_bps\n"
        "  - ret_3s_bps\n"
        "  - ret_5s_bps\n"
        "  - ret_15s_bps\n"
        "  - realized_vol_15s_bps\n"
        "  - realized_vol_30s_bps\n"
        "  - range_so_far_bps\n"
        "  - clean_book_implied_probability\n"
        "fallback_without_btcusdt_kline: research_report_only_no_live_orders\n"
        "```\n"
    )
    lines.append("\n### 当前优势边成交关系\n")
    lines.append(
        markdown_table(
            advantage_rows,
            [
                ("interval", "interval"),
                ("advantage_relation", "relation"),
                ("fills", "fills"),
                ("markets", "markets"),
                ("cost", "cost"),
                ("cost_share", "cost_share"),
                ("pnl", "pnl"),
                ("roi", "roi"),
                ("win_rate", "win_rate"),
            ],
            max_rows=40,
        )
    )
    lines.append(
        "\n`with_current_advantage` 表示成交 outcome 与成交秒 BTC 相对开盘方向一致；"
        "`against_current_advantage` 表示优势边为 Up 时成交 Down，或优势边为 Down 时成交 Up。"
        "若逆势成本占比不是接近 0，它就是策略结构的一部分；复刻时只能在便宜 optionality、库存修复或 alpha 模糊时保留，不能追价。"
    )
    lines.append("\n### 顺势/逆势连续成交 streak\n")
    lines.append(
        markdown_table(
            advantage_streak_rows,
            [
                ("interval", "interval"),
                ("relation", "relation"),
                ("streaks", "streaks"),
                ("markets", "markets"),
                ("median_streak_orders", "median_streak_orders"),
                ("p90_streak_orders", "p90_streak_orders"),
                ("max_streak_orders", "max_streak_orders"),
                ("cost", "cost"),
            ],
            max_rows=40,
        )
    )
    lines.append(
        "\n这张表用于识别它是否机械地强弱边轮换。若顺势或逆势 streak 明显存在，复刻逻辑应是两个独立 candidate pool "
        "分别过 q*/net/budget/book gate，而不是“买完强边必须买弱边”。"
    )

    lines.append("\n## 样本派生的复刻配置\n")
    lines.append("```json\n" + json.dumps(config, ensure_ascii=False, indent=2) + "\n```\n")
    lines.append(
        "这些值不是永恒参数，而是该地址在本窗口内的行为锚点。上线前必须在新窗口重算，并使用 shadow gate。"
    )
    if config:
        hard_cap = config.get("market_budget_hard_cap", "sample_p99_market_cost")
        soft_cap = config.get("market_budget_soft_cap", "sample_p95_market_cost")
        abs_net_soft = config.get("abs_net_soft_cap", "sample_median_abs_net")
        abs_net_hard = config.get("abs_net_hard_cap", "sample_p90_abs_net")
        lines.append("\n## 可直接实现的默认参数\n")
        lines.append(
            "```yaml\n"
            "price_tick: 0.01\n"
            "min_order_price: 0.01\n"
            "max_order_price: 0.99\n"
            "post_only: true\n"
            "order_ttl_sec: 5\n"
            "post_only_reject_retry_ticks: 1\n"
            "post_only_reject_max_retries: 1\n"
            "qstar_required_margin: 0.025\n"
            "model_probability_buffer: 0.020\n"
            "execution_buffer: 0.010\n"
            "fee_buffer: 0.003\n"
            "weak_side_size_multiplier: 0.35\n"
            "weak_side_allow_when:\n"
            "  - qstar_after <= qstar_before - 0.010\n"
            "  - abs_net_after <= abs_net_before * 0.85\n"
            "  - price <= p_side - 0.060\n"
            f"market_budget_soft_cap_usdc: {soft_cap}\n"
            f"market_budget_hard_cap_usdc: {hard_cap}\n"
            f"abs_net_soft_cap_shares: {abs_net_soft}\n"
            f"abs_net_hard_cap_shares: {abs_net_hard}\n"
            "cancel_all_when:\n"
            "  data_lag_sec: 2\n"
            "  book_age_ms: 500\n"
            "  reconciliation_gap_usdc: 1.00\n"
            "  consecutive_post_only_rejects: 3\n"
            "```\n"
        )

    lines.append("\n## 决策状态机\n")
    lines.append(
        "```text\n"
        "on each market tick:\n"
        "  if market is not BTC Up/Down or interval not in enabled config: no-op\n"
        "  if data lag > 2s or book stale > 500ms: cancel open quotes and pause\n"
        "  if elapsed < start_quote_after_open_sec: no-op\n"
        "  if seconds_to_close < stop_new_orders_before_close_sec: cancel or do not add risk\n"
        "  estimate p_up/p_down from live alpha model\n"
        "  reconcile filled inventory from user activity/order API\n"
        "  for side in Up/Down:\n"
        "    build rank ladder from anchor price and rank_lots\n"
        "    simulate each candidate fill\n"
        "    accept expand only if p_side >= qstar_after + required_margin\n"
        "    accept weak-side only if it reduces abs_net or is cheap optionality\n"
        "  enforce market_budget_soft_cap, market_budget_hard_cap, abs_net_hard_cap\n"
        "  send post-only GTC/GTD BUY intents; on post-only reject, lower one tick or skip\n"
        "```\n"
    )

    lines.append("\n## Live 实现数据模型\n")
    lines.append(
        "```python\n"
        "@dataclass\n"
        "class MarketState:\n"
        "    slug: str\n"
        "    interval: Literal['5m', '15m']\n"
        "    open_time: datetime\n"
        "    close_time: datetime\n"
        "    now: datetime\n"
        "    elapsed_s: float\n"
        "    seconds_to_close: float\n"
        "    btc_open: float\n"
        "    btc_now: float\n"
        "    p_up: float\n"
        "    p_down: float\n"
        "    current_advantage: Literal['Up', 'Down', 'Tie']\n"
        "    up_book: SideBook\n"
        "    down_book: SideBook\n"
        "    inventory: InventoryState\n"
        "    market_budget_used: float\n"
        "\n"
        "@dataclass\n"
        "class InventoryState:\n"
        "    up_shares: float\n"
        "    down_shares: float\n"
        "    total_cost: float\n"
        "\n"
        "    def qstar(self) -> float | None:\n"
        "        if self.up_shares > self.down_shares:\n"
        "            return (self.total_cost - self.down_shares) / (self.up_shares - self.down_shares)\n"
        "        if self.down_shares > self.up_shares:\n"
        "            return (self.total_cost - self.up_shares) / (self.down_shares - self.up_shares)\n"
        "        return None\n"
        "\n"
        "@dataclass\n"
        "class CandidateOrder:\n"
        "    side: Literal['Up', 'Down']\n"
        "    rank: int\n"
        "    limit_price: Decimal\n"
        "    shares: Decimal\n"
        "    reason: Literal['expand', 'trim', 'cheap_optionality', 'new_net']\n"
        "    p_side: float\n"
        "    qstar_after: float | None\n"
        "    abs_net_after: float\n"
        "    budget_after: float\n"
        "    post_only: bool = True\n"
        "    ttl_s: int = 4\n"
        "```\n"
    )

    lines.append("\n## 价格、阶梯和 size 规则\n")
    lines.append(
        "```text\n"
        "fair_cap = p_side - qstar_required_margin - execution_buffer - fee_buffer\n"
        "book_cap = best_ask - tick\n"
        "join_cap = best_bid + tick if best_bid is clean else book_cap\n"
        "anchor = floor_to_tick(min(fair_cap, book_cap, join_cap))\n"
        "level_price[i] = anchor - offsets_ticks[i] * tick\n"
        "shares[i] = round_lot(ladder_rank_lots[i] * side_multiplier * edge_multiplier)\n"
        "```\n\n"
        "Default offsets: `[0, 1, 2, 3, 5, 8]` ticks. If sample has fewer ranks, reuse the last observed rank lot for deeper levels only in shadow."
    )

    lines.append("\n## 风控硬阈值\n")
    lines.append(
        "```yaml\n"
        "market_budget_soft_cap: sample_p95_market_cost\n"
        "market_budget_hard_cap: sample_p99_market_cost\n"
        "abs_net_soft_cap: sample_median_abs_net\n"
        "abs_net_hard_cap: sample_p90_abs_net\n"
        "data_lag_pause_sec: 2\n"
        "book_age_pause_ms: 500\n"
        "post_only_reject_action: lower_one_tick_once_else_skip\n"
        "unexplained_reconciliation_gap_action: cancel_all_and_pause\n"
        "resolved_market_loss_cooldown_min: 30\n"
        "daily_drawdown_stop: min(3 * sample_median_market_loss, 2% account_equity)\n"
        "resume_after_pause: require data_health_ok and manual_or_scripted_reconciliation_ok\n"
        "```\n"
    )

    lines.append("\n## Candidate 生成与 risk gate 伪代码\n")
    lines.append(
        "默认辅助函数必须按以下阈值实现，不能留成空壳：\n\n"
        "```text\n"
        "book_quality_clean(book):\n"
        "  book.age_ms <= 500\n"
        "  recv_lag_ms <= 500\n"
        "  best_bid < best_ask\n"
        "  spread <= 0.03\n"
        "  top_size_shares >= 5\n"
        "\n"
        "required_margin(market): qstar_required_margin = 0.025 unless shadow calibration overwrites it\n"
        "dynamic_budget_cap(market): min(market_budget_hard_cap_usdc, market_budget_soft_cap_usdc * edge_multiplier)\n"
        "dynamic_net_cap(market, side): min(abs_net_hard_cap_shares, abs_net_soft_cap_shares * edge_multiplier)\n"
        "edge_multiplier: clamp((abs(p_side - 0.5) - 0.03) / 0.07, 0.40, 1.00)\n"
        "is_materially_cheap(order): p_side - limit_price >= 0.060 for weak side, 0.030 for strong side\n"
        "```\n"
    )
    lines.append(
        "```python\n"
        "def build_ladder_candidates(market, side, p_side, inventory):\n"
        "    book = market.book(side)\n"
        "    if not book_quality_clean(book):\n"
        "        return []\n"
        "\n"
        "    fair_cap = p_side - qstar_buffer(market, side) - execution_buffer(market) - fee_buffer(book)\n"
        "    book_cap = book.best_ask - book.tick\n"
        "    join_cap = book.best_bid + book.tick if book.best_bid < book.best_ask else book_cap\n"
        "    anchor = floor_to_tick(min(fair_cap, book_cap, join_cap), book.tick)\n"
        "    if anchor <= 0:\n"
        "        return []\n"
        "\n"
        "    out = []\n"
        "    for rank, offset in enumerate([0, 1, 2, 3, 5, 8], start=1):\n"
        "        price = anchor - offset * book.tick\n"
        "        shares = lot_size_for_rank_price(rank, price, market, side)\n"
        "        simulated = inventory.after_buy(side, price, shares)\n"
        "        out.append(CandidateOrder(\n"
        "            side=side,\n"
        "            rank=rank,\n"
        "            limit_price=price,\n"
        "            shares=shares,\n"
        "            reason=classify_reason(inventory, simulated, side, market.current_advantage, p_side),\n"
        "            p_side=p_side,\n"
        "            qstar_after=simulated.qstar(),\n"
        "            abs_net_after=simulated.abs_net,\n"
        "            budget_after=simulated.total_cost,\n"
        "        ))\n"
        "    return out\n"
        "\n"
        "def risk_gate_accepts(order, market, inventory):\n"
        "    if market.interval != '5m':\n"
        "        return False\n"
        "    if market.seconds_to_close < stop_new_orders_before_close_s:\n"
        "        return False\n"
        "    if order.limit_price >= market.book(order.side).best_ask:\n"
        "        return False\n"
        "    if order.budget_after > dynamic_budget_cap(market):\n"
        "        return False\n"
        "\n"
        "    if order.reason in {'expand', 'new_net'}:\n"
        "        if order.abs_net_after > dynamic_net_cap(market, order.side):\n"
        "            return False\n"
        "        return order.qstar_after is not None and order.p_side >= order.qstar_after + required_margin(market)\n"
        "\n"
        "    if order.reason in {'trim', 'cheap_optionality'}:\n"
        "        return improves_qstar(order, inventory) or reduces_abs_net(order, inventory) or is_materially_cheap(order)\n"
        "\n"
        "    return False\n"
        "```\n"
    )

    lines.append("\n## 回放、shadow 和上线 gate\n")
    lines.append(
        "```yaml\n"
        "offline_replay_required:\n"
        "  min_resolved_markets: 300\n"
        "  fill_models: [observed_fill_replay, post_only_touch_proxy, one_tick_worse]\n"
        "  fee_sensitivity: [0x, 0.5x, 1x, 2x]\n"
        "  pass:\n"
        "    roi_after_fee: '> 0'\n"
        "    rolling_100_market_pnl: '> 0'\n"
        "    qstar_margin: '>= 1.5 percentage points when q* is applicable'\n"
        "    behavior_distance: lifecycle, ladder, budget, and inventory metrics within observed median +/- 25%, or explained\n"
        "shadow_required:\n"
        "  duration_days: 7\n"
        "  outputs: [order_intents.ndjson, simulated_fills.ndjson, inventory_snapshots.ndjson, scorecard.csv]\n"
        "live_ramp:\n"
        "  phase_1: 0.10x sample budget scale\n"
        "  phase_2: 0.25x after 500 resolved shadow/live markets pass\n"
        "  rollback: any reconciliation gap, data lag incident, or unexplained loss cluster\n"
        "```\n"
    )

    lines.append("\n## 行为复刻 Scorecard\n")
    primary_interval = config.get("interval", "")
    primary_order = next((row for row in order_rows if row.get("interval") == primary_interval), {})
    primary_batch = next((row for row in batch_rows if row.get("interval") == primary_interval), {})
    primary_lifecycle = next((row for row in lifecycle_rows if row.get("interval") == primary_interval), {})
    primary_ladder_rank1 = next((row for row in ladder_rows if row.get("interval") == primary_interval and row.get("rank_bucket") == "1"), {})
    scorecard_rows = [
        {"metric": "5m ROI after fees", "target": "> 0", "reason": "收益为必要但不充分条件"},
        {"metric": "qstar_margin", "target": ">= 1.5pp when applicable", "reason": "净仓方向必须覆盖 q*"},
        {"metric": "weighted_net_correct", "target": f"{fmt_pct(primary_lifecycle.get('weighted_net_correct_rate', math.nan))} +/- 25%", "reason": "方向质量不能退化"},
        {"metric": "both_sides_market_rate", "target": "90%-99%", "reason": "生命周期双边库存特征"},
        {"metric": "both_side_batch_rate", "target": f"{fmt_pct(primary_batch.get('both_side_batch_rate', math.nan))} +/- 25%", "reason": "每轮不机械双边"},
        {"metric": "median_first_order_elapsed", "target": f"{fmt_num(config.get('start_quote_after_open_sec', math.nan))}s +/- 25%", "reason": "开始挂单时点"},
        {"metric": "median_last_before_close", "target": f"{fmt_num(config.get('stop_new_orders_before_close_sec', math.nan))}s +/- 25%", "reason": "避免末秒追单"},
        {"metric": "median_order_gap", "target": f"{fmt_num(config.get('quote_refresh_sec', math.nan))}s +/- 25%", "reason": "刷新频率"},
        {"metric": "multi_fill_order_rate", "target": f"{fmt_pct(primary_order.get('multi_fill_order_rate', math.nan))} +/- 25%", "reason": "限价挂单代理"},
        {"metric": "rank1 ladder cost share", "target": f"{fmt_pct(primary_ladder_rank1.get('cost_share', math.nan))} +/- 25%", "reason": "微阶梯形状"},
        {"metric": "median_order_shares", "target": f"{fmt_num(config.get('median_order_shares', math.nan))} +/- 25%", "reason": "离散 lot 复刻"},
        {"metric": "against_current_cost_share", "target": "nonzero but gated", "reason": "弱边 optionality/库存修复"},
        {"metric": "stale_or_crossing_cost_share", "target": "<= 5%", "reason": "禁止追价和 stale book"},
        {"metric": "15m live exposure", "target": "0 unless separately proven", "reason": "15m 默认不继承 5m 结论"},
    ]
    lines.append(markdown_table(scorecard_rows, [("metric", "metric"), ("target", "target"), ("reason", "reason")], max_rows=40))

    lines.append("\n## PnL 归因框架\n")
    lines.append(
        "- Direction alpha：最终净仓是否偏向 winning outcome。\n"
        "- Execution improvement：成交价是否优于同秒/邻近盘口；没有 orderbook 时不能证明。\n"
        "- Inventory optionality：双边库存降低亏损底座，q* 低于预测概率。\n"
        "- Adverse selection：高价、临近收盘、stale book 或连续错误净仓导致的亏损。\n"
        "- Fees/rebates：CSV 未完全暴露时必须做敏感性，而不是只看毛收益。\n"
        "- Capacity：用 p95/p99 market cost 和 top-of-book notional 验证，不能线性放大。"
    )

    lines.append("\n## 实现模块拆分与交付顺序\n")
    lines.append(
        "```text\n"
        "btc_updown_replica/\n"
        "  data_layer/\n"
        "    polymarket_activity_loader.py\n"
        "    btcusdt_kline_store.py\n"
        "    polymarket_orderbook_store.py\n"
        "  signal_layer/\n"
        "    probability_engine.py\n"
        "    diffusion_probability.py\n"
        "    calibration.py\n"
        "  inventory_layer/\n"
        "    qstar.py\n"
        "    inventory_state.py\n"
        "    inventory_targets.py\n"
        "  execution_layer/\n"
        "    ladder_quote_engine.py\n"
        "    risk_gate.py\n"
        "    post_only_router.py\n"
        "    order_reconciler.py\n"
        "  replay/\n"
        "    trade_csv_replay.py\n"
        "    orderbook_fill_simulator.py\n"
        "    behavior_scorecard.py\n"
        "  monitoring/\n"
        "    shadow_logger.py\n"
        "    regime_monitor.py\n"
        "    kill_switch.py\n"
        "```\n\n"
        "最低交付顺序：\n\n"
        "1. `qstar.py`：纯函数测试，锁死 q* 公式。\n"
        "2. `inventory_state.py`：支持模拟成交后的 U/D/C、q*、abs_net。\n"
        "3. `probability_engine.py`：用 BTCUSDT 1s 特征产出校准后的 `p_up/p_down`。\n"
        "4. `ladder_quote_engine.py`：生成 post-only BUY 微阶梯候选。\n"
        "5. `risk_gate.py`：实现 q*/net/budget/book/current_advantage gate。\n"
        "6. `orderbook_fill_simulator.py`：用 1s orderbook 回放 passive fill 代理。\n"
        "7. `post_only_router.py`：最后接真实 CLOB，默认 dry-run。"
    )

    lines.append("\n## Worked Example\n")
    if example_market and example_rows:
        lines.append(
            f"示例市场：`{example_market['market']}`，asset `{example_market['asset']}`，interval `{example_market['interval']}`，"
            f"cost `{fmt_num(example_market['cost'])}`，PnL `{fmt_num(example_market['pnl'])}`。"
        )
        lines.append(
            markdown_table(
                example_rows,
                [
                    ("ts_utc", "ts_utc"),
                    ("outcome", "outcome"),
                    ("current_advantage", "current_adv"),
                    ("advantage_relation", "adv_relation"),
                    ("side", "side"),
                    ("price", "price"),
                    ("shares", "shares"),
                    ("cost", "cost"),
                    ("cum_up", "cum_up"),
                    ("cum_down", "cum_down"),
                    ("cum_cost", "cum_cost"),
                    ("net_side", "net_side"),
                    ("abs_net", "abs_net"),
                    ("qstar", "qstar"),
                ],
                max_rows=20,
            )
        )
    else:
        lines.append("_No worked example available because no market had enough inferred orders._")

    lines.append("\n## 已确定、未知和禁止外推\n")
    lines.append(
        "已确定：\n\n"
        "1. 成交时间、价格、size、side、market、settlement labels、PnL 字段。\n"
        "2. BTC-only 过滤后的市场、interval、生命周期、成本和收益分布。\n"
        "3. inferred order、quote batch、ladder rank、price band、phase、q* 账本的构造方法。\n"
        "4. 若有 BTCUSDT kline，当前优势边、顺/逆势成交、streak、q* 动态锚点和最终净仓锁定时点。\n\n"
        "强推断：\n\n"
        "1. 限价/挂单风格：由 same-price short-gap multi-fill 和被动成交代理支持，但不是 order-id 证明。\n"
        "2. 双边库存结构：market-level both-side 与 batch-level both-side 分离。\n"
        "3. q* 控制：扩大净风险必须由 `p_side - q*_after` 覆盖 buffer。\n"
        "4. size 主体是离散 lot + rank multiplier + gate，不是 Kelly 连续函数。\n\n"
        "未知：\n\n"
        "1. 未成交单、撤单、真实 TTL、maker/taker 标记、队列位置、完整 L2 深度。\n"
        "2. 真实外部 alpha、是否使用 Binance depth/perp/mark price/latency feed。\n"
        "3. 账户总资金、跨市场组合限制、隐藏 hedge、多账户协同、手续费/返佣。\n"
        "4. Polymarket 规则、tick、rate limit、post-only 语义和市场微结构变化。\n\n"
        "禁止外推：不要把 ex-post winner 直接写成 live alpha；不要把 median cost 写成固定 cap；"
        "不要把离散 lot 写成 Kelly；不要把缺 kline/orderbook 的报告拿去 live 下单。"
    )

    lines.append("\n## Auditor Readiness Checklist\n")
    lines.append(
        "- [x] exact address/window/input path\n"
        "- [x] BTC Up/Down filter and data fields\n"
        "- [x] inferred order and batch construction\n"
        "- [x] lifecycle, ladder, size, budget, inventory, q* sections\n"
        "- [x] alpha boundary and default live model spec\n"
        "- [x] deterministic config with sample-derived defaults\n"
        "- [x] risk, backtest, shadow and live gates\n"
        "- [x] worked market example\n"
        "- [x] known unknowns and non-goals\n"
    )

    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    summary = {
        "input_csv": str(input_csv),
        "report": str(report_path),
        "generated_utc": generated,
        "trade_rows": len(trades),
        "markets": len(market_rows),
        "orders": len(orders),
        "total_cost": total_cost,
        "resolved_cost": resolved_cost,
        "total_pnl": total_pnl,
        "roi": safe_div(total_pnl, resolved_cost),
        "primary_config": config,
        "data_audit": audit,
        "interval_modes": interval_mode_rows,
        "advantage_coverage": advantage_coverage,
        "qstar_anchor_rows": qstar_anchor_rows[:20],
        "final_net_lock_rows": final_lock_rows,
    }
    return report_path, summary


def infer_user_from_rows(trades: list[Trade]) -> str:
    for trade in trades:
        value = trade.raw.get("proxyWallet") or trade.raw.get("user") or ""
        if value:
            return str(value)
    return ""


def main() -> int:
    args = parse_args()
    load_env_file(args.env_file)
    out_dir = Path(args.out_dir).expanduser().resolve()
    label = args.label or (args.user or "input").lower().replace("0x", "addr_")[:18]
    run_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = out_dir / f"{label}_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.input:
        input_csv = Path(args.input).expanduser().resolve()
        if not has_settlement_columns(input_csv):
            enriched_name = input_csv.stem + "_with_capped_settlements.csv"
            binance_kline_csv = prepare_binance_kline_csv(input_csv, args, out_dir)
            input_csv = enrich_activity_csv(
                input_csv,
                out_dir / enriched_name,
                out_dir / (Path(enriched_name).stem + "_market_settlements.json"),
                int(args.max_settlement_markets),
                binance_kline_csv,
            )
        else:
            binance_kline_csv = prepare_binance_kline_csv(input_csv, args, out_dir)
            input_csv = attach_binance_kline_fields(
                input_csv,
                out_dir / f"{input_csv.stem}_with_binance_kline.csv",
                binance_kline_csv,
            )
    elif args.skip_export:
        raise SystemExit("--skip-export requires --input.")
    else:
        input_csv = export_activity(args, out_dir, label)

    trades, audit = load_trades(input_csv, args.price_decimals)
    if not trades:
        raise SystemExit("No BTC Up/Down trades found after filtering.")

    orders = infer_orders(trades, args.order_gap_sec)
    interval_rows = summarize_intervals(trades)
    market_rows = market_summaries(trades, orders)
    lifecycle_rows = lifecycle_summary(market_rows, orders)
    order_rows = order_summary(orders)
    batch_rows, ladder_rows = batch_and_ladder(orders, args.batch_gap_sec)
    price_rows = price_band_summary(orders)
    phase_rows = phase_summary(trades)
    sequence_rows = sequence_summary(orders)
    qstar_anchor_rows = qstar_anchor_summary(market_rows, orders)
    final_lock_rows = final_net_lock_summary(market_rows, orders)
    advantage_rows = advantage_summary(trades)
    advantage_streak_rows = advantage_streak_summary(orders)
    size_diagnostic_rows = size_price_diagnostic(orders)
    interval_mode_rows = interval_mode_summary(interval_rows, lifecycle_rows)

    write_csv(out_dir / "interval_summary.csv", interval_rows)
    write_csv(out_dir / "market_summary.csv", market_rows)
    write_csv(out_dir / "order_summary.csv", order_rows)
    write_csv(out_dir / "batch_summary.csv", batch_rows)
    write_csv(out_dir / "ladder_rank_summary.csv", ladder_rows)
    write_csv(out_dir / "price_band_summary.csv", price_rows)
    write_csv(out_dir / "phase_summary.csv", phase_rows)
    write_csv(out_dir / "sequence_summary.csv", sequence_rows)
    write_csv(out_dir / "qstar_anchor_summary.csv", qstar_anchor_rows)
    write_csv(out_dir / "final_net_lock_summary.csv", final_lock_rows)
    write_csv(out_dir / "advantage_relation_summary.csv", advantage_rows)
    write_csv(out_dir / "advantage_streak_summary.csv", advantage_streak_rows)
    write_csv(out_dir / "size_price_diagnostic.csv", size_diagnostic_rows)
    write_csv(out_dir / "interval_mode_summary.csv", interval_mode_rows)

    report_path, summary = generate_report(
        out_dir=out_dir,
        input_csv=input_csv,
        args=args,
        trades=trades,
        orders=orders,
        audit=audit,
        interval_rows=interval_rows,
        market_rows=market_rows,
        lifecycle_rows=lifecycle_rows,
        order_rows=order_rows,
        batch_rows=batch_rows,
        ladder_rows=ladder_rows,
        price_rows=price_rows,
        phase_rows=phase_rows,
        sequence_rows=sequence_rows,
        qstar_anchor_rows=qstar_anchor_rows,
        final_lock_rows=final_lock_rows,
        advantage_rows=advantage_rows,
        advantage_streak_rows=advantage_streak_rows,
        size_diagnostic_rows=size_diagnostic_rows,
        interval_mode_rows=interval_mode_rows,
    )
    (out_dir / "analysis_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nREPORT={report_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130)
