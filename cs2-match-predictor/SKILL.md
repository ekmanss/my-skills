---
name: cs2-match-predictor
description: CS2 esports match analysis and prediction workflow for live map, full-series, and totals probabilities. Use when the user provides a Counter-Strike 2 match link, current score, map score, side/half information, 5EPlay/HLTV/BO3.gg/Liquipedia/Dust2.us link, or asks for first/second/third map win rates, live win probability, Over/Under round-line probabilities such as Over 18.5 or Over 21.5, team style, player matchup, map pool, veto, recent form, or score-based prediction.
---

# CS2 Match Predictor

## Overview

Use this skill to produce source-backed CS2 predictions for live maps, completed-map follow-ups, and full BO1/BO3/BO5 series reads. Treat every percentage as a calibrated judgment, not a betting guarantee.

Read `references/data-sources.md` when choosing sources, explaining source quality, or researching a new match/provider.

Use `scripts/round_model.py` whenever the user asks for live map win rates or Over/Under round-line probabilities from a current score.

## Core Workflow

1. Verify the live context first. For active or recently completed matches, browse or fetch current sources before answering. If the user's score is ahead of public sources, use the user's score and explicitly say that public sources lag.
2. Resolve the match:
   - Identify teams, aliases, event, BO format, series score, current map, map order, map pick, veto, current score, half/stage, and CT/T sides.
   - For 5EPlay match URLs, prefer its structured endpoints:
     - `https://esports-data.5eplaycdn.com/v1/api/csgo/matches/<match_id>/data`
     - `https://esports-data.5eplaycdn.com/v1/api/csgo/matches/<match_id>/analysis_v1`
     - `https://esports-data.5eplaycdn.com/v1/api/csgo/match/<match_id>/event/log?update_version=0&limit=1000`
   - Use `bouts_state` for canonical team scores and sides. Use event logs for freshest round-end signals when `bouts_state` lags, but map CT/T score labels back to team sides before reasoning.
3. Build the historical baseline before giving any final probability:
   - Recent 5-10 matches for both teams, prioritizing current roster, current map pool, LAN/online context, and current patch/season.
   - Map pool by team: map count, win rate, pick/ban rate, recent results, CT/T splits if available, pistol and conversion signals if available.
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
6. Estimate a per-round probability for the current map state, then run `scripts/round_model.py` to anchor:
   - Current map win probability.
   - Overtime probability.
   - Total-round line probabilities such as Over 18.5, Over 20.5, Over 21.5, Over 22.5, Over 23.5.
7. Synthesize only after the data gates above are attempted. Weight current score and side state first, then map strength, veto ownership, recent form, tactical matchup, player matchup, and long-term baseline.
8. Answer in the user's language. For Chinese prompts, use concise Chinese, concrete percentages, and short swing thresholds.

## Mandatory Data Gate

Do not give a final probability until these items have been attempted:

- Live score, map, sides, series score, and refresh time.
- Map veto/order and map ownership.
- Recent form and current roster.
- Map pool and relevant map stats.
- Completed-map player and side-split signals when the same series is underway.
- Current-map score math with round-line probabilities.
- Tactical/style and player-matchup explanation.

If a source is blocked, stale, or missing, say what could not be verified and lower confidence. Do not silently skip historical data, current live data, tactical style, player matchup, or recent form.

For very live updates in the same match, reuse previously gathered context only when teams, map, sides, and roster have not changed. Still refresh any live score that may have changed.

## Probability Heuristics

Use the model script for score math, then adjust from these CS2 MR12 anchors:

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
- If public sources conflict with the user-provided score, use the freshest plausible source and say which one you used.
- If event logs are ahead of the main scoreboard, state that logs are ahead and use logs for the latest score only after side/team mapping is clear.
- Refresh sources when a new map starts, a map ends, or the current score differs from the previous answer.
- Do not quote live odds as truth. Use odds only as one weak market signal, not as the model itself.

## Round Model Script

Run:

```bash
python3 scripts/round_model.py --team-a Imperial --team-b Alka --score 1-3 --p-round-a 0.46 --lines 18.5,21.5,22.5,23.5
```

Interpretation:

- `p-round-a` is Team A's estimated probability of winning each remaining regulation round from the current context, after considering sides, map, form, and economy.
- The script treats overtime as a separate event and defaults overtime win probability to 50%.
- Use the output as the mathematical anchor, then adjust final prose for tactical/player context.

## Output Shape

For live-score prompts, answer in this order:

1. Verified context: match, map, score, sides, series score, map pick, refresh time.
2. Historical baseline: recent form, map pool, and source caveats.
3. Current-map read: side split, economy/round momentum if known, player form.
4. Tactical/player matchup: 2-4 decisive points.
5. Current map probabilities.
6. Series probabilities if relevant.
7. Total-round probabilities for requested lines; include Over and Under when useful.
8. Swing thresholds for the next 1-3 rounds.
9. Sources used.

Example:

```markdown
按你给的实时比分：Imperial 1-3 Alka，图二 Nuke，Imperial 先 CT。

当前图二胜率：
- Imperial：38%
- Alka：62%

总轮数：
- Over 18.5：74%
- Over 21.5：46%
- Over 22.5：31%

关键原因：Alka 已经在 T 方拿到 3 分，Imperial 的 CT 开局没有守住经济；但 Nuke 仍有强 CT 回合修正空间。若 Imperial 追到 3-4，胜率回到接近 45%；若 Alka 到 5-1，Imperial 会跌到 25% 以下。
```

## Common Pitfalls

- Do not treat the same score equally across CT/T sides.
- Do not rely only on series odds once a map has started.
- Do not use old all-time map stats when current roster data is available.
- Do not overstate Cache/Train/new-pool maps when sample size is tiny.
- Do not invent economy, utility, or role data when live sources do not show it.
- Do not collapse "map win probability" into "series win probability."
