---
name: mlb-game-predictor
description: MLB game analysis and independent win-probability workflow for live, upcoming, and recently completed Major League Baseball games. Use when the user asks to analyze or predict an MLB game, especially in-progress prompts like "分析正在进行的 Mets vs Braves", requests historical and current game context, matchup reads, ballpark/weather context, or asks for a probability that must not copy sportsbook odds, MLB contextMetrics, ESPN win probability, Baseball Savant win expectancy, or any third-party win-probability number.
---

# MLB Game Predictor

## Goal

Produce an independent, source-backed MLB probability read. Refresh factual game state first, use the local model when the live state is supported, and make uncertainty explicit.

## Hard Rules

- Do not use sportsbook odds, betting markets, MLB contextMetrics, ESPN win probability, Baseball Savant win expectancy, or any third-party current-game probability as an input, anchor, or sanity check.
- Use `references/data-sources.md` when choosing or explaining sources.
- For in-progress games, run `scripts/mlb_live_snapshot.py` before answering when a game can be resolved.
- Run `scripts/markov_wp.py` when score, inning, half-inning, outs, bases, and home/away context are known.
- Do not give a final probability until historical baseline, team style, team matchup, player matchup, ballpark/weather, recent form, current-game data, and model calculation have been attempted.
- Treat the script output as the numerical anchor. Adjust only for verified context the script does not know, such as pitcher command, bullpen fatigue, lineup pocket, defense, baserunning, injuries, park, or weather.
- If the live state is unsupported, stale, contradictory, or missing required fields, say so and lower confidence instead of forcing a precise probability.

## Required Facts

For a live game, collect the minimum facts before giving a final probability:

- Refresh time, official date, gamePk, teams, venue, and source links.
- Score, inning, top/bottom, outs, occupied bases, count if available, batter, pitcher, and next lineup pocket.
- Current game shape: recent plays, hits/XBH, walks/Ks, errors, LOB, pitch counts, bullpen usage, and high-leverage events.
- Baseline context: team strength, recent form, starting/current pitcher quality, bullpen, lineup, handedness matchup, ballpark, and weather when available.

## Analysis Layers

Build the probability from these layers, in order:

1. **Historical baseline**: season record, run differential, hitting, pitching, bullpen, fielding, home/road context, and relevant head-to-head or common-opponent context.
2. **Team style**: power/contact profile, plate discipline, strikeout/whiff tendency, bullpen volatility, speed, defense, and baserunning pressure.
3. **Team and player matchup**: starting/current pitcher vs lineup, current pitcher vs batter, handedness/platoon, lineup pocket, hot/cold bats, catcher running-game pressure, and leverage relievers.
4. **Ballpark/map layer**: venue, park factors, dimensions, roof/surface/altitude, weather, wind, temperature, and handedness-specific run or HR effects when available.
5. **Recent form**: last 5-10 games, current series, travel/rest, injuries, lineup changes, bullpen workload, and today’s game flow.
6. **Current-game data and calculation**: score, inning, base/out/count, batter/pitcher, recent plays, box score, Statcast signals when available, then the Markov calculation.

If a layer cannot be verified, name the missing layer and widen the final range.

## Process

1. Resolve the game by query or `gamePk`.

```bash
python3 scripts/mlb_live_snapshot.py --query "Mets vs Braves"
python3 scripts/mlb_live_snapshot.py --game-pk 824900
```

2. Convert the verified live state into Markov inputs. Be careful with official date, home/away, inning state, and extra-inning automatic runner.

```bash
python3 scripts/markov_wp.py \
  --inning 10 --half top --away-runs 5 --home-runs 5 \
  --outs 0 --bases 2 \
  --away-rpg 4.03 --home-rpg 4.90
```

3. Estimate any manual scale conservatively. If a scale is judgment-based, label it as an estimate and give a range.
4. Combine model output with the analysis layers. Scoreboard leverage comes first in late-game states; historical and matchup layers matter more early.
5. Use exact dates and source refresh times for live games because MLB official dates can differ from the user's local date.

## Output

For live prompts, answer in the user's language with:

1. Verified current state and refresh time.
2. Model inputs and Markov probability.
3. Historical, style, matchup, ballpark/weather, recent-form, and current-game drivers.
4. Final probability with a small range, not false precision.
5. Missing-data caveats and confidence.
6. Swing conditions for the next 1-3 plate appearances or inning halves.
7. Sources used.

## Failure Modes

- If public sources lag behind a credible user-provided state, say which state is used.
- If the state cannot be converted into model inputs, give a provisional qualitative read rather than a formal model probability.
- Do not invent injuries, weather, Statcast metrics, pitch mixes, or batter-pitcher history.
- Do not treat `inningState: End` or administrative plays as a completed game state without checking the official status and linescore.
