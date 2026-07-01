# Changelog

All notable changes to **clock-in** are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com); this project uses [semantic versioning](https://semver.org)
(`0.x` = pre-1.0, still evolving).

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
### Fixed
- **Boss Board opens the panel once**, on server start — later asks refresh the
  already-open window instead of popping a duplicate (explicit `/board` still opens on demand).

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

[0.4.0]: https://github.com/Lumos221/clock-in/releases/tag/v0.4.0
[0.3.0]: https://github.com/Lumos221/clock-in/releases/tag/v0.3.0
[0.2.0]: https://github.com/Lumos221/clock-in/releases/tag/v0.2.0
[0.1.0]: https://github.com/Lumos221/clock-in/releases/tag/v0.1.0
