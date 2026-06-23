# Morning brief — `scripts/brief.py`

> Meetings themselves — 例会 / 董事会 / decisions → `DECISIONS.md` — are defined in `SKILL.md` §4. This page is only the *rendered* brief.

For an overnight run: the CEO **fills a few fields** (it authors the content) and the script renders a clean PDF/PNG, **auto-opened** when the Boss asks. The runnable `brief.py` command is in `SKILL.md` §4; the input it takes:

```json
{ "shipped": ["v0.1 live on Vercel"],
  "queued": ["China-access check"],
  "needs_boss": ["pick Postgres vs SQLite"],
  "note": "all gates green" }
```

Fields (all optional): `project`, `shipped[]`, `queued[]`, `needs_boss[]`, `note`. The script only formats + opens — the CEO writes the content.