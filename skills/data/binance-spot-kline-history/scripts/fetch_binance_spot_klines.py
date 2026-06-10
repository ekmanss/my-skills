#!/usr/bin/env python3
"""Fetch Binance spot kline history with archive-first fallback."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ARCHIVE_BASE_URL = "https://data.binance.vision"
API_BASE_URL = "https://api.binance.com"
USER_AGENT = "codex-binance-spot-kline-history/1.0"
HTTP_TIMEOUT_SECONDS = 60
DEFAULT_LIMIT = 1000
MAX_REST_LIMIT = 1000
MILLISECOND_DIGITS = 13
UTC = timezone.utc

SUPPORTED_INTERVALS = {
    "1s",
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
    "1M",
}

OUTPUT_FIELDS = [
    "symbol",
    "interval",
    "open_time",
    "open_time_iso",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "close_time_iso",
    "quote_asset_volume",
    "number_of_trades",
    "taker_buy_base_asset_volume",
    "taker_buy_quote_asset_volume",
    "source",
]


@dataclass
class FetchStats:
    monthly_attempted: int = 0
    monthly_found: int = 0
    daily_attempted: int = 0
    daily_found: int = 0
    api_segments: int = 0
    api_pages: int = 0
    records_by_source: dict[str, int] = field(default_factory=dict)
    duplicates_skipped: int = 0

    def add_records(self, source: str, count: int) -> None:
        self.records_by_source[source] = self.records_by_source.get(source, 0) + count


@dataclass(frozen=True)
class ArchiveWindow:
    label: str
    start_ms: int
    end_ms: int
    data_source: str


def log(message: str, quiet: bool = False) -> None:
    if not quiet:
        print(message, file=sys.stderr)


def parse_time_arg(value: str) -> int:
    text = value.strip()
    if not text:
        raise ValueError("time value cannot be empty")

    if text.isdigit():
        if len(text) >= 12:
            return int(text)
        if len(text) == 10:
            return int(text) * 1000
        raise ValueError(f"numeric time '{value}' must be milliseconds or 10-digit seconds")

    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        text = f"{text}T00:00:00Z"

    normalized = text.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return int(dt.timestamp() * 1000)


def ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def normalize_binance_timestamp(value: Any) -> int | None:
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("-"):
        return None
    if "." in text:
        text = text.split(".", 1)[0]
    if not text.isdigit():
        return None
    if len(text) > MILLISECOND_DIGITS:
        text = text[:MILLISECOND_DIGITS]
    try:
        return int(text)
    except ValueError:
        return None


def month_floor(dt: datetime) -> datetime:
    return datetime(dt.year, dt.month, 1, tzinfo=UTC)


def add_month(dt: datetime) -> datetime:
    if dt.month == 12:
        return datetime(dt.year + 1, 1, 1, tzinfo=UTC)
    return datetime(dt.year, dt.month + 1, 1, tzinfo=UTC)


def day_floor(dt: datetime) -> datetime:
    return datetime(dt.year, dt.month, dt.day, tzinfo=UTC)


def dt_to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def iter_month_windows(start_ms: int, end_ms: int) -> list[ArchiveWindow]:
    start_dt = datetime.fromtimestamp(start_ms / 1000, tz=UTC)
    end_dt = datetime.fromtimestamp((end_ms - 1) / 1000, tz=UTC)
    current = month_floor(start_dt)
    final = month_floor(end_dt)
    windows: list[ArchiveWindow] = []

    while current <= final:
        next_month = add_month(current)
        windows.append(
            ArchiveWindow(
                label=current.strftime("%Y-%m"),
                start_ms=max(start_ms, dt_to_ms(current)),
                end_ms=min(end_ms, dt_to_ms(next_month)),
                data_source="monthly",
            )
        )
        current = next_month

    return windows


def iter_day_windows(start_ms: int, end_ms: int) -> list[ArchiveWindow]:
    start_dt = datetime.fromtimestamp(start_ms / 1000, tz=UTC)
    end_dt = datetime.fromtimestamp((end_ms - 1) / 1000, tz=UTC)
    current = day_floor(start_dt)
    final = day_floor(end_dt)
    windows: list[ArchiveWindow] = []

    while current <= final:
        next_day = current + timedelta(days=1)
        windows.append(
            ArchiveWindow(
                label=current.strftime("%Y-%m-%d"),
                start_ms=max(start_ms, dt_to_ms(current)),
                end_ms=min(end_ms, dt_to_ms(next_day)),
                data_source="daily",
            )
        )
        current = next_day

    return windows


def merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    valid = sorted((start, end) for start, end in intervals if start < end)
    if not valid:
        return []

    merged = [valid[0]]
    for start, end in valid[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def subtract_coverage(start_ms: int, end_ms: int, coverage: list[tuple[int, int]]) -> list[tuple[int, int]]:
    gaps = [(start_ms, end_ms)]
    for cover_start, cover_end in merge_intervals(coverage):
        next_gaps: list[tuple[int, int]] = []
        for gap_start, gap_end in gaps:
            if cover_end <= gap_start or cover_start >= gap_end:
                next_gaps.append((gap_start, gap_end))
                continue
            if gap_start < cover_start:
                next_gaps.append((gap_start, min(cover_start, gap_end)))
            if cover_end < gap_end:
                next_gaps.append((max(cover_end, gap_start), gap_end))
        gaps = next_gaps
    return [(start, end) for start, end in gaps if start < end]


def intersects_any(start_ms: int, end_ms: int, intervals: list[tuple[int, int]]) -> bool:
    return any(start_ms < other_end and end_ms > other_start for other_start, other_end in intervals)


def request_bytes(url: str, max_retries: int, retry_delay: float, quiet: bool) -> bytes | None:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    attempt = 0
    while True:
        try:
            with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code == 404:
                return None
            retryable = exc.code in {418, 429, 500, 502, 503, 504}
            if not retryable or attempt >= max_retries:
                raise
            wait_seconds = 60 if exc.code == 418 else retry_delay * (attempt + 1)
            log(f"HTTP {exc.code} for {url}; retrying in {wait_seconds:.1f}s", quiet)
            time.sleep(wait_seconds)
            attempt += 1
        except URLError:
            if attempt >= max_retries:
                raise
            wait_seconds = retry_delay * (attempt + 1)
            log(f"Network error for {url}; retrying in {wait_seconds:.1f}s", quiet)
            time.sleep(wait_seconds)
            attempt += 1


def request_json(url: str, max_retries: int, retry_delay: float, quiet: bool) -> Any:
    data = request_bytes(url, max_retries=max_retries, retry_delay=retry_delay, quiet=quiet)
    if data is None:
        raise RuntimeError(f"HTTP 404 for API URL: {url}")
    return json.loads(data.decode("utf-8"))


def archive_path(symbol: str, interval: str, window: ArchiveWindow) -> str:
    filename = f"{symbol}-{interval}-{window.label}.zip"
    return f"data/spot/{window.data_source}/klines/{symbol}/{interval}/{filename}"


def archive_url(base_url: str, symbol: str, interval: str, window: ArchiveWindow) -> str:
    return f"{base_url.rstrip('/')}/{archive_path(symbol, interval, window)}"


def cache_file_path(cache_dir: Path, symbol: str, interval: str, window: ArchiveWindow) -> Path:
    return cache_dir / archive_path(symbol, interval, window)


def download_archive_zip(
    base_url: str,
    cache_dir: Path,
    symbol: str,
    interval: str,
    window: ArchiveWindow,
    max_retries: int,
    retry_delay: float,
    no_cache: bool,
    quiet: bool,
) -> bytes | None:
    cache_path = cache_file_path(cache_dir, symbol, interval, window)
    if not no_cache and cache_path.exists():
        log(f"Using cached {window.data_source} archive {cache_path}", quiet)
        return cache_path.read_bytes()

    url = archive_url(base_url, symbol, interval, window)
    log(f"Fetching {window.data_source} archive {url}", quiet)
    data = request_bytes(url, max_retries=max_retries, retry_delay=retry_delay, quiet=quiet)
    if data is None:
        log(f"Missing {window.data_source} archive for {symbol} {interval} {window.label}", quiet)
        return None

    if not no_cache:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(data)
    return data


def read_archive_rows(zip_bytes: bytes, expected_csv_name: str) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        names = archive.namelist()
        csv_name = expected_csv_name if expected_csv_name in names else ""
        if not csv_name:
            csv_files = [name for name in names if name.endswith(".csv")]
            if not csv_files:
                raise RuntimeError(f"no CSV file found in archive; files={names}")
            csv_name = csv_files[0]

        with archive.open(csv_name) as csv_file:
            text_stream = io.TextIOWrapper(csv_file, encoding="utf-8", newline="")
            reader = csv.reader(text_stream)
            rows: list[list[str]] = []
            for row in reader:
                if not row:
                    continue
                if row[0].strip().lower() in {"open_time", "open time"}:
                    continue
                rows.append(row)
            return rows


def parse_kline_row(row: list[Any], symbol: str, interval: str, source: str) -> dict[str, Any] | None:
    if len(row) < 11:
        return None

    open_time = normalize_binance_timestamp(row[0])
    close_time = normalize_binance_timestamp(row[6])
    if open_time is None or close_time is None:
        return None

    try:
        number_of_trades = int(str(row[8]))
    except ValueError:
        return None

    return {
        "symbol": symbol,
        "interval": interval,
        "open_time": open_time,
        "open_time_iso": ms_to_iso(open_time),
        "open": str(row[1]),
        "high": str(row[2]),
        "low": str(row[3]),
        "close": str(row[4]),
        "volume": str(row[5]),
        "close_time": close_time,
        "close_time_iso": ms_to_iso(close_time),
        "quote_asset_volume": str(row[7]),
        "number_of_trades": number_of_trades,
        "taker_buy_base_asset_volume": str(row[9]),
        "taker_buy_quote_asset_volume": str(row[10]),
        "source": source,
    }


def add_records(
    records_by_open_time: dict[int, dict[str, Any]],
    rows: list[list[Any]],
    symbol: str,
    interval: str,
    source: str,
    start_ms: int,
    end_ms: int,
    stats: FetchStats,
) -> int:
    added = 0
    duplicates = 0

    for row in rows:
        record = parse_kline_row(row, symbol, interval, source)
        if record is None:
            continue
        open_time = int(record["open_time"])
        if open_time < start_ms or open_time >= end_ms:
            continue
        if open_time in records_by_open_time:
            duplicates += 1
            continue
        records_by_open_time[open_time] = record
        added += 1

    stats.duplicates_skipped += duplicates
    stats.add_records(source, added)
    return added


def process_archive_window(
    records_by_open_time: dict[int, dict[str, Any]],
    base_url: str,
    cache_dir: Path,
    symbol: str,
    interval: str,
    window: ArchiveWindow,
    max_retries: int,
    retry_delay: float,
    no_cache: bool,
    quiet: bool,
    stats: FetchStats,
) -> bool:
    if window.data_source == "monthly":
        stats.monthly_attempted += 1
    else:
        stats.daily_attempted += 1

    zip_bytes = download_archive_zip(
        base_url=base_url,
        cache_dir=cache_dir,
        symbol=symbol,
        interval=interval,
        window=window,
        max_retries=max_retries,
        retry_delay=retry_delay,
        no_cache=no_cache,
        quiet=quiet,
    )
    if zip_bytes is None:
        return False

    expected_csv_name = f"{symbol}-{interval}-{window.label}.csv"
    rows = read_archive_rows(zip_bytes, expected_csv_name=expected_csv_name)
    source = f"archive_{window.data_source}"
    added = add_records(
        records_by_open_time=records_by_open_time,
        rows=rows,
        symbol=symbol,
        interval=interval,
        source=source,
        start_ms=window.start_ms,
        end_ms=window.end_ms,
        stats=stats,
    )

    if window.data_source == "monthly":
        stats.monthly_found += 1
    else:
        stats.daily_found += 1

    log(
        f"Processed {window.data_source} {window.label}: {len(rows)} archive rows, {added} in requested range",
        quiet,
    )
    return True


def build_api_url(api_base_url: str, symbol: str, interval: str, start_ms: int, end_ms: int, limit: int) -> str:
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": str(start_ms),
        "endTime": str(end_ms - 1),
        "limit": str(limit),
    }
    return f"{api_base_url.rstrip('/')}/api/v3/klines?{urlencode(params)}"


def fetch_api_segment(
    records_by_open_time: dict[int, dict[str, Any]],
    api_base_url: str,
    symbol: str,
    interval: str,
    segment_start_ms: int,
    segment_end_ms: int,
    limit: int,
    include_open: bool,
    max_api_pages: int,
    max_retries: int,
    retry_delay: float,
    quiet: bool,
    stats: FetchStats,
) -> None:
    stats.api_segments += 1
    current_start = segment_start_ms
    pages_for_segment = 0
    now_ms = int(time.time() * 1000)

    while current_start < segment_end_ms:
        if pages_for_segment >= max_api_pages:
            raise RuntimeError(
                f"max API pages reached for segment {ms_to_iso(segment_start_ms)} -> {ms_to_iso(segment_end_ms)}"
            )

        url = build_api_url(
            api_base_url=api_base_url,
            symbol=symbol,
            interval=interval,
            start_ms=current_start,
            end_ms=segment_end_ms,
            limit=limit,
        )
        log(f"Fetching API klines {ms_to_iso(current_start)} -> {ms_to_iso(segment_end_ms)}", quiet)
        data = request_json(url, max_retries=max_retries, retry_delay=retry_delay, quiet=quiet)
        if not isinstance(data, list) or not data:
            break

        stats.api_pages += 1
        pages_for_segment += 1

        filtered_rows: list[list[Any]] = []
        last_open_time: int | None = None
        for row in data:
            if not isinstance(row, list) or len(row) < 11:
                continue
            open_time = normalize_binance_timestamp(row[0])
            close_time = normalize_binance_timestamp(row[6])
            if open_time is None:
                continue
            last_open_time = open_time if last_open_time is None else max(last_open_time, open_time)
            if open_time < segment_start_ms or open_time >= segment_end_ms:
                continue
            if not include_open and close_time is not None and close_time > now_ms:
                continue
            filtered_rows.append(row)

        added = add_records(
            records_by_open_time=records_by_open_time,
            rows=filtered_rows,
            symbol=symbol,
            interval=interval,
            source="api",
            start_ms=segment_start_ms,
            end_ms=segment_end_ms,
            stats=stats,
        )
        log(f"API page returned {len(data)} rows, added {added}", quiet)

        if last_open_time is None:
            break
        next_start = last_open_time + 1
        if next_start <= current_start:
            break
        current_start = next_start

        if len(data) < limit:
            break


def default_output_path(symbol: str, interval: str, start_ms: int, end_ms: int, output_format: str) -> Path:
    start_label = datetime.fromtimestamp(start_ms / 1000, tz=UTC).strftime("%Y%m%dT%H%M%S")
    end_label = datetime.fromtimestamp(end_ms / 1000, tz=UTC).strftime("%Y%m%dT%H%M%S")
    suffix = "jsonl" if output_format == "jsonl" else output_format
    return Path(f"{symbol}_{interval}_{start_label}_{end_label}.{suffix}")


def write_output(records: list[dict[str, Any]], output_path: str, output_format: str) -> None:
    if output_path == "-":
        output_stream = sys.stdout
        close_stream = False
    else:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        output_stream = path.open("w", encoding="utf-8", newline="")
        close_stream = True

    try:
        if output_format == "csv":
            writer = csv.DictWriter(output_stream, fieldnames=OUTPUT_FIELDS)
            writer.writeheader()
            for record in records:
                writer.writerow(record)
        elif output_format == "json":
            json.dump(records, output_stream, ensure_ascii=False, indent=2)
            output_stream.write("\n")
        elif output_format == "jsonl":
            for record in records:
                output_stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        else:
            raise ValueError(f"unsupported output format: {output_format}")
    finally:
        if close_stream:
            output_stream.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch Binance spot kline history using monthly archives, daily archives, then REST API gaps.",
    )
    parser.add_argument("--symbol", required=True, help="Spot symbol, for example BTCUSDT")
    parser.add_argument("--interval", required=True, choices=sorted(SUPPORTED_INTERVALS), help="Kline interval")
    parser.add_argument("--start", required=True, help="Inclusive UTC start, ISO/date or millisecond timestamp")
    parser.add_argument("--end", required=True, help="Exclusive UTC end, ISO/date or millisecond timestamp")
    parser.add_argument("--out", help="Output path. Use '-' for stdout. Defaults to a generated filename.")
    parser.add_argument("--format", choices=["csv", "json", "jsonl"], default="csv", help="Output format")
    parser.add_argument("--cache-dir", help="Archive ZIP cache directory")
    parser.add_argument("--no-cache", action="store_true", help="Do not read or write archive ZIP cache files")
    parser.add_argument("--include-open", action="store_true", help="Include not-yet-closed API candles")
    parser.add_argument("--archive-base-url", default=ARCHIVE_BASE_URL, help="Archive base URL")
    parser.add_argument("--api-base-url", default=API_BASE_URL, help="Spot REST API base URL")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="REST API page size, max 1000")
    parser.add_argument("--max-api-pages", type=int, default=10000, help="Maximum REST API pages per uncovered segment")
    parser.add_argument("--max-retries", type=int, default=3, help="HTTP retries for archives/API")
    parser.add_argument("--retry-delay", type=float, default=3.0, help="Base retry delay in seconds")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress logs")
    return parser


def run(args: argparse.Namespace) -> int:
    symbol = args.symbol.strip().upper()
    interval = args.interval.strip()
    start_ms = parse_time_arg(args.start)
    end_ms = parse_time_arg(args.end)
    if start_ms >= end_ms:
        raise ValueError("--start must be earlier than --end")

    limit = min(max(1, args.limit), MAX_REST_LIMIT)
    output_path = args.out or str(default_output_path(symbol, interval, start_ms, end_ms, args.format))
    if args.cache_dir:
        cache_dir = Path(args.cache_dir)
    elif output_path == "-":
        cache_dir = Path.cwd() / ".binance-kline-cache"
    else:
        cache_dir = Path(output_path).resolve().parent / ".binance-kline-cache"

    stats = FetchStats()
    records_by_open_time: dict[int, dict[str, Any]] = {}
    coverage: list[tuple[int, int]] = []

    log(f"Requested {symbol} {interval}: {ms_to_iso(start_ms)} -> {ms_to_iso(end_ms)}", args.quiet)

    for window in iter_month_windows(start_ms, end_ms):
        found = process_archive_window(
            records_by_open_time=records_by_open_time,
            base_url=args.archive_base_url,
            cache_dir=cache_dir,
            symbol=symbol,
            interval=interval,
            window=window,
            max_retries=args.max_retries,
            retry_delay=args.retry_delay,
            no_cache=args.no_cache,
            quiet=args.quiet,
            stats=stats,
        )
        if found:
            coverage.append((window.start_ms, window.end_ms))

    monthly_gaps = subtract_coverage(start_ms, end_ms, coverage)
    if monthly_gaps:
        log(
            "Monthly archive gaps: "
            + ", ".join(f"{ms_to_iso(start)} -> {ms_to_iso(end)}" for start, end in monthly_gaps),
            args.quiet,
        )

    for window in iter_day_windows(start_ms, end_ms):
        if not intersects_any(window.start_ms, window.end_ms, monthly_gaps):
            continue
        found = process_archive_window(
            records_by_open_time=records_by_open_time,
            base_url=args.archive_base_url,
            cache_dir=cache_dir,
            symbol=symbol,
            interval=interval,
            window=window,
            max_retries=args.max_retries,
            retry_delay=args.retry_delay,
            no_cache=args.no_cache,
            quiet=args.quiet,
            stats=stats,
        )
        if found:
            coverage.append((window.start_ms, window.end_ms))

    api_gaps = subtract_coverage(start_ms, end_ms, coverage)
    if api_gaps:
        log(
            "API fallback gaps: "
            + ", ".join(f"{ms_to_iso(start)} -> {ms_to_iso(end)}" for start, end in api_gaps),
            args.quiet,
        )

    for segment_start_ms, segment_end_ms in api_gaps:
        fetch_api_segment(
            records_by_open_time=records_by_open_time,
            api_base_url=args.api_base_url,
            symbol=symbol,
            interval=interval,
            segment_start_ms=segment_start_ms,
            segment_end_ms=segment_end_ms,
            limit=limit,
            include_open=args.include_open,
            max_api_pages=args.max_api_pages,
            max_retries=args.max_retries,
            retry_delay=args.retry_delay,
            quiet=args.quiet,
            stats=stats,
        )

    records = [records_by_open_time[key] for key in sorted(records_by_open_time)]
    write_output(records, output_path=output_path, output_format=args.format)

    source_summary = ", ".join(
        f"{source}={count}" for source, count in sorted(stats.records_by_source.items())
    ) or "none"
    log(
        "Summary: "
        f"rows={len(records)}, sources=({source_summary}), "
        f"monthly={stats.monthly_found}/{stats.monthly_attempted}, "
        f"daily={stats.daily_found}/{stats.daily_attempted}, "
        f"api_segments={stats.api_segments}, api_pages={stats.api_pages}, "
        f"duplicates_skipped={stats.duplicates_skipped}",
        args.quiet,
    )
    if output_path != "-":
        print(output_path)
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return run(args)
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
