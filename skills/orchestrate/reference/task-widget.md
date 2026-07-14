# The platform task widget — contract + sync hooks (detail for `SKILL.md` §2.4)

The task tools (`TaskCreate` / `TaskUpdate` / `TaskList` / `TaskGet`) are Claude Code built-ins riding the agent-teams feature. The widget is the channel that actually gets followed — the harness re-injects task state as reminders — while `TaskBoard.md` stays the durable, git-diffable, hook-readable layer. The sync hooks keep the two aligned so neither is hand-maintained twice.

## Availability

- **Deferred loading:** current CLI builds don't preload the task tools. Not loaded? Run `ToolSearch` with `select:TaskCreate,TaskUpdate,TaskList,TaskGet` once — then call them normally. **A model that hasn't run that search truthfully reports "no task tools" — that's invisibility, not absence.** Always verify with the actual ToolSearch call.
- **Interactive sessions may lack them entirely** (root-caused 2026-07-14 on CLI 2.1.208 via `--debug-file` diff): interactive sessions ran a different server-delivered feature configuration than headless ones (`cc_version=2.1.208.1a2` vs `.80c`) whose deferred registry simply omits the task family — "ToolSearchTool: select failed — none found: TaskCreate, TaskUpdate, TaskList, TaskGet" — while headless (`claude -p`) sessions on the same binary/account/settings load all four every time. Nothing local flips it (account, env, permission mode, model, directory, teammate backend all ruled out empirically). Remote pause during the agent-teams rework; re-test after CLI updates — the schemas still ship in the binary.
- A pane **resumed after its team died** also cannot load them (team infra doesn't rehydrate on `/resume` — documented limitation). Task **data** survives resume on disk (`~/.claude/tasks/session-<8hex>/`); only the tools drop.
- In a session without the tools, every task-keyed hook (review gate · completion logger · task-sync) is **dormant, fail-open** — completion runs on the honour system and the board is hand-kept, exactly the pre-0.9.0 discipline. Everything re-arms automatically the day the registry exposes the tools again.

## Tool contract (verified against the CLI binary)

- `TaskCreate(subject, description[, activeForm])` — ONE task per call; born `pending`, **unowned** (there is no owner parameter at creation).
- `TaskUpdate(taskId, …)` — assign `owner` (= teammate name), set `status` (`pending` / `in_progress` / `completed` — the enum ends there), edit dependencies (`blockedBy`).
- Task ids are small integers, unique per session team, **restarting each session** — never reuse them across sessions.

## What the sync hooks do (all fail-open, active-project only)

- **`TaskCreate` births the card** on `docs/TaskBoard.md`: `### #<id> · <subject>` with `task_id` pre-filled, `what` from the description's first line, status `todo`. A hand-written card whose name matches the subject is **filled, not duplicated**. A stale Active card holding a recycled id is **detached** (`task_id` → `—`, trace in `.claude/marker-misses.log`) before the new card is appended.
- **`TaskUpdate` mirrors the lifecycle:** `pending`→`todo` · `in_progress`→`doing` · `owner` fills an empty `dept`. The fine states (`review` / `blocked`) stay dept-written prose — the widget doesn't know them and the hook never overwrites what it only half understands.
- **`completed` retires the card** (completion hook): deletes it from `## Active`, writes the *Recently shipped* line + the `BACKLOG.md` row, archives the review trail.
- **All card surgery keys on a `task_id` field that is EXACTLY one id** — shared multi-id cards and prose the hooks can't parse are left alone.
- **Session start flags** Active cards carrying no `task_id`, with the ToolSearch load hint.
