---
name: wimbledon-match-predictor
description: Wimbledon tennis match analysis and independent prediction workflow for live, suspended, upcoming, and recently completed Wimbledon matches. Use when the user asks to analyze or predict a Wimbledon match such as "分析Wimbledon正在进行的 Lehecka vs Zverev", requests historical and current match data, style matchup, head-to-head, grass/court/roof conditions, recent form, or asks for independent current win probabilities that must not use betting odds, market-implied probabilities, IBM Live Likelihood, bookmaker lines, or third-party prediction percentages.
---

# Wimbledon Match Predictor

## Goal

Produce an independent Wimbledon match probability read from comprehensive historical data, player matchup context, court conditions, current match data, and Markov-style tennis state reasoning. Do not reduce the workflow to a fixed formula or one bundled script.

## Hard Rules

- Do not use betting odds, market-implied probabilities, IBM Live Likelihood, bookmaker lines, or third-party prediction percentages as inputs, anchors, or sanity checks.
- Do not give a final probability until historical data, playing style, player matchup, court/conditions, recent form, current-match data, and probability reasoning have been attempted.
- Use Markov thinking as a state-transition frame: point, game, set, server, tiebreak, best-of format, current score leverage, and remaining hold/break paths. Do not claim false precision when point/server data is missing.
- Treat any calculator or model helper as optional only when its assumptions match the current state. If it cannot represent point score, tiebreak state, retirement risk, or suspension context, use sensitivity cases or a probability range.
- Current score leverage comes before style opinions. A two-set lead, break advantage, or deciding-set tiebreak state dominates most qualitative factors.
- If a layer or source cannot be verified, name the gap and widen the final range.

## Tool And Data Acquisition

Use the best available tools, not just search snippets:

- Prefer source-close data: Wimbledon official scores/SlamTracker/match centre, ATP/WTA official pages, match reports, live-score sites for raw facts, Tennis Abstract/UTS/ITF/SteveG for historical context.
- Use Chrome when live pages, logged-in sessions, dynamic scoreboards, SlamTracker, or anti-scraping behavior require the user's browser.
- Use chrome-devtools when available to inspect network calls, JSON payloads, rendered DOM, console state, and live scoreboard updates.
- Use Playwright for browser automation, snapshots, screenshots, and dynamic-page extraction.
- Use Python, Node, curl, jq, local scripts, or site-specific parsers to fetch and normalize score, serve stats, and historical data.
- If a useful local tool is missing, install it globally or user-scoped in the active environment when allowed, verify it works, then use it.
- Read `references/data-sources.md` when choosing sources or explaining source quality.

## Analysis Layers

Build the probability from these layers, in order:

1. **Historical baseline**: grass and recent-season results, Wimbledon record, best-of-five record where relevant, H2H, opponent quality, and hold/break tendencies.
2. **Playing style**: serve dominance, return quality, rally tolerance, movement, net play, backhand/forehand pressure, tiebreak profile, and grass suitability.
3. **Player matchup**: serve pattern vs return position, first-strike pressure, rally patterns, physical/fatigue edge, injury or medical context, and pressure-point history.
4. **Court/map layer**: court, roof, weather/light, wind, ball/skid conditions, suspension/resumption, and how they affect serve, return, movement, and rally length.
5. **Recent and current-match data**: current score, server, point score when available, service points won, first/second-serve performance, break points, winners/errors, net points, and momentum swings.
6. **Probability synthesis**: estimate future service/return strength, apply Markov-style point/game/set reasoning, then synthesize match probability with sensitivity ranges.

## Output

Answer in the user's language with:

1. Verified current state: timestamp, status, score, server, point state if available, court/conditions, and source links.
2. Data used from each analysis layer; name missing layers.
3. Probability reasoning: score leverage, service/return paths, tiebreak or break scenarios, and key assumptions.
4. Independent win probabilities with range and confidence.
5. What changes the number next: hold/break, tiebreak, set result, injury, suspension, or resumption scenarios.

## Failure Modes

- If point score is unknown in a high-leverage game, widen the range.
- If current server is unknown, run neutral or both-server sensitivity cases.
- If service-point estimates are unavailable, give only a provisional qualitative probability.
- Do not invent injuries, medical limitations, court conditions, or current-match stats.
