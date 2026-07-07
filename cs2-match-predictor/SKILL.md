---
name: cs2-match-predictor
description: CS2 esports match analysis and independent prediction workflow for live map, full-series, and totals probabilities. Use when the user provides a Counter-Strike 2 match link, current score, map score, side/half information, 5EPlay/HLTV/BO3.gg/Liquipedia/Dust2.us link, or asks for independently calculated live map probability, Over/Under round-line probabilities, team style, player matchup, map pool, veto, recent form, or score-based prediction that must not copy sportsbook odds, bookmaker lines, site prediction percentages, analyst pick percentages, or third-party model probabilities.
---

# CS2 Match Predictor

## Goal

Produce an independent CS2 map, series, and totals probability read from comprehensive historical data, tactical context, map data, live match data, and Markov-style round-state reasoning. Do not reduce the workflow to a fixed per-round formula.

## Hard Rules

- Do not use sportsbook odds, market-implied probabilities, bookmaker lines, site prediction percentages, analyst pick percentages, or third-party model probabilities as inputs, anchors, or sanity checks.
- Do not give a final probability until historical data, team style, team matchup, player matchup, map data, recent form, current-match data, and probability reasoning have been attempted.
- Use Markov thinking as a state-transition frame: score, rounds remaining, side, economy, weapon state, map, player form, series state, and overtime paths. Do not pretend one fixed per-round rate captures the whole map.
- Treat any calculator or model helper as optional only when its assumptions match the current state. If the state is richer than the helper, use a custom calculation, sensitivity cases, or a probability range.
- Keep map probability, series probability, and totals probability separate. Say whether totals include or exclude overtime.
- If a layer or source cannot be verified, name the gap and widen the final range.

## Tool And Data Acquisition

Use the best available tools, not just search snippets:

- Prefer structured or source-close data: 5EPlay match list and JSON endpoints, HLTV, BO3.gg, Liquipedia, Dust2.us, GRID/Bayes/Abios/PandaScore when credentials exist, and official tournament sources.
- Use Chrome when live pages, logged-in sessions, dynamic scoreboards, or anti-scraping behavior require the user's browser.
- Use chrome-devtools when available to inspect network calls, JSON payloads, rendered DOM, console state, and live scoreboard updates.
- Use Playwright for browser automation, snapshots, screenshots, and dynamic-page extraction.
- Use Python, Node, curl, jq, local scripts, or site-specific parsers to fetch and normalize match history, map stats, and live state.
- If a useful local tool is missing, install it globally or user-scoped in the active environment when allowed, verify it works, then use it.
- Read `references/data-sources.md` when choosing sources or explaining source quality.

## Analysis Layers

Build the probability from these layers, in order:

1. **Historical baseline**: recent 5-10 matches, current roster, event/LAN-online context, head-to-head, common opponents, and current patch/season.
2. **Team style**: pace, defaults, contact-heavy rounds, execute depth, mid control, AWP reliance, lurk timing, post-plants, retakes, and force-buy volatility.
3. **Team matchup**: how one team's T defaults attack the opponent's CT setups, and how CT rotations, anchors, or utility match the opponent's pace.
4. **Player matchup**: entry pair, AWP duel, star rifler pressure, anchor isolation, clutch players, support pieces, substitutes, and current individual form.
5. **Map data**: veto/order, map pick ownership, historical map win rate, CT/T splits, recent same-map results, pistol and conversion signals.
6. **Recent and current-match data**: latest score, side, half/stage, economy/weapon state, completed-map signals, round momentum, player ratings, opening kills, and clutch/multikill events.
7. **Probability synthesis**: use Markov-style round-state reasoning, then synthesize map, series, and totals probabilities with sensitivity ranges.

## Output

Answer in the user's language with:

1. Verified context: match, event, series, map, score, sides, map pick/veto, and source refresh time.
2. Data used from each analysis layer; name missing layers.
3. Probability reasoning: round-state leverage, side/economy implications, overtime path, and key assumptions.
4. Current-map probability with range and confidence.
5. Series probability if relevant.
6. Totals probability if requested, clearly stating whether overtime is included.
7. Swing conditions for the next 1-3 rounds.

## Failure Modes

- If public sources lag behind the user's score, say which state is used and mark the probability provisional.
- If side/team mapping from event logs is unclear, do not use log scores as team scores.
- If economy, side, or player data is unknown, widen the range.
- If the map is in overtime or an unsupported state, do not force a fixed regulation model.
- Do not invent economy, utility, role, or player data.
