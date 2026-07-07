---
name: wimbledon-match-predictor
description: Wimbledon tennis match analysis and prediction workflow for live, suspended, upcoming, and recently completed Wimbledon matches. Use when the user asks to analyze or predict a Wimbledon match such as "分析Wimbledon正在进行的Lehecka vs Zverev", requests historical + current match data, style matchup, head-to-head, grass/court/roof conditions, recent form, or asks for independent current win probabilities. Do not use betting odds, market-implied probabilities, IBM Live Likelihood, bookmaker lines, or third-party prediction percentages as model inputs.
---

# Wimbledon Match Predictor

## Workflow

1. Verify the match state with current sources. For live/suspended matches, browse first; if the user mentions Chrome or the live site needs a browser session, use Chrome. Record the exact timestamp, status, score, set/game/point state, server if known, format, court, roof/weather, and source URLs.
2. Gather raw current-match stats: service points won, first-serve in, first-serve points won, second-serve points won, break points, return points won, winners/errors, net points, rally/pressure notes, distance/medical interruptions if available.
3. Gather historical context: grass and season form, Wimbledon history, best-of-five record, head-to-head, hold/break/service/return tendencies, tiebreak record, recent opponents, and injury/fatigue context.
4. Convert "map data" to tennis context: surface = grass, venue/court, roof open/closed, time of day, ball/skid conditions, wind/light, and how those conditions affect serve, return, rally length, and movement.
5. Build an independent model. Exclude all odds, market prices, bookmaker pages, IBM/AI live likelihood, and third-party prediction percentages. You may use sites that display odds only for raw scores/stats, but ignore the odds panels completely.
6. Run the Markov script when the match is in progress or suspended and enough current score/service information exists:

```bash
python3 scripts/tennis_markov.py \
  --label-a "Jiri Lehecka" \
  --label-b "Alexander Zverev" \
  --server-a 0.674 \
  --server-b 0.729 \
  --sets-a 0 --sets-b 2 \
  --games-a 3 --games-b 3 \
  --next-server neutral \
  --best-of 5
```

7. Produce a concise analysis in the user's language. Lead with the current state and final probabilities, then explain the main drivers: scoreboard leverage, serve/return edge, pressure points, style matchup, H2H, grass/court conditions, recent form, and uncertainty.

## Modeling Rules

- Estimate each player's future service-point win probability from a blend of baseline ability and current-match performance.
- Use grass/recent-season service-point data as the baseline when available. If only hold/break or serve/return indicators are available, translate them conservatively and state the approximation.
- Default live blend: 70-85% baseline and 15-30% current match. Move toward 35-40% current only when the in-match sample is large and clearly stable. Do not overweight one hot set.
- Account for score leverage before style opinions. In best-of-five, a two-set lead dominates most qualitative factors.
- Treat tiebreaks and grass volatility as widening uncertainty, not as a reason to ignore the current scoreboard.
- If the current server or exact point score is unknown, run a neutral or sensitivity case and disclose it.
- Give one main probability and a narrow reasonable range. Avoid false precision beyond whole percentages unless the user asks for model details.

## Data References

Read [references/data-sources.md](references/data-sources.md) when selecting sources or deciding whether a data field is allowed.

Use `scripts/tennis_markov.py` for deterministic score-to-probability conversion. The script assumes player A/B labels supplied by the caller and does not fetch data.

## Output Shape

Use this structure unless the user asks for another format:

- Current state: timestamp, match status, score, court/conditions.
- Independent win probabilities: Player A %, Player B %, plus range.
- Model inputs: baseline service-point estimates, current-match service-point estimates, blend weight, score state.
- Analysis: scoreboard, serve/return, pressure points, style matchup, H2H, grass/court conditions, recent form.
- What changes the number next: immediate break/hold scenarios, set result scenarios, injury/resumption caveats.
