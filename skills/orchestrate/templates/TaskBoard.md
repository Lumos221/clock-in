# <项目> · TaskBoard

> **What** — the live work board: the current workline.
> **Holds** — active tasks (`todo`/`doing`/`review`/`blocked`) **plus** the last ~5 under *Recently shipped* (so recent progress shows here without opening BACKLOG).
> **Writers** — the **CEO** writes cards + fills `task_id`; each **dept** updates **only its own card's** `status`; the **审查官** marks `done`; the **CEO** then moves the card to *Recently shipped* (trimming to ~5).
> **Not** the source of truth (`SoT.md`) or the full history (`BACKLOG.md` — auto-logged on completion). `<id>` = the platform `task_id`, **not** the `TASK-NNN` label.

Status: `todo` → `doing` → `review` → `blocked` → `done`

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
<rolling — last ~5; full history in `BACKLOG.md`. The CEO adds one line on a 审查 pass; oldest drops off.>
- <TASK-00X · dept · sha · one line>
