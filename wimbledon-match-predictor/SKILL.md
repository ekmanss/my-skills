---
name: wimbledon-match-predictor
description: Wimbledon tennis match analysis and independent prediction workflow for live, suspended, upcoming, and recently completed Wimbledon matches. Use when the user asks to analyze or predict a Wimbledon match such as "分析Wimbledon正在进行的 Lehecka vs Zverev", requests historical and current match data, style matchup, head-to-head, grass/court/roof conditions, recent form, or asks for independent current win probabilities that must not use betting odds, market-implied probabilities, IBM Live Likelihood, bookmaker lines, or third-party prediction percentages.
---

# Wimbledon Match Predictor

## Goal

Produce an independent Wimbledon match probability read from verified score state, service-point estimates, grass/court context, and the local tennis model.

## Hard Rules

- Do not use betting odds, market-implied probabilities, IBM Live Likelihood, bookmaker lines, or third-party prediction percentages as inputs, anchors, or sanity checks.
- Use `references/data-sources.md` when choosing or explaining sources.
- For live or suspended matches, verify score, server, format, and court conditions before giving a final probability.
- Run `scripts/tennis_markov.py` when sets, games, server, and service-point estimates are available.
- Do not give a final probability until historical data, playing style, player matchup, court/conditions, recent form, current-match data, and model calculation have been attempted.
- Treat service-point probabilities as estimates from baseline grass/recent-season data blended with verified current-match serve/return performance.
- Current score leverage comes before style opinions. A two-set lead or final-set tiebreak state dominates most qualitative factors.
- If server, point score, or service estimates are missing, run neutral/sensitivity cases and lower confidence.

## Required Facts

Collect as many of these as the prompt and sources allow:

- Timestamp, match status, sets, games, point score if available, current/next server, and best-of format.
- Court, roof, weather/light, suspension/resumption, medical or movement concerns.
- Current-match serve/return facts: service points won, first-serve in, first/second-serve points won, break points, return points won, winners/errors, and pressure points.
- Historical context: grass and recent-season form, Wimbledon record, best-of-five record where relevant, head-to-head, hold/break tendencies, and fatigue/injury context.

## Analysis Layers

Build the probability from these layers, in order:

1. **Historical baseline**: grass and recent-season results, Wimbledon record, best-of-five record where relevant, H2H, opponent quality, and hold/break tendencies.
2. **Playing style**: serve dominance, return quality, rally tolerance, movement, net play, backhand/forehand pressure, tiebreak profile, and grass suitability.
3. **Player matchup**: serve pattern vs return position, first-strike pressure, rally patterns, physical/fatigue edge, injury or medical context, and pressure-point history.
4. **Court/map layer**: court, roof, weather/light, wind, ball/skid conditions, suspension/resumption, and how they affect serve, return, movement, and rally length.
5. **Recent and current-match data**: current score, server, point score when available, service points won, first/second-serve performance, break points, winners/errors, net points, and momentum swings.
6. **Calculation**: estimate future service-point win rates, run the local model when supported, then synthesize a match probability.

If a layer cannot be verified, name the missing layer and widen the final range.

## Process

1. Verify the factual score state from Wimbledon official scores/SlamTracker, ATP/WTA, or named factual live-score sources.
2. Ignore odds, prediction, likelihood, and recommendation fields if present.
3. Estimate each player's future service-point win probability conservatively. Label baseline, current-match blend, and uncertainty.
4. Run the model:

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

5. Synthesize the model result with the analysis layers. Scoreboard leverage comes first live; historical and matchup layers anchor pre-match or early-match reads.
6. For deciding-set 6-6 states, use a 10-point match tiebreak. If the script cannot represent a score state, say so and do not force a formal model probability.
7. Give one main probability and a narrow reasonable range. Avoid false precision beyond whole percentages unless the user asks for model details.

## Output

Answer in the user's language with:

1. Current state: timestamp, status, score, server, court/conditions.
2. Model inputs: service-point estimates, blend basis, score state, and any sensitivity case.
3. Historical, style, player matchup, court/conditions, recent-form, and current-match drivers.
4. Independent win probabilities with a reasonable range.
5. Missing-data caveats and confidence.
6. What changes the number next: hold/break, tiebreak, set result, injury, or resumption scenarios.
7. Sources used.

## Failure Modes

- If point score is unknown in a high-leverage game, widen the range.
- If current server is unknown, run neutral or both-server sensitivity cases.
- If service-point estimates are unavailable, give only a provisional qualitative probability.
- Do not invent injuries, medical limitations, court conditions, or current-match stats.
