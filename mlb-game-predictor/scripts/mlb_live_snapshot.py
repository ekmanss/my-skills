#!/usr/bin/env python3
"""Fetch a compact MLB live-game snapshot from public MLB Stats API endpoints.

This script intentionally omits provider win-probability endpoints such as MLB
contextMetrics. The skill using this script calculates probabilities
independently from factual game state and historical context.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.parse
import urllib.request
from typing import Any

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None


BASE = "https://statsapi.mlb.com"


def fetch_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "mlb-game-predictor/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def api(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    return fetch_json(url)


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def today_eastern() -> dt.date:
    if ZoneInfo:
        return dt.datetime.now(ZoneInfo("America/New_York")).date()
    return dt.datetime.utcnow().date()


def date_window(date_value: str | None, before: int, after: int) -> list[dt.date]:
    base = dt.date.fromisoformat(date_value) if date_value else today_eastern()
    return [base + dt.timedelta(days=i) for i in range(-before, after + 1)]


def split_query(query: str) -> list[str]:
    parts = re.split(r"\s+(?:vs\.?|versus|v\.?|at|@)\s+|\s+-\s+", query.strip(), flags=re.I)
    parts = [p.strip() for p in parts if p.strip()]
    return parts if parts else [query.strip()]


def team_aliases(team: dict[str, Any]) -> set[str]:
    fields = [
        team.get("name"),
        team.get("teamName"),
        team.get("locationName"),
        team.get("shortName"),
        team.get("abbreviation"),
        team.get("teamCode"),
        team.get("fileCode"),
    ]
    aliases = {norm(str(v)) for v in fields if v}
    if team.get("locationName") and team.get("teamName"):
        aliases.add(norm(f"{team['locationName']} {team['teamName']}"))
    return aliases


def team_matches(part: str, team: dict[str, Any]) -> bool:
    needle = norm(part)
    aliases = team_aliases(team)
    return any(needle == alias or needle in alias or alias in needle for alias in aliases if alias)


def game_matches_query(game: dict[str, Any], query: str) -> bool:
    parts = split_query(query)
    away = game["teams"]["away"]["team"]
    home = game["teams"]["home"]["team"]
    if len(parts) >= 2:
        return (
            (team_matches(parts[0], away) and team_matches(parts[1], home))
            or (team_matches(parts[0], home) and team_matches(parts[1], away))
        )
    return team_matches(parts[0], away) or team_matches(parts[0], home)


def resolve_game_pk(query: str, date_value: str | None, before: int, after: int) -> int:
    candidates: list[dict[str, Any]] = []
    for day in date_window(date_value, before, after):
        sched = api(
            "/api/v1/schedule",
            {
                "sportId": 1,
                "date": day.isoformat(),
                "hydrate": "team,linescore,probablePitcher,venue",
            },
        )
        for date_block in sched.get("dates", []):
            for game in date_block.get("games", []):
                if game_matches_query(game, query):
                    candidates.append(game)

    if not candidates:
        raise SystemExit(f"No MLB game found for query {query!r} in the selected date window.")

    live = [g for g in candidates if g.get("status", {}).get("abstractGameState") == "Live"]
    target = live[0] if live else candidates[0]
    return int(target["gamePk"])


def name(obj: dict[str, Any] | None) -> str | None:
    return obj.get("fullName") if obj else None


def compact_person(obj: dict[str, Any] | None) -> dict[str, Any] | None:
    if not obj:
        return None
    return {"id": obj.get("id"), "name": obj.get("fullName")}


def compact_offense(offense: dict[str, Any]) -> dict[str, Any]:
    keys = ["batter", "onDeck", "inHole", "pitcher", "first", "second", "third"]
    return {key: compact_person(offense.get(key)) for key in keys if offense.get(key)}


def compact_current_play(play: dict[str, Any]) -> dict[str, Any]:
    matchup = play.get("matchup") or {}
    return {
        "count": play.get("count"),
        "result": play.get("result"),
        "about": play.get("about"),
        "matchup": {
            "batter": compact_person(matchup.get("batter")),
            "pitcher": compact_person(matchup.get("pitcher")),
            "batSide": matchup.get("batSide"),
            "pitchHand": matchup.get("pitchHand"),
            "postOnFirst": compact_person(matchup.get("postOnFirst")),
            "postOnSecond": compact_person(matchup.get("postOnSecond")),
            "postOnThird": compact_person(matchup.get("postOnThird")),
        },
    }


def team_stat(team_id: int, season: str) -> dict[str, Any]:
    data = api(
        f"/api/v1/teams/{team_id}/stats",
        {"stats": "season", "group": "hitting,pitching,fielding", "season": season, "gameType": "R"},
    )
    out: dict[str, Any] = {}
    for item in data.get("stats", []):
        group = item.get("group", {}).get("displayName")
        splits = item.get("splits") or []
        if group and splits:
            out[group] = splits[0].get("stat", {})
    return out


def standings_map(season: str) -> dict[int, dict[str, Any]]:
    data = api(
        "/api/v1/standings",
        {
            "leagueId": "103,104",
            "season": season,
            "standingsTypes": "regularSeason",
            "hydrate": "team,division,league,sport",
        },
    )
    out: dict[int, dict[str, Any]] = {}
    for record in data.get("records", []):
        for team_record in record.get("teamRecords", []):
            out[int(team_record["team"]["id"])] = team_record
    return out


def recent_games(team_id: int, end_date: str, days: int = 14, limit: int = 10) -> list[dict[str, Any]]:
    end = dt.date.fromisoformat(end_date)
    start = end - dt.timedelta(days=days)
    data = api(
        "/api/v1/schedule",
        {
            "sportId": 1,
            "teamId": team_id,
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "gameTypes": "R",
            "hydrate": "team,linescore",
        },
    )
    games: list[dict[str, Any]] = []
    for date_block in data.get("dates", []):
        for game in date_block.get("games", []):
            status = game.get("status", {})
            if status.get("abstractGameState") not in {"Final", "Live"}:
                continue
            ls = game.get("linescore", {})
            away = game["teams"]["away"]["team"]
            home = game["teams"]["home"]["team"]
            away_runs = ls.get("teams", {}).get("away", {}).get("runs")
            home_runs = ls.get("teams", {}).get("home", {}).get("runs")
            games.append(
                {
                    "gamePk": game.get("gamePk"),
                    "date": game.get("officialDate"),
                    "status": status.get("detailedState"),
                    "away": away.get("name"),
                    "home": home.get("name"),
                    "score": f"{away_runs}-{home_runs}" if away_runs is not None and home_runs is not None else None,
                }
            )
    return games[-limit:]


def build_snapshot(game_pk: int, include_season: bool) -> dict[str, Any]:
    feed = api(f"/api/v1.1/game/{game_pk}/feed/live")
    box = api(f"/api/v1/game/{game_pk}/boxscore")

    game_data = feed["gameData"]
    live = feed["liveData"]
    linescore = live["linescore"]
    season = str(game_data.get("game", {}).get("season") or game_data.get("datetime", {}).get("officialDate", "")[:4])
    away_team = game_data["teams"]["away"]
    home_team = game_data["teams"]["home"]
    official_date = game_data["datetime"].get("officialDate")

    completed_plays = [
        p
        for p in live.get("plays", {}).get("allPlays", [])
        if p.get("result", {}).get("event") or p.get("result", {}).get("description")
    ]

    snapshot: dict[str, Any] = {
        "fetchedAtUtc": dt.datetime.now(dt.UTC).isoformat(),
        "gamePk": game_pk,
        "officialDate": official_date,
        "status": game_data.get("status"),
        "venue": game_data.get("venue"),
        "teams": {
            "away": {"id": away_team.get("id"), "name": away_team.get("name")},
            "home": {"id": home_team.get("id"), "name": home_team.get("name")},
        },
        "score": {
            "away": linescore.get("teams", {}).get("away", {}).get("runs"),
            "home": linescore.get("teams", {}).get("home", {}).get("runs"),
        },
        "inning": {
            "current": linescore.get("currentInning"),
            "half": linescore.get("inningHalf"),
            "state": linescore.get("inningState"),
            "outs": linescore.get("outs"),
        },
        "offense": compact_offense(linescore.get("offense", {})),
        "defensePitcher": compact_person(linescore.get("defense", {}).get("pitcher")),
        "currentPlay": compact_current_play(live.get("plays", {}).get("currentPlay", {})),
        "lastPlays": [
            {
                "inning": p.get("about", {}).get("inning"),
                "half": p.get("about", {}).get("halfInning"),
                "event": p.get("result", {}).get("event"),
                "description": p.get("result", {}).get("description"),
                "awayScore": p.get("result", {}).get("awayScore"),
                "homeScore": p.get("result", {}).get("homeScore"),
            }
            for p in completed_plays[-10:]
        ],
        "probabilityPolicy": "No provider win-probability or odds fields fetched. Calculate independently.",
        "boxscore": {
            side: {
                "team": box["teams"][side]["team"]["name"],
                "batting": box["teams"][side].get("teamStats", {}).get("batting", {}),
                "pitching": box["teams"][side].get("teamStats", {}).get("pitching", {}),
                "fielding": box["teams"][side].get("teamStats", {}).get("fielding", {}),
            }
            for side in ["away", "home"]
        },
        "gameInfo": box.get("info", []),
        "sourceUrls": {
            "liveFeed": f"{BASE}/api/v1.1/game/{game_pk}/feed/live",
            "boxscore": f"{BASE}/api/v1/game/{game_pk}/boxscore",
            "baseballSavant": f"https://baseballsavant.mlb.com/gf?game_pk={game_pk}",
        },
    }

    if include_season and official_date:
        standings = standings_map(season)
        snapshot["seasonContext"] = {}
        for side, team in [("away", away_team), ("home", home_team)]:
            team_id = int(team["id"])
            snapshot["seasonContext"][side] = {
                "standings": standings.get(team_id),
                "teamStats": team_stat(team_id, season),
                "recentGames": recent_games(team_id, official_date),
            }

    return snapshot


def print_text(snapshot: dict[str, Any]) -> None:
    teams = snapshot["teams"]
    score = snapshot["score"]
    inning = snapshot["inning"]
    print(f"Fetched UTC: {snapshot['fetchedAtUtc']}")
    print(f"GamePk: {snapshot['gamePk']} | Date: {snapshot['officialDate']} | Venue: {snapshot['venue'].get('name')}")
    print(f"Status: {snapshot['status'].get('detailedState')}")
    print(f"Score: {teams['away']['name']} {score['away']} - {score['home']} {teams['home']['name']}")
    print(f"Inning: {inning['half']} {inning['current']} ({inning['state']}), outs={inning['outs']}")
    print(f"Offense: {json.dumps(snapshot['offense'], ensure_ascii=False)}")
    print(f"Defense pitcher: {snapshot['defensePitcher']}")
    print(f"Current play: {json.dumps(snapshot['currentPlay'], ensure_ascii=False)}")
    print(f"Probability policy: {snapshot['probabilityPolicy']}")
    print("Last plays:")
    for play in snapshot["lastPlays"]:
        print(f"- {play['inning']} {play['half']}: {play['event']} | {play['description']}")
    print("Source URLs:")
    for label, url in snapshot["sourceUrls"].items():
        print(f"- {label}: {url}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--game-pk", type=int, help="MLB Stats API gamePk")
    group.add_argument("--query", help='Matchup query, for example "Mets vs Braves"')
    parser.add_argument("--date", help="Official-date search anchor, YYYY-MM-DD. Defaults to current US/Eastern date.")
    parser.add_argument("--days-before", type=int, default=1, help="Schedule search days before anchor date.")
    parser.add_argument("--days-after", type=int, default=1, help="Schedule search days after anchor date.")
    parser.add_argument("--no-season-context", action="store_true", help="Skip standings, team stats, and recent games.")
    parser.add_argument("--json", action="store_true", help="Print full JSON instead of a compact text summary.")
    args = parser.parse_args()

    game_pk = args.game_pk or resolve_game_pk(args.query, args.date, args.days_before, args.days_after)
    snapshot = build_snapshot(game_pk, include_season=not args.no_season_context)

    if args.json:
        print(json.dumps(snapshot, indent=2, ensure_ascii=False))
    else:
        print_text(snapshot)
    return 0


if __name__ == "__main__":
    sys.exit(main())
