---
name: valorant-match-predictor
description: Valorant esports match analysis and independent prediction workflow for live map and series win-probability estimates, map-by-map tactical reads, team style research, and source-backed analysis from Liquipedia, VLR.gg, RIB.GG, THESPIKE, BO3.gg, official VALORANT Esports, and related data sources. Use when the user provides a Valorant match link, current score, side information such as attack/defense, or asks for independently calculated map or series probabilities that must not copy sportsbook odds, VLR odds, BO3.gg/Tips.gg widgets, analyst pick percentages, or third-party model probabilities.
---

# Valorant Match Predictor

## Goal

Produce an independent Valorant map and series probability read from verified match state, map/side context, and a local score model. Keep map probability separate from series probability.

## Hard Rules

- Do not use sportsbook odds, market-implied probabilities, VLR odds, prediction widgets, analyst pick percentages, or third-party model probabilities as inputs, anchors, or sanity checks.
- Use `references/data-sources.md` when choosing or explaining sources.
- For live maps, verify the factual score, map, side, and series state before giving a final probability.
- Run `scripts/round_model.py` when the current score is in regulation and a defensible `p-round-a` can be estimated.
- Do not give a final probability until historical data, team style, team matchup, player/role matchup, map data, recent form, current-match data, and model calculation have been attempted.
- Treat `p-round-a` as an estimate from verified map, side, economy/ult, form, roster, and matchup context. Label it as estimated and give a range when key state is missing.
- If the map is in overtime or the current state is not supported by the script, say the model cannot produce a formal live probability for that state.

## Required Facts

Collect as many of these as the prompt and sources allow:

- Teams, event, BO format, series score, current map, map pick/veto, and current score.
- Attack/defense sides and whether a half switch, pistol, bonus, or full-buy phase is pending.
- Recent 5 matches, current roster/roles, map pool, same-map results, and attack/defense splits when available.
- Current-map player and tactical signals: first contact, post-plant/retake quality, economy swings, ult economy, role pressure, and player form.

## Analysis Layers

Build the probability from these layers, in order:

1. **Historical baseline**: recent matches, current roster, patch/event context, head-to-head, common opponents, and map-by-map record.
2. **Team style**: pace, defaults, executes, post-plants, retakes, clutch profile, economy discipline, and adaptation across halves.
3. **Team matchup**: how each team’s attack/defense patterns interact on the current and remaining maps.
4. **Player/role matchup**: duelist first contact, initiator setup, controller utility, sentinel/lurk value, IGL pressure, substitutes, and current individual form.
5. **Map data**: map pick/veto, picker ownership, historical map win rate, attack/defense splits, recent same-map results, and comfort maps.
6. **Recent and current-match data**: latest score, side, economy/ult state, pistol/bonus/full-buy phase, completed-map stats, round swings, and live player signals.
7. **Calculation**: estimate `p-round-a`, run the local model when supported, then synthesize a map and series probability.

If a layer cannot be verified, name the missing layer and widen the final range.

## Process

1. Resolve the match from user link, Liquipedia, VLR, official VALORANT Esports, or another named factual source.
2. Ignore odds, prediction, percentage, and recommendation fields if present.
3. Estimate `p-round-a` conservatively from verified context. Do not overfit stale all-time stats.
4. Run the model for regulation live states:

```bash
python3 scripts/round_model.py --team-a NRG --team-b KC --score 11-5 --p-round-a 0.58 --lines 20.5,21.5,22.5
```

5. Explain adjustments in plain language across the analysis layers. Score leverage comes first live; historical and matchup layers anchor pre-map or early-map reads.
6. For series probability, combine the current-map result with remaining-map baselines. Do not collapse map win probability into series win probability.

## Output

For live-score prompts, answer in the user's language with:

1. Verified context: map, score, side, map pick, series score, and refresh/source.
2. Model input: estimated `p-round-a`, what supports it, and what is missing.
3. Historical, style, team matchup, player/role matchup, map, recent-form, and current-match drivers.
4. Current-map probability with a reasonable range.
5. Series probability if relevant.
6. Missing-data caveats and confidence.
7. Swing conditions for the next 1-3 rounds.
8. Sources used.

## Failure Modes

- If public sources lag behind the user's score, say "按你给的实时比分..." and mark the probability provisional.
- If side, economy, or ult state is unknown, widen the range.
- If the score is already in overtime, do not present the regulation script as the final live model.
- Do not invent player stats, economy, ult state, agent roles, or roster changes.
