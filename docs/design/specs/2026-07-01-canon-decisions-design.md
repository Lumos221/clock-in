# Canonical Answers v2 — key decisions in CANON

**Date:** 2026-07-01
**Status:** approved design (pre-implementation)
**Plugin:** clock-in (founder-mode orchestration)
**Extends:** `2026-06-30-canonical-answers-design.md` (CANON v1, files-only — shipped)

---

## 1 · Problem

CANON v1 mechanized SoT's hand-maintained **"Canonical files"** section into a read-first, machine-maintained registry. But SoT still carries a *second* hand-maintained index — **"Key decisions"** (SubmitToday: "Decisions (仍在塑形项目的几条)") — a curated list of the in-force important decisions, each a one-line gist + a pointer to its `DECISIONS.md` entry. Real-file evidence shows it **rots the same way** the canonical-files list did:

- **Stale gists** — nothing forces an update when a decision shifts.
- **Superseded ones linger** — a reversed decision's gist stays because removal is manual.
- **Ambiguous pointers** — "→ DECISIONS.md 2026-06-30" when five decisions share that date; grep-by-date lands on the wrong entry.
- **Buried** under SoT's large "Now" block.

The user already invented the right structure by hand ("Boss 2026-06-29, Option A — GIST in SoT, WHY in DECISIONS.md"); it just isn't mechanical. Meanwhile `DECISIONS.md` is a **large on-demand log** (every decision + full *why*), **not read-first** — so a binding decision settled long ago never enters a dept's startup view, and the dept acts on pre-decision memory (the same daily bug CANON v1 fixed for files).

## 2 · Solution in one line

Extend CANON from "canonical files" to **"current binding answers = files + key in-force decisions."** A key decision earns a CANON row whose pointer is the literal `DECISIONS`; canon **greps** `DECISIONS.md` for the decision's tag and **mirrors its headline** as the gist. This mechanizes the "Key decisions" section exactly as v1 did "Canonical files."

## 3 · Goals / non-goals

**Goals**
- Key in-force binding decisions become read-first (in CANON), registered mechanically (no CEO relay, no hand-maintained gist).
- Only **key** decisions are indexed (deliberate register); the full `DECISIONS.md` log is untouched and un-indexed.
- The gist is **mirrored** from the `DECISIONS.md` headline (authored once), so it cannot drift.
- Superseded decisions drop off the read-first index automatically; dependents are flagged on change.
- SoT drops **both** "Key decisions" and "Canonical files" → one pointer to CANON.

**Non-goals (parked — by agreement)**
- The `SoT.md` "Now" status-block bloat (separate status-discipline problem — still parked).
- The platform task system / `TaskBoard.md` / task hooks — untouched.
- Indexing *all* decisions, or restructuring `DECISIONS.md`'s content — out of scope (it stays the full why-log).

## 4 · Concept

A CANON row is now a **binding answer** whose pointer resolves to either:
- a **file** (owning dept's canonical file) — pointer-only, exactly as v1; or
- a **decision** — the literal pointer `DECISIONS`, resolved by grepping `docs/DECISIONS.md` for the entry tagged with the row's topic-key; its headline is mirrored as the gist.

"Key" = a deliberate `@CANON` register (the "this decision binds other depts" signal). Tactical / within-one-dept decisions stay log-only, no row. This bounds CANON to ~10–15 binding answers.

## 5 · `docs/CANON.md` v2 layout

Storage stays **one table** (unchanged columns — round-trips through the v1 parser). A **read-only mirrored section** for decisions is regenerated on every render and ignored by the loader (it parses only the `## Registry` table). Example:

```markdown
# <项目> · CANON — canonical answers (read-first · machine-maintained · do not hand-edit)

> …guidance…

## ⚠ Needs re-check
- `pricing-tier` → Marketing (updated 2026-07-01)

## Registry
| topic | dept | file | version | updated | affects | needs-recheck |
|---|---|---|---|---|---|---|
| pricing-tier | Fin | docs/财务/pricing-tier.md | a7643d1 | 2026-07-01 | Marketing | Marketing |
| monetization-model | Fin | DECISIONS | 2026-06-30 | 2026-07-01 | Marketing | — |

## Key decisions (mirrored from DECISIONS.md · read-only)
- `monetization-model` · Fin — Monetization model: free=earned-credits · paid=v0.2 packs+subs · NO 买断 → `docs/DECISIONS.md`
```

- A **decision row** in the Registry: `file` = `DECISIONS` (the discriminator vs a path), `version` = the tagged entry's date.
- The **Key decisions** section is derived each render; `load_rows` ignores it (only `|` table lines are parsed), so it never affects storage.

## 6 · The `DECISIONS.md` tag + grep resolution

- **Tag the entry.** A key decision's headline carries the topic-key in brackets:
  `## 2026-06-30 · [monetization-model] Monetization model: free=earned-credits · paid=v0.2 packs+subs · NO 买断`
  Only key decisions are tagged; tactical ones stay untagged. ASCII kebab token, decoupled from any filename.
- **Resolve = grep the topmost tag.** canon finds the **first** (topmost = newest, per the 新在上 order) `##`-headline line containing `[<topic-key>]`. Grep-by-token — not a fragile markdown `#anchor`, not a line number, not a colliding date.
- **Mirror.** canon extracts that headline's text (minus the `[token]`) and renders it as the row's gist. If no tagged entry is found, the mirror shows `(no [<topic-key>] entry in DECISIONS.md — tag it)` — fail-visible.

## 7 · Components (changes to the shipped CANON)

All changes are additive to `skills/orchestrate/scripts/canon.py`; the table schema, CLI verbs, launcher, and hook wiring are unchanged.

### 7.1 · `canon.py`
- **`decision_entry(root, topic) -> (date, headline) | (None, None)`** — read `docs/DECISIONS.md`, return the topmost `##` headline containing `[<topic>]`, split into its leading date and the text after the `[token]`.
- **`cmd_set`** — when `file == "DECISIONS"`, stamp `version` = `decision_entry(...)` date (not a git sha); else git sha as today.
- **`render`** — after the Registry table, emit the "## Key decisions (mirrored …)" section: for each row with `file == "DECISIONS"`, resolve + list `- \`<topic>\` · <dept> — <headline> → \`docs/DECISIONS.md\``.
- **`cmd_get`** — for a decision row, print the mirrored headline + `docs/DECISIONS.md`; for a file row, the path as today.
- **Marker parser** — **unchanged**: `@CANON[Fin] monetization-model → DECISIONS (affects: Marketing)` already parses to `file="DECISIONS"`. (Optional explicit form `→ DECISIONS:<key>` may override the grep token; default token = topic.)
- **`load_rows` / `save_rows`** — unchanged; the loader already parses only `|` table lines, so the mirrored section is ignored.

### 7.2 · Docs / templates
- `templates/DECISIONS.md` — document the `[topic-key]` tag convention for key decisions (one line + example); note only key/binding decisions get tagged.
- `templates/department.md` — extend the "Cross-domain facts" section: a key binding **decision** is registered with `@CANON[<handle>] <topic> → DECISIONS (affects: …)` once its `DECISIONS.md` entry is tagged `[<topic>]`.
- `reference/canon.md` — add a "Decisions" subsection (tag → grep → mirror; register/supersede).
- `templates/SoT.md` — **delete** the "Key decisions" section too (v1 already replaced "Canonical files"); SoT keeps Goal + Now + Spec/Open-work/History pointers.
- `reference/departments.md` — one line noting binding decisions also earn CANON rows (pointer `DECISIONS`).

## 8 · Behaviours

- **Register:** CEO/owning dept logs the tagged entry in `DECISIONS.md`, then ends the turn with `@CANON[<dept>] <topic> → DECISIONS (affects: …)`. The Stop hook writes the row; `version` = the entry date.
- **Mirror:** every render resolves each decision row's headline live from `DECISIONS.md`, so the read-first gist is always current even if the headline is edited.
- **Supersede:** log a **new** `[<topic>]` entry on top + re-emit the marker. canon sees the topmost tag's date differ → re-points (new `version`) + writes `affects` into `needs-recheck`. The old entry remains in the log as history; the read-first index shows only the newest.
- **Handoff:** identical to v1 — dependents appear under "⚠ Needs re-check"; they `@CANON-ACK[<dept>] <topic>`.
- **Lookup:** `orchestrate-canon get <topic>` → mirrored headline + `docs/DECISIONS.md`.
- **Known edge:** two supersessions of the same topic on the **same date** → same `version` → `needs-recheck` not re-flagged (rare; the mirrored gist still updates live). Mirrors the v1 file edge (uncommitted same-sha change).

## 9 · What stays the same / out of scope

- CANON's table schema, CLI verbs, `orchestrate-canon` launcher, and the `stop_canon.py` hook are unchanged — this is purely additive logic in `canon.py` + docs.
- Boss Board, the task system/`TaskBoard.md`, and `DECISIONS.md`'s content/length are untouched.
- SoT "Now" bloat remains parked.

## 10 · Verification

- **Register a decision:** tag `## 2026-06-30 · [monetization-model] …` in `DECISIONS.md`, emit `@CANON[Fin] monetization-model → DECISIONS (affects: Marketing)` → a row appears with `file=DECISIONS`, `version=2026-06-30`, and the "Key decisions" section mirrors the headline.
- **Grep resolution / collision:** two entries share `2026-06-30`; only the one tagged `[monetization-model]` is mirrored; adding a **newer** `[monetization-model]` entry on top switches the mirror to it.
- **Supersede + handoff:** newer tagged entry + re-emit → `version` bumps, `Marketing` lands in `needs-recheck`; `@CANON-ACK[Marketing] monetization-model` clears it.
- **Lookup:** `get monetization-model` prints the mirrored headline + `docs/DECISIONS.md`.
- **Round-trip:** save→load preserves the decision row (`file=DECISIONS`) and ignores the mirrored section.
- **Files untouched:** file rows still resolve to paths; the v1 file tests still pass; Boss Board + task files unchanged.
- **Fail-visible:** a row whose `[topic]` tag is missing from `DECISIONS.md` renders `(no [topic] entry …)` rather than crashing.
