# Polymarket Activity And Gamma Notes

## Data API: `/activity`

Endpoint:

```text
GET https://data-api.polymarket.com/activity
```

Important parameters:

| Parameter | Use |
|---|---|
| `user` | Required `0x` address. |
| `type` | Use `TRADE` for trade rows. Multiple values are comma-separated. |
| `start`, `end` | Unix second timestamps, inclusive. |
| `limit` | Use `1000`; larger values are clamped. |
| `offset` | Use `0`, `1000`, `2000`, `3000`; `3001` fails. |
| `sortBy` | Use `TIMESTAMP`. |
| `sortDirection` | Use `ASC` for deterministic time-window fetching. |
| `excludeDepositsWithdrawals` | Defaults true. Set false only when the user asks for deposits/withdrawals too. |

Returned fields commonly include `proxyWallet`, `timestamp`, `conditionId`, `type`, `size`, `usdcSize`, `transactionHash`, `price`, `asset`, `side`, `outcomeIndex`, `title`, `slug`, `eventSlug`, and `outcome`.

Completeness rule:

- Fetch pages at offsets `0`, `1000`, `2000`, and `3000`.
- If the page at offset `3000` has `limit` rows, the API may have more rows in that time window.
- Split the time window and fetch both halves recursively.
- If a one-second window still hits the cap, report a warning because completeness cannot be proven from this endpoint.

## Gamma API: Market By Slug

Endpoint:

```text
GET https://gamma-api.polymarket.com/markets/slug/{eventSlug}
```

For BTC up/down interval markets, activity `slug` and `eventSlug` are usually identical, e.g. `btc-updown-15m-1779362100`.

Settlement fields:

```json
{
  "outcomes": "[\"Up\", \"Down\"]",
  "outcomePrices": "[\"1\", \"0\"]",
  "closed": true
}
```

Parse `outcomes` and `outcomePrices` as JSON arrays. When `closed` is true, the outcome whose corresponding price is exactly `1` is the winning outcome. A price of `0` is losing.

## PnL Convention

For BUY trade rows:

- Winning payout is `size`.
- Losing payout is `0`.
- Cost is `usdcSize`.
- PnL is `payout - usdcSize`.

Do not use this convention for SELL rows without revisiting the accounting. If SELL rows are present, report that the bundled script leaves SELL payout/PnL unknown unless explicitly extended.
