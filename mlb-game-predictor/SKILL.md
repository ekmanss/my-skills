---
name: mlb-game-predictor
description: MLB game analysis and prediction workflow for live, upcoming, and recently completed Major League Baseball games. Use when the user asks to analyze or predict an MLB game, especially in-progress prompts like "分析正在进行的 Mets vs Braves", or asks for live win probability, historical data, current game data, team style, team matchup, player matchup, ballpark/weather context, recent form, head-to-head, bullpen state, or source-backed baseball betting-style analysis.
---

# MLB Game Predictor

## Overview

Use this skill to produce source-backed MLB win-probability analysis from both historical context and current game state. Treat every percentage as a calibrated judgment, not a betting guarantee.

Read `references/data-sources.md` when choosing sources, explaining source quality, researching a provider, or deciding where to fetch historical vs live data.

Use `scripts/mlb_live_snapshot.py` to resolve and fetch official live MLB data before answering an in-progress game prompt.

## Core Workflow

1. Verify the live context first. For active or recent games, fetch current sources before answering. Do not rely on memory, stale search snippets, or a prior response when the game may have advanced pitch-by-pitch.
2. Resolve the game:
   - Parse teams, aliases, likely date, and home/away if available.
   - For prompts such as `分析正在进行的 Mets vs Braves`, search MLB official schedules around the current US/Eastern date, also checking the previous date when the user is in Asia or Europe.
   - Prefer `gamePk` once found; use it consistently across MLB Stats API, Baseball Savant, and source links.
   - Run:

```bash
python3 scripts/mlb_live_snapshot.py --query "Mets vs Braves"
python3 scripts/mlb_live_snapshot.py --game-pk 824900
```

3. Build the current-game layer:
   - Score, inning half, outs, base runners, count, batter, pitcher, on-deck, in-hole, lineups, current pitcher, and last 5-10 completed plays.
   - MLB `contextMetrics` win probability when available; cross-check ESPN Gamecast win probability when precision matters.
   - Box score: hits, extra-base hits, walks, strikeouts, left on base, errors, stolen bases, pitch counts, bullpen lines, inherited runners.
   - Statcast/Savant when available: exit velocity, launch angle, xBA/xwOBA, barrels, hard-hit balls, WPA/top performers.
   - Treat administrative events (`Pitching Substitution`, `Runner Placed On Base`, mound visit) as context, not a completed plate appearance.
4. Build the historical baseline:
   - Standings, record, run differential, expected record if available, home/road and day/night context.
   - Team hitting style: AVG/OBP/SLG/OPS, HR rate, K/BB profile, stolen-base efficiency, ground-ball/double-play tendency when available.
   - Team run prevention: ERA, WHIP, K/9, BB/9, HR/9, bullpen saves/blown saves, high-leverage relievers, fielding errors.
   - Recent form: last 5-10 games, current series, head-to-head, common-opponent context, travel/rest if discoverable.
5. Build the matchup layer:
   - Starting pitcher vs opposing lineup, current pitcher vs current batter, handedness/platoon splits, pitch arsenal vs hitter swing profile.
   - Player matchups: hot/cold hitters, batter-pitcher history only as a small signal, RISP performance, baserunning and catcher running-game pressure.
   - Team-on-team style fit: power vs contact, patience vs wild bullpen, strikeout arms vs whiff-heavy lineup, speed vs defensive/catcher weakness.
   - Ballpark "map" data: venue, park factors, dimensions, roof, surface, altitude, weather, wind, temperature, and handedness-specific HR effects when available.
6. Estimate probability:
   - For live games, anchor on the freshest official or high-quality win probability that matches the actual base/out/inning state.
   - If MLB and ESPN conflict, compare timestamps and current play state. Use the source that has incorporated the latest completed play, and say which one may be lagging.
   - Adjust only when there is a clear reason: current pitcher fatigue, unusual lineup pocket, bullpen mismatch, automatic runner, weather/park effects, severe source lag, or missing official probability.
   - Keep live state dominant. Historical team strength should not override a decisive late-inning base/out situation.
7. Answer in the user's language. For Chinese prompts, use concise Chinese, exact percentages, confidence/range, and short swing thresholds.

## Mandatory Data Gate

Do not give a final probability until these items have been attempted:

- Refresh time, official game date, gamePk, venue, and source links.
- Live score, inning, half-inning, outs, runners, count, batter, pitcher, and the next lineup pocket.
- MLB contextMetrics win probability or a clear note that it is unavailable/stale.
- ESPN/Gamecast or another independent live-score cross-check when the game is in a high-leverage state.
- Team season baseline: record, run differential, hitting, pitching, bullpen, and fielding.
- Recent form: last 5-10 games and current series/head-to-head when available.
- Current game shape: box-score profile, extra-base hits, walks/Ks, errors, LOB, bullpen workload, high-leverage plays.
- Ballpark/weather context.
- Player/team matchup explanation, not just scoreboard math.

If a source is blocked, stale, or missing, say what could not be verified and lower confidence. Do not silently skip historical data, current live data, style, player matchup, recent form, or ballpark context.

## Live Update Rules

- Re-fetch live sources on every live update request. Reuse prior historical context only when the same game is still in progress and teams/lineups have not materially changed.
- Use exact dates for clarity. MLB official dates often differ from the user's local date for night games.
- In extra innings, explicitly account for the automatic runner on second base and whether the current team bats top or bottom.
- If public sources lag behind a plausible user-provided live state, state the discrepancy and base the estimate on the freshest named source or the user's stated score if it is credible.
- Do not quote betting odds as truth. Odds can be one weak market signal, never the model itself.
- Do not invent injuries, pitch mixes, weather, Statcast metrics, or batter-pitcher history when sources do not provide them.

## Probability Heuristics

Use official live win probability as the anchor when available. When it is missing or clearly stale, reason from base/out/inning state:

- Tie game, bottom 9th or later: home team advantage is large only while it has live scoring leverage; it collapses if the inning ends.
- Runner on second, 0 outs in extras: batting team has a real scoring expectation, but the home team still gets the matching automatic-runner chance.
- Late lead with elite closer and bases empty: strong favorite, but reduce for wildness, fatigue, platoon mismatch, or recent traffic.
- Bases loaded or winning run on third in bottom 9th/extras: base/out state can dominate all season-long team quality.
- Early innings: team strength, starting pitching, lineup quality, and park/weather matter more because many plate appearances remain.

Use ranges when source latency is visible, for example: "MLB still says 63/37, ESPN has incorporated the last out and says 52/48; I use 51/49 as the current estimate."

## Output Shape

For in-progress prompts, answer in this order:

1. Verified context: game, score, inning/base-out-count, batter/pitcher, refresh time.
2. Current live probability for both teams, with the source anchor.
3. Why the probability moved: latest play sequence and current base/out leverage.
4. Historical baseline: season strength, recent form, current series/head-to-head.
5. Current-game read: offensive quality, bullpen state, defense/baserunning, Statcast signals if available.
6. Matchup read: team style, pitcher-batter, lineup pocket, handedness/platoon, ballpark/weather.
7. Final probabilities, confidence, and swing thresholds for the next 1-3 plate appearances or inning halves.
8. Sources used.

Example:

```markdown
截至 2026-07-07 10:34 新加坡时间：Mets 5-5 Braves，10局上，0出局，Bo Bichette 自动跑者在二垒，Francisco Lindor 对 Owen Murphy。

当前胜率：
- Mets：51%
- Braves：49%

MLB contextMetrics 此刻是 50/50；我略偏 Mets，因为他们先拿到十局上 0出局二垒有人，且后面是 Lindor/Benge/Young。Braves 的后攻优势仍在，所以差距很小。

分水岭：Mets 若至少推进跑者到三垒，胜率会上到 56-60%；若十局上无分，Braves 底十局会变成 60%+。
```

## Common Pitfalls

- Do not treat a stale win-probability number as current if the last completed play changed base/out state.
- Do not confuse `inningState: End` with a completed game; check `abstractGameState` and score.
- Do not read `currentPlay` alone; inspect `linescore.offense`, `count`, and last completed plays.
- Do not overrate batter-pitcher history with tiny samples.
- Do not call a late game "basically over" when the tying/winning run is already on base.
- Do not use all-time franchise head-to-head as a major signal for a live game; current roster and current game state matter more.
