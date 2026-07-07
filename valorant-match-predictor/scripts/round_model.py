#!/usr/bin/env python3
"""Independent Valorant live map Markov calculator.

This script uses score state and an independently estimated per-round
probability. It does not fetch or use sportsbook odds, market probabilities, or
third-party prediction percentages.
"""

import argparse
import json
import math


def comb(n, k):
    if k < 0 or k > n:
        return 0
    return math.comb(n, k)


def parse_score(value):
    for sep in ("-", ":", " "):
        if sep in value:
            parts = [p for p in value.replace(":", "-").replace(" ", "-").split("-") if p != ""]
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
    raise ValueError("score must look like 11-5 or 9:8")


def model(score_a, score_b, p_round_a, ot_win_a=0.5, mr=12, lines=None):
    target = mr + 1
    regulation_rounds = mr * 2
    if score_a < 0 or score_b < 0:
        raise ValueError("score cannot be negative")
    if score_a + score_b > regulation_rounds:
        raise ValueError("score is outside regulation range")
    if score_a >= target or score_b >= target:
        raise ValueError("map is already won in regulation")

    p = p_round_a
    q = 1.0 - p
    need_a = target - score_a
    need_b = target - score_b
    max_remaining = regulation_rounds - score_a - score_b
    rows = []

    for b_wins_before_final in range(need_b):
        remaining = need_a + b_wins_before_final
        if remaining <= max_remaining:
            prob = comb(remaining - 1, b_wins_before_final) * (p ** need_a) * (q ** b_wins_before_final)
            rows.append({"winner": "team_a", "remaining_rounds": remaining, "regulation_total_rounds": score_a + score_b + remaining, "probability": prob})

    for a_wins_before_final in range(need_a):
        remaining = need_b + a_wins_before_final
        if remaining <= max_remaining:
            prob = comb(remaining - 1, a_wins_before_final) * (q ** need_b) * (p ** a_wins_before_final)
            rows.append({"winner": "team_b", "remaining_rounds": remaining, "regulation_total_rounds": score_a + score_b + remaining, "probability": prob})

    a_to_ot = mr - score_a
    b_to_ot = mr - score_b
    if a_to_ot >= 0 and b_to_ot >= 0 and a_to_ot + b_to_ot == max_remaining:
        prob = comb(max_remaining, a_to_ot) * (p ** a_to_ot) * (q ** b_to_ot)
        rows.append({"winner": "overtime", "remaining_rounds": max_remaining, "regulation_total_rounds": regulation_rounds, "probability": prob})

    overtime_probability = sum(r["probability"] for r in rows if r["winner"] == "overtime")
    team_a_regulation = sum(r["probability"] for r in rows if r["winner"] == "team_a")
    team_b_regulation = sum(r["probability"] for r in rows if r["winner"] == "team_b")
    team_a_map = team_a_regulation + overtime_probability * ot_win_a
    team_b_map = team_b_regulation + overtime_probability * (1.0 - ot_win_a)
    expected_regulation_total = sum(r["regulation_total_rounds"] * r["probability"] for r in rows)

    distribution = {}
    for r in rows:
        key = str(r["regulation_total_rounds"])
        distribution[key] = distribution.get(key, 0.0) + r["probability"]

    line_probs = {}
    line_notes = {}
    for line in lines or []:
        over = sum(r["probability"] for r in rows if r["regulation_total_rounds"] > line)
        line_probs[f"over_{line}"] = over
        line_probs[f"under_{line}"] = 1.0 - over
        if line >= regulation_rounds:
            line_notes[
                str(line)
            ] = "Line is above or equal to regulation length; this script excludes overtime total rounds."

    return {
        "model": "absorbing Markov chain over remaining regulation rounds; independent, no odds or third-party probabilities",
        "score": {"team_a": score_a, "team_b": score_b},
        "assumptions": {
            "mr": mr,
            "p_round_team_a": p_round_a,
            "ot_win_team_a": ot_win_a,
            "round_line_scope": "regulation_only_excludes_overtime",
        },
        "map_win_probability": {"team_a": team_a_map, "team_b": team_b_map},
        "regulation_win_probability": {"team_a": team_a_regulation, "team_b": team_b_regulation},
        "overtime_probability": overtime_probability,
        "expected_regulation_total_rounds": expected_regulation_total,
        "regulation_total_distribution": distribution,
        "regulation_round_line_probabilities": line_probs,
        "round_line_probabilities": line_probs,
        "round_line_notes": line_notes,
    }


def main():
    parser = argparse.ArgumentParser(description="Independent Valorant MR12 Markov live map win and total-round probability calculator.")
    parser.add_argument("--team-a", default="Team A")
    parser.add_argument("--team-b", default="Team B")
    parser.add_argument("--score", required=True, help="Current score for team A-team B, e.g. 11-5 or 9:8")
    parser.add_argument("--p-round-a", type=float, required=True, help="Independently estimated Team A probability for each remaining regulation round")
    parser.add_argument("--ot-win-a", type=float, default=0.5, help="Independently estimated Team A overtime win probability")
    parser.add_argument("--mr", type=int, default=12, help="Max rounds per half. Valorant standard is 12.")
    parser.add_argument("--lines", default="20.5,21.5,22.5,23.5", help="Comma-separated total round lines")
    args = parser.parse_args()

    if not 0 <= args.p_round_a <= 1:
        raise ValueError("--p-round-a must be between 0 and 1")
    if not 0 <= args.ot_win_a <= 1:
        raise ValueError("--ot-win-a must be between 0 and 1")

    score_a, score_b = parse_score(args.score)
    lines = [float(x.strip()) for x in args.lines.split(",") if x.strip()]
    try:
        result = model(score_a, score_b, args.p_round_a, args.ot_win_a, args.mr, lines)
    except ValueError as exc:
        if "outside regulation" in str(exc):
            raise SystemExit(
                "Current score is outside regulation. This script only models regulation states and pre-overtime probability; do not use it as the final live model for overtime-in-progress maps."
            ) from exc
        raise
    result["teams"] = {"team_a": args.team_a, "team_b": args.team_b}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
