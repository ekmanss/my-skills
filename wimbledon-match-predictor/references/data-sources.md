# Data Sources

Use sources for raw facts only. Always cite sources in the final answer when browsing was used.

## Current Wimbledon Match State

Preferred sources:

1. Wimbledon official scores, SlamTracker, match centre, and official match reports.
2. ATP/WTA official match pages and reports.
3. Flashscore, Sofascore, Tennis Explorer, or similar live-score sites for raw score/stat cross-checks only.
4. Direct broadcast/live text reports for court conditions, medical timeouts, roof status, or suspension reasons.

Allowed fields:

- Score, status, elapsed time, server, point/game/set state.
- Serve/return stats, winners/errors, break points, net points, distance, rally notes.
- Court, roof, weather/light, suspension/resumption timing.
- Reported injury, medical timeout, visible movement limitation, fatigue scheduling.

Forbidden fields:

- Betting odds, bookmaker lines, exchange prices.
- Market-implied probability.
- IBM Live Likelihood or any site-provided live win probability.
- Third-party prediction percentages, tipster picks, or model outputs.

If a page mixes raw stats with odds, extract only the raw stats and ignore odds completely.

## Historical Context

Prefer:

- ATP/WTA official profiles and stats for ranking, recent results, surface records, and match reports.
- Wimbledon official player pages and tournament history.
- Tennis Abstract, Ultimate Tennis Statistics, TennisStats, SteveG Tennis, ITF, or official draw pages for H2H and surface/recent-form context.
- Recent match reports for injuries, fatigue, roof/court comments, and tactical notes.

Cross-check player identity, ranking, and H2H when using non-official databases.

## Minimum Dataset For Live Prediction

Collect as many of these as available:

- Exact score: sets, games, point score, next server.
- Match format: best-of-five for men's singles, best-of-three for most other events.
- Current service points won by each player, or enough first/second serve stats to calculate them.
- Baseline service-point estimate on grass or recent season.
- Break point conversion and receiving points won.
- Court conditions: grass, Centre/No.1/outer court, roof open/closed, wind/light.

If service-point estimates are missing, still analyze qualitatively, but label the probability lower confidence.
