# Boss Board — `scripts/board.py`

> A live **decision panel for the Boss**: every pending ask on top — each linked to its task for context — with a read-only *current iteration* kanban (from `TaskBoard.md`) underneath. It never touches the task system or its gates. Design: `docs/design/specs/2026-06-30-boss-board-design.md`.

## What it is
The Boss works solo and multi-pane; the one message that needs the Boss gets buried — and a bare "need input" line isn't decidable anyway. The panel fixes both: asks are pinned in the upper **Needs you** section with the ask's task card shown as a chip (id · name · status), and the lower section renders the iteration board (Todo / In progress / Done — Done includes the hook-maintained *Recently shipped* tail), so the Boss can locate the task that needs them and glance at the related ones. Mostly mechanical — the model writes a one-line marker; a Stop hook does the panel work; the server re-reads `TaskBoard.md` per poll.

## How an ask is raised / resolved
- **A pane needs the Boss:** end the turn with `@BOSS[<dept>#<task_id>]: <ask>` — the `#<task_id>` (the platform id on the card) links the ask to its task on the panel; omit it only for non-task asks. **The ask must be decidable from the board alone**: question · options · recommendation, 1–2 lines. The `Stop`/`SubagentStop` hook (`hooks/stop_boss_board.py`) captures it. An unlinked ask falls back to showing the dept's in-flight cards.
- **The Boss answered, pane moves on:** end with `@BOSS-DONE[<dept>]` (its one open ask) or `@BOSS-DONE[<id>]` (a specific one). Append the outcome — `@BOSS-DONE[<id>]: <one-line outcome>` — and the Answered row collapses to that line instead of the ask's opening words (the full ask stays one click behind). Ambiguous dept-level DONE with several asks open → a discuss item surfaces the ambiguity instead of silently resolving nothing.
- **A revised ask supersedes an old one only by explicit close.** The board never auto-supersedes: dedup is exact-text, so a reworded re-raise is a NEW entry and the stale one stays in Needs-you. The pane must put `@BOSS-DONE[<old-id>]` in the same turn as the new `@BOSS[…]`; fallback, the Boss runs `/board done <old-id>`.
- **The Boss's own items:** the `/board` command — `/board <text>` adds a discuss item; bare `/board` opens the panel; `/board park <id>` / `done <id>` / `reopen <id>` change status.
- **Direction banner:** `orchestrate-board direction --text "…"` pins the product's standing direction (a launch checklist, the current battle line) in its own section above *On your desk*; `--clear` removes it. One slot, whole-text replace, set on the Boss's word — rendering is mechanical, so it costs nothing per poll.

## States & ownership
`open → resolved`, plus `parked`. Panes drive open→resolved; the **Boss** owns park/reopen. The panel is read-only display.

## Anti-spam & token-saving
- `add` is **idempotent per (dept, normalised text)** while open — a pane re-flagging every idle turn never piles up duplicates.
- Ids are dept-prefixed (`QA-1`); `orchestrate-board get <id>` and `list --dept <dept>` read only what's needed, so a pane never parses the whole board.

## The panel
A singleton localhost server (port derived from the project path; pidfile = "is it up"). The page polls every ~1.5 s and re-renders. It **self-reaps** when there are no open items and it hasn't been polled for ~10 min; the next `add` respawns it. A server the record no longer names (version stamp or port moved on) **exits within ~30 s even while polled** — an open tab otherwise keeps a stale one immortal; and at respawn the derived port is **reclaimed** from any lost-generation zombie that still answers as this project's board, so open tabs never orphan onto old code. Stdlib only; degrades to no-op if a browser can't open.

## CLI (the launcher is `orchestrate-board`, on PATH)
`add --dept <h> --kind <needs|discuss> --text "…"` · `done <id> [--sum "…"]` · `resolve --dept <h>` · `park <id>` · `reopen <id>` · `get <id>` · `list [--dept <h>]` · `direction --text "…" | --clear` · `open` · `stop`.
