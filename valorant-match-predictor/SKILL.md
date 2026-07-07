---
name: valorant-match-predictor
description: Valorant esports match analysis and independent prediction workflow for live map and series win-probability estimates, map-by-map tactical reads, team style research, and source-backed analysis from Liquipedia, VLR.gg, RIB.GG, THESPIKE, BO3.gg, official VALORANT Esports, and related data sources. Use when the user provides a Valorant match link, current score, side information such as attack/defense, or asks for independently calculated map or series probabilities that must not copy sportsbook odds, VLR odds, BO3.gg/Tips.gg widgets, analyst pick percentages, or third-party model probabilities.
---

# Valorant Match Predictor

## Goal

Produce an independent Valorant map and series probability read from comprehensive historical data, team/player context, map data, live match data, and Markov-style round-state reasoning. Do not reduce the workflow to a fixed per-round formula.

## Hard Rules

- Do not use sportsbook odds, market-implied probabilities, VLR odds, prediction widgets, analyst pick percentages, or third-party model probabilities as inputs, anchors, or sanity checks.
- Do not give a final probability until historical data, team style, team matchup, player/role matchup, map data, recent form, current-match data, and probability reasoning have been attempted.
- Use Markov thinking as a state-transition frame: score, rounds remaining, side, economy, ult economy, pistol/bonus/full-buy phase, map, player form, and series state. Do not pretend one fixed per-round rate captures the whole map.
- Treat any calculator or model helper as optional only when its assumptions match the current state. If the state is richer than the helper, use a custom calculation, sensitivity cases, or a probability range.
- Keep map probability separate from series probability.
- If a layer or source cannot be verified, name the gap and widen the final range.

## Tool And Data Acquisition

Use the best available tools, not just search snippets:

- Prefer structured or source-close data: VLR match/team pages, Liquipedia API/wikitext, official VALORANT Esports, RIB.GG, THESPIKE, BO3.gg, and provider APIs when accessible.
- Use Chrome when live pages, logged-in sessions, dynamic scoreboards, or anti-scraping behavior require the user's browser.
- Use chrome-devtools when available to inspect network calls, JSON payloads, rendered DOM, console state, and live scoreboard updates.
- Use Playwright for browser automation, snapshots, screenshots, and dynamic-page extraction.
- Use Python, Node, curl, jq, local scripts, or site-specific parsers to fetch and normalize match history, map stats, and live state.
- If a useful local tool is missing, install it globally or user-scoped in the active environment when allowed, verify it works, then use it.
- Read `references/data-sources.md` when choosing sources or explaining source quality.

## Analysis Layers

Build the probability from these layers, in order:

1. **Historical baseline**: recent matches, current roster, patch/event context, head-to-head, common opponents, and map-by-map record.
2. **Team style**: pace, defaults, executes, post-plants, retakes, clutch profile, economy discipline, and adaptation across halves.
3. **Team matchup**: how each team's attack/defense patterns interact on the current and remaining maps.
4. **Player/role matchup**: duelist first contact, initiator setup, controller utility, sentinel/lurk value, IGL pressure, substitutes, and current individual form.
5. **Map data**: map pick/veto, picker ownership, historical map win rate, attack/defense splits, recent same-map results, and comfort maps.
6. **Recent and current-match data**: latest score, side, economy/ult state, pistol/bonus/full-buy phase, completed-map stats, round swings, and live player signals.
7. **Probability synthesis**: use Markov-style round-state reasoning, then synthesize map and series probabilities with sensitivity ranges.

## Output

Answer in the user's language with:

1. Verified context: event, series, map, score, side, map pick/veto, and source refresh time.
2. Data used from each analysis layer; name missing layers.
3. Probability reasoning: round-state leverage, side/economy/ult implications, and key assumptions.
4. Current-map probability with range and confidence.
5. Series probability if relevant.
6. Swing conditions for the next 1-3 rounds.

## Failure Modes

- If public sources lag behind the user's score, say which state is used and mark the probability provisional.
- If side, economy, ult state, or player stats are unknown, widen the range.
- If the map is in overtime or an unsupported state, do not force a fixed regulation model.
- Do not invent player stats, economy, ult state, agent roles, or roster changes.
