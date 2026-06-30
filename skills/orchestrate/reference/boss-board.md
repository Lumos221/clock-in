# Boss Board — `scripts/board.py`

> A live **"Needs-You" panel**: every pending ask *for the Boss*, across all panes, in one always-open window. Separate from `TaskBoard.md` (dept work) — it does not touch the task system or its gates. Design: `docs/superpowers/specs/2026-06-30-boss-board-design.md`.

## What it is
The Boss works solo and multi-pane; the one message that needs the Boss gets buried. The Boss Board surfaces those asks into a single self-refreshing panel on the Boss's laptop. Mostly mechanical — the model writes a one-line marker; a Stop hook does the panel work.

## How an ask is raised / resolved
- **A pane needs the Boss:** end the turn with `@BOSS[<dept>]: <one-line ask>`. The `Stop`/`SubagentStop` hook (`hooks/stop_boss_board.py`) captures it → `orchestrate-board add`. The panel opens (or refreshes) on the Boss's screen.
- **The Boss answered, pane moves on:** end with `@BOSS-DONE[<dept>]` (its one open ask) or `@BOSS-DONE[<id>]` (a specific one).
- **The Boss's own items:** the `/board` command — `/board <text>` adds a discuss item; bare `/board` opens the panel; `/board park <id>` / `done <id>` / `reopen <id>` change status.

## States & ownership
`open → resolved`, plus `parked`. Panes drive open→resolved; the **Boss** owns park/reopen. The panel is read-only display.

## Anti-spam & token-saving
- `add` is **idempotent per (dept, normalised text)** while open — a pane re-flagging every idle turn never piles up duplicates.
- Ids are dept-prefixed (`QA-1`); `orchestrate-board get <id>` and `list --dept <dept>` read only what's needed, so a pane never parses the whole board.

## The panel
A singleton localhost server (port derived from the project path; pidfile = "is it up"). The page polls every ~1.5 s and re-renders. It **self-reaps** when there are no open items and it hasn't been polled for ~10 min; the next `add` respawns it. Stdlib only; degrades to no-op if a browser can't open.

## CLI (the launcher is `orchestrate-board`, on PATH)
`add --dept <h> --kind <needs|discuss> --text "…"` · `done <id>` · `resolve --dept <h>` · `park <id>` · `reopen <id>` · `get <id>` · `list [--dept <h>]` · `open` · `stop`.
