# My Codex Skills

Personal Codex skills, organized by domain.

## Layout

```text
skills/
  strategy-replication-auditor/
  data/
    polymarket-address-activity/
```

- `skills/data/`: data export, API collection, market research, and analytics workflows.

## Skills

| Skill | Category | Purpose |
|---|---|---|
| `strategy-replication-auditor` | `quant review` | Audit pixel-level strategy replication docs against independent-team no-context reproducibility and score them out of 100. |
| `polymarket-address-activity` | `data` | Export complete Polymarket address activity for a time range and enrich trades with Gamma market settlement results. |

## Install

Copy a skill folder into `~/.codex/skills`:

```bash
mkdir -p ~/.codex/skills
cp -R skills/strategy-replication-auditor ~/.codex/skills/
cp -R skills/data/polymarket-address-activity ~/.codex/skills/
```

After copying, invoke skills by name, such as `$strategy-replication-auditor` or `$polymarket-address-activity`.
