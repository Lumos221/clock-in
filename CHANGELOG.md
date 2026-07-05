# Changelog

All notable changes to **clock-in** are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com); this project uses [semantic versioning](https://semver.org)
(`0.x` = pre-1.0, still evolving).

## [0.5.0] — 2026-07-05
### Added
- **Token-saving two-stage execution.** A 部门 now runs its **head** (the teammate/pane) on **opus**
  — plan + precise per-piece specs + review — and delegates the *typing* to cheap **staff** (one-shot
  subagents it spawns; `sonnet` default, `haiku` **only when a deterministic script could do the
  piece** — and a bounced `haiku` piece is redone on `sonnet`, never retried). Most output tokens move
  to cheap tiers while opus stays the thin planning/review layer. Smart model plans, cheap model
  implements.
- **`hooks/stop_refute_tally.py`** — auto-tallies the 审查 ledger (`docs/reviews/*.refute` / `*.fail`)
  each turn and raises **one** Boss-Board item when a documented `orchestrate.json` threshold is first
  crossed (flag-once via a sentinel). `orchestrate.json` stays thresholds-only; the marker files stay
  the ledger — no counter to drift.
- Hook tests: `hooks/test_review_gate.py` (incl. a worktree-shadow case) · `hooks/test_refute_tally.py`.
### Changed
- **`reference/model-routing.md` rewritten** (SSOT): the head/staff split; the only per-spawn model
  decision is a head choosing each staff spawn's tier; standing roles (部门 heads · 审查官 · experts)
  are opus, pinned in frontmatter; a dated, refreshable model menu (alias-first, so a stale price never
  breaks routing); `fable` documented as **non-routable** (a Boss hand-switch only).
- **Corrected L2 flow.** The **部门 invokes the 审查官 itself**; a FAIL bounces straight back to the
  dept (CEO uninvolved); a PASS goes up, and the **CEO** makes the final merge call and owns
  `TaskUpdate`. The Auditor now writes only the review marker + verdict — it never mutates task state.
  Fixes a subagent-completes-the-CEO's-task bug and the duplicated report/ping. `SKILL.md`
  §2.5/§2.6/§8 · `templates/auditor.md` · `templates/department.md`.
- **CEO orchestrates only** — removed the "CEO may *suggest* a method" carve-out from `SKILL.md`
  §0/§7 and `department.md`; craft is wholly dept-owned (the CEO and every dept head are both opus, so
  there's no craft asymmetry to justify it).
- `templates/department.md` frontmatter now pins `model: opus`.
### Fixed
- **Review-marker anchor is worktree-invariant.** `hooks/pretool_review_gate.py` and the 审查官 resolve
  the project root via `git rev-parse --git-common-dir` → its parent (the main worktree), so a `.pass`
  written from a linked worktree under `.claude/worktrees/` lands where the completion-gate hook (in
  the main tree) looks. Previously the marker could be written where the check never found it —
  silently blocking completion — the moment `orchestrate.json` became git-tracked. Falls back to the
  ancestor walk for non-git projects.

## [0.4.2] — 2026-07-02
### Changed
- **Spawn-kind hard rules on both sides of the org** (from a live incident: a dept passed
  `name:` when spawning its research staff, creating *orphaned* pane-agents — live,
  unmanaged, on nobody's roster). Dept briefs (`templates/department.md`) now prohibit
  `name:` outright — staff/experts are one-shot; `SKILL.md` §8 requires `name:<handle>`
  on every 部门 spawn and bans `name:` on one-shots (staff · expert · 审查官 · research).
### Fixed
- §8's orphan description claimed a non-lead's named spawn gets "no pane" — orphans can
  open panes; they're unmanaged, not invisible.

## [0.4.1] — 2026-07-02
### Changed
- **`reference/model-routing.md`** is now the single source of truth for per-role model
  routing; `SKILL.md` / `departments.md` / the templates point at it instead of restating
  the policy.
- **Lean pass** over `SKILL.md`, `departments.md`, the dept/HR templates, and the plugin
  description — rules stated once (no-relay, ≤6 concurrent, non-overlapping files, own-domain
  bar, bounce counting), L1/L2 bar definitions and marker mechanics deferred to the 审查官
  contract, `plugin.json` description cut to one line.
### Fixed
- **`orchestrate` now actually registers as a skill.** Its frontmatter `description`
  spanned multiple raw lines — invalid YAML, so the skill (and its 「开始上班」 trigger)
  was silently absent from the skill registry in every prior version. Folded to a
  single line.
- **Boss Board opens the panel once**, on server start — later asks refresh the
  already-open window instead of popping a duplicate (explicit `/board` still opens on demand).

## [0.4.0] — 2026-07-01
### Added
- **CANON now indexes key in-force _decisions_, not just files.** A registry row can
  point at a `DECISIONS.md` entry (pointer = the literal `DECISIONS`), resolved by
  grepping the **topmost** `[topic-key]` tag — no line numbers, no fragile `#anchors`.
- The decision entry's headline is **mirrored** into `CANON.md` as the gist (authored
  once in `DECISIONS.md`, so it can't drift). Register/supersede with
  `@CANON[<dept>] <topic> → DECISIONS (affects: …)`.
- `DECISIONS.md` `[topic-key]` tag convention; `orchestrate-canon get <topic>` prints
  the mirrored headline + the log pointer.
### Changed
- `SoT.md`'s hand-maintained **"Key decisions"** section folds into CANON (now a single
  read-first index of files **and** decisions).

## [0.3.0] — 2026-07-01
### Added
- **Canonical Answers registry** — machine-maintained `docs/CANON.md`, the read-first
  index of the current canonical **file** per answered question. `orchestrate-canon` CLI
  (`set`/`get`/`list`/`ack`/`supersede`/`archive`) + `bin` launcher.
- `@CANON[<dept>] <topic> → <path>` / `@CANON-ACK` markers captured by a fail-open
  `Stop`/`SubagentStop` hook — registered from the dept's own message, so the pointer
  can't be lost in a CEO relay.
- Cross-domain handoff (`affects → needs-recheck → ack`) and a stable-name +
  archive-on-supersede file convention.
### Changed
- `SoT.md`'s hand-maintained "Canonical files" section replaced by a pointer to CANON.

## [0.2.0] — 2026-06-30
### Added
- **Boss Board** — a live "Needs-You" panel aggregating every pending ask for the Boss
  across panes. `/board` command + `orchestrate-board` CLI + a singleton localhost,
  self-refreshing panel (Python stdlib only, idle self-reap).
- `@BOSS[<dept>]:` / `@BOSS-DONE` markers captured by a `Stop`/`SubagentStop` hook;
  idempotent add (anti-spam), dept-prefixed ids, targeted reads.

## [0.1.0] — 2026-06-23
### Added
- Initial founder-mode orchestration: a multi-department Agent-Teams squad (CEO ·
  departments · 董事会) running the `规划→审查→派发→执行→产出审查→汇总→报告` spine, a hard
  **2-layer 审查 gate**, the **红线** (law-offense) boundary owned by 法务部, and
  independent **人事部** oversight.
- Skills: `orchestrate` + `recruit`. Hooks: review-gate, accident-guard, backlog-log,
  session-start. Rendered morning brief (`orchestrate-brief`). Artifact model:
  `SoT.md` · `TaskBoard.md` · `BACKLOG.md` · `DECISIONS.md`.

[0.4.2]: https://github.com/Lumos221/clock-in/releases/tag/v0.4.2
[0.4.1]: https://github.com/Lumos221/clock-in/releases/tag/v0.4.1
[0.4.0]: https://github.com/Lumos221/clock-in/releases/tag/v0.4.0
[0.3.0]: https://github.com/Lumos221/clock-in/releases/tag/v0.3.0
[0.2.0]: https://github.com/Lumos221/clock-in/releases/tag/v0.2.0
[0.1.0]: https://github.com/Lumos221/clock-in/releases/tag/v0.1.0
