# Boss Board — a live "Needs-You" panel

**Date:** 2026-06-30
**Status:** approved design (pre-implementation)
**Plugin:** clock-in (founder-mode orchestration)

---

## 1 · Problem

The Boss works solo and heavily multi-pane. Department panes flood with messages,
and the one line that actually needs the Boss's response gets buried — a started
discussion dilutes and is forgotten. There is a rendered CEO→Boss output (the morning
brief) but **nothing that surfaces, in one place, every pending ask *for the Boss*
across all panes**.

## 2 · Solution in one line

A **live, always-open "Needs-You" panel** on the Boss's laptop that aggregates every
pending ask from every pane. Panes raise asks and mark them done themselves (mostly
automatically, near-zero tokens); the Boss owns deferral. One persistent window that
refreshes itself — not a fresh PDF each time.

## 3 · Goals / non-goals

**Goals**
- Surface every "needs the Boss" item from any pane into one panel the Boss can't miss.
- Capture must work *in the moment*, from inside any pane, without the Boss relaying.
- Mostly mechanical / low-token: the model writes one short line of intent; a hook does
  the panel work.
- One persistent, self-refreshing panel ("detect → open if absent → append + refresh
  if present").

**Non-goals (explicitly out of scope for v0)**
- No coupling to `TaskBoard.md`, the platform task system, or the existing task hooks
  (`pretool_review_gate.py`, `posttool_backlog_log.py`). This board does **not** touch
  them. (Whether the dept TaskBoard is even still needed is a separate later discussion.)
- No promote-bridge from a board entry to a dept task card.
- No native Claude-Code task-pane integration.
- **No staleness** detection / no time-pressure flags / no age threshold.
- No click-to-act on the panel (read-only display in v0; clickable actions are a possible
  later add).

## 4 · Concept & lifecycle

One entry = one **ask for the Boss** (or a Boss-raised "discuss" item).

States: `open → resolved`, plus `parked` (Boss-deferred). No other states.

**Who edits status**
- `open` — set by whoever raises it: a pane (via marker/hook) or the Boss.
- `resolved` — driven by the **pane** (it knows when the Boss's answer landed and it moved
  on), via the `@BOSS-DONE` marker → hook, or any manual `done`.
- `parked` / `reopen` — **the Boss's** call only ("not now" / "useless"). The Boss says it;
  it gets parked.

The panel is **read-only**: it displays state; all status changes go through the marker
protocol (§7) or the `/board` command (§6.4), never through clicks.

## 5 · Data model & storage

**Store:** `.claude/boss-board.json` (project-local; survives restart). It is **runtime
state, gitignored** — add `.claude/boss-board.json` to `.gitignore`. It is *not* a product
doc and never lives in `docs/`.

**Entry shape:**

```json
{
  "id": "QA-1",
  "dept": "QA",
  "text": "Postgres or SQLite for the job queue?",
  "kind": "needs",
  "status": "open",
  "created": "2026-06-30T14:03:11",
  "updated": "2026-06-30T14:03:11"
}
```

- `id` — **dept-prefixed + sequential**: `QA-1`, `RnD-2`, `Boss-1`. Each dept's entries
  "start with its own id" (its handle), enabling cheap per-dept filtering and O(1)
  targeted resolve. The sequence is per-dept, monotonic, never reused.
- `kind` — `needs` (a pane needs the Boss) or `discuss` (Boss-raised).
- `dept` — the raising pane's handle (`QA`, `RnD`, …) or `Boss` for Boss-raised items.

**Runtime files (never in the repo):** the server pidfile + chosen port live in a temp
runtime dir keyed by project, e.g. `$TMPDIR/clockin-board-<projecthash>/` containing
`server.pid` and `port`.

## 6 · Components

All new code is self-contained; edits to existing files are minimal (a `.gitignore`
line, one `hooks.json` entry, one line in the dept template, ~2 lines in SKILL.md §4).

### 6.1 · `skills/orchestrate/scripts/board.py` — CLI + server + page

Single self-contained script (stdlib only — `http.server`, `json`, `hashlib`,
`subprocess`, `datetime`; same zero-dependency ethic as `brief.py`). Subcommands:

| Command | Effect |
|---|---|
| `add --dept <h> --kind <needs\|discuss> --text "<one-liner>"` | Append an `open` entry (idempotent — see §8.1); ensure the panel is up + open; print the entry id. |
| `done <id>` | Mark `<id>` `resolved`. |
| `resolve --dept <h>` | Mark that dept's open entry `resolved` (for `@BOSS-DONE[<dept>]`). If the dept has exactly one open entry, resolve it; if it has several, this is a no-op that prints a notice listing them so the caller re-issues with an explicit `done <id>`. |
| `park <id>` / `reopen <id>` | Boss-only status moves. |
| `get <id>` | Print just that one entry (targeted read — §8.2). |
| `list [--dept <h>]` | Print all entries, or only one dept's (targeted read). |
| `open` | Ensure the panel server is up and open the tab (no entry change). |
| `serve` | Internal: run the web server (invoked detached by the script itself). |
| `stop` | Stop the server (also self-reaps when idle — §8.4). |

The HTML+JS page is **embedded as a string** in `board.py` (like `brief.py`'s CSS),
served by the internal server. The page polls `/state.json` every ~1.5 s and re-renders:
open items grouped by dept, parked in a collapsed strip, recently-resolved faded out.

### 6.2 · `bin/orchestrate-board` — PATH launcher

Thin bash launcher mirroring `bin/orchestrate-brief`: resolves `board.py` relative to its
own location and `exec`s `python3 board.py "$@"`. Exposed on PATH by the plugin's `bin/`
dir, so any pane calls it by bare name from any cwd.

### 6.3 · `hooks/stop_boss_board.py` + one `hooks.json` entry — the automatic driver

A new **Stop** (and **SubagentStop**) hook. On stop it reads the last assistant message
from the transcript and scans for markers (§7):
- `@BOSS[<dept>]: <ask>` → `orchestrate-board add --dept <dept> --kind needs --text "<ask>"`
- `@BOSS-DONE[<dept>]` or `@BOSS-DONE[<id>]` → `orchestrate-board resolve --dept <dept>` /
  `done <id>`

Constraints (matching the existing hooks): **fail-open** (any error → allow/no-op), acts
**only under an active `.claude/orchestrate.json` marker** (cwd-based lookup, covers
teammate panes). It only ever *calls the CLI* — all board logic stays in `board.py`.

`hooks.json` gains one `Stop`/`SubagentStop` block pointing at this hook.

### 6.4 · `commands/board.md` — the `/board` slash command (Boss side)

One command file, available in every pane (explicit trigger — never mis-fires like a
fuzzy keyword would). The command instructs the current session to run the matching
`orchestrate-board` subcommand from `$ARGUMENTS`:
- `/board` (bare) → `orchestrate-board open` (just surface the panel).
- `/board <text>` → `orchestrate-board add --dept Boss --kind discuss --text "<text>"`.
- `/board done <id>` / `/board park <id>` / `/board reopen <id>` → the obvious subcommand.

### 6.5 · Docs (minimal)

- `templates/department.md` — **one line** teaching the convention: *"When (and only when)
  you need the Boss, end your turn with `@BOSS[<your-handle>]: <one-line ask>`; once the
  Boss has answered and you've acted, end with `@BOSS-DONE[<your-handle>]`. Raise each ask
  once — repeats are ignored."*
- `reference/boss-board.md` — new on-demand reference (the detail; loaded only when needed,
  same pattern as the other reference pages).
- `SKILL.md` §4 — **~2 lines** next to the morning brief, pointing to `reference/boss-board.md`.

## 7 · Marker protocol

Explicit sigils that cannot fire by accident (no natural-language keyword detection):

- **Raise:** `@BOSS[<dept>]: <one-line ask>` — authored by the pane that needs the Boss,
  *only when it needs the Boss*. One organized line, not a dump. The hook extracts only the
  text after the colon.
- **Resolve:** `@BOSS-DONE[<dept>]` (resolves that dept's open ask when it has exactly one;
  if it has several open, use the specific form) or `@BOSS-DONE[<id>]` (a specific entry).
  Authored by the pane when the Boss's answer has been received and acted on.
- **Boss side:** the `/board` command (§6.4), not a marker.

The model writes one cheap line of *intent*; the hook does all board *mechanics*. The CEO
is not in this loop (keeps it low-token).

## 8 · Key behaviours

### 8.1 · Anti-spam (idempotent add)

A dept waiting on the Boss may re-emit its marker every idle turn. `add` is **idempotent
per (dept, normalised-text)** while an entry is `open`: a repeat is a **no-op** — one open
entry, never a flood. Normalisation = trim + lowercase + collapse whitespace (enough to
absorb trivial rewording; no fuzzy matching). The guarantee is in the CLI, so a misbehaving
dept cannot pile up duplicates regardless of what the template says.

### 8.2 · Targeted reads (token-saving)

No full board is ever loaded into a model context just to act on one line. `get <id>`
returns a single entry; `list --dept <h>` returns only that dept's entries; resolve is
id/dept-targeted. Combined with dept-prefixed ids (§5), a pane spends ~one line of tokens
to find or close its own item.

### 8.3 · Port selection

No hard-coded port. The port is **derived from the project path** (hash → private range
49152–65535), so the same project deterministically reuses the same port; the pidfile
confirms the listener is ours. On collision (port held by something else), **probe upward**
to the next free port and record the chosen port in the runtime `port` file so the CLI and
the browser URL always agree.

### 8.4 · Server lifecycle

- "Detect if the panel exists" = is our server up? (pidfile + port check.)
  - **Down** → start `serve` detached, then `open http://localhost:<port>`.
  - **Up** → just write the entry to the store; the open page polls and updates itself.
- **Self-reaps when idle:** if the board has no `open` items and hasn't been polled for
  ~10 min, the server exits; the next `add` respawns it. So it only runs while there are
  pending asks. Idle RAM is ~15–20 MB (one small Python process) — less than a browser tab.
- Cross-platform open: `open` (macOS) / `xdg-open` (Linux) / `os.startfile` (Windows),
  mirroring `brief.py`. Degrades, never hard-fails.

## 9 · What this deliberately does NOT change

- `TaskBoard.md`, the platform task system, `TaskCreate`/`TaskUpdate`, and the two task
  hooks are untouched. The new Stop hook is additive and independent, fail-open, and gated
  on the active-project marker.
- `SKILL.md` grows by ~2 lines; the dept template by one line. All other content is in new,
  on-demand files.

## 10 · Verification

- **Idempotency:** fire the same `@BOSS[QA]: …` ask N times → exactly one open `QA-n`.
- **Targeted read:** `get QA-1` and `list --dept QA` return only QA's data.
- **Singleton panel:** two `add`s in a row → one server, one tab, port stable across calls.
- **Port collision:** occupy the derived port → server picks the next free one; URL matches.
- **Resolve:** `@BOSS-DONE[QA]` flips `QA-1` to `resolved`; panel clears it on next poll.
- **Park/reopen:** Boss `park QA-1` → moves to parked strip; `reopen QA-1` → back to open.
- **Idle reap:** empty board, no polling → server exits within the window; next `add`
  respawns it.
- **Fail-open hook:** malformed transcript / missing marker → hook is a no-op, run
  uninterrupted.
- **No side effects:** running the whole flow leaves `TaskBoard.md` / `BACKLOG.md` /
  `docs/reviews/` unchanged.
