# Strategy Replication Auditor Review

## Verdict

**Score: 83 / 100**
**Status:** strong but incomplete
**Main reason:** 文档已经足够让独立团队实现一个可回放、可 shadow 的地址行为复刻器，但 alpha 模型训练产物、非 BTC 长尾结算、真实队列/撤单证据和 out-of-sample 结果仍不足以直接生产上线。

Optional lens scores:

- Professional quant memo: 86 / 100
- Independent no-context reproduction: 83 / 100
- Beginner executable clarity: 79 / 100

## Scorecard

| Dimension | Points | Score | Rationale |
| --- | ---: | ---: | --- |
| Reproducibility boundary and scope | 7 | 6 | 地址、窗口、输入、限制、未知项明确；但 strategy version 仍是报告内派生名，缺少独立配置文件版本。 |
| Market mechanics, payoff, and order types | 8 | 7 | 二元 payoff、BUY-only、post-only 推断、费用近似、tick/price 默认值已写清；仍缺交易所 min size、真实 cancel/expiry 语义。 |
| Data specification and time alignment | 8 | 8 | 原始/过滤行数、字段优先级、UTC、3h 分片、DB BTC settlement、Gamma cap、unknown/open 处理都可追踪。 |
| Alpha/probability model | 12 | 7 | 有 label、特征、训练/验证窗口和 fallback；没有训练命令、模型 artifact、系数、校准曲线和验证结果。 |
| Decision rules and state machine | 10 | 8 | no-op、pause、quote、weak-side、cap、post-only reject 流程具体；冲突优先级还可再表格化。 |
| Execution and microstructure | 10 | 8 | ladder、price formula、TTL、post-only、stale book、reject 处理具体；无真实 order id、撤单、L2、queue proof。 |
| Sizing, inventory, budget, and capital allocation | 10 | 9 | q*、lot、rank size、budget cap、abs net cap、weak-side 条件和 worked example 充足。 |
| Risk controls and kill switches | 10 | 8 | data lag、book age、reconciliation、reject、drawdown、cooldown 有阈值；相关性/账户级总暴露仍偏粗。 |
| Backtest, replay, and validation | 9 | 6 | 有 replay/shadow pass-fail 设计和 sensitivity 维度；缺实际 OOS 回测结果、ablation、fill model 实测。 |
| Shadow and live rollout gates | 5 | 4 | 7 天 shadow、输出文件、ramp、rollback 有定义；人工审批/owner 还不够明确。 |
| PnL attribution, economics, and capacity | 6 | 4 | 分解框架存在，resolved ROI 有口径；非 BTC 未全量结算、capacity/ROI decay 还没实证。 |
| Production operations, governance, compliance, readability | 5 | 4 | 监控和恢复要点覆盖，有 glossary-like 解释和 worked example；凭证、变更审批、venue/legal 仍需单独 runbook。 |

## Blocking Gaps

### P1: alpha 仍是可实现框架，不是可复现模型

- **Where:** `strategy_replication_report.md` 的 “alpha 与方向来源”
- **Problem:** 有特征、label、窗口和模型类，但没有训练命令、模型参数、校准结果、阈值来源和 artifact 路径。
- **Why it blocks reproduction:** 两个团队会训练出不同概率，进而产生不同 q* gate、报价方向和 size。
- **Required fix:** 增加 model card：训练 SQL/特征生成脚本、样本切分、模型文件 hash、校准曲线、Brier/logloss、阈值选择表。

### P1: 非 BTC 长尾结算不完整

- **Where:** 数据来源与过滤规则、analysis_summary.json
- **Problem:** 本次用 DB 结算 BTC，并对剩余 market 只拉 Gamma top 1,000；`UNKNOWN` 仍有 312,214 行。
- **Why it blocks reproduction:** PnL、final net correctness、弱边/强边序列在 ETH/SOL/XRP 长尾上仍是部分视图。
- **Required fix:** 增加 ETH/SOL/XRP 的 1s kline settlement，或异步全量 Gamma cache；报告中按 resolved coverage 分资产给出可用性门槛。

### P1: 执行层仍缺真实订单生命周期

- **Where:** inferred order、quote batch、execution sections
- **Problem:** same-price fills 只能代理限价单；没有未成交单、撤单、maker/taker、queue position。
- **Why it blocks reproduction:** 可复刻成交后行为，但不能像素级复刻 quote density、撤单时机和被动成交概率。
- **Required fix:** 接入 CLOB order history 或 live shadow intents，输出 order_id、create/cancel/fill、queue age、book-before-fill。

### P2: 回放验证尚未执行

- **Where:** 回放、shadow 和上线 gate
- **Problem:** pass/fail 标准存在，但没有本地址历史 replay 结果、OOS split 或 fill sensitivity 表。
- **Required fix:** 加一个 `replay_scorecard.csv` 和报告段落：observed_fill、post_only_touch_proxy、one_tick_worse、fee 0x/1x/2x 的 ROI、drawdown、behavior distance。

## Minimal Rewrite Checklist

- [ ] 增加 alpha model card 与训练命令。
- [ ] 用 DB 或 Gamma cache 补齐非 BTC settlement，或按资产明确禁用未结算资产。
- [ ] 把 report 中的默认参数另存为 machine-readable `replication_config.json`。
- [ ] 增加真实 replay 结果和 OOS walk-forward 表。
- [ ] 增加 CLOB/shadow order lifecycle 证据以替代 inferred-order proxy。
- [ ] 增加账户级总暴露、相关性和 capital scaling runbook。
