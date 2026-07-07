# Valorant Data Sources

Use this reference when selecting data sources or explaining data quality. Do not use sportsbook odds, market-implied probabilities, site prediction percentages, or third-party model win probabilities as inputs, anchors, or sanity checks.

## Source Tiers

### VLR.gg

Best default source for live match pages, match results, player stats, and team map statistics.

Use for:
- Live score and side split on active match pages.
- VLR match ID lookup from Liquipedia `vlr=` fields.
- Team map statistics via `/team/stats/<team-id>/<slug>/`.
- Player aggregate stats via `/stats`.
- Recent matches, head-to-head, and event context.

Strengths:
- Broad pro, tier-2, Game Changers, and regional coverage.
- Team map pages expose map count, win rate, attack/defense round records, and recent map history.
- Live pages often update score and side earlier than Liquipedia.

Limitations:
- Unofficial and HTML-only unless using third-party wrappers.
- Player stats for active maps may lag or show placeholders until later.
- Team IDs must be resolved from match page links; guessed IDs are error-prone.

### Liquipedia

Best source for tournament structure, bracket, match IDs, veto, map order, rosters, and completed-map details.

Use for:
- Match pages from user links.
- Map veto and map pick order.
- Series state, bracket context, tournament dates, patch, casters/streams.
- Completed map data: first kills, post-plants, clutches, player ACS/KDA, round details.

Workflow:
- If normal page fetch is blocked, call MediaWiki API:
  `https://liquipedia.net/valorant/api.php?action=parse&page=<MATCH_TITLE>&prop=wikitext|text|links&format=json&formatversion=2`
- Extract `vlr=<id>` from wikitext when present.

Limitations:
- Live score can lag.
- API map data may not populate until after a map finishes.
- Team abbreviations can differ from VLR.

### RIB.GG

Good supplemental source for analytics, team/player profiles, match history, rankings, and 2D replay/heatmap style analysis where accessible.

Use for:
- Deeper historical or tactical review.
- Cross-checking player/team analytics.
- Roster/team history and ELO-style context.

Limitations:
- Some data is rendered client-side and may require browser tooling.
- Live match reliability varies by event.
- Coverage can be less convenient to scrape quickly than VLR/Liquipedia.

### THESPIKE.GG

Good supplemental source for news, team pages, match lists, rosters, and event coverage.

Use for:
- Cross-checking team roster, recent matches, and event narratives.
- News/context such as roster changes, benchings, previews, and regional coverage.

Limitations:
- Live score and advanced stat coverage may be slower or less complete than VLR for quick predictions.
- Pages can be sparse for lower-tier teams.

### BO3.gg

Useful live-score cross-check and current match listing source.

Use for:
- Today's matches, live scores, and quick scoreboard confirmation.
- Cross-checking when VLR/Liquipedia disagree or lag.

Limitations:
- Coverage depth varies.
- Historical map/team analytics are not as convenient as VLR for prediction work.

### Official VALORANT Esports

Authoritative schedule and stream hub for official Riot ecosystem events.

Use for:
- Official schedule, event status, teams, stream links.
- Cross-checking VCT/official event timing.

Limitations:
- Not a complete tier-2/tier-3 historical stat database.
- Riot Developer API is for VALORANT game data such as match-by-id and ranked leaderboards, not a convenient public live esports analytics feed.

### PandaScore

Commercial API source for structured esports data and post-game stats when credentials are available.

Use for:
- Programmatic workflows that require a supported API.
- Post-game data such as agents, kills, deaths, clutches, and round outcomes.

Limitations:
- Usually requires API access/credentials.
- Coverage and latency depend on plan/source integration.
- Ignore odds or probability fields if present.

### Third-Party VLR APIs

Examples include community wrappers around VLR. Use only as convenience layers.

Use for:
- Faster prototyping if the wrapper is reachable and current.
- Programmatic match, player, and team endpoints.

Limitations:
- Unofficial wrappers inherit VLR scraping risks and can break.
- Always cross-check high-stakes live predictions against original VLR/Liquipedia/stream pages.

## Selection Recipes

### User Gives a Liquipedia Match Link

1. Parse the match page through Liquipedia API.
2. Extract teams, event, BO format, map veto, map order, current/finished maps, and `vlr=` id.
3. Open the VLR match page for live score and side splits.
4. Open VLR team stats pages from team links.
5. Gather both teams' recent 5 matches, current roster/roles, map pool, attack/defense splits, and same-map recent results.
6. Use Liquipedia completed-map data for first kills, post-plants, retakes, clutches, player performance, and economy swings.
7. Add tactical and matchup analysis: pace/defaults, exec quality, post-plants, retakes, player role duels, and style fit against the opponent.
8. For in-progress maps, use Markov-style round-state reasoning across score, side, economy, ult economy, map strength, player form, and tactical matchup before final probabilities.
9. Only then produce map and series probabilities, citing missing or stale data as caveats.

### User Gives Only Teams and Score

1. Search VLR and Liquipedia by team names, event, and current date.
2. Use VLR live match page if found.
3. Gather recent form, map pool, roster/role context, player form, tactical style, and matchup context from the best available sources.
4. If not found, use the user's score as live state and say public pages could not be verified quickly.
5. Use Markov-style round-state reasoning when score and MR format are known.
6. Mark the probability provisional if key historical, current-match, tactical, or player-matchup data could not be verified.

### User Asks for First/Second/Third Map Prediction

1. Identify current map and series score.
2. If a prior map ended, use its actual first-kill, post-plant, player stat, and economy/clutch signals.
3. For the next map, use map pick ownership, map win rate, attack/defense splits, and recent same-map results.
4. Add team style and player-role matchup for that specific map before estimating probability.
5. Keep current map probability separate from series probability.

## Probability Ban

Never use these as inputs, anchors, calibration targets, or sanity checks:

- Sportsbook odds, moneylines, handicaps, totals, market-implied probabilities, or betting consensus.
- VLR odds/prediction fields, BO3.gg widgets, Tips.gg/Strafe/SofaScore predictions, analyst pick percentages, or community model probabilities.
- Commercial provider odds or probability fields from PandaScore or similar APIs.

It is acceptable to use factual data from the same sites: score, map, side, round history, economy/ult context when available, player stats, roster, veto, map pool, historical map win rate, attack/defense splits, and recent results.

For in-progress maps with enough current state, calculate independently from score, MR format, side, economy/ult state, map strength, player form, tactical matchup, and series context. Do not collapse the analysis into a fixed single per-round probability.

### User Asks for Deep Team Style Research

1. Start with VLR map pool and recent match pages.
2. Add Liquipedia roster/event/patch/veto context.
3. Add RIB.GG/THESPIKE for analytics and roster/news cross-checks.
4. Summarize style in operational terms: pace, defaulting, post-plant, retakes, first-contact dependence, map-specific comfort.
5. Translate the style read into matchup impact: which team benefits on each map, which roles are under pressure, and which live-round signals would confirm or refute the read.
