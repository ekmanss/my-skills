---
name: mlb-game-predictor
description: MLB game analysis and independent win-probability workflow for live, upcoming, and recently completed Major League Baseball games. Use when the user asks to analyze or predict an MLB game, especially in-progress prompts like "分析正在进行的 Mets vs Braves", requests historical and current game context, matchup reads, ballpark/weather context, or asks for a probability that must not copy sportsbook odds, MLB contextMetrics, ESPN win probability, Baseball Savant win expectancy, or any third-party win-probability number.
---

# MLB Game Predictor

## Goal

Produce an independent MLB probability read from comprehensive factual data, historical context, multi-dimensional baseball analysis, and Markov-style state reasoning. Do not reduce the workflow to a fixed formula or one bundled script.

## Hard Rules

- Do not use sportsbook odds, betting markets, MLB contextMetrics, ESPN win probability, Baseball Savant win expectancy, or any third-party current-game probability as an input, anchor, or sanity check.
- Do not give a final probability until historical baseline, team style, team matchup, player matchup, ballpark/weather, recent form, current-game data, and probability reasoning have been attempted.
- Use Markov thinking as a state-transition frame: score, inning, half, outs, bases, count, batting order, pitcher/batter, bullpen, and remaining run paths. Do not claim false precision from a fixed model when the state or inputs are incomplete.
- Treat any calculator or model helper as optional only when its assumptions match the live state. If it does not fit, use a custom calculation, sensitivity cases, or a qualitative probability range.
- If a layer or source cannot be verified, name the gap and widen the final range.

## Tool And Data Acquisition

Use the best available tools, not just search snippets:

- Prefer structured sources first: MLB Stats API/Gameday, boxscore, schedule, live feed, team/player stats, Baseball Savant/Statcast, Retrosheet/Lahman/FanGraphs/Baseball-Reference when relevant.
- Use Chrome when the task benefits from the user's logged-in browser state, live pages, dynamic scoreboards, or difficult pages.
- Use chrome-devtools when available to inspect network calls, JSON payloads, rendered DOM, console state, and live scoreboard updates.
- Use Playwright when browser automation, snapshots, screenshots, or dynamic-page extraction is faster or more reliable than plain HTTP.
- Use Python, Node, curl, jq, pybaseball, local scripts, or other CLI tools to fetch and normalize data.
- If a necessary local tool is missing, install it globally or user-scoped in the active environment when allowed, verify it works, then use it. Do not abandon data collection merely because a browser or scraping helper is not already installed.
- Read `references/data-sources.md` when choosing sources or explaining source quality.

## Analysis Layers

Build the probability from these layers, in order:

1. **Historical baseline**: season record, run differential, hitting, pitching, bullpen, fielding, home/road context, head-to-head, and common opponents.
2. **Team style**: power/contact profile, plate discipline, strikeout/whiff tendency, bullpen volatility, speed, defense, and baserunning pressure.
3. **Team and player matchup**: starting/current pitcher vs lineup, current pitcher vs batter, handedness/platoon, lineup pocket, hot/cold bats, catcher running-game pressure, and leverage relievers.
4. **Ballpark/map layer**: venue, park factors, dimensions, roof/surface/altitude, weather, wind, temperature, and handedness-specific run or HR effects.
5. **Recent form**: last 5-10 games, current series, travel/rest, injuries, lineup changes, bullpen workload, and today's game flow.
6. **Current-game data**: score, inning, base/out/count, batter/pitcher, recent plays, box score, pitch count, bullpen state, and Statcast signals when available.
7. **Probability synthesis**: use Markov-style remaining-state reasoning, then adjust for verified layers above. Use sensitivity ranges for uncertain event rates or context.

## Output

Answer in the user's language with:

1. Verified current state, source refresh time, and source links.
2. Data used from each analysis layer; name missing layers.
3. Probability reasoning: current state leverage, remaining run paths, and key assumptions.
4. Final probability with a realistic range and confidence.
5. Swing conditions for the next 1-3 plate appearances or inning halves.

## Failure Modes

- If public sources lag behind a credible user-provided state, say which state is used.
- If live state cannot be verified, give only a provisional read.
- Do not invent injuries, weather, Statcast metrics, pitch mixes, or batter-pitcher history.
- Do not treat a single calculator output as the answer when the broader data disagrees or important layers are missing.
