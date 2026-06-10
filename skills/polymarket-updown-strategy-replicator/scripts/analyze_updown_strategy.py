#!/usr/bin/env python3
"""Analyze a Polymarket wallet's crypto Up/Down trades and write a replication report."""

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
    "eth": ("eth", "ethereum"),
    "sol": ("sol", "solana"),
    "xrp": ("xrp", "ripple"),
    "doge": ("doge", "dogecoin"),
    "bnb": ("bnb", "binance"),
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
        help="Maximum unique market slugs to enrich through Gamma, ranked by traded cost. Use 0 for all. Default 5000.",
    )
    parser.add_argument("--btc-kline-database-url", default="", help="Optional DB URL with BTCUSDT 1s kline for local settlement.")
    parser.add_argument("--btc-kline-table", default="public.kline")
    parser.add_argument("--disable-db-btc-settlement", action="store_true")
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
            if key.endswith("_rate") or key in {"roi", "cost_share", "order_share", "qstar_margin"}:
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


def is_crypto_updown(slug: str, title: str) -> bool:
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


def normalize_db_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://") :]
    return url


def safe_sql_table(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*", str(value)):
        raise ValueError(f"Unsafe SQL table name: {value!r}")
    return str(value)


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
    if not is_crypto_updown(slug, title):
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


def load_btc_kline_prices(db_url: str, table: str, timestamps: list[int]) -> dict[int, float]:
    if not db_url or not timestamps:
        return {}
    sys.path.insert(0, "/tmp/pbot3_pgdeps")
    try:
        from sqlalchemy import create_engine, text
    except Exception as exc:  # noqa: BLE001 - optional dependency.
        print(f"Skipping DB BTC settlement because SQLAlchemy is unavailable: {exc!r}", flush=True)
        return {}
    safe_table = safe_sql_table(table)
    engine = create_engine(normalize_db_url(db_url), connect_args={"connect_timeout": 10})
    prices: dict[int, float] = {}
    try:
        unique_ts = sorted(set(timestamps))
        for idx in range(0, len(unique_ts), 5000):
            chunk = unique_ts[idx : idx + 5000]
            datetimes = [dt.datetime.fromtimestamp(ts, dt.timezone.utc) for ts in chunk]
            sql = f"""
            SELECT open_time, close::float AS close
            FROM {safe_table}
            WHERE symbol = 'BTCUSDT'
              AND time_period = '1s'
              AND open_time = ANY(:times)
            """
            with engine.connect() as conn:
                rows = conn.execute(text(sql), {"times": datetimes}).fetchall()
            for open_time, close in rows:
                parsed = open_time
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=dt.timezone.utc)
                prices[int(parsed.timestamp())] = float(close)
    finally:
        engine.dispose()
    return prices


def db_settle_btc_markets(rows: list[dict[str, Any]], db_url: str, table: str) -> dict[str, dict[str, Any]]:
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
    prices = load_btc_kline_prices(db_url, table, needed)
    settlements: dict[str, dict[str, Any]] = {}
    missing = 0
    for slug, (start, end) in windows.items():
        open_price = prices.get(start)
        close_price = prices.get(end - 1)
        if open_price is None or close_price is None:
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
            "settlementStatus": "RESOLVED_DB_BTC_KLINE",
            "winningOutcome": winning,
            "outcomes": json.dumps(["Up", "Down"]),
            "outcomePrices": json.dumps([1 if winning == "Up" else 0, 1 if winning == "Down" else 0]),
            "endDate": dt.datetime.fromtimestamp(end, dt.timezone.utc).isoformat(),
            "closedTime": "",
            "apiError": "",
            "btcOpen": open_price,
            "btcClose": close_price,
        }
    print(
        f"DB BTC settlement resolved {len(settlements)}/{len(windows)} BTC Up/Down markets"
        + (f"; missing kline for {missing}" if missing else ""),
        flush=True,
    )
    return settlements


def enrich_activity_csv(
    raw_csv: Path,
    enriched_csv: Path,
    settlements_json: Path,
    max_settlement_markets: int = 0,
    btc_kline_db_url: str = "",
    btc_kline_table: str = "public.kline",
) -> Path:
    with raw_csv.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        base_fields = list(reader.fieldnames or [])
    db_settlements = db_settle_btc_markets(rows, btc_kline_db_url, btc_kline_table) if btc_kline_db_url else {}
    cost_by_slug: defaultdict[str, float] = defaultdict(float)
    for row in rows:
        slug = row.get("eventSlug") or row.get("slug") or ""
        title = row.get("title") or row.get("question") or row.get("name") or ""
        if slug and is_crypto_updown(slug, title) and slug not in db_settlements:
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
    settlements = dict(db_settlements)
    settlements.update(fetch_settlements_once(slugs))
    settlement_payload = {
        "fetched_market_count": len(slugs),
        "db_btc_market_count": len(db_settlements),
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
    ]
    fieldnames = list(base_fields)
    for field in extra_fields:
        if field not in fieldnames:
            fieldnames.append(field)
    enriched_rows: list[dict[str, Any]] = []
    for row in rows:
        slug = row.get("eventSlug") or row.get("slug") or ""
        settlement = settlements.get(slug, {})
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
            }
        )
        enriched_rows.append(enriched)
    with enriched_csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(enriched_rows)
    return enriched_csv


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
        return result

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
    return enrich_activity_csv(
        merged_raw,
        merged_enriched,
        out_dir / f"{label}_{user}_market_settlements.json",
        int(args.max_settlement_markets),
        "" if args.disable_db_btc_settlement else (args.btc_kline_database_url or os.environ.get("OVH2_DATABASE_URL", "")),
        args.btc_kline_table,
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
        if not is_crypto_updown(slug, title):
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
                raw=row,
            )
        )
    audit = {
        "input_csv": str(path),
        "input_rows": len(rows),
        "crypto_updown_trade_rows": len(trades),
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
                "first_order_elapsed_sec": median(first_elapsed),
                "last_order_seconds_before_close": median(last_before_close),
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
                "weighted_qstar": weighted_average(qstars, [r["abs_net"] for r in group if math.isfinite(float(r["qstar"]))]),
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
    report_path = out_dir / "strategy_replication_report.md"
    min_data_warning = ""
    if len(market_rows) < args.min_report_markets:
        min_data_warning = (
            f"\n> 数据不足提示：样本只有 `{len(market_rows)}` 个 crypto Up/Down 市场，低于默认 `{args.min_report_markets}`。"
            "本报告仍给出复刻框架，但 live 策略不得上线，只能作为研究草案。\n"
        )

    lines: list[str] = []
    lines.append("# Polymarket Crypto Up/Down 地址策略像素级复刻报告\n")
    lines.append("## 技术摘要\n")
    lines.append(
        f"- 地址：`{args.user or infer_user_from_rows(trades) or 'input-csv'}`\n"
        f"- 输入：`{input_csv}`\n"
        f"- 生成时间 UTC：`{generated}`\n"
        f"- 默认/实际窗口：`{args.days:g}` 天；若使用 `--input`，窗口以 CSV 为准。\n"
        f"- crypto Up/Down 成交行：`{len(trades):,}`；市场：`{len(market_rows):,}`；inferred orders：`{len(orders):,}`。\n"
        f"- 总成本：`{fmt_num(total_cost)}`；已结算/已拉取成本：`{fmt_num(resolved_cost)}`；"
        f"已标记 PnL：`{fmt_num(total_pnl)}`；resolved ROI：`{fmt_pct(safe_div(total_pnl, resolved_cost))}`。\n"
        f"- BUY-only：`{buy_only}`；market both-side rate：`{fmt_pct(both_sides_rate)}`；multi-fill order rate：`{fmt_pct(multi_fill_order_rate)}`；final net correct：`{fmt_pct(net_correct)}`。"
    )
    lines.append(min_data_warning)
    lines.append(
        "\n本报告的复刻边界是“从地址成交历史复刻可观察行为与可验证执行规则”。"
        "若没有订单 ID、撤单、未成交单、maker/taker 标记、队列位置和底层价格路径，本报告不会声称拿到了真实源码。"
        "它会把可确定事实、强推断、弱推断和 live 上线前必须补的数据分开。"
    )

    lines.append("\n## 一页机制图\n")
    lines.append(
        "```text\n"
        "address trades -> crypto Up/Down filter -> settlement labels\n"
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
        f"- crypto Up/Down 过滤后行数：`{audit['crypto_updown_trade_rows']:,}`。\n"
        f"- 过滤逻辑：slug/title 中必须出现 crypto asset 别名，并包含 `updown`、`up-or-down`、`up or down` 或等价描述。\n"
        f"- settlement 字段优先级：`activityOutcomeResult` / `tradeOutcomeResult`；PnL 字段优先级：`activityPnLUSDC` / `tradePnLUSDC`。\n"
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
        "- 费用：若 CSV PnL 已含费用则以 CSV 为准；若 live 复刻需要估算，默认使用 `fee_rate = 0.07 * min(price, 1-price)` 的保守 crypto fee 近似，并在回放中做 `0x/0.5x/1x/2x` 敏感性。\n"
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
                ("weighted_qstar", "weighted_qstar"),
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

    lines.append("\n## alpha 与方向来源\n")
    lines.append(
        "仅凭地址成交 CSV 不能直接恢复 live alpha。可确定的是最终净仓与结算边之间的关系，以及订单在生命周期中的偏向。"
        "若要从本报告上线策略，必须补底层 1s kline/orderbook 并训练或校准 fair value 模型。\n\n"
        "默认 live alpha 模型规格：\n\n"
        "```yaml\n"
        "label: market_winning_outcome_up\n"
        "training_window: rolling_45_days_before_trade_day\n"
        "validation_window: next_7_days_walk_forward\n"
        "sample_frequency: every_1s_or_5s_while_market_open\n"
        "model: logistic_regression_or_calibrated_gradient_boosting\n"
        "features:\n"
        "  - asset_one_hot\n"
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
        "fallback_without_kline: research_report_only_no_live_orders\n"
        "```\n"
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
        "  if market asset/interval not in enabled config: no-op\n"
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
        "    behavior_distance: lifecycle, ladder, budget, and inventory metrics within sample p25-p75 or explained\n"
        "shadow_required:\n"
        "  duration_days: 7\n"
        "  outputs: [order_intents.ndjson, simulated_fills.ndjson, inventory_snapshots.ndjson, scorecard.csv]\n"
        "live_ramp:\n"
        "  phase_1: 0.10x sample budget scale\n"
        "  phase_2: 0.25x after 500 resolved shadow/live markets pass\n"
        "  rollback: any reconciliation gap, data lag incident, or unexplained loss cluster\n"
        "```\n"
    )

    lines.append("\n## PnL 归因框架\n")
    lines.append(
        "- Direction alpha：最终净仓是否偏向 winning outcome。\n"
        "- Execution improvement：成交价是否优于同秒/邻近盘口；没有 orderbook 时不能证明。\n"
        "- Inventory optionality：双边库存降低亏损底座，q* 低于预测概率。\n"
        "- Adverse selection：高价、临近收盘、stale book 或连续错误净仓导致的亏损。\n"
        "- Fees/rebates：CSV 未完全暴露时必须做敏感性，而不是只看毛收益。\n"
        "- Capacity：用 p95/p99 market cost 和 top-of-book notional 验证，不能线性放大。"
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
        "已确定：成交时间、价格、size、side、market、settlement labels、PnL 字段、inferred order 代理、库存账本。\n\n"
        "强推断：限价/挂单风格、阶梯结构、预算分布、q* 控制、final net 方向质量。\n\n"
        "未知：未成交单、撤单、maker/taker、队列位置、完整 L2、真实外部 alpha、账户总资金、隐藏 hedge。\n\n"
        "禁止外推：不要把 ex-post winner 直接写成 live alpha；不要把 median cost 写成固定 cap；不要把离散 lot 写成 Kelly。"
    )

    lines.append("\n## Auditor Readiness Checklist\n")
    lines.append(
        "- [x] exact address/window/input path\n"
        "- [x] crypto Up/Down filter and data fields\n"
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
            input_csv = enrich_activity_csv(
                input_csv,
                out_dir / enriched_name,
                out_dir / (Path(enriched_name).stem + "_market_settlements.json"),
                int(args.max_settlement_markets),
                "" if args.disable_db_btc_settlement else (args.btc_kline_database_url or os.environ.get("OVH2_DATABASE_URL", "")),
                args.btc_kline_table,
            )
    elif args.skip_export:
        raise SystemExit("--skip-export requires --input.")
    else:
        input_csv = export_activity(args, out_dir, label)

    trades, audit = load_trades(input_csv, args.price_decimals)
    if not trades:
        raise SystemExit("No crypto Up/Down trades found after filtering.")

    orders = infer_orders(trades, args.order_gap_sec)
    interval_rows = summarize_intervals(trades)
    market_rows = market_summaries(trades, orders)
    lifecycle_rows = lifecycle_summary(market_rows, orders)
    order_rows = order_summary(orders)
    batch_rows, ladder_rows = batch_and_ladder(orders, args.batch_gap_sec)
    price_rows = price_band_summary(orders)
    phase_rows = phase_summary(trades)
    sequence_rows = sequence_summary(orders)

    write_csv(out_dir / "interval_summary.csv", interval_rows)
    write_csv(out_dir / "market_summary.csv", market_rows)
    write_csv(out_dir / "order_summary.csv", order_rows)
    write_csv(out_dir / "batch_summary.csv", batch_rows)
    write_csv(out_dir / "ladder_rank_summary.csv", ladder_rows)
    write_csv(out_dir / "price_band_summary.csv", price_rows)
    write_csv(out_dir / "phase_summary.csv", phase_rows)
    write_csv(out_dir / "sequence_summary.csv", sequence_rows)

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
