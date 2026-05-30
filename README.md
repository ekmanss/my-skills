# My Codex Skills

Personal Codex skills, organized by domain.

## Layout

```text
skills/
  data/
    polymarket-address-activity/
```

- `skills/data/`: data export, API collection, market research, and analytics workflows.

## Skills

| Skill | Category | Purpose |
|---|---|---|
| `polymarket-address-activity` | `data` | Export complete Polymarket address activity for a time range and enrich trades with Gamma market settlement results. |

## Install

Copy a skill folder into `~/.codex/skills`:

```bash
mkdir -p ~/.codex/skills
cp -R skills/data/polymarket-address-activity ~/.codex/skills/
```

After copying, invoke it as `$polymarket-address-activity`.
