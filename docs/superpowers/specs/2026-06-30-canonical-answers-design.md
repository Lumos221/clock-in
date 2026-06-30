# Canonical Answers — a mechanical cross-domain registry + file convention

**Date:** 2026-06-30
**Status:** approved design (pre-implementation)
**Plugin:** clock-in (founder-mode orchestration)
**Related:** Boss Board spec `2026-06-30-boss-board-design.md` (same store+CLI+marker/hook spine)

---

## 1 · Problem

Founder-mode already has a "canonical file" concept ([departments.md:43-44](../../../skills/orchestrate/reference/departments.md): a dept proposes its canonical output → the CEO gates it → the CEO points `SoT.md` at it; `SoT.md` has a "Canonical files" section). But **every step is soft prose** — the dept must remember to propose, the CEO must remember to gate *and* hand-write the pointer, and `SoT.md` must stay lean. In real use the chain breaks:

- **Cross-domain handoff loss (the motivating bug):** Finance confirmed a pricing tier and logged it in `docs/财务/`. Days later Marketing needed it; the pointer had been lost in the CEO relay, so Marketing browsed `docs/财务/`, guessed the current file by filename, and **picked the wrong (stale) version**.
- **Folder chaos:** dept work folders accrete inconsistently-named files (`pricing-v0.1-核算.md`, `pricing-v0.2-核算.md`, `命名与品牌-2026-06-17.md`, `naming-exploration.md` …) with no way to tell current from stale at a glance.
- **`SoT.md` bloat:** the hand-maintained "Canonical files" + "Now" sections have grown into a wall, burying the pointers that do exist.

Root cause: the mechanism **relies on model behaviour**, not structure.

## 2 · Solution in one line

A **mechanically-maintained canonical-answer registry** (`docs/CANON.md`) plus a **stable-name + archive-on-supersede file convention** — both kept correct by a CLI/hook, not by prompts — so the current answer to any cross-domain question is always registered, discoverable by topic (never by guessing filenames), and dependents are flagged when it changes.

## 3 · Goals / non-goals

**Goals**
- The current canonical answer to any answered question is registered **mechanically** (no CEO relay in the critical path).
- Any dept finds another domain's current answer **by topic**, and reads the exact file the registry names — never browses a peer's folder and guesses.
- When a canonical answer **changes**, its dependent depts are flagged to re-check.
- A dept folder is legible at a glance: bare names are current, superseded files are quarantined.
- `SoT.md` stops hand-maintaining canonical pointers (slims it, removes a rot source).

**Non-goals (out of scope — revisit after this lands)**
- The `SoT.md` "Now" status-block bloat (a separate status-discipline problem).
- **`DECISIONS.md` integration** — letting a registry pointer reference a `DECISIONS.md` entry (so a binding *decision* with no document becomes read-first), and any decision-propagation mechanism. Discussed and deliberately **parked for a follow-up round** (the DECISIONS mechanism needs further discussion). This v1 indexes canonical **files** only; the `file` column holds a dept file path (no `source`/decision-ref rename).
- The platform task system / `TaskBoard.md` / the existing task hooks — untouched.
- Auto-detecting that a dept read a peer's folder (not enforceable; handled by rule + the registry being the easy path).

## 4 · The registry — `docs/CANON.md`

**One file.** A committed, **machine-maintained markdown table** — `canon.py` parses and rewrites it (the same idea as `log.py`/`BACKLOG.md`, but with row *updates*, not only appends). Depts **read** it (it joins their read-first set); they never hand-edit it (it's a CEO/system-owned orchestration file, like `SoT.md`). It is **markdown, not JSON**, precisely because depts read it as a document — no parsing, git-diff-friendly, greppable. There is **no `canon.json`**; the handoff state fits as a table column, so nothing relational justifies a separate store.

**Entry = pointer-only** (no inline answer summary — an inline summary becomes a second source of truth that drifts, and models pad it until the registry bloats like the files did):

```markdown
# <项目> · CANON — canonical answers (read-first · machine-maintained · do not hand-edit)

> Each row = the current authoritative file for one answered question.
> Owning dept registers via `@CANON[..]`; the CEO may correct via `orchestrate-canon`.
> To use a cross-domain fact: `orchestrate-canon get <topic>` → read the named file. NEVER browse a peer's folder.

## ⚠ Needs re-check
<rolling — topics whose answer changed and dependents haven't ack'd>
- `pricing-tier` → Marketing (changed 2026-07-02)

## Registry
| topic | dept | file | version | updated | affects | needs-recheck |
|---|---|---|---|---|---|---|
| pricing-tier | Fin | docs/财务/pricing-tier.md | a7643d1 | 2026-06-30 | Marketing | — |
```

- `topic` — a short **ASCII kebab key** (the lookup handle; **decoupled** from the filename, which may stay Chinese).
- `file` — explicit path to the current canonical file.
- `version` — the file's last-commit short git sha (stamped by the script); `—` if uncommitted.
- `affects` — comma-separated dept handles that depend on this answer (`—` if none).
- `needs-recheck` — comma-separated dependent depts who must re-check after the latest change (`—` if clear). Mirrored into the top "⚠ Needs re-check" block on render for visibility.

## 5 · Components

All new code is self-contained; edits to existing files are small. Mirrors the Boss Board layout.

### 5.1 · `skills/orchestrate/scripts/canon.py` — CLI + `CANON.md` parser/writer

Stdlib only. Subcommands:

| Command | Effect |
|---|---|
| `set --dept <h> --topic <k> --file <path> [--affects a,b]` | Register/re-point. Change-detection (§6.1): on a real change, archive the old path if different (§6.4), bump `version`+`updated`, set `needs-recheck` = `affects`. Idempotent if nothing changed. |
| `get <topic>` | Print the row's current file path (targeted read — no full-table dump). |
| `list [--dept <h>]` | Print all rows, or one dept's. |
| `ack <topic> --dept <h>` | Remove `<h>` from that row's `needs-recheck`. |
| `supersede <topic>` | Archive the current file (§6.4) and remove the row — answer retired without replacement (git retains history; presence of a row = a current answer). |
| `archive <path>` | Move one file into its dept's `archive/` (the mechanical primitive for cleanup/migration). |

The table parse/rewrite lives here so the format has one source of truth. `version` is stamped via `git log -1 --format=%h -- <file>` (fallback `git rev-parse --short HEAD`, then `—`).

### 5.2 · `bin/orchestrate-canon` — PATH launcher

Thin bash launcher mirroring `bin/orchestrate-board` / `bin/orchestrate-brief`: resolves `canon.py` by its own location and `exec`s it. Callable by bare name from any pane.

### 5.3 · `hooks/stop_canon.py` + `hooks.json` — the mechanical register/ack

A new **Stop / SubagentStop** hook (own file, same pattern + constraints as `stop_boss_board.py`: fail-open, acts only under an active `.claude/orchestrate.json`, reads the last assistant message). It parses the markers and calls `canon.py`:
- `@CANON[<dept>] <topic> → <path> (affects: <a>,<b>)` → `set --dept <dept> --topic <topic> --file <path> --affects a,b`
- `@CANON-ACK[<dept>] <topic>` → `ack <topic> --dept <dept>`

Written from the **dept's own message**, so the CEO relay is out of the critical path — the pointer can no longer be lost. `hooks.json` gains the new hook on `Stop` and `SubagentStop` (alongside `stop_boss_board.py`).

### 5.4 · Docs / templates (small)

- `templates/department.md` — add to the dept brief: (a) read-first now includes `docs/CANON.md`; (b) the rule **"a cross-domain fact → `orchestrate-canon get <topic>` then read the named file; never browse a peer's folder"**; (c) the convention **"when you finalise an answer the project will act on, emit `@CANON[<handle>] <topic> → <path> (affects: …)`; after you've incorporated an upstream change flagged for you, emit `@CANON-ACK[<handle>] <topic>`"**; (d) the **stable-name + `archive/`** file rule (§6.4).
- `reference/departments.md` — replace the prose "How it's set" canonical paragraph with a pointer to the mechanical registry (`reference/canon.md`); keep the *definition* of "canonical".
- `reference/canon.md` — new on-demand reference (full detail; loaded only when needed).
- `SKILL.md` — add a `docs/CANON.md` row to the **Files** table and a one-line note in the relevant section; extend the References line. Add `docs/CANON.md` to the "orchestration files off-limits to dept hand-edits" set (it is read-only to depts; the script writes it).
- `templates/SoT.md` — **replace** the hand-maintained "## Canonical files" list with a single pointer: `## Canonical answers → docs/CANON.md`.

## 6 · Behaviours

### 6.1 · Registration + change-detection (no re-flag spam)

`set` finds the row by `topic`:
- **New topic** → add the row (a row's presence = a current answer); if `affects` given, set `needs-recheck` = `affects` (dependents should incorporate the new answer).
- **Existing topic, real change** → "real change" = the file's stamped `version` differs from the stored one, or the `file` path differs. Then: archive the old path if the path changed (§6.4), update `file`/`version`/`updated`, set `needs-recheck` = union(existing-unacked, `affects`).
- **Existing topic, no change** (same path, same version) → **no-op** (idempotent re-emit doesn't re-spam dependents).

Auto-registers as **current** (no proposed/confirmed gate): the dept's output already passed **L2 审查** before it reported, so it's vetted; the CEO can still re-point/correct via `orchestrate-canon set` if a wrong entry slips in.

### 6.2 · Lookup

`CANON.md` is in every dept's read-first set, so a dept *starts* seeing the current answers. For a precise pull: `orchestrate-canon get <topic>` → the one current path; the dept then reads **that named file** (allowed — it's authoritative-by-registration, not a guess). Browsing a peer's `docs/<dept>/` to choose a file is the banned action.

### 6.3 · Active handoff (affects → needs-recheck → ack)

When `set` makes a real change to a row whose `affects` lists dependents, those dependents are written into `needs-recheck` and surfaced in the top "⚠ Needs re-check" block. A dependent dept sees its handle there when it reads `CANON.md`, re-reads the named file, and clears itself with `@CANON-ACK[<dept>] <topic>` (or `orchestrate-canon ack`). All Python; the flag rides in a file the dept already reads — no extra model cost beyond the one ack line.

### 6.4 · Naming + archive convention

- **Each answered question = one stable, suffix-free file** (`docs/财务/pricing-tier.md`, not `pricing-v0.2-核算.md`). Bare name = always current. The **filename is decoupled** from the ASCII topic-key and may stay Chinese.
- **Updates are in-place:** a dept edits the stable file and commits; git holds prior versions; `version` bumps on the next `set`. No new sibling files accrete.
- **`archive/` quarantines superseded *paths*:** when `set` registers a canonical at a *different* path than the stored one (a genuine rename/restructure, or migration), the script moves the old path into `docs/<dept>/archive/`. So the folder top level is always all-current; `archive/` is obviously old. (With stable in-place names this rarely fires — it's mainly migration and topic restructuring.)
- `archive/` lives inside the dept's own boundary (`docs/<dept>/archive/`), so no cross-boundary writes.

### 6.5 · Migration (adoption — separate from this skill change)

This spec builds the mechanism in the **clock-in skill**. Applying it to an existing messy project (e.g. refcheck) is **adoption**, done in that project: per dept, decide the current file per topic, rename it to a stable name, `orchestrate-canon archive` the stale siblings, and `set` each canonical (or emit `@CANON`). The `archive` verb makes each step mechanical; the reorg itself is CEO-orchestrated and reviewed with the Boss. The plan will include the procedure and the helper verb, but the refcheck reorg is executed in refcheck, not here.

## 7 · What this deliberately does NOT change

- `TaskBoard.md`, the platform task system, `TaskCreate`/`TaskUpdate`, and the two task hooks — untouched.
- The Boss Board — independent; this adds a sibling CLI + Stop hook, not a change to it.
- `SoT.md`'s "Now" block — left as-is for a later pass (out of scope, by agreement).
- Each dept still owns its own `docs/<dept>/`; the registry only *points* across boundaries, it doesn't move ownership.

## 8 · Verification

- **Register via marker:** a message with `@CANON[Fin] pricing-tier → docs/财务/pricing-tier.md (affects: Marketing)` under an active project → a row appears in `CANON.md`.
- **No relay dependency:** the row is written even if no CEO action follows (hook reads the dept's own message).
- **Lookup:** `orchestrate-canon get pricing-tier` prints exactly the current path; `list --dept Fin` prints only Fin's rows.
- **Change → handoff:** re-`set` the same topic at a new version → `Marketing` lands in `needs-recheck` + the "⚠ Needs re-check" block.
- **Ack:** `@CANON-ACK[Marketing] pricing-tier` (or `ack`) clears `Marketing` from `needs-recheck`.
- **Idempotency:** re-emitting the identical `@CANON` (same path, same version) is a no-op — no re-flag.
- **Archive-on-path-change:** `set` to a different path moves the old file into `docs/<dept>/archive/` and re-points the row.
- **Decoupling:** a Chinese-named canonical file (e.g. `红线法律依据.md`) registers under an ASCII topic-key and resolves via `get`.
- **Fail-open hook:** malformed transcript / missing marker / inactive project → no-op, turn uninterrupted.
- **No side effects:** a full run leaves `TaskBoard.md` / `BACKLOG.md` / the Boss Board untouched.
