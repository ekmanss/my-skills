---
name: valorant-match-predictor
description: Valorant esports match analysis and prediction workflow for live map and series win-probability estimates, map-by-map tactical reads, team style research, and source-backed analysis from Liquipedia, VLR.gg, RIB.GG, THESPIKE, BO3.gg, official VALORANT Esports, and related data sources. Use when the user provides a Valorant match link, current score, side information such as attack/defense, or asks for first/second/third map probabilities, live win rates, map veto interpretation, team form, player performance, or matchup prediction.
---

# Valorant Match Predictor

## Overview

Use this skill to produce source-backed Valorant esports predictions for live maps and full series. The default workflow is a full pre-judgment analysis, not a lightweight score reaction. Treat all probabilities as calibrated judgment, not deterministic betting advice.

## Core Workflow

1. Verify the live context first. For active or recent matches, browse or fetch current sources before answering. If the user's score is ahead of public pages, use the user's score as the live state and say so.
2. Resolve the match:
   - Identify teams, aliases, event, BO format, series score, current map, map pick, map veto, current score, and attack/defense sides.
   - For Liquipedia match links, use the MediaWiki parse API when normal pages block scripts:
     `https://liquipedia.net/valorant/api.php?action=parse&page=<MATCH_TITLE>&prop=wikitext|text|links&format=json&formatversion=2`
   - Extract the `vlr=` id from Liquipedia wikitext, then open `https://www.vlr.gg/<id>`.
3. Build the historical baseline before giving any probability:
   - Recent 5 matches for both teams, prioritizing the current roster and current patch.
   - Map pool by team: map count, win rate, recent results, attack/defense round win rates, and comfort maps.
   - Head-to-head and common-opponent context when available.
   - Roster, role, agent, IGL, substitute, and role-swap context.
4. Build the current-match layer:
   - Current map score and side split from VLR, official stream/scoreboard, or another named live source.
   - Map order, veto, picks, decider, and series state from Liquipedia/VLR.
   - Completed-map details from Liquipedia/VLR: first kills, post-plant conversion, retakes, clutches, player ACS/KDA, FK/FD, KAST, and economy swings when available.
5. Build the matchup layer:
   - Tactical style: fast exec vs default-heavy, contact pace, lurk value, post-plant quality, retake quality, clutch frequency, and economy vulnerability.
   - Team-on-team fit: how each team's style attacks the opponent's usual weaknesses on the current and remaining maps.
   - Player-on-player fit: duelist first-contact battle, initiator setup quality, controller utility value, sentinel/lurker survival, and current individual form.
6. Synthesize only after steps 1-5 are attempted. Weight live score and side context first, then map strength, veto ownership, recent form, tactical/style matchup, player matchup, and historical baseline.
7. Estimate the current map win rate, then estimate the series win rate by combining the current map probability with remaining-map baselines.
8. Answer in the user's language. For Chinese prompts, use concise Chinese and include concrete percentages.

Read `references/data-sources.md` when choosing among sources, explaining source quality, or doing match research.

## Mandatory Data Gate

Do not give a final probability until the full workflow above has been attempted. If a source is blocked, stale, or missing a stat, explicitly say what could not be verified and mark the affected estimate as lower-confidence or provisional. Do not silently skip historical data, current live data, tactical style, team matchup, player matchup, or recent form.

For very live prompts, keep the response concise but still do the full analysis. Reuse previously gathered full-context data only when the same match and map are still in progress and the user is asking for a score update; refresh any layer that may have changed.

## Probability Heuristics

Build probabilities from these factors, in this order:

1. **Score and rounds remaining**: a late 10-8 lead is more valuable than an early 5-3 lead.
2. **Side context**: always interpret score with attack/defense. A 7-5 half is strong if earned on the weaker side, weaker if earned on the stronger side.
3. **Map strength**: use map win rate plus attack/defense round win rates, not overall team strength alone.
4. **Map ownership**: give the picker a small baseline edge only when the pick matches historical strength.
5. **Economy phase**: pistol, anti-eco, bonus, and first full-buy rounds can move live probabilities sharply.
6. **Series state**: if one team already leads the series, separate map probability from series probability.
7. **Player and style signals**: first-kill gap, post-plant conversion, duelist impact, sentinel survival, and controller utility value matter more than raw kills alone.
8. **Recent form and matchup**: recent event results and head-to-head matter, but do not override live score and side state.

Use these anchors, then adjust for map/side/team context:

- **6-6 or 7-7**: start near 50/50; add 5-10 points for stronger side/map/team.
- **7-5 after first half**: 55-60% if leader won expected strong side; 65-75% if leader won weak side.
- **9-8 with leader on preferred side**: usually 60-70%.
- **10-3**: usually 95-99%, especially if the leader is still on a favorable side.
- **11-5**: usually 97-99% for the leader unless the trailing team is moving to a very strong side with pistol pending.
- **0-7 while defending on a map where defense should score**: opponent usually 94-98%.
- **12-x**: leader usually 98-99%+, but mention overtime path if the economy is broken.

Do not overfit old all-time stats. Prefer recent maps from the same roster and current patch when they are available. If only all-time data is available, say that the estimate is less precise.

## Live Update Rules

- If the user says "current 9-8" or similar, update from the last verified full-context analysis without redoing all research only when the match, map, sides, veto, and roster context are unchanged.
- Refresh sources when the user provides a new link, a new map starts, or the current score conflicts with the last known state.
- If VLR and Liquipedia conflict, usually prefer VLR for live score/side and Liquipedia for tournament structure/veto. Prefer official stream/official VALORANT Esports for final score if available.
- If public sources lag behind the user-provided score, phrase it as: "按你给的实时比分..." and base the probability on that score.

## Output Shape

For live-score prompts, keep the answer tight but include the full-analysis signal:

1. State verified context: map, score, side, map pick, series score.
2. Summarize historical baseline: recent form, map pool, and head-to-head/common-opponent context.
3. Summarize tactical and player matchup: style fit, key player duels, and role pressure points.
4. Give current map probabilities.
5. Give series probabilities if relevant.
6. Explain 2-4 decisive reasons and any missing-data caveats.
7. Give swing thresholds for the next 1-3 rounds.
8. Link sources used.

Example:

```markdown
按你给的实时比分：图一 Breeze，NRG 11-5 KC，NRG 进攻。

当前图一胜率：
- NRG：98%
- KC：2%

整场 BO3：
- NRG：86%
- KC：14%

关键原因：Breeze 是 NRG 选图，NRG 进攻已经拿到 11 分；KC 防守端被打穿。第二图是 KC 的 Fracture，所以系列赛不能直接给 NRG 95%+。

分水岭：NRG 到 12-5 基本锁图；KC 追到 11-8 才有真实压力。
```

## Mandatory Research Checklist

Before giving a judgment, attempt to gather and reason from every item below:

- Recent 5 matches for both teams.
- Current roster and role changes.
- Map pool: win rate, map count, recent results, attack/defense round win rates.
- Map veto logic: bans, picks, decider, comfort maps.
- Team matchup: how each team's pace, defaults, executes, retakes, and post-plants line up against the opponent.
- Player form: ACS/R2.0, ADR, KAST, FK/FD, duelist first contact, controller/sentinel survival.
- Player matchup: key role-on-role pressure points, especially duelists, initiators, controllers, and sentinel/lurk roles.
- Style: fast exec vs default-heavy, post-plant conversion, retake quality, clutch frequency, economy vulnerability.
- Event context: elimination/qualification pressure, BO3/BO5, upper/lower bracket, patch.

## Common Pitfalls

- Do not treat 5-7 as equal across sides; 5 defense rounds on Haven is very different from 5 attack rounds.
- Do not use only series odds after a map has started; live score dominates.
- Do not call a series over because map one is nearly over if the opponent's strong pick is map two.
- Do not cite exact live data without naming the source and refresh time when the user needs precision.
- Do not invent player stats if live pages have not populated them yet.
