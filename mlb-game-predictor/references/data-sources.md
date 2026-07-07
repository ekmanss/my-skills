# MLB Data Sources

Use this reference when selecting data for MLB game prediction. Prefer structured APIs and official feeds; use browser/Chrome workflows when a page is JavaScript-rendered, blocked, or ahead of API wrappers.

## Live/In-Progress Data Ranking

1. **MLB Stats API / Gameday**  
   Best default free source for live state. Use it for schedules, gamePk resolution, live feed, linescore, boxscore, play-by-play, lineups, standings, team/player stats, weather, and MLB contextMetrics win probability.
   - Live feed: `https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live`
   - Context metrics: `https://statsapi.mlb.com/api/v1/game/{gamePk}/contextMetrics`
   - Boxscore: `https://statsapi.mlb.com/api/v1/game/{gamePk}/boxscore`
   - Schedule: `https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=YYYY-MM-DD&hydrate=team,linescore,probablePitcher,venue`
   - Team stats: `https://statsapi.mlb.com/api/v1/teams/{teamId}/stats?stats=season&group=hitting,pitching,fielding&season=YYYY&gameType=R`
   - Strengths: official scoring, no API key in practice, pitch/play granularity, current lineups and box score.
   - Limitations: public documentation is informal; win probability can lag a play; `currentPlay` may be an administrative event.

2. **ESPN Gamecast / site API**  
   Strong cross-check for live score and win probability, often useful when MLB contextMetrics lags.
   - Public web page: `https://www.espn.com/mlb/game/_/gameId/{espnGameId}`
   - Site summary JSON often works at: `https://site.web.api.espn.com/apis/site/v2/sports/baseball/mlb/summary?event={espnGameId}`
   - Strengths: quick Gamecast state, win-probability history, readable play sequence.
   - Limitations: not an official MLB data contract; ESPN ids differ from MLB gamePk; can lag or omit details.

3. **Baseball Savant / Statcast Gamefeed**  
   Best public source for pitch and batted-ball quality: exit velocity, launch angle, xBA/xwOBA, barrels, hard-hit, pitch movement, WPA/top performers.
   - Gamefeed: `https://baseballsavant.mlb.com/gf?game_pk={gamePk}`
   - CSV docs: `https://baseballsavant.mlb.com/csv-docs`
   - Strengths: advanced pitch-by-pitch and batted-ball context.
   - Limitations: may return 403 outside a browser; can lag Gameday; large Statcast searches can time out. Use Chrome/browser, pybaseball, or Baseball Savant pages when direct fetch is blocked.

4. **Commercial APIs for production-grade live systems**  
   Use only if credentials are available.
   - Sportradar MLB API: official venue-collected MLB data normalized into Sportradar format; real-time play-by-play, boxscore, game summary, push feeds, and some Statcast fields. Historical MLB API data starts in 2013; Statcast fields from 2020 for supported endpoints.
   - SportsDataIO MLB API: real-time game lifecycle coverage including scores, game state, team/player stats, play-by-play/pitch-by-pitch, in-play odds, weather, lineups, injuries, projections, and historical database offerings.
   - Strengths: SLAs, stable docs, odds/injuries/depth charts, push/production integration.
   - Limitations: paid, key-based, provider-specific ids and schemas.

5. **Scoreboard/news fallbacks**  
   MLB.com, CBS, Yahoo, The Athletic, team sites, and beat reporters can help with injuries, late scratches, rain delays, and qualitative context. Do not use them as the primary source for exact live base/out state if structured feeds are available.

## Historical Data Ranking

1. **Retrosheet**  
   Best free historical event-level source. Retrosheet reports complete play-by-play for AL/NL seasons from 1910-2025 plus Federal League 1914-1915, with many early accounts deduced from newspaper stories and box scores. Also provides box-score data and downloadable parsed play-by-play/daily logs.  
   Use for historical play-by-play, run expectancy, base/out modeling, event studies, long-term head-to-head, and game logs. Not real-time; releases lag the current season.

2. **Lahman Baseball Database / SABR**  
   Best free long-range season-level relational database. Lahman contains batting and pitching statistics from 1871-2025 plus fielding, standings, team stats, managers, postseason, and Negro Leagues data where available.  
   Use for season/career/team baselines and long historical comparisons. Not pitch-by-pitch and not current live data.

3. **Baseball Savant Statcast CSV**  
   Best public advanced-data history for the modern tracking era. CSV docs include pitch-level fields such as `game_pk`, pitch velocity, pitch movement, count, base state, plate location, launch speed, launch angle, estimated BA/wOBA, and player ids. Velocity data spans PitchFX 2008-2016 and Statcast from 2017 onward; richer batted-ball tracking is strongest in the Statcast era.  
   Use for pitch arsenal, hitter quality of contact, xwOBA, hard-hit/barrel trends, platoon and rolling-window analysis.

4. **FanGraphs**  
   Best public-facing advanced leaderboard ecosystem for wRC+, WAR, FIP/xFIP, K-BB%, team pages, splits, projections, playoff odds, depth charts, and park factors. FanGraphs notes MLB/MiLB data from MLB and pitch/play data from Sports Info Solutions.  
   Use for current-season team/player quality, projections, bullpen depth, park factors, and contextual sabermetrics. Scraping may be brittle; prefer browser or pybaseball when helpful.

5. **Baseball-Reference / Stathead**  
   Excellent for box scores, game logs, splits, streaks, player/team pages, historical records, park factors, and Stathead query tools.  
   Use for human-readable verification and deep split/head-to-head questions. Some advanced querying is subscription-gated and pages can be scraper-hostile.

6. **pybaseball / baseballr wrappers**  
   Useful developer accelerators. pybaseball retrieves Statcast, pitching/hitting stats, standings/team records, awards, and other data from Baseball Savant, Baseball Reference, and FanGraphs.  
   Use when installed and when a scripted data pull is faster than manual endpoint work. Remember wrappers can lag upstream schema changes.

7. **Commercial historical feeds**  
   Sportradar and SportsDataIO are better for productized historical/live integration when budget and API keys exist. Prefer Retrosheet/Lahman/Savant/FanGraphs for free research unless the user explicitly has credentials.

## Recommended Source Mix by Task

- **Live win probability**: MLB live feed + MLB contextMetrics + ESPN Gamecast cross-check. Add Savant for batted-ball quality.
- **Pre-game prediction**: MLB schedule/probables + standings/team stats + FanGraphs projections/park factors + Savant pitcher/hitter trends + injury/lineup news.
- **Historical model/backtest**: Retrosheet play-by-play + Lahman season/team tables + Savant modern pitch quality.
- **Player matchup**: Savant pitch arsenal and batter quality-of-contact + MLB player stats/splits + FanGraphs/Stathead splits.
- **Ballpark/map layer**: MLB venue/weather from boxscore/live feed + FanGraphs/Savant park factors + weather/wind/roof context from MLB or weather source.

## Source Conflict Policy

- Name the source and refresh time for live states.
- Prefer the latest completed play over a stale probability number.
- Prefer MLB official feed for score/base/out and official scoring.
- Prefer ESPN only when its win probability has clearly incorporated a newer completed play than MLB contextMetrics.
- Prefer Savant for quality-of-contact, not official score correction.
- If browser-only pages are ahead or direct API calls 403, use Chrome/browser extraction rather than abandoning the source.

## Research Sources

- Retrosheet: `https://www.retrosheet.org/`
- Lahman/SABR: `https://sabr.org/lahman-database/`
- Baseball Savant CSV docs: `https://baseballsavant.mlb.com/csv-docs`
- Baseball Savant gamefeed: `https://baseballsavant.mlb.com/gamefeed`
- FanGraphs: `https://www.fangraphs.com/`
- Baseball-Reference: `https://www.baseball-reference.com/`
- pybaseball: `https://github.com/jldbc/pybaseball`
- Sportradar MLB API basics: `https://developer.sportradar.com/baseball/docs/mlb-ig-api-basics`
- Sportradar historical coverage: `https://developer.sportradar.com/baseball/docs/mlb-ig-historical-data`
- SportsDataIO MLB API: `https://sportsdata.io/mlb-api`
