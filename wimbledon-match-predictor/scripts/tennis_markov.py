#!/usr/bin/env python3
"""Independent tennis score model for Wimbledon match analysis.

Inputs are caller-supplied service-point win probabilities and current score.
The script never fetches data and never uses odds or external win probabilities.
"""

from __future__ import annotations

import argparse
import json
from functools import lru_cache


def hold_probability(service_point_win: float) -> float:
    p = service_point_win
    q = 1.0 - p
    pre_deuce = p**4 * (1 + 4 * q + 10 * q * q)
    reach_deuce = 20 * p**3 * q**3
    win_from_deuce = (p * p) / (p * p + q * q)
    return pre_deuce + reach_deuce * win_from_deuce


def tiebreak_probability(p_a: float, p_b: float, first_server: str) -> float:
    @lru_cache(None)
    def win_prob(points_a: int, points_b: int, point_index: int) -> float:
        if (points_a >= 7 or points_b >= 7) and abs(points_a - points_b) >= 2:
            return 1.0 if points_a > points_b else 0.0

        # The remaining probability mass beyond this point is tiny for the
        # service probabilities this script is intended to model.
        if points_a >= 24 and points_b >= 24 and points_a == points_b:
            return 0.5

        server = tiebreak_server(first_server, point_index)
        point_prob_a = p_a if server == "A" else 1.0 - p_b
        return point_prob_a * win_prob(points_a + 1, points_b, point_index + 1) + (
            1.0 - point_prob_a
        ) * win_prob(points_a, points_b + 1, point_index + 1)

    return win_prob(0, 0, 0)


def tiebreak_server(first_server: str, point_index: int) -> str:
    if point_index == 0:
        return first_server
    block = (point_index - 1) // 2
    if first_server == "A":
        return "B" if block % 2 == 0 else "A"
    return "A" if block % 2 == 0 else "B"


def set_probability(
    p_a: float, p_b: float, games_a: int, games_b: int, next_server: str
) -> float:
    hold_a = hold_probability(p_a)
    hold_b = hold_probability(p_b)

    @lru_cache(None)
    def win_prob(g_a: int, g_b: int, server: str) -> float:
        if g_a >= 6 and g_a - g_b >= 2:
            return 1.0
        if g_b >= 6 and g_b - g_a >= 2:
            return 0.0
        if g_a == 6 and g_b == 6:
            return tiebreak_probability(p_a, p_b, server)

        if server == "A":
            return hold_a * win_prob(g_a + 1, g_b, "B") + (1.0 - hold_a) * win_prob(
                g_a, g_b + 1, "B"
            )
        return (1.0 - hold_b) * win_prob(g_a + 1, g_b, "A") + hold_b * win_prob(
            g_a, g_b + 1, "A"
        )

    return win_prob(games_a, games_b, next_server)


def neutral_set_probability(p_a: float, p_b: float) -> float:
    return 0.5 * set_probability(p_a, p_b, 0, 0, "A") + 0.5 * set_probability(
        p_a, p_b, 0, 0, "B"
    )


def remaining_match_probability(
    set_prob_a: float, sets_a: int, sets_b: int, best_of: int
) -> float:
    target = best_of // 2 + 1

    @lru_cache(None)
    def win_prob(s_a: int, s_b: int) -> float:
        if s_a >= target:
            return 1.0
        if s_b >= target:
            return 0.0
        return set_prob_a * win_prob(s_a + 1, s_b) + (1.0 - set_prob_a) * win_prob(
            s_a, s_b + 1
        )

    return win_prob(sets_a, sets_b)


def current_match_probability(args: argparse.Namespace) -> dict:
    p_a = args.server_a
    p_b = args.server_b
    future_set_a = neutral_set_probability(p_a, p_b)

    if args.next_server == "neutral":
        current_set_a = 0.5 * set_probability(
            p_a, p_b, args.games_a, args.games_b, "A"
        ) + 0.5 * set_probability(p_a, p_b, args.games_a, args.games_b, "B")
    else:
        current_set_a = set_probability(
            p_a, p_b, args.games_a, args.games_b, args.next_server
        )

    target = args.best_of // 2 + 1
    if args.sets_a >= target:
        match_a = 1.0
    elif args.sets_b >= target:
        match_a = 0.0
    else:
        match_a = current_set_a * remaining_match_probability(
            future_set_a, args.sets_a + 1, args.sets_b, args.best_of
        ) + (1.0 - current_set_a) * remaining_match_probability(
            future_set_a, args.sets_a, args.sets_b + 1, args.best_of
        )

    return {
        "labels": {"A": args.label_a, "B": args.label_b},
        "inputs": {
            "server_a": p_a,
            "server_b": p_b,
            "sets_a": args.sets_a,
            "sets_b": args.sets_b,
            "games_a": args.games_a,
            "games_b": args.games_b,
            "next_server": args.next_server,
            "best_of": args.best_of,
        },
        "derived": {
            "hold_a": hold_probability(p_a),
            "hold_b": hold_probability(p_b),
            "current_set_a": current_set_a,
            "current_set_b": 1.0 - current_set_a,
            "neutral_future_set_a": future_set_a,
            "neutral_future_set_b": 1.0 - future_set_a,
        },
        "match_probability": {
            "A": match_a,
            "B": 1.0 - match_a,
            args.label_a: match_a,
            args.label_b: 1.0 - match_a,
        },
    }


def bounded_probability(value: str) -> float:
    parsed = float(value)
    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError("probability must be between 0 and 1")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calculate independent tennis match probabilities from score and service-point estimates."
    )
    parser.add_argument("--label-a", default="Player A")
    parser.add_argument("--label-b", default="Player B")
    parser.add_argument("--server-a", type=bounded_probability, required=True)
    parser.add_argument("--server-b", type=bounded_probability, required=True)
    parser.add_argument("--sets-a", type=int, required=True)
    parser.add_argument("--sets-b", type=int, required=True)
    parser.add_argument("--games-a", type=int, required=True)
    parser.add_argument("--games-b", type=int, required=True)
    parser.add_argument(
        "--next-server", choices=["A", "B", "neutral"], default="neutral"
    )
    parser.add_argument("--best-of", type=int, choices=[3, 5], default=5)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    output = current_match_probability(args)
    print(json.dumps(output, indent=2 if args.pretty else None, sort_keys=True))


if __name__ == "__main__":
    main()
