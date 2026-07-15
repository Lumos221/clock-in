---
description: Housekeeping — archive stale marked-shot/mockup artefacts (reference-safe, never deletes), sweep plugin residue; prune old archives on the Boss's explicit word.
---

Visual working artefacts (the Boss's marked screenshots, dept-rendered mockups) retire mechanically once their round ships. Archiving is **reference-safe** (anything named on an Active card, an open Boss-Board ask, `CANON.md` or the SoT is never touched) and **reversible** (files move to `<dir>/archive/YYYY-MM/`, nothing is deleted). Run the matching command from `$ARGUMENTS`:

- **no args** → report what's stale and unreferenced, then archive it (safe by construction):
  `orchestrate-housekeep scan` · then `orchestrate-housekeep run`
- **`scan`** → report only, touch nothing.
- **`prune <days>`** → DELETE archived files older than `<days>` — destructive, so run it only when the Boss asked for the prune in their own words:
  `orchestrate-housekeep prune --days <days>`

Which folders it watches: `orchestrate.json` → `"housekeeping": [{"path": "docs/mockups", "days": 14}]`; without the key it defaults to `docs/mockups` at 14 days when that dir exists. A session-start nudge fires when candidates exist and no run happened for a week.

$ARGUMENTS
