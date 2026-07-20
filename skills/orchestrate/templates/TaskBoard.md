# <项目> · TaskBoard

> **What** — the whole-board glance: a **generated digest** of the per-card store
> (`docs/board/` — one note per card, YAML frontmatter + free body; `done/` and
> `archive/` keep retired cards).
> **Writers** — hooks only. Cards are **born by the task-sync hook** when the CEO runs
> `TaskCreate` (durable `#NNN` + `task_id` pre-filled); the **CEO** enriches
> `what`/`done-when` **in the card file**; each **dept** updates **only its own card
> file's** `status`; on an L2 pass the **CEO** calls `TaskUpdate→completed` — the
> completion hook **retires the card** into `done/` + *Recently shipped* + `BACKLOG.md`
> (the 审查官 never touches the board). The Active section below is machine-rewritten
> from the cards on every write — **don't hand-edit it**; edit the card files.
> **Not** the source of truth (`SoT.md`) or the full history (`BACKLOG.md`).

Status: `todo` → `doing` → `review` → `done` (any stage may park at `blocked`)

## Active

## Recently shipped
Machine-maintained by the completion hook — newest first, keeps ~5; full history in `BACKLOG.md`. **Don't hand-edit between the markers.**
<!-- SHIPPED:START -->
<!-- SHIPPED:END -->
