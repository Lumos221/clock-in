# <项目> · TaskBoard

> **What** — the live work board: the current workline, so teammates coordinate here
> instead of trawling `BACKLOG.md`.
> **Holds** — active tasks (`todo`/`doing`/`review`/`blocked`) **plus** a machine-kept
> *Recently shipped* tail (last ~5), so recent progress shows without opening BACKLOG.
> **Writers** — cards are **born by the task-sync hook** when the CEO runs `TaskCreate`
> (`task_id` pre-filled); the **CEO** enriches `what`/`done-when` in place; each **dept**
> updates **only its own card's** `status`; on an L2 pass the **CEO** calls
> `TaskUpdate→completed` — the completion hook **retires the card** into *Recently
> shipped* + `BACKLOG.md` (the 审查官 never touches this board).
> **Not** the source of truth (`SoT.md`) or the full history (`BACKLOG.md`). `<id>` = the
> platform `task_id`, **not** the `TASK-NNN` label.

Status: `todo` → `doing` → `review` → `done` (any stage may park at `blocked`)

## Active

### TASK-001 · <short name>
- **dept:** <handle, e.g. RnD>
- **task_id:** <machine-filled: the platform id from TaskCreate — the review gate keys on it>
- **status:** todo
- **blocked_on:** —
- **what:** <the slice this must accomplish>
- **done-when:** <checkable acceptance criterion>
- **artifacts:** —

## Recently shipped
Machine-maintained by the completion hook — newest first, keeps ~5; full history in `BACKLOG.md`. **Don't hand-edit between the markers.**
<!-- SHIPPED:START -->
<!-- SHIPPED:END -->
