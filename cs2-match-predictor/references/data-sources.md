# CS2 Data Sources

Use this reference when choosing data sources or explaining source quality.

## Best Public Historical Sources

### HLTV

Primary public source for professional Counter-Strike historical data. Use for match pages, map veto, lineups, final scores, player ratings, team pages, rankings, recent matches, player/team/map filters, and advanced stats pages.

Strengths:
- Deepest public historical CS database.
- Strong player/team/map filters.
- Good for roster-aware recent form, map pool, and top-tier event context.

Limits:
- Some pages are hard to scrape and may block automation.
- Live logs can lag or be unavailable for lower-tier matches.
- Side/economy detail is less complete than official telemetry.

Useful URLs:
- `https://www.hltv.org/matches`
- `https://www.hltv.org/stats`
- `https://www.hltv.org/stats/maps`
- `https://www.hltv.org/team/<id>/<slug>`
- `https://www.hltv.org/matches/<id>/<slug>`

### BO3.gg

Strong public source for live scores, team/player pages, and match statistics. Use it as a live cross-check and for player/team stats when HLTV is blocked or sparse.

Strengths:
- Publicly presents CS2 live scores and match pages.
- Team pages often include recent stats, transfers, and player performance tables.
- Often easier to browse than HLTV.

Limits:
- Historical depth and canonical status are weaker than HLTV.
- Some stats use BO3.gg-specific scoring; do not mix blindly with HLTV rating.

Useful URLs:
- `https://bo3.gg/`
- `https://bo3.gg/matches/current`
- `https://bo3.gg/teams/<team-slug>`

### Liquipedia Counter-Strike

Use for tournament structure, bracket context, event tier, roster pages, match schedules, and team match histories.

Strengths:
- Excellent event and roster context.
- Useful for lower-tier events and team match lists.
- Good for BO format, bracket pressure, and elimination context.

Limits:
- Player and round statistics are usually limited.
- Live score speed varies.

Useful URLs:
- `https://liquipedia.net/counterstrike/Main_Page`
- `https://liquipedia.net/counterstrike/<Team>/Matches`

### 5EPlay Event Data

Primary public source for in-progress CS2 matches when covered. Use it first when the user provides a 5EPlay match URL, and also use it first when the user only provides team names or a current live score. The public match list at `https://event.5eplay.com/csgo/matches` exposes current live teams and match links; use it to locate the relevant `csgo_mc_*` match id before fetching structured JSON.

Endpoints:
- Match list: `https://event.5eplay.com/csgo/matches`
- Match page: `https://event.5eplay.com/csgo/matches/<match_id>`
- Current data: `https://esports-data.5eplaycdn.com/v1/api/csgo/matches/<match_id>/data`
- Analysis: `https://esports-data.5eplaycdn.com/v1/api/csgo/matches/<match_id>/analysis_v1`
- Event log: `https://esports-data.5eplaycdn.com/v1/api/csgo/match/<match_id>/event/log?update_version=0&limit=1000`
- Score tabs: `https://app.5eplay.com/api/score/match_score_tab?match_id=<match_id>&game_type=1`

Live discovery workflow:
1. Open or browse `https://event.5eplay.com/csgo/matches` and search the current teams, aliases, or tournament.
2. Extract the match id from a link such as `https://event.5eplay.com/csgo/matches/csgo_mc_2395587`.
3. Fetch `/data` first for live score, current map, sides, player stats, economy, veto, and series state.
4. Fetch `/analysis_v1` for pre-match comparison, historical baselines, map pool, and player references.
5. Fetch `/event/log` when the live score looks stale or the user reports a score one round ahead of `bouts_state`.
6. Use the rendered match/list pages for discovery and sanity checks; use the structured endpoints as the analytic source of record.

Fields to inspect:
- `data.match.mc_info`: teams, format, event, planned start.
- `data.match.global_state.bp_map_item`: veto, picks, decider.
- `data.match.bouts_state`: map order, score, stage, side, player stats.
- Event `log_info`: latest round start/end, bomb events, kills. Logs may update before `bouts_state`.
- `analysis_v1.result.comparison`: team stats, player baselines, map pool.

Limits:
- Not all CS2 matches are covered.
- Chinese team aliases may differ from HLTV names.
- Event-log CT/T scores must be mapped to current sides before treating as team score.
- Some market/odds fields can be stale; do not use them as the main model.

### Dust2.us

Use as a secondary source for match pages, NA coverage, news, and sometimes mirrored match metadata.

Strengths:
- Useful when HLTV links are hard to parse.
- Good for North American CS context.

Limits:
- Not comprehensive globally.
- Historical/team-stat depth is not HLTV-level.

### Tips.gg, EGamersWorld, Strafe, SofaScore, Esports Charts

Use as secondary confirmation for schedules, live score, event pages, and odds/sentiment. Do not treat as primary player-stat sources unless they expose the missing match cleanly.

## Best Live / Official Data Sources

### GRID

Official real-time esports data platform. Best option when credentials or open access are available, especially for telemetry-grade live CS2 data.

Strengths:
- Official, real-time data.
- CS2 and Dota 2 open-access program exists.
- Useful for low-latency live score, round events, telemetry, widgets, and model feeds.

Limits:
- Requires access approval or commercial integration.
- Not always available in an ordinary browsing session.

Useful URLs:
- `https://grid.gg/`
- `https://grid.gg/open-access/`
- `https://grid.gg/live-esports-data/`

### Bayes Esports

Official live match data supplier for major tournament ecosystems, including ESL/BLAST-related Counter-Strike coverage.

Strengths:
- High-granularity live match data.
- Betting-grade official data for top-tier events.

Limits:
- Enterprise/commercial access.
- Not usually available through public browsing.

### Abios

Commercial esports API for live and historical data. Use if API credentials exist.

Strengths:
- Normalized live and historical esports data.
- Covers live scores, player stats, and event context.

Limits:
- Paid/credentialed.
- Coverage details depend on package.

Useful URLs:
- `https://abiosgaming.com/esports-data-api`
- `https://abiosgaming.com/packaging`

### PandaScore

Commercial stats and odds API. Use if credentials exist for schedules, live stats, and odds products.

Strengths:
- Public developer positioning for real-time esports statistics and odds.
- Broad esport coverage and documented API ecosystem.

Limits:
- Stats API and odds product are distinct.
- Live low-latency betting use may require paid plan.

Useful URLs:
- `https://www.pandascore.co/`
- `https://www.pandascore.co/stats`
- `https://developers.pandascore.co/docs/frequently-asked-questions`

### GameScorekeeper

Commercial API with REST historical fixture data and live WebSocket data.

Strengths:
- Live WebSocket model is useful for in-progress matches.
- REST can cover past and future fixtures.

Limits:
- Credentialed API.

Useful URL:
- `https://docs.gamescorekeeper.com/`

## Source Priority

For public analysis:

1. 5EPlay match list plus structured data for in-progress matches, especially when the teams appear on `https://event.5eplay.com/csgo/matches` or the user provides a 5E match link.
2. HLTV match/team/stats pages for canonical history.
3. BO3.gg for live cross-check and accessible team/player data.
4. Liquipedia for event/bracket/roster context.
5. Dust2.us, Tips.gg, EGamersWorld, Strafe, SofaScore as secondary confirmation.

For credentialed analysis:

1. GRID or Bayes for official live telemetry.
2. Abios, PandaScore, or GameScorekeeper for normalized live/historical APIs.
3. Public sources above for human-readable context and sanity checks.

## Research Notes From Prior Use

- 5EPlay was very effective for live BO3 analysis because `/data`, `/analysis_v1`, and `/event/log` exposed current score, map order, player stats, and historical map stats.
- 5EPlay's match list is the preferred entry point for "正在比赛中" prompts because it can reveal the current live teams and the exact `csgo_mc_*` match id even when the user only gives team names and score.
- 5E event logs can lead the main `bouts_state` score by one round. When this happens, state that the event log is fresher and use it cautiously.
- HLTV is best for historical completeness, but scraping can fail. Search by team names plus numeric match id when a direct page is unknown.
- BO3.gg is useful when you need fast live match pages or player tables and HLTV is blocked.
