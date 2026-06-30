# Canonical Answers — `scripts/canon.py`

> A machine-maintained registry of the **current authoritative file per answered question**: `docs/CANON.md`. Read-first by every dept; registered mechanically so the CEO relay can't drop a pointer. Separate from `DECISIONS.md` (full why-log, on-demand). Design: `docs/superpowers/specs/2026-06-30-canonical-answers-design.md`.

## Why
A decision settled in one dept must reach the depts that act on it. `CANON.md` is the lean, read-first index of current binding answers — a dept that re-reads it each session can't carry pre-decision memory, and a peer needing a cross-domain fact looks it up by topic instead of guessing a filename.

## Register / look up / hand off
- **Register (owning dept):** end a turn with `@CANON[<dept>] <topic> → <path> (affects: <depts>)`. The `Stop`/`SubagentStop` hook (`hooks/stop_canon.py`) writes the row. Auto-registers as current (L2 already vetted the output). Register only cross-cutting *answers*, not drafts/rounds.
- **Look up (any dept):** `orchestrate-canon get <topic>` → the current file path; read that file. `CANON.md` is also in your read-first set. **Never browse a peer's `docs/<其领域>/`.**
- **Hand off on change:** when an answer changes, its `affects` depts are written into `needs-recheck` and surfaced under "⚠ Needs re-check". A flagged dept re-reads the file, then `@CANON-ACK[<dept>] <topic>` (or `orchestrate-canon ack <topic> --dept <dept>`).

## File convention
One **stable, suffix-free** file per question (`pricing-tier.md`, not `pricing-v2.md`) — bare name = current. Updates are in-place (git holds history). Re-pointing to a *different* path archives the old one under `<dir>/archive/`. The ASCII topic-key is decoupled from the filename (which may stay Chinese).

## Anti-bloat
One row per *question*, not per file/version — updates re-point the same row. Only an explicit `@CANON` registers (nothing sweeps a folder in). Only cross-cutting settled answers qualify. So `CANON.md` grows with distinct cross-cutting questions (small, stable), not file count.

## CLI (`orchestrate-canon`, on PATH)
`set --dept <h> --topic <k> --file <path> [--affects a,b]` · `get <topic>` · `list [--dept <h>]` · `ack <topic> --dept <h>` · `supersede <topic>` · `archive <path>`. The registry auto-creates on first `set`.
