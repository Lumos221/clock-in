# <项目> · TaskBoard

> **What** — the live work board: the current workline, so teammates coordinate here
> instead of trawling `BACKLOG.md`.
> **Holds** — active tasks (`todo`/`doing`/`review`/`blocked`) **plus** a machine-kept
> *Recently shipped* tail (last ~5), so recent progress shows without opening BACKLOG.
> **Writers** — the **CEO** writes cards + fills `task_id`; each **dept** updates **only
> its own card's** `status`; on an L2 pass the **CEO** marks `done` and **deletes the
> card** — the completion hook records it under *Recently shipped* and in `BACKLOG.md`
> (the 审查官 never touches this board).
> **Not** the source of truth (`SoT.md`) or the full history (`BACKLOG.md`). `<id>` = the
> platform `task_id`, **not** the `TASK-NNN` label.

Status: `todo` → `doing` → `review` → `done` (any stage may park at `blocked`)

## Active

### TASK-001 · <short name>
- **dept:** <handle, e.g. RnD>
- **task_id:** <CEO fills at dispatch: the platform id TaskCreate returns, e.g. 3>
- **status:** todo
- **blocked_on:** —
- **what:** <the slice this must accomplish>
- **done-when:** <checkable acceptance criterion>
- **artifacts:** —

## Recently shipped
Machine-maintained by the completion hook — newest first, keeps ~5; full history in `BACKLOG.md`. **Don't hand-edit between the markers.**
<!-- SHIPPED:START -->
<!-- SHIPPED:END -->
