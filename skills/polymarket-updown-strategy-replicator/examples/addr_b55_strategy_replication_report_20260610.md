# Polymarket Crypto Up/Down 地址策略像素级复刻报告

## 技术摘要

- 地址：`0xb55fa1296e6ec55d0ce53d93b9237389f11764d4`
- 输入：`/Users/hfer/temp/my-skills/tmp/updown-replication-audits/addr_b55_input_20260610_173119/addr_b55_0xb55fa1296e6ec55d0ce53d93b9237389f11764d4_merged_activity_with_capped_settlements.csv`
- 生成时间 UTC：`2026-06-10T09:35:16+00:00`
- 默认/实际窗口：`30` 天；若使用 `--input`，窗口以 CSV 为准。
- crypto Up/Down 成交行：`670,421`；市场：`28,680`；inferred orders：`499,165`。
- 总成本：`12,963,075.57`；已结算/已拉取成本：`9,575,338.33`；已标记 PnL：`766.99`；resolved ROI：`0.01%`。
- BUY-only：`True`；market both-side rate：`83.17%`；multi-fill order rate：`12.69%`；final net correct：`43.29%`。


本报告的复刻边界是“从地址成交历史复刻可观察行为与可验证执行规则”。若没有订单 ID、撤单、未成交单、maker/taker 标记、队列位置和底层价格路径，本报告不会声称拿到了真实源码。它会把可确定事实、强推断、弱推断和 live 上线前必须补的数据分开。

## 一页机制图

```text
address trades -> crypto Up/Down filter -> settlement labels
       -> inferred orders by same market/outcome/side/price within 5s
       -> quote batches by market time gap within 5s
       -> ladder ranks, lifecycle timing, budget, size lots
       -> inventory ledger: Up shares, Down shares, C cost, q*
       -> replication config + backtest/shadow/live gates
```

## 数据来源与过滤规则

- 原始 CSV 行数：`678,119`。
- crypto Up/Down 过滤后行数：`670,421`。
- 过滤逻辑：slug/title 中必须出现 crypto asset 别名，并包含 `updown`、`up-or-down`、`up or down` 或等价描述。
- settlement 字段优先级：`activityOutcomeResult` / `tradeOutcomeResult`；PnL 字段优先级：`activityPnLUSDC` / `tradePnLUSDC`。
- 时间字段：优先 `timestamp` Unix 秒；显示统一使用 UTC。
- market_start：优先从 slug 末尾 10 位 Unix 秒解析；否则使用 market end 字段进行部分生命周期分析。
- inferred order：同 market + outcome + side + rounded price，连续 fill gap <= `5s`。
- quote batch：同 market 中 inferred order 的 first timestamp gap <= `5s`。

| metric | value |
| --- | --- |
| assets | {"BTC": 287257, "ETH": 198751, "SOL": 108177, "XRP": 76236} |
| intervals | {"1h": 137384, "4h": 26463, "15m": 238914, "5m": 267660} |
| side_counts | {"BUY": 670421} |
| result_counts | {"LOSS": 201659, "UNKNOWN": 312214, "WIN": 156465, "OPEN": 83} |

## 市场机制、订单类型和费用假设

- Up/Down 市场是二元 payoff：买中结算边的 share 最终按 `1` 兑付，买错边按 `0` 兑付。
- BUY 行的历史 PnL 使用 settlement enrichment 字段；SELL 行不强行按同一公式解释，报告会保留 side_counts。
- 费用：若 CSV PnL 已含费用则以 CSV 为准；若 live 复刻需要估算，默认使用 `fee_rate = 0.07 * min(price, 1-price)` 的保守 crypto fee 近似，并在回放中做 `0x/0.5x/1x/2x` 敏感性。
- maker/taker：CSV 没有逐笔 maker/taker 标记。若 multi-fill same-price 与低价阶梯明显，默认实现用 `post-only` 限价；若样本显示高价单笔或 SELL 多，应单独降级为未知执行风格。


## 总体表现与市场分布

| asset | interval | markets | fills | cost | pnl | roi | avg_price | resolved_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BTC | 5m | 4133 | 116369 | 2,958,248.67 | 37,258.22 | 1.26% | 0.4479 | 100.00% |
| BTC | 15m | 2455 | 95734 | 2,847,008.76 | -13,582.29 | -0.48% | 0.4742 | 100.00% |
| BTC | 1h | 671 | 60554 | 1,777,217.02 | 22,255.42 | 1.25% | 0.4702 | 100.00% |
| ETH | 15m | 2430 | 73466 | 1,178,035.22 | -23,691.88 | -2.01% | 0.4867 | 32.19% |
| ETH | 5m | 4077 | 79920 | 1,061,235.85 | -10,464.68 | -0.99% | 0.4406 | 11.33% |
| ETH | 1h | 661 | 39749 | 671,721.31 | -8,431.15 | -1.26% | 0.4417 | 65.16% |
| BTC | 4h | 181 | 14600 | 465,807.59 | 8,487.83 | 1.82% | 0.5197 | 99.95% |
| SOL | 15m | 2385 | 41673 | 454,265.38 | -3,374.38 | -0.74% | 0.5268 | 4.23% |
| SOL | 5m | 3850 | 42145 | 388,832.02 | -1,643.14 | -0.42% | 0.4865 | 1.02% |
| XRP | 15m | 2298 | 28041 | 258,944.09 | -1,364.52 | -0.53% | 0.5119 | 1.22% |
| SOL | 1h | 654 | 20996 | 239,410.49 | -3,576.41 | -1.49% | 0.4435 | 15.69% |
| XRP | 5m | 3706 | 29226 | 202,108.10 | 0.00 | 0.00% | 0.4526 | 0.00% |
| ETH | 4h | 180 | 5616 | 160,389.12 | -813.11 | -0.51% | 0.5155 | 59.72% |
| XRP | 1h | 644 | 16085 | 156,509.52 | 1,250.42 | 0.80% | 0.4372 | 8.69% |
| SOL | 4h | 178 | 3363 | 85,963.01 | -1,564.98 | -1.82% | 0.5250 | 28.78% |
| XRP | 4h | 177 | 2884 | 57,379.40 | 21.65 | 0.04% | 0.4896 | 25.14% |

## 生命周期、频率和库存质量

| asset | interval | markets | orders | both_sides_rate | net_correct_rate | weighted_qstar | first_s | last_before_close_s | gap_s | median_cost | p95_cost | median_abs_net | p90_abs_net |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BTC | 15m | 2455 | 69960 | 93.93% | 44.89% | 0.3662 | 432.0000 | 468.0000 | 7.0000 | 830.43 | 3,408.89 | 297.11 | 1,113.52 |
| BTC | 1h | 671 | 37890 | 96.57% | 45.60% | 0.2878 | 1,833.0000 | 1,765.0000 | 14.0000 | 2,031.19 | 6,800.07 | 420.34 | 2,141.73 |
| BTC | 4h | 181 | 11334 | 98.34% | 67.22% | 0.6194 | 7,404.0000 | 6,996.0000 | 48.0000 | 2,215.41 | 6,199.35 | 583.77 | 1,753.77 |
| BTC | 5m | 4133 | 60877 | 87.64% | 39.06% | 0.2257 | 133.0000 | 167.0000 | 6.0000 | 488.76 | 2,223.22 | 165.59 | 736.81 |
| ETH | 15m | 2430 | 62823 | 89.55% | 61.16% | 0.4433 | 412.5000 | 487.2500 | 7.0000 | 333.99 | 1,393.92 | 158.64 | 521.07 |
| ETH | 1h | 661 | 31184 | 97.58% | 34.38% | 0.2115 | 1,889.5000 | 1,710.5000 | 15.0000 | 798.85 | 2,567.12 | 256.77 | 1,146.91 |
| ETH | 4h | 180 | 4745 | 95.00% | 50.00% | 0.5771 | 8,239.0000 | 6,161.0000 | 75.0000 | 724.46 | 2,574.18 | 248.00 | 732.81 |
| ETH | 5m | 4077 | 62721 | 85.99% | 66.06% | 0.2850 | 136.0000 | 163.0000 | 5.0000 | 163.47 | 791.27 | 100.74 | 384.35 |
| SOL | 15m | 2385 | 36696 | 82.94% | 71.43% | 0.5943 | 428.0000 | 472.0000 | 9.0000 | 131.48 | 585.04 | 73.60 | 225.64 |
| SOL | 1h | 654 | 17213 | 93.43% | 30.00% | 0.2670 | 2,060.2500 | 1,539.7500 | 27.0000 | 261.45 | 1,048.08 | 112.62 | 514.13 |
| SOL | 4h | 178 | 2905 | 92.70% | 36.00% | 0.6176 | 8,228.5000 | 6,171.5000 | 135.0000 | 353.40 | 1,310.80 | 117.25 | 368.19 |
| SOL | 5m | 3850 | 34858 | 75.48% | 62.50% | 0.4589 | 137.0000 | 162.5000 | 7.0000 | 63.54 | 326.99 | 44.13 | 149.88 |
| XRP | 15m | 2298 | 24798 | 74.24% | 25.00% | 0.5382 | 453.2500 | 446.7500 | 12.0000 | 69.08 | 360.89 | 47.08 | 153.06 |
| XRP | 1h | 644 | 13621 | 90.06% | 33.33% | 0.2447 | 1,997.5000 | 1,602.5000 | 30.0000 | 174.96 | 702.80 | 85.27 | 312.45 |
| XRP | 4h | 177 | 2318 | 86.44% | 33.33% | 0.4476 | 8,212.0000 | 6,188.0000 | 149.0000 | 214.08 | 1,099.46 | 79.17 | 307.30 |
| XRP | 5m | 3706 | 25222 | 67.51% | n/a | 0.3716 | 139.0000 | 161.0000 | 10.0000 | 31.52 | 190.69 | 28.91 | 98.32 |

## inferred order 证据

| asset | interval | orders | fills | markets | cost | multi_fill_rate | multi_fill_cost | median_fills | p95_fills | median_shares | p95_shares | median_order_cost | p95_order_cost |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BTC | 5m | 60877 | 116369 | 4133 | 2,958,248.67 | 19.88% | 25.65% | 1.0000 | 7.0000 | 67.01 | 357.00 | 23.72 | 173.26 |
| BTC | 15m | 69960 | 95734 | 2455 | 2,847,008.76 | 13.29% | 21.06% | 1.0000 | 3.0000 | 42.00 | 300.00 | 17.03 | 157.44 |
| BTC | 1h | 37890 | 60554 | 671 | 1,777,217.02 | 17.51% | 24.32% | 1.0000 | 3.0000 | 38.92 | 390.00 | 14.92 | 201.92 |
| ETH | 15m | 62823 | 73466 | 2430 | 1,178,035.22 | 10.25% | 17.52% | 1.0000 | 2.0000 | 22.09 | 122.15 | 10.03 | 62.79 |
| ETH | 5m | 62721 | 79920 | 4077 | 1,061,235.85 | 11.85% | 16.13% | 1.0000 | 2.0000 | 23.00 | 119.98 | 9.10 | 58.05 |
| ETH | 1h | 31184 | 39749 | 661 | 671,721.31 | 14.25% | 20.76% | 1.0000 | 3.0000 | 21.00 | 189.00 | 9.55 | 75.68 |
| BTC | 4h | 11334 | 14600 | 181 | 465,807.59 | 12.05% | 15.58% | 1.0000 | 2.0000 | 23.00 | 353.12 | 10.43 | 180.39 |
| SOL | 15m | 36696 | 41673 | 2385 | 454,265.38 | 9.05% | 15.18% | 1.0000 | 2.0000 | 15.50 | 68.55 | 7.64 | 38.19 |
| SOL | 5m | 34858 | 42145 | 3850 | 388,832.02 | 11.04% | 14.67% | 1.0000 | 2.0000 | 16.03 | 65.40 | 7.01 | 36.21 |
| XRP | 15m | 24798 | 28041 | 2298 | 258,944.09 | 8.22% | 12.87% | 1.0000 | 2.0000 | 14.60 | 59.97 | 6.45 | 32.84 |
| SOL | 1h | 17213 | 20996 | 654 | 239,410.49 | 11.36% | 18.00% | 1.0000 | 2.0000 | 18.00 | 114.32 | 6.07 | 48.02 |
| XRP | 5m | 25222 | 29226 | 3706 | 202,108.10 | 8.88% | 9.95% | 1.0000 | 2.0000 | 12.00 | 50.00 | 5.03 | 25.56 |
| ETH | 4h | 4745 | 5616 | 180 | 160,389.12 | 9.36% | 14.56% | 1.0000 | 2.0000 | 32.00 | 242.40 | 11.74 | 132.20 |
| XRP | 1h | 13621 | 16085 | 644 | 156,509.52 | 9.52% | 13.53% | 1.0000 | 2.0000 | 15.07 | 87.19 | 5.18 | 42.77 |
| SOL | 4h | 2905 | 3363 | 178 | 85,963.01 | 8.36% | 16.20% | 1.0000 | 2.0000 | 34.00 | 180.00 | 12.00 | 97.02 |
| XRP | 4h | 2318 | 2884 | 177 | 57,379.40 | 9.62% | 19.83% | 1.0000 | 2.0000 | 40.00 | 144.00 | 9.20 | 81.43 |

解释：multi-fill same-price inferred order 越高，越支持限价挂单或挂单被连续打中的解释。但这仍不是订单 ID 级证明，因为 CSV 看不到未成交单和撤单。

## quote batch 和阶梯结构

| asset | interval | batches | markets | orders | cost | both_side_batch | both_side_cost | multi_order_batch | median_orders_batch | p90_price_levels |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BTC | 5m | 33905 | 4133 | 60877 | 2,958,248.67 | 9.78% | 26.58% | 38.05% | 1.0000 | 3.0000 |
| BTC | 15m | 41169 | 2455 | 69960 | 2,847,008.76 | 4.41% | 15.00% | 33.74% | 1.0000 | 3.0000 |
| BTC | 1h | 26444 | 671 | 37890 | 1,777,217.02 | 2.60% | 11.12% | 22.74% | 1.0000 | 2.0000 |
| ETH | 15m | 35267 | 2430 | 62823 | 1,178,035.22 | 3.27% | 11.75% | 33.74% | 1.0000 | 3.0000 |
| ETH | 5m | 33183 | 4077 | 62721 | 1,061,235.85 | 7.14% | 20.51% | 39.67% | 1.0000 | 4.0000 |
| ETH | 1h | 21961 | 661 | 31184 | 671,721.31 | 2.27% | 10.87% | 22.85% | 1.0000 | 2.0000 |
| BTC | 4h | 9322 | 181 | 11334 | 465,807.59 | 2.06% | 7.67% | 13.39% | 1.0000 | 2.0000 |
| SOL | 15m | 22355 | 2385 | 36696 | 454,265.38 | 1.71% | 6.21% | 30.13% | 1.0000 | 3.0000 |
| SOL | 5m | 21087 | 3850 | 34858 | 388,832.02 | 3.39% | 9.95% | 32.53% | 1.0000 | 3.0000 |
| XRP | 15m | 16593 | 2298 | 24798 | 258,944.09 | 1.74% | 6.89% | 25.58% | 1.0000 | 3.0000 |
| SOL | 1h | 13641 | 654 | 17213 | 239,410.49 | 1.92% | 9.25% | 15.45% | 1.0000 | 2.0000 |
| XRP | 5m | 17271 | 3706 | 25222 | 202,108.10 | 3.50% | 11.17% | 26.66% | 1.0000 | 2.0000 |
| ETH | 4h | 3918 | 180 | 4745 | 160,389.12 | 2.17% | 7.16% | 12.53% | 1.0000 | 2.0000 |
| XRP | 1h | 10932 | 644 | 13621 | 156,509.52 | 2.02% | 8.70% | 15.03% | 1.0000 | 2.0000 |
| SOL | 4h | 2513 | 178 | 2905 | 85,963.01 | 1.71% | 5.89% | 10.86% | 1.0000 | 2.0000 |
| XRP | 4h | 2018 | 177 | 2318 | 57,379.40 | 2.58% | 11.67% | 10.36% | 1.0000 | 2.0000 |

阶梯 rank 中，BUY 价格最高为 rank 1，更低价格为更深阶梯。
| asset | interval | rank | levels | cost | shares | median_shares | cost_share |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BTC | 15m | 1 | 43042 | 1,777,715.44 | 3,809,550.24 | 42.00 | 62.44% |
| BTC | 15m | 2 | 13687 | 518,786.00 | 1,080,374.36 | 40.00 | 18.22% |
| BTC | 15m | 3 | 5964 | 233,381.85 | 471,113.03 | 41.99 | 8.20% |
| BTC | 15m | 4 | 2922 | 121,884.25 | 244,058.90 | 45.01 | 4.28% |
| BTC | 15m | 5 | 1624 | 73,671.72 | 144,708.50 | 53.10 | 2.59% |
| BTC | 15m | 6+ | 2721 | 121,569.49 | 253,920.80 | 50.00 | 4.27% |
| BTC | 1h | 1 | 27186 | 1,322,166.93 | 2,837,829.14 | 39.83 | 74.40% |
| BTC | 1h | 2 | 5850 | 242,457.28 | 510,612.65 | 34.91 | 13.64% |
| BTC | 1h | 3 | 2194 | 92,319.06 | 178,526.87 | 35.00 | 5.19% |
| BTC | 1h | 4 | 1042 | 45,476.99 | 91,602.67 | 40.00 | 2.56% |
| BTC | 1h | 5 | 545 | 25,486.42 | 49,882.37 | 43.69 | 1.43% |
| BTC | 1h | 6+ | 1073 | 49,310.34 | 111,432.60 | 46.00 | 2.77% |
| BTC | 4h | 1 | 9523 | 413,311.91 | 797,024.21 | 23.90 | 88.73% |
| BTC | 4h | 2 | 1141 | 33,599.58 | 63,788.56 | 20.00 | 7.21% |
| BTC | 4h | 3 | 345 | 10,736.18 | 19,473.92 | 20.14 | 2.30% |
| BTC | 4h | 4 | 142 | 4,068.90 | 8,302.55 | 24.00 | 0.87% |
| BTC | 4h | 5 | 81 | 2,003.71 | 3,347.42 | 23.00 | 0.43% |
| BTC | 4h | 6+ | 102 | 2,087.32 | 4,294.92 | 16.21 | 0.45% |
| BTC | 5m | 1 | 37313 | 1,857,421.91 | 4,148,442.29 | 70.00 | 62.79% |
| BTC | 5m | 2 | 12500 | 570,053.16 | 1,275,784.69 | 62.92 | 19.27% |
| BTC | 5m | 3 | 5397 | 253,569.86 | 555,243.28 | 61.69 | 8.57% |
| BTC | 5m | 4 | 2595 | 126,018.27 | 283,957.83 | 66.84 | 4.26% |
| BTC | 5m | 5 | 1316 | 65,465.48 | 143,306.20 | 64.42 | 2.21% |
| BTC | 5m | 6+ | 1756 | 85,719.98 | 197,697.50 | 67.18 | 2.90% |
| ETH | 15m | 1 | 36498 | 651,519.74 | 1,375,635.35 | 21.19 | 55.31% |
| ETH | 15m | 2 | 11876 | 223,559.09 | 450,213.77 | 22.00 | 18.98% |
| ETH | 15m | 3 | 5623 | 115,374.69 | 226,313.21 | 24.49 | 9.79% |
| ETH | 15m | 4 | 3159 | 67,882.93 | 131,355.41 | 25.29 | 5.76% |
| ETH | 15m | 5 | 1926 | 41,337.39 | 79,114.13 | 25.01 | 3.51% |
| ETH | 15m | 6+ | 3741 | 78,361.39 | 157,825.83 | 26.09 | 6.65% |

## price band 与 size 是否像 Kelly

| asset | interval | price_band | orders | markets | cost | shares | pnl | roi | avg_order_shares | avg_price |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BTC | 1h | 0-0.25 | 9234 | 603 | 96,134.10 | 1,050,677.95 | 12,894.38 | 13.41% | 113.78 | 0.0915 |
| BTC | 1h | 0.25-0.40 | 5315 | 533 | 124,372.85 | 376,353.96 | 8,948.41 | 7.19% | 70.81 | 0.3305 |
| BTC | 1h | 0.40-0.47 | 2974 | 494 | 113,944.58 | 254,546.40 | -1,820.51 | -1.60% | 85.59 | 0.4476 |
| BTC | 1h | 0.47-0.49 | 1124 | 417 | 102,090.78 | 208,817.98 | -9,669.12 | -9.47% | 185.78 | 0.4889 |
| BTC | 1h | 0.49-0.51 | 1184 | 413 | 75,852.19 | 148,071.89 | 5,086.09 | 6.71% | 125.06 | 0.5123 |
| BTC | 1h | 0.51-0.65 | 8050 | 605 | 449,256.72 | 764,801.74 | 11,026.40 | 2.45% | 95.01 | 0.5874 |
| BTC | 1h | 0.65-0.85 | 6757 | 580 | 400,145.21 | 534,818.44 | -13,618.15 | -3.40% | 79.15 | 0.7482 |
| BTC | 1h | 0.85-1.00 | 3252 | 472 | 415,420.59 | 441,797.93 | 9,407.91 | 2.26% | 135.85 | 0.9403 |
| ETH | 1h | 0-0.25 | 8856 | 606 | 47,496.61 | 536,541.68 | 5,350.64 | 11.27% | 60.59 | 0.0885 |
| ETH | 1h | 0.25-0.40 | 4029 | 507 | 49,459.64 | 151,168.09 | 281.62 | 0.57% | 37.52 | 0.3272 |
| ETH | 1h | 0.40-0.47 | 1979 | 391 | 32,252.89 | 72,247.54 | -644.32 | -2.00% | 36.51 | 0.4464 |
| ETH | 1h | 0.47-0.49 | 852 | 362 | 28,062.76 | 56,822.33 | -764.53 | -2.72% | 66.69 | 0.4939 |
| ETH | 1h | 0.49-0.51 | 954 | 397 | 21,187.16 | 41,310.96 | -327.40 | -1.55% | 43.30 | 0.5129 |
| ETH | 1h | 0.51-0.65 | 6279 | 593 | 144,244.73 | 244,352.81 | -7,341.42 | -5.09% | 38.92 | 0.5903 |
| ETH | 1h | 0.65-0.85 | 6137 | 592 | 179,633.60 | 241,215.12 | -5,507.14 | -3.07% | 39.31 | 0.7447 |
| ETH | 1h | 0.85-1.00 | 2098 | 436 | 169,383.92 | 176,994.43 | 521.40 | 0.31% | 84.36 | 0.9570 |
| ETH | 4h | 0-0.25 | 1112 | 147 | 8,452.06 | 88,218.92 | 2,177.06 | 25.76% | 79.33 | 0.0958 |
| ETH | 4h | 0.25-0.40 | 551 | 116 | 8,713.50 | 26,537.05 | 2,976.89 | 34.16% | 48.16 | 0.3284 |
| ETH | 4h | 0.40-0.47 | 219 | 76 | 4,772.74 | 10,847.08 | -666.16 | -13.96% | 49.53 | 0.4400 |
| ETH | 4h | 0.47-0.49 | 68 | 51 | 1,782.59 | 3,618.52 | -679.85 | -38.14% | 53.21 | 0.4926 |
| ETH | 4h | 0.49-0.51 | 131 | 70 | 3,562.08 | 6,950.89 | -1,387.18 | -38.94% | 53.06 | 0.5125 |
| ETH | 4h | 0.51-0.65 | 829 | 157 | 25,387.82 | 43,327.91 | -1,270.31 | -5.00% | 52.27 | 0.5859 |
| ETH | 4h | 0.65-0.85 | 1351 | 172 | 64,429.44 | 85,112.52 | -2,467.29 | -3.83% | 63.00 | 0.7570 |
| ETH | 4h | 0.85-1.00 | 484 | 135 | 43,288.90 | 46,516.41 | 503.73 | 1.16% | 96.11 | 0.9306 |
| BTC | 4h | 0-0.25 | 2014 | 167 | 16,483.16 | 212,334.28 | -3,422.07 | -20.76% | 105.43 | 0.0776 |
| BTC | 4h | 0.25-0.40 | 1551 | 144 | 28,881.16 | 86,500.07 | 11,491.93 | 39.79% | 55.77 | 0.3339 |
| BTC | 4h | 0.40-0.47 | 869 | 141 | 18,970.76 | 42,521.34 | 1,691.90 | 8.92% | 48.93 | 0.4461 |
| BTC | 4h | 0.47-0.49 | 285 | 107 | 10,277.38 | 21,010.95 | 2,559.62 | 24.91% | 73.72 | 0.4891 |
| BTC | 4h | 0.49-0.51 | 360 | 121 | 11,736.20 | 22,926.69 | -2,696.02 | -22.97% | 63.69 | 0.5119 |
| BTC | 4h | 0.51-0.65 | 2633 | 172 | 97,343.85 | 165,414.65 | -5,144.17 | -5.28% | 62.82 | 0.5885 |

判定规则：如果 shares 在价格桶间主要是离散 lot 且不随 edge 连续缩放，就不能称为 Kelly。复刻实现默认使用离散 lot + rank multiplier + q*/budget gate，而不是 `stake = bankroll * Kelly(p, price)`。

## 市场阶段收益

| asset | interval | phase | fills | markets | cost | pnl | roi | winner_cost_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BTC | 1h | 0-10% | 6072 | 622 | 320,641.74 | -5,775.36 | -1.80% | 53.64% |
| BTC | 1h | 10-20% | 3617 | 552 | 138,257.55 | -3,234.86 | -2.34% | 59.14% |
| BTC | 1h | 20-40% | 8510 | 609 | 249,758.88 | 7,377.51 | 2.95% | 61.34% |
| BTC | 1h | 40-60% | 9756 | 592 | 259,276.30 | 7,749.70 | 2.99% | 64.79% |
| BTC | 1h | 60-80% | 10844 | 564 | 293,755.60 | 13,865.05 | 4.72% | 70.93% |
| BTC | 1h | 80-95% | 17073 | 471 | 354,206.78 | 7,020.20 | 1.98% | 76.13% |
| BTC | 1h | 95-100% | 4682 | 259 | 161,320.18 | -4,746.82 | -2.94% | 67.61% |
| ETH | 1h | 0-10% | 3999 | 582 | 92,389.29 | -5,473.08 | -5.92% | 33.43% |
| ETH | 1h | 10-20% | 2804 | 485 | 53,195.25 | -3,313.96 | -6.23% | 38.82% |
| ETH | 1h | 20-40% | 6301 | 589 | 101,271.49 | 1,908.90 | 1.88% | 41.82% |
| ETH | 1h | 40-60% | 7509 | 592 | 106,805.57 | 2,801.98 | 2.62% | 44.49% |
| ETH | 1h | 60-80% | 8188 | 559 | 123,313.17 | -3,927.58 | -3.19% | 53.86% |
| ETH | 1h | 80-95% | 8578 | 474 | 146,188.97 | -1,379.61 | -0.94% | 60.77% |
| ETH | 1h | 95-100% | 2370 | 233 | 48,557.58 | 952.21 | 1.96% | 63.49% |
| ETH | 4h | 0-10% | 440 | 134 | 9,464.33 | 330.84 | 3.50% | 29.60% |
| ETH | 4h | 10-20% | 384 | 114 | 11,510.21 | -1,767.98 | -15.36% | 31.45% |
| ETH | 4h | 20-40% | 867 | 147 | 24,263.29 | 1,752.11 | 7.22% | 46.33% |
| ETH | 4h | 40-60% | 993 | 153 | 29,377.83 | 1,657.33 | 5.64% | 47.52% |
| ETH | 4h | 60-80% | 1194 | 148 | 32,317.61 | -1,132.92 | -3.51% | 42.84% |
| ETH | 4h | 80-95% | 1191 | 124 | 33,499.43 | -2,171.40 | -6.48% | 54.80% |
| ETH | 4h | 95-100% | 547 | 67 | 19,956.41 | 518.91 | 2.60% | 62.91% |
| BTC | 4h | 0-10% | 1168 | 164 | 38,061.19 | -5,874.66 | -15.43% | 46.22% |
| BTC | 4h | 10-20% | 881 | 159 | 29,604.15 | 1,116.08 | 3.77% | 59.26% |
| BTC | 4h | 20-40% | 2427 | 169 | 87,542.72 | -1,254.80 | -1.43% | 64.32% |
| BTC | 4h | 40-60% | 2502 | 167 | 98,698.25 | 3,385.44 | 3.43% | 71.85% |
| BTC | 4h | 60-80% | 3173 | 162 | 94,114.22 | 3,885.59 | 4.13% | 74.74% |
| BTC | 4h | 80-95% | 3416 | 141 | 77,997.38 | 5,829.50 | 7.47% | 81.76% |
| BTC | 4h | 95-100% | 1033 | 72 | 39,789.69 | 1,400.68 | 3.52% | 78.45% |
| ETH | 15m | 0-10% | 9794 | 1873 | 200,341.77 | -6,689.06 | -3.34% | 21.66% |
| ETH | 15m | 10-20% | 6681 | 1634 | 104,522.49 | -3,556.31 | -3.40% | 22.94% |

## 序列：是否连续买强边或弱边

| asset | interval | prev | current | orders | cost | share_from_prev |
| --- | --- | --- | --- | --- | --- | --- |
| BTC | 15m | loser_proxy | loser_proxy | 26721 | 806,895.36 | 0.8003 |
| BTC | 15m | loser_proxy | winner_proxy | 6668 | 382,143.34 | 0.1997 |
| BTC | 15m | winner_proxy | loser_proxy | 6948 | 195,307.18 | 0.2037 |
| BTC | 15m | winner_proxy | winner_proxy | 27168 | 1,339,872.94 | 0.7963 |
| BTC | 1h | loser_proxy | loser_proxy | 15987 | 479,928.83 | 0.8301 |
| BTC | 1h | loser_proxy | winner_proxy | 3271 | 265,603.87 | 0.1699 |
| BTC | 1h | winner_proxy | loser_proxy | 3317 | 95,228.74 | 0.1847 |
| BTC | 1h | winner_proxy | winner_proxy | 14644 | 859,079.43 | 0.8153 |
| BTC | 4h | loser_proxy | loser_proxy | 4078 | 102,576.34 | 0.7673 |
| BTC | 4h | loser_proxy | winner_proxy | 1237 | 75,168.38 | 0.2327 |
| BTC | 4h | unknown | unknown | 6 | 257.79 | 1.0000 |
| BTC | 4h | winner_proxy | loser_proxy | 1236 | 30,900.39 | 0.2119 |
| BTC | 4h | winner_proxy | winner_proxy | 4596 | 248,973.09 | 0.7881 |
| BTC | 5m | loser_proxy | loser_proxy | 21281 | 771,493.31 | 0.7357 |
| BTC | 5m | loser_proxy | winner_proxy | 7644 | 502,930.49 | 0.2643 |
| BTC | 5m | winner_proxy | loser_proxy | 8168 | 285,061.95 | 0.2936 |
| BTC | 5m | winner_proxy | winner_proxy | 19651 | 1,172,263.21 | 0.7064 |
| ETH | 15m | loser_proxy | loser_proxy | 7712 | 171,243.56 | 0.8314 |
| ETH | 15m | loser_proxy | winner_proxy | 1564 | 46,832.52 | 0.1686 |
| ETH | 15m | unknown | unknown | 40543 | 614,483.55 | 1.0000 |
| ETH | 15m | winner_proxy | loser_proxy | 1569 | 23,946.24 | 0.1484 |
| ETH | 15m | winner_proxy | winner_proxy | 9005 | 255,101.68 | 0.8516 |
| ETH | 1h | loser_proxy | loser_proxy | 8816 | 137,445.14 | 0.8271 |
| ETH | 1h | loser_proxy | winner_proxy | 1843 | 95,259.03 | 0.1729 |
| ETH | 1h | unknown | unknown | 10536 | 164,916.31 | 1.0000 |
| ETH | 1h | winner_proxy | loser_proxy | 1842 | 26,188.57 | 0.1975 |
| ETH | 1h | winner_proxy | winner_proxy | 7486 | 226,350.38 | 0.8025 |
| ETH | 4h | loser_proxy | loser_proxy | 1019 | 23,816.82 | 0.7347 |
| ETH | 4h | loser_proxy | winner_proxy | 368 | 19,377.64 | 0.2653 |
| ETH | 4h | unknown | unknown | 1818 | 47,257.54 | 1.0000 |

`winner_proxy` / `loser_proxy` 是 ex-post 标签，只说明最终结果，不代表当时 live alpha。若连续 loser_proxy 很多，可能是弱边便宜 optionality、库存修复，也可能是错误 alpha；必须结合底层价格路径验证。

## q* 库存账本

设 `U` 为 Up shares，`D` 为 Down shares，`C` 为累计买入成本。

```text
if U > D: q*_up = (C - D) / (U - D)
if D > U: q*_down = (C - U) / (D - U)
if U == D: no directional q*, evaluate bundle cost and future optionality
```

每个候选订单必须先模拟成交后库存，再用 `p_side >= q*_after + required_margin` 判断是否扩大净风险。

## alpha 与方向来源

仅凭地址成交 CSV 不能直接恢复 live alpha。可确定的是最终净仓与结算边之间的关系，以及订单在生命周期中的偏向。若要从本报告上线策略，必须补底层 1s kline/orderbook 并训练或校准 fair value 模型。

默认 live alpha 模型规格：

```yaml
label: market_winning_outcome_up
training_window: rolling_45_days_before_trade_day
validation_window: next_7_days_walk_forward
sample_frequency: every_1s_or_5s_while_market_open
model: logistic_regression_or_calibrated_gradient_boosting
features:
  - asset_one_hot
  - interval
  - elapsed_frac
  - seconds_remaining_sqrt
  - ret_from_open_bps
  - abs_ret_from_open_bps
  - ret_1s_bps
  - ret_3s_bps
  - ret_5s_bps
  - ret_15s_bps
  - realized_vol_15s_bps
  - realized_vol_30s_bps
  - range_so_far_bps
  - clean_book_implied_probability
fallback_without_kline: research_report_only_no_live_orders
```


## 样本派生的复刻配置

```json
{
  "strategy_id": "btc_15m_address_updown_replica_v1",
  "asset": "BTC",
  "interval": "15m",
  "order_merge_gap_sec": 5,
  "batch_gap_sec": 5,
  "start_quote_after_open_sec": 432.0,
  "stop_new_orders_before_close_sec": 468.0,
  "quote_refresh_sec": 7.0,
  "median_order_shares": 42.0,
  "p95_order_shares": 300.0,
  "ladder_rank_lots": [
    42.0,
    40.0,
    41.99,
    45.0116,
    53.0956,
    50.0
  ],
  "market_budget_median": 830.4287,
  "market_budget_soft_cap": 3408.8877,
  "market_budget_hard_cap": 5675.9151,
  "abs_net_soft_cap": 297.11,
  "abs_net_hard_cap": 1113.5229,
  "qstar_reference": 0.366176
}
```

这些值不是永恒参数，而是该地址在本窗口内的行为锚点。上线前必须在新窗口重算，并使用 shadow gate。

## 可直接实现的默认参数

```yaml
price_tick: 0.01
min_order_price: 0.01
max_order_price: 0.99
post_only: true
order_ttl_sec: 5
post_only_reject_retry_ticks: 1
post_only_reject_max_retries: 1
qstar_required_margin: 0.025
model_probability_buffer: 0.020
execution_buffer: 0.010
fee_buffer: 0.003
weak_side_size_multiplier: 0.35
weak_side_allow_when:
  - qstar_after <= qstar_before - 0.010
  - abs_net_after <= abs_net_before * 0.85
  - price <= p_side - 0.060
market_budget_soft_cap_usdc: 3408.8877
market_budget_hard_cap_usdc: 5675.9151
abs_net_soft_cap_shares: 297.11
abs_net_hard_cap_shares: 1113.5229
cancel_all_when:
  data_lag_sec: 2
  book_age_ms: 500
  reconciliation_gap_usdc: 1.00
  consecutive_post_only_rejects: 3
```


## 决策状态机

```text
on each market tick:
  if market asset/interval not in enabled config: no-op
  if data lag > 2s or book stale > 500ms: cancel open quotes and pause
  if elapsed < start_quote_after_open_sec: no-op
  if seconds_to_close < stop_new_orders_before_close_sec: cancel or do not add risk
  estimate p_up/p_down from live alpha model
  reconcile filled inventory from user activity/order API
  for side in Up/Down:
    build rank ladder from anchor price and rank_lots
    simulate each candidate fill
    accept expand only if p_side >= qstar_after + required_margin
    accept weak-side only if it reduces abs_net or is cheap optionality
  enforce market_budget_soft_cap, market_budget_hard_cap, abs_net_hard_cap
  send post-only GTC/GTD BUY intents; on post-only reject, lower one tick or skip
```


## 价格、阶梯和 size 规则

```text
fair_cap = p_side - qstar_required_margin - execution_buffer - fee_buffer
book_cap = best_ask - tick
join_cap = best_bid + tick if best_bid is clean else book_cap
anchor = floor_to_tick(min(fair_cap, book_cap, join_cap))
level_price[i] = anchor - offsets_ticks[i] * tick
shares[i] = round_lot(ladder_rank_lots[i] * side_multiplier * edge_multiplier)
```

Default offsets: `[0, 1, 2, 3, 5, 8]` ticks. If sample has fewer ranks, reuse the last observed rank lot for deeper levels only in shadow.

## 风控硬阈值

```yaml
market_budget_soft_cap: sample_p95_market_cost
market_budget_hard_cap: sample_p99_market_cost
abs_net_soft_cap: sample_median_abs_net
abs_net_hard_cap: sample_p90_abs_net
data_lag_pause_sec: 2
book_age_pause_ms: 500
post_only_reject_action: lower_one_tick_once_else_skip
unexplained_reconciliation_gap_action: cancel_all_and_pause
resolved_market_loss_cooldown_min: 30
daily_drawdown_stop: min(3 * sample_median_market_loss, 2% account_equity)
resume_after_pause: require data_health_ok and manual_or_scripted_reconciliation_ok
```


## 回放、shadow 和上线 gate

```yaml
offline_replay_required:
  min_resolved_markets: 300
  fill_models: [observed_fill_replay, post_only_touch_proxy, one_tick_worse]
  fee_sensitivity: [0x, 0.5x, 1x, 2x]
  pass:
    roi_after_fee: '> 0'
    rolling_100_market_pnl: '> 0'
    qstar_margin: '>= 1.5 percentage points when q* is applicable'
    behavior_distance: lifecycle, ladder, budget, and inventory metrics within sample p25-p75 or explained
shadow_required:
  duration_days: 7
  outputs: [order_intents.ndjson, simulated_fills.ndjson, inventory_snapshots.ndjson, scorecard.csv]
live_ramp:
  phase_1: 0.10x sample budget scale
  phase_2: 0.25x after 500 resolved shadow/live markets pass
  rollback: any reconciliation gap, data lag incident, or unexplained loss cluster
```


## PnL 归因框架

- Direction alpha：最终净仓是否偏向 winning outcome。
- Execution improvement：成交价是否优于同秒/邻近盘口；没有 orderbook 时不能证明。
- Inventory optionality：双边库存降低亏损底座，q* 低于预测概率。
- Adverse selection：高价、临近收盘、stale book 或连续错误净仓导致的亏损。
- Fees/rebates：CSV 未完全暴露时必须做敏感性，而不是只看毛收益。
- Capacity：用 p95/p99 market cost 和 top-of-book notional 验证，不能线性放大。

## Worked Example

示例市场：`bitcoin-up-or-down-may-13-2026-3am-et`，asset `BTC`，interval `1h`，cost `15,413.73`，PnL `-531.40`。
| ts_utc | outcome | side | price | shares | cost | cum_up | cum_down | cum_cost | net_side | abs_net | qstar |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-05-13T07:00:16+00:00 | Up | BUY | 0.5300 | 148.00 | 81.02 | 148.0000 | 0.0000 | 81.02 | Up | 148.00 | 0.5474 |
| 2026-05-13T07:00:23+00:00 | Up | BUY | 0.6000 | 99.80 | 61.56 | 247.8000 | 0.0000 | 142.58 | Up | 247.80 | 0.5754 |
| 2026-05-13T07:00:33+00:00 | Up | BUY | 0.6000 | 37.50 | 22.50 | 285.3000 | 0.0000 | 165.08 | Up | 285.30 | 0.5786 |
| 2026-05-13T07:01:08+00:00 | Down | BUY | 0.3800 | 5.00 | 1.98 | 285.3000 | 5.0000 | 167.06 | Up | 280.30 | 0.5782 |
| 2026-05-13T07:04:05+00:00 | Down | BUY | 0.3900 | 5.00 | 2.03 | 285.3000 | 10.0000 | 169.09 | Up | 275.30 | 0.5779 |
| 2026-05-13T07:07:07+00:00 | Down | BUY | 0.4400 | 493.00 | 225.42 | 285.3000 | 503.0000 | 394.52 | Down | 217.70 | 0.5017 |
| 2026-05-13T07:08:56+00:00 | Up | BUY | 0.5700 | 235.42 | 138.23 | 520.7200 | 503.0000 | 532.74 | Up | 17.72 | 1.6786 |
| 2026-05-13T07:10:21+00:00 | Down | BUY | 0.4000 | 663.00 | 276.34 | 520.7200 | 1,166.0000 | 809.08 | Down | 645.28 | 0.4469 |
| 2026-05-13T07:11:31+00:00 | Up | BUY | 0.5800 | 91.75 | 53.22 | 612.4733 | 1,166.0000 | 862.30 | Down | 553.53 | 0.4513 |
| 2026-05-13T07:12:57+00:00 | Up | BUY | 0.5600 | 80.00 | 44.80 | 692.4733 | 1,166.0000 | 907.10 | Down | 473.53 | 0.4533 |
| 2026-05-13T07:13:11+00:00 | Up | BUY | 0.5600 | 4.55 | 2.55 | 697.0188 | 1,166.0000 | 909.65 | Down | 468.98 | 0.4534 |
| 2026-05-13T07:13:48+00:00 | Up | BUY | 0.6300 | 25.00 | 16.16 | 722.0188 | 1,166.0000 | 925.80 | Down | 443.98 | 0.4590 |

## 已确定、未知和禁止外推

已确定：成交时间、价格、size、side、market、settlement labels、PnL 字段、inferred order 代理、库存账本。

强推断：限价/挂单风格、阶梯结构、预算分布、q* 控制、final net 方向质量。

未知：未成交单、撤单、maker/taker、队列位置、完整 L2、真实外部 alpha、账户总资金、隐藏 hedge。

禁止外推：不要把 ex-post winner 直接写成 live alpha；不要把 median cost 写成固定 cap；不要把离散 lot 写成 Kelly。

## Auditor Readiness Checklist

- [x] exact address/window/input path
- [x] crypto Up/Down filter and data fields
- [x] inferred order and batch construction
- [x] lifecycle, ladder, size, budget, inventory, q* sections
- [x] alpha boundary and default live model spec
- [x] deterministic config with sample-derived defaults
- [x] risk, backtest, shadow and live gates
- [x] worked market example
- [x] known unknowns and non-goals
