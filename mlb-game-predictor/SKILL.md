---
name: mlb-game-predictor
description: MLB game analysis and independent prediction workflow for live, upcoming, and recently completed Major League Baseball games. Use when the user asks to analyze or predict an MLB game, especially in-progress prompts like "分析正在进行的 Mets vs Braves", or asks for independently calculated live win probability, historical data, current game data, team style, team matchup, player matchup, ballpark/weather context, recent form, head-to-head, bullpen state, or source-backed baseball analysis that must not copy sportsbook odds or third-party win-probability numbers.
---

# MLB Game Predictor

## Overview

Use this skill to produce source-backed MLB win-probability analysis from both historical context and current game state. Calculate the probabilities independently; do not use sportsbook odds, betting markets, MLB contextMetrics, ESPN win probability, Baseball Savant win expectancy, or any other third-party win-probability number as an input or anchor.

Read `references/data-sources.md` when choosing sources, explaining source quality, researching a provider, or deciding where to fetch historical vs live data.

Use `scripts/mlb_live_snapshot.py` to resolve and fetch official live MLB data before answering an in-progress game prompt.

Use `scripts/markov_wp.py` for in-progress games when enough current state is available.

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
   - Use ESPN/Gamecast, MLB.com, or other scoreboards only to cross-check factual state such as score, inning, outs, runners, and play sequence. Ignore and do not quote any win-probability or odds fields.
   - Box score: hits, extra-base hits, walks, strikeouts, left on base, errors, stolen bases, pitch counts, bullpen lines, inherited runners.
   - Statcast/Savant when available: exit velocity, launch angle, xBA/xwOBA, barrels, hard-hit balls, pitch velocity, and pitch movement. Ignore WPA/win-expectancy fields.
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
6. Estimate probability independently:
   - Start from the current game state: inning, half-inning, score differential, outs, base occupancy, count, batting order, home/away, and extra-inning automatic runner rules.
   - For in-progress games, use Markov calculation when enough state is known: score, inning, half-inning, outs, base occupancy, home/away teams, and whether extra-inning automatic runner rules apply. Run `scripts/markov_wp.py` as the numerical anchor.
   - Estimate each team's remaining run distribution from base/out state, lineup pocket quality, pitcher quality/fatigue, bullpen depth, park/weather, and team offensive/defensive strength.
   - For pre-game or early-game states, build a baseline from team run differential, season and recent hitting/pitching/fielding, starting pitcher quality, bullpen availability, lineup strength, handedness matchups, park/weather, and home field.
   - For late-game states, let score/base/out leverage dominate, then adjust for pitcher-batter matchup, bullpen condition, defense, baserunning, and lineup pocket.
   - State the model logic in prose. If you use rough empirical anchors such as run expectancy or win expectancy from historical play-by-play tables, cite the table/source; do not use a third-party current-game probability.
7. Answer in the user's language. For Chinese prompts, use concise Chinese, exact percentages, confidence/range, and short swing thresholds.

## Mandatory Data Gate

Do not give a final probability until these items have been attempted:

- Refresh time, official game date, gamePk, venue, and source links.
- Live score, inning, half-inning, outs, runners, count, batter, pitcher, and the next lineup pocket.
- At least one independent live-score cross-check when the game is in a high-leverage state, using it only for factual state, not win probability.
- Markov calculation for in-progress games when score, inning, half-inning, outs, base occupancy, and home/away context are known. If any required state is missing, fetch it or state why Markov could not be run.
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
- If public factual sources lag behind a plausible user-provided live state, state the discrepancy and base the estimate on the freshest named factual state or the user's stated score if it is credible.
- Never use or quote betting odds, sportsbook lines, market-implied probabilities, MLB contextMetrics, ESPN win probability, Baseball Savant win expectancy, or any other provider's current-game win-probability number.
- Do not invent injuries, pitch mixes, weather, Statcast metrics, or batter-pitcher history when sources do not provide them.

## Probability Heuristics

Calculate win probability from the game state and baseball fundamentals. Use these anchors as reasoning guides, not as copied external probabilities:

- **Markov first for live games**: with sufficient state, run a 24-state base/out Markov model. Use team runs per game, OPS, bullpen/pitcher quality, handedness pocket, and park/weather to adjust event/run scales before the final percentage.
- Tie game, bottom 9th or later: home team advantage is large only while it has live scoring leverage; it collapses if the inning ends.
- Runner on second, 0 outs in extras: batting team has a real scoring expectation, but the home team still gets the matching automatic-runner chance.
- Late lead with elite closer and bases empty: strong favorite, but reduce for wildness, fatigue, platoon mismatch, or recent traffic.
- Bases loaded or winning run on third in bottom 9th/extras: base/out state can dominate all season-long team quality.
- Early innings: team strength, starting pitching, lineup quality, and park/weather matter more because many plate appearances remain.

Use ranges when the model is sensitive to incomplete details such as exact bullpen availability, injury status, defensive alignment, or source latency in factual play state.

## Markov Script

Run the script after `mlb_live_snapshot.py` for live states:

```bash
python3 scripts/markov_wp.py \
  --inning 10 --half top --away-runs 5 --home-runs 5 \
  --outs 0 --bases 2 \
  --away-rpg 4.03 --home-rpg 4.90
```

Interpretation:

- `--bases` accepts `0`, `1`, `2`, `3`, `1,3`, or a `first-second-third` bit string such as `010`.
- `--away-rpg` and `--home-rpg` scale league-average event probabilities. Use team season runs per game as a baseline, then adjust `--away-scale` or `--home-scale` for pitcher fatigue, lineup pocket, bullpen quality, and park/weather.
- The script models half-inning scoring with 24 base/out states and projects the game forward, including extra-inning automatic runners by default.
- The script is a numerical anchor. After running it, make small, explicit adjustments only for verified context the script does not know, such as current pitcher command, pinch runners, defensive substitutions, injury news, or extreme weather.

## Output Shape

For in-progress prompts, answer in this order:

1. Verified context: game, score, inning/base-out-count, batter/pitcher, refresh time.
2. Markov model output for in-progress games, or a clear reason Markov could not be run.
3. Why the probability moved: latest play sequence, current base/out leverage, and model adjustments.
4. Historical baseline: season strength, recent form, current series/head-to-head.
5. Current-game read: offensive quality, bullpen state, defense/baserunning, Statcast signals if available.
6. Matchup read: team style, pitcher-batter, lineup pocket, handedness/platoon, ballpark/weather.
7. Final probabilities, confidence, and swing thresholds for the next 1-3 plate appearances or inning halves.
8. Sources used.

Example:

```markdown
截至 2026-07-07 10:34 新加坡时间：Mets 5-5 Braves，10局上，0出局，Bo Bichette 自动跑者在二垒，Francisco Lindor 对 Owen Murphy。

当前胜率：
- Mets：44%
- Braves：56%

我不使用外部胜率或赔率。Markov 模型把当前状态作为输入：十局上平局、0出局、二垒自动跑者；Mets 有先得分机会，但 Braves 底十局也会有自动跑者和后攻 walk-off 权，因此主队仍略优。若结合 Mets 当前棒次更强，可把 Mets 小幅上修到约 46%，但不能跳过 Markov 锚点。

分水岭：Mets 若至少推进跑者到三垒，胜率会上到 56-60%；若十局上无分，Braves 底十局会变成 60%+。
```

## Common Pitfalls

- Do not use external win-probability numbers or sportsbook odds, even as a "sanity check" for the final percentage.
- Do not skip Markov for live games when the required current state is available.
- Do not confuse `inningState: End` with a completed game; check `abstractGameState` and score.
- Do not read `currentPlay` alone; inspect `linescore.offense`, `count`, and last completed plays.
- Do not overrate batter-pitcher history with tiny samples.
- Do not call a late game "basically over" when the tying/winning run is already on base.
- Do not use all-time franchise head-to-head as a major signal for a live game; current roster and current game state matter more.
