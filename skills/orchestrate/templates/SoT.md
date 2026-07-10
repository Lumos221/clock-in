# <项目> · SoT — source of truth (read first)

> **What** — the project's CLAUDE.md: the one clean, lean index that never bloats while
> every other file does. **Pointers, not detail.**
> **Who** — the CEO writes + curates it. **Hard cap ~15 content lines** — a hook injects
> this file into EVERY session, so each extra line is a recurring token tax.
> **Rule** — only **Goal** + **Now** are written text (Now = three slots, one line each);
> everything else is a pointer to the file that owns the detail. Decisions are NOT
> restated here — `CANON.md` mirrors the key ones (machine-maintained), `DECISIONS.md`
> holds every why.

## Goal
<project-level — what we're building + the bar for "done" (1–2 lines)>

## Now
- **live:** <what's deployed/working — only state not readable elsewhere (1 line)>
- **blocked:** <hard blockers only — asks for the Boss live on the Boss Board, not here (1 line, or —)>
- **next:** <the current focus (1 line) — full ordering lives on `TaskBoard.md`>

## Pointers
Fixed:
- Open work → `docs/TaskBoard.md` · finished history → `docs/BACKLOG.md` (on-demand, never load whole)
- Canonical answers **& key decisions** → `docs/CANON.md` (machine-maintained · read-first · don't restate its rows)
- Decision whys → `docs/DECISIONS.md`

Curated (one line each — a thing an agent must not miss + why; prune ruthlessly):
- <`docs/<其领域>/SPEC.md` — the product spec>
- <staging URL · dashboard · key design doc · …>
