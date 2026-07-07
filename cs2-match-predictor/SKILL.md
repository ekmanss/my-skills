---
name: cs2-match-predictor
description: CS2 esports match analysis and independent prediction workflow for live map, full-series, and totals probabilities. Use when the user provides a Counter-Strike 2 match link, current score, map score, side/half information, 5EPlay/HLTV/BO3.gg/Liquipedia/Dust2.us link, or asks for independently calculated live map probability, Over/Under round-line probabilities, team style, player matchup, map pool, veto, recent form, or score-based prediction that must not copy sportsbook odds, bookmaker lines, site prediction percentages, analyst pick percentages, or third-party model probabilities.
---

# CS2 Match Predictor

## Goal

Produce an independent CS2 map, series, and regulation round-line probability read from verified live state, map/side context, and a local score model.

## Hard Rules

- Do not use sportsbook odds, market-implied probabilities, bookmaker lines, site prediction percentages, analyst pick percentages, or third-party model probabilities as inputs, anchors, or sanity checks.
- Use `references/data-sources.md` when choosing or explaining sources.
- Try 5EPlay first for public in-progress matches when the teams or match are likely covered.
- Verify map, score, half/stage, CT/T side, series score, and refresh time before giving a final live probability.
- Run `scripts/round_model.py` when the current score is in regulation and a defensible `p-round-a` can be estimated.
- Do not give a final probability until historical data, team style, team matchup, player matchup, map data, recent form, current-match data, and model calculation have been attempted.
- Treat `p-round-a` as an estimate from verified map, side, economy, weapon state, form, roster, and matchup context. Label it as estimated and give a range when key state is missing.
- If the map is in overtime or the current state is not supported by the script, say the model cannot produce a formal live probability for that state.

## Required Facts

Collect as many of these as the prompt and sources allow:

- Teams, event, BO format, series score, current map, map order, map pick/veto, and current score.
- Half/stage, CT/T sides, economy/weapon state, timeout or tech-pause context if relevant.
- Recent 5-10 matches, current roster/substitutes, map pool, same-map results, CT/T splits, and pistol/conversion signals when available.
- Current-map player and tactical signals: opening kills, AWP impact, anchor pressure, clutch/multikill events, economy swings, and side split.

## Analysis Layers

Build the probability from these layers, in order:

1. **Historical baseline**: recent 5-10 matches, current roster, event/LAN-online context, head-to-head, common opponents, and current patch/season.
2. **Team style**: pace, defaults, contact-heavy rounds, execute depth, mid control, AWP reliance, lurk timing, post-plants, retakes, and force-buy volatility.
3. **Team matchup**: how one team’s T defaults attack the opponent’s CT setups, and how CT rotations, anchors, or utility match the opponent’s pace.
4. **Player matchup**: entry pair, AWP duel, star rifler pressure, anchor isolation, clutch players, support pieces, substitutes, and current individual form.
5. **Map data**: veto/order, map pick ownership, historical map win rate, CT/T splits, recent same-map results, pistol and conversion signals.
6. **Recent and current-match data**: latest score, side, half/stage, economy/weapon state, completed-map signals, round momentum, player ratings, opening kills, and clutch/multikill events.
7. **Calculation**: estimate `p-round-a`, run the local model when supported, then synthesize map, series, and regulation round-line probabilities.

If a layer cannot be verified, name the missing layer and widen the final range.

## Process

1. Resolve the match. For live matches without a URL, check `https://event.5eplay.com/csgo/matches` first; if found, use structured 5EPlay data as the primary factual feed.
2. Ignore odds, market, prediction, percentage, and recommendation fields if present.
3. Estimate `p-round-a` conservatively from verified context. Do not overfit old all-time map stats.
4. Run the model for regulation live states:

```bash
python3 scripts/round_model.py --team-a Imperial --team-b Alka --score 1-3 --p-round-a 0.46 --lines 18.5,21.5,22.5,23.5
```

5. Explain adjustments in plain language across the analysis layers. Score leverage comes first live; historical and matchup layers anchor pre-map or early-map reads.
6. Keep map probability, series probability, and regulation round-line probability separate.

## Output

For live-score prompts, answer in the user's language with:

1. Verified context: match, map, score, sides, series score, map pick, refresh/source.
2. Model input: estimated `p-round-a`, what supports it, and what is missing.
3. Historical, style, team matchup, player matchup, map, recent-form, and current-match drivers.
4. Current-map probability with a reasonable range.
5. Series probability if relevant.
6. Regulation round-line probabilities for requested lines; say clearly if totals exclude OT.
7. Missing-data caveats and confidence.
8. Swing conditions for the next 1-3 rounds.
9. Sources used.

## Failure Modes

- If public sources lag behind the user's score, say which state is used and mark the probability provisional.
- If side/team mapping from event logs is unclear, do not use log scores as team scores.
- If economy or side state is unknown, widen the range.
- If the score is already in overtime, do not present the regulation script as the final live model.
- Do not invent economy, utility, role, or player data.
