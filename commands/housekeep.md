---
description: Housekeeping — archive stale marked-shot/mockup artefacts (reference-safe, never deletes), sweep plugin residue; prune old archives on the Boss's explicit word.
---

Visual working artefacts (the Boss's marked screenshots, dept-rendered mockups) retire mechanically once their round ships. Archiving is **reference-safe** (anything named on an Active card, an open Boss-Board ask, `CANON.md` or the SoT is never touched) and **reversible** (files move to `<dir>/archive/YYYY-MM/`, nothing is deleted). Run the matching command from `$ARGUMENTS`:

- **no args** → report what's stale and unreferenced, then archive it (safe by construction):
  `orchestrate-housekeep scan` · then `orchestrate-housekeep run`
- **`scan`** → report only, touch nothing.
- **the Boss named or implied a folder** ("clean up the renders folder", a path in `$ARGUMENTS`) → resolve it to the actual project dir and pass it through — ad-hoc, no config needed:
  `orchestrate-housekeep run --path <dir> [--days <N>]`
- **`prune <days>`** → DELETE archived files older than `<days>` — destructive, so run it only when the Boss asked for the prune in their own words:
  `orchestrate-housekeep prune --days <days>`

Which folders it watches standing: `orchestrate.json` → `"housekeeping": [{"path": "docs/mockups", "days": 14}]`; without the key it defaults to `docs/mockups` at 14 days when that dir exists. A session-start nudge fires when candidates exist and no run happened for a week.

**First run in a project with no `housekeeping` config and no `docs/mockups`:** do the one-time discovery yourself — look for dirs that accumulate visual/working artefacts (mockups, screenshots, renders, exports; image-heavy, dated filenames), propose the entries to the Boss in one line, and on their OK write `"housekeeping": [...]` into `.claude/orchestrate.json`, then run. One turn of judgment; every later run and nudge is pure machine.

**When the script prints a `hint: possible new artefact dir(s)` line** (a mechanical detector spotted an unconfigured dir crossing the artefact-file threshold): judge it — working artefacts get proposed to the Boss as a new `housekeeping` entry (write on their OK); product assets (logos, README images, app resources) get left alone, and if the hint keeps naming the same asset dir, tell the Boss it may deserve an `assets`-style name the detector skips.

$ARGUMENTS
