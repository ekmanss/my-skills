#!/usr/bin/env python3
"""Independent MLB live win probability from a 24-state base/out Markov model.

The model uses factual game state plus configurable event probabilities. It does
not fetch or use provider win-probability numbers or betting odds.
"""

from __future__ import annotations

import argparse
import json
from functools import lru_cache

DEFAULT_EVENTS = {
    "out": 0.675,
    "bb": 0.088,
    "single": 0.150,
    "double": 0.047,
    "triple": 0.004,
    "hr": 0.036,
}


def parse_bases(value: str) -> int:
    raw = (value or "").strip().lower()
    if raw in {"", "0", "none", "empty", "---"}:
        return 0
    if len(raw) == 3 and set(raw) <= {"0", "1"}:
        return (1 if raw[0] == "1" else 0) | (2 if raw[1] == "1" else 0) | (4 if raw[2] == "1" else 0)
    bases = 0
    for item in raw.replace("/", ",").replace(";", ",").split(","):
        token = item.strip()
        if not token:
            continue
        if token in {"1", "first", "1b"}:
            bases |= 1
        elif token in {"2", "second", "2b"}:
            bases |= 2
        elif token in {"3", "third", "3b"}:
            bases |= 4
        else:
            raise SystemExit(f"Unrecognized base token: {token!r}")
    return bases


def bases_label(bases: int) -> str:
    return "".join("1" if bases & bit else "0" for bit in (1, 2, 4))


def count_runners(bases: int) -> int:
    return (1 if bases & 1 else 0) + (1 if bases & 2 else 0) + (1 if bases & 4 else 0)


def parse_events(value: str | None, scale: float, league_rpg: float, rpg: float | None) -> tuple[tuple[str, float], ...]:
    if value:
        parts = [float(x) for x in value.split(",")]
        if len(parts) != 6:
            raise SystemExit("--events must be six comma-separated probabilities: out,bb,single,double,triple,hr")
        events = dict(zip(["out", "bb", "single", "double", "triple", "hr"], parts))
    else:
        events = dict(DEFAULT_EVENTS)

    if any(prob < 0 for prob in events.values()):
        raise SystemExit("event probabilities must be non-negative")
    if scale <= 0:
        raise SystemExit("manual scale values must be positive")
    if league_rpg <= 0:
        raise SystemExit("--league-rpg must be positive")
    if rpg is not None and rpg < 0:
        raise SystemExit("team runs per game must be non-negative")

    run_scale = scale * ((rpg / league_rpg) if rpg and league_rpg > 0 else 1.0)
    run_scale = max(0.55, min(1.55, run_scale))
    adjusted = {"out": events["out"]}
    for key in ["bb", "single", "double", "triple", "hr"]:
        adjusted[key] = events[key] * run_scale
    total = sum(adjusted.values())
    if total <= 0:
        raise SystemExit("event probabilities must sum to a positive value")
    return tuple((key, adjusted[key] / total) for key in ["out", "bb", "single", "double", "triple", "hr"])


def walk_transition(bases: int) -> tuple[int, int]:
    first = bool(bases & 1)
    second = bool(bases & 2)
    third = bool(bases & 4)
    if not first:
        return bases | 1, 0
    runs = 1 if second and third else 0
    new_bases = 1 | 2
    if second or third:
        new_bases |= 4
    return new_bases, runs


def transition(event: str, bases: int, outs: int) -> tuple[int, int, int]:
    if event == "out":
        return bases, outs + 1, 0
    if event == "bb":
        new_bases, runs = walk_transition(bases)
        return new_bases, outs, runs
    if event == "single":
        runs = (1 if bases & 2 else 0) + (1 if bases & 4 else 0)
        new_bases = 1 | (4 if bases & 1 else 0)
        return new_bases, outs, runs
    if event == "double":
        return 2, outs, count_runners(bases)
    if event == "triple":
        return 4, outs, count_runners(bases)
    if event == "hr":
        return 0, outs, count_runners(bases) + 1
    raise AssertionError(event)


def half_distribution(
    events: tuple[tuple[str, float], ...],
    bases: int,
    outs: int,
    max_runs: int,
    epsilon: float,
    max_pa: int,
) -> tuple[float, ...]:
    active: dict[tuple[int, int, int], float] = {(outs, bases, 0): 1.0}
    finished = [0.0] * (max_runs + 1)
    for _ in range(max_pa):
        if not active or sum(active.values()) < epsilon:
            break
        next_active: dict[tuple[int, int, int], float] = {}
        for (state_outs, state_bases, runs), prob in active.items():
            if state_outs >= 3:
                finished[min(runs, max_runs)] += prob
                continue
            for event, event_prob in events:
                new_bases, new_outs, scored = transition(event, state_bases, state_outs)
                new_runs = min(max_runs, runs + scored)
                if new_outs >= 3:
                    finished[new_runs] += prob * event_prob
                else:
                    key = (new_outs, new_bases, new_runs)
                    next_active[key] = next_active.get(key, 0.0) + prob * event_prob
        active = next_active
    for (_state_outs, _state_bases, runs), prob in active.items():
        finished[min(runs, max_runs)] += prob
    total = sum(finished)
    return tuple(x / total for x in finished)


def build_model(args: argparse.Namespace):
    away_events = parse_events(args.away_events, args.away_scale, args.league_rpg, args.away_rpg)
    home_events = parse_events(args.home_events, args.home_scale, args.league_rpg, args.home_rpg)
    max_runs = args.max_runs

    @lru_cache(maxsize=None)
    def half_dist(team: str, bases: int, outs: int) -> tuple[float, ...]:
        events = away_events if team == "away" else home_events
        return half_distribution(events, bases, outs, max_runs, args.epsilon, args.max_pa)

    def start_bases(inning: int) -> int:
        return 2 if args.extras_auto_runner and inning >= 10 else 0

    def unresolved_tie_home_prob() -> float:
        return args.tie_home_prob

    @lru_cache(maxsize=None)
    def home_win_prob(inning: int, half: str, diff: int, bases: int, outs: int) -> float:
        if diff < -args.max_score_diff:
            return 1.0
        if diff > args.max_score_diff:
            return 0.0
        if inning > args.max_inning:
            if diff < 0:
                return 1.0
            if diff > 0:
                return 0.0
            return unresolved_tie_home_prob()

        if half == "top":
            total = 0.0
            for runs, prob in enumerate(half_dist("away", bases, outs)):
                if prob == 0:
                    continue
                new_diff = min(args.max_score_diff, diff + runs)
                if inning >= 9 and new_diff < 0:
                    total += prob
                else:
                    total += prob * home_win_prob(inning, "bottom", new_diff, start_bases(inning), 0)
            return total

        total = 0.0
        for runs, prob in enumerate(half_dist("home", bases, outs)):
            if prob == 0:
                continue
            new_diff = max(-args.max_score_diff, diff - runs)
            if inning >= 9:
                if new_diff < 0:
                    total += prob
                elif new_diff > 0:
                    total += 0.0
                else:
                    total += prob * home_win_prob(inning + 1, "top", 0, start_bases(inning + 1), 0)
            else:
                total += prob * home_win_prob(inning + 1, "top", new_diff, start_bases(inning + 1), 0)
        return total

    return home_win_prob, away_events, home_events


def validate_args(args: argparse.Namespace) -> None:
    if args.inning < 1:
        raise SystemExit("--inning must be at least 1")
    if args.away_runs < 0 or args.home_runs < 0:
        raise SystemExit("runs must be non-negative")
    if args.outs < 0 or args.outs > 2:
        raise SystemExit("--outs must be 0, 1, or 2 for an active half-inning")
    if args.max_runs < 1:
        raise SystemExit("--max-runs must be positive")
    if args.max_pa < 1:
        raise SystemExit("--max-pa must be positive")
    if args.epsilon <= 0:
        raise SystemExit("--epsilon must be positive")
    if args.max_inning < args.inning:
        raise SystemExit("--max-inning must be greater than or equal to --inning")
    if args.max_score_diff < 1:
        raise SystemExit("--max-score-diff must be positive")
    if not 0.0 <= args.tie_home_prob <= 1.0:
        raise SystemExit("--tie-home-prob must be between 0 and 1")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inning", type=int, required=True)
    parser.add_argument("--half", choices=["top", "bottom"], required=True)
    parser.add_argument("--away-runs", type=int, required=True)
    parser.add_argument("--home-runs", type=int, required=True)
    parser.add_argument("--outs", type=int, required=True)
    parser.add_argument("--bases", default="0", help='Occupied bases, e.g. "2", "1,3", or "010".')
    parser.add_argument("--away-rpg", type=float, help="Away team runs per game, used to scale default event probabilities.")
    parser.add_argument("--home-rpg", type=float, help="Home team runs per game, used to scale default event probabilities.")
    parser.add_argument("--league-rpg", type=float, default=4.40)
    parser.add_argument("--away-scale", type=float, default=1.0, help="Manual away offense/pitcher/park adjustment multiplier.")
    parser.add_argument("--home-scale", type=float, default=1.0, help="Manual home offense/pitcher/park adjustment multiplier.")
    parser.add_argument("--away-events", help="Override away events as out,bb,single,double,triple,hr probabilities.")
    parser.add_argument("--home-events", help="Override home events as out,bb,single,double,triple,hr probabilities.")
    parser.add_argument("--no-extras-auto-runner", dest="extras_auto_runner", action="store_false")
    parser.add_argument("--max-runs", type=int, default=12)
    parser.add_argument("--max-pa", type=int, default=80, help="Plate-appearance iteration cap per half-inning distribution.")
    parser.add_argument("--epsilon", type=float, default=1e-10, help="Residual active probability cutoff per half-inning distribution.")
    parser.add_argument("--max-inning", type=int, default=16)
    parser.add_argument("--max-score-diff", type=int, default=12)
    parser.add_argument("--tie-home-prob", type=float, default=0.52, help="Fallback if still tied after max inning.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    validate_args(args)
    bases = parse_bases(args.bases)
    diff = args.away_runs - args.home_runs
    home_win_prob, away_events, home_events = build_model(args)
    home_wp = home_win_prob(args.inning, args.half, diff, bases, args.outs)
    away_wp = 1.0 - home_wp

    result = {
        "model": "24-state base/out Markov chain; independent, no provider win probability or odds",
        "state": {
            "inning": args.inning,
            "half": args.half,
            "awayRuns": args.away_runs,
            "homeRuns": args.home_runs,
            "outs": args.outs,
            "bases": bases_label(bases),
            "scoreDiffAwayMinusHome": diff,
        },
        "probability": {
            "away": round(away_wp * 100, 2),
            "home": round(home_wp * 100, 2),
        },
        "eventProbabilities": {
            "away": dict(away_events),
            "home": dict(home_events),
        },
        "assumptions": {
            "extrasAutoRunner": args.extras_auto_runner,
            "maxRunsBucket": args.max_runs,
            "maxInning": args.max_inning,
            "tieHomeProbAfterMaxInning": args.tie_home_prob,
        },
    }

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result["model"])
        print(
            f"State: {args.half} {args.inning}, score away-home {args.away_runs}-{args.home_runs}, "
            f"outs={args.outs}, bases={bases_label(bases)}"
        )
        print(f"Away win probability: {result['probability']['away']:.2f}%")
        print(f"Home win probability: {result['probability']['home']:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
