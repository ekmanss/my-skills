---
name: cs2-match-predictor
description: CS2 esports match analysis and independent prediction workflow for live map, full-series, and totals probabilities. Use when the user provides a Counter-Strike 2 match link, current score, map score, side/half information, 5EPlay/HLTV/BO3.gg/Liquipedia/Dust2.us link, or asks for first/second/third map win rates, independently calculated live win probability, Over/Under round-line probabilities such as Over 18.5 or Over 21.5, team style, player matchup, map pool, veto, recent form, or score-based prediction that must not copy sportsbook odds or third-party model probabilities.
---

# CS2 Match Predictor

## Overview

Use this skill to produce source-backed CS2 predictions for live maps, completed-map follow-ups, and full BO1/BO3/BO5 series reads. Calculate probabilities independently; never use sportsbook odds, market-implied probabilities, bookmaker lines, site prediction percentages, analyst pick percentages, or third-party model probabilities as an input, anchor, or sanity check.

For in-progress public matches, try 5EPlay first. Start from `https://event.5eplay.com/csgo/matches` to locate the current teams and match id, then fetch structured 5EPlay data endpoints before using HLTV, BO3.gg, or other sites as factual cross-checks.

Read `references/data-sources.md` when choosing sources, explaining source quality, or researching a new match/provider.

Use `scripts/round_model.py` for in-progress maps when enough current state is available.

## Core Workflow

1. Verify the live context first. For active or recently completed matches, browse or fetch current factual sources before answering. If the user's score is ahead of public sources, use the user's score and explicitly say that public sources lag.
2. Resolve the match:
   - Identify teams, aliases, event, BO format, series score, current map, map order, map pick, veto, current score, half/stage, and CT/T sides.
   - When only team names or a user-provided live score are available, search the 5EPlay match list first for those teams. If found, extract the `csgo_mc_*` match id from the URL and treat that match as the live factual source of record.
   - For 5EPlay match URLs or match ids, prefer its structured endpoints:
     - `https://esports-data.5eplaycdn.com/v1/api/csgo/matches/<match_id>/data`
     - `https://esports-data.5eplaycdn.com/v1/api/csgo/matches/<match_id>/analysis_v1`
     - `https://esports-data.5eplaycdn.com/v1/api/csgo/match/<match_id>/event/log?update_version=0&limit=1000`
   - Use `bouts_state` for canonical team scores and sides. Use event logs for freshest round-end signals when `bouts_state` lags, but map CT/T score labels back to team sides before reasoning.
   - Ignore all odds, market, prediction, percentage, and recommendation fields if present.
3. Build the historical baseline before giving any final probability:
   - Recent 5-10 matches for both teams, prioritizing current roster, current map pool, LAN/online context, and current patch/season.
   - Map pool by team: map count, historical win rate, pick/ban rate, recent results, CT/T splits if available, pistol and conversion signals if available.
   - Head-to-head and common-opponent context when available.
   - Roster/substitute/role-change context.
4. Build the current-match layer:
   - Current score, rounds remaining, half/stage, CT/T side, economy if available, timeout/tech pause context if relevant.
   - Completed maps: final score, side splits, OT history, player rating/ADR/K-D, opening kill impact, clutch/multikill signals.
   - Live map: identify whether the leader's score was earned on the stronger side or weaker side.
5. Build the matchup layer:
   - Tactical style: pace, defaults, contact-heavy rounds, execute depth, mid control, AWP impact, lurk timing, post-plant, retake quality, and force-buy volatility.
   - Team-on-team fit: how one team's T defaults attack the opponent's CT setups, and how CT rotations punish or fail against the opponent's usual pace.
   - Player-on-player fit: entry pair, AWP duel, star rifler pressure, anchor isolation, clutch players, and underperforming support pieces.
6. Estimate probability independently:
   - For in-progress maps, use Markov calculation when enough state is known: current score, MR format, teams, map, side/half context or a clear reason side context is unavailable, and a defensible independently estimated per-round probability.
   - Estimate `p-round-a` from map strength, current side, economy, weapon round state, player form, tactical matchup, recent same-map results, and roster context. Do not derive it from odds or any provider's live win probability.
   - Run `scripts/round_model.py` as the numerical anchor for current map win probability, overtime probability, and total-round line probabilities.
   - For series probability, combine the current-map Markov result with remaining-map baselines from map pool, veto ownership, side starts, and matchup context.
7. Synthesize only after the data gates above are attempted. Weight Markov score math and side state first, then map strength, veto ownership, recent form, tactical matchup, player matchup, and long-term baseline.
8. Answer in the user's language. For Chinese prompts, use concise Chinese, concrete percentages, and short swing thresholds.

## Mandatory Data Gate

Do not give a final probability until these items have been attempted:

- Live score, map, sides, series score, and refresh time.
- For in-progress matches, attempted 5EPlay match-list discovery or confirmed why 5EPlay did not cover the match.
- Map veto/order and map ownership.
- Recent form and current roster.
- Map pool and relevant map stats.
- Completed-map player and side-split signals when the same series is underway.
- Markov score math with current-map win probability and round-line probabilities when score and MR format are known. If required state is missing, fetch it or state why Markov could not be run.
- Tactical/style and player-matchup explanation.

If a source is blocked, stale, or missing, say what could not be verified and lower confidence. Do not silently skip historical data, current live data, Markov score math, tactical style, player matchup, or recent form.

For very live updates in the same match, reuse previously gathered context only when teams, map, sides, and roster have not changed. Still refresh any live score that may have changed.

## Probability Heuristics

Use Markov score math for live maps when sufficient state exists, then adjust from these CS2 MR12 anchors:

- **0-0 pre-map**: Start from map baseline, veto ownership, recent form, side start, and player matchups.
- **7-5 half**: Leader is 55-60% if they won expected strong side; 65-75% if they won weak side.
- **8-4 half**: Leader is usually 70-82%, but reduce if moving from strong side to weak side.
- **9-8 mid-late**: Leader is usually 58-70%; side and economy decide direction.
- **10-8 / 10-9**: Leader often 65-80%; underdog needs immediate economy break or two-round swing.
- **11-9**: Leader usually 75-85%; trailing team still has a real overtime path.
- **12-x**: Leader usually 90-99% depending on x and economy.
- **Trailing 2-6 while starting CT**: Usually severe trouble; opponent often 85-95% if their T side already banked 6 rounds.
- **Overtime after two close maps**: Increase volatility; use current player form and fatigue signals rather than old map win rates.

Keep map probability and series probability separate. A team can be favored on the current map but still weaker in the remaining series, or vice versa.

## Live Update Rules

- If the user says "Imperial 1 - 3 Alka" or similar, parse the first named team as Team A unless the user specifies otherwise.
- For live matches without a URL, check `https://event.5eplay.com/csgo/matches` first. If the teams are listed there, use the 5EPlay match URL and structured JSON as the primary factual feed.
- If public sources conflict with the user-provided score, use the freshest plausible factual source and say which one you used.
- If event logs are ahead of the main scoreboard, state that logs are ahead and use logs for the latest score only after side/team mapping is clear.
- Refresh sources when a new map starts, a map ends, or the current score differs from the previous answer.
- Never use or quote betting odds, bookmaker lines, market-implied probabilities, site prediction percentages, or third-party model probabilities.

## Markov Round Model Script

Run:

```bash
python3 scripts/round_model.py --team-a Imperial --team-b Alka --score 1-3 --p-round-a 0.46 --lines 18.5,21.5,22.5,23.5
```

Interpretation:

- `p-round-a` is Team A's independently estimated probability of winning each remaining regulation round from the current context, after considering sides, map, form, and economy.
- The script treats overtime as a separate event and defaults overtime win probability to 50%.
- Use the output as the Markov mathematical anchor, then adjust final prose only for verified tactical/player context the script does not know.

## Output Shape

For live-score prompts, answer in this order:

1. Verified context: match, map, score, sides, series score, map pick, refresh time.
2. Historical baseline: recent form, map pool, and source caveats.
3. Current-map read: side split, economy/round momentum if known, player form.
4. Tactical/player matchup: 2-4 decisive points.
5. Markov current-map probabilities, or a clear reason Markov could not be run.
6. Series probabilities if relevant.
7. Total-round probabilities for requested lines; include Over and Under when useful.
8. Swing thresholds for the next 1-3 rounds.
9. Sources used.

## Common Pitfalls

- Do not treat the same score equally across CT/T sides.
- Do not use external odds or third-party prediction percentages, even as a sanity check.
- Do not skip Markov for live maps when score and MR format are known.
- Do not use old all-time map stats when current roster data is available.
- Do not overstate Cache/Train/new-pool maps when sample size is tiny.
- Do not invent economy, utility, or role data when live sources do not show it.
- Do not collapse "map win probability" into "series win probability."
