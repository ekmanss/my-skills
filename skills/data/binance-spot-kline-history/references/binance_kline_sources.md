# Binance Spot Kline Sources

## Public Archives

Binance public market data archives are hosted under:

```text
https://data.binance.vision/data/spot/{monthly|daily}/klines/{SYMBOL}/{INTERVAL}/
```

Expected ZIP filenames:

```text
{SYMBOL}-{INTERVAL}-{YYYY-MM}.zip
{SYMBOL}-{INTERVAL}-{YYYY-MM-DD}.zip
```

Use monthly files before daily files. Monthly files cover completed calendar months. Daily files cover completed UTC days and are useful for months that do not yet have a monthly archive, missing monthly files, or recent history.

## REST API Fallback

Use public Spot REST only after archive coverage is exhausted:

```text
GET https://api.binance.com/api/v3/klines
```

Parameters:

```text
symbol={SYMBOL}
interval={INTERVAL}
startTime={start_ms}
endTime={end_ms_inclusive}
limit=1000
```

Binance spot klines are identified by open time. REST `limit` is capped at 1000. Treat the requested user `end` as exclusive, then call REST with `endTime=end-1`.

## Row Fields

Archive CSV rows and REST rows use the same first 11 fields:

```text
0 open_time
1 open
2 high
3 low
4 close
5 volume
6 close_time
7 quote_asset_volume
8 number_of_trades
9 taker_buy_base_asset_volume
10 taker_buy_quote_asset_volume
```

The bundled script writes these fields plus:

```text
symbol
interval
open_time_iso
close_time_iso
source
```

## Timestamp Caveat

Some newer Binance spot archive rows can contain timestamps with more than 13 digits. Normalize these to milliseconds by taking the first 13 digits before filtering, de-duplicating, or writing `open_time` and `close_time`.

## Official References

- Binance public data archive: https://github.com/binance/binance-public-data
- Binance Spot kline REST endpoint: https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints
