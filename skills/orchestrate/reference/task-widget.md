# The platform task widget — contract + sync hooks (detail for `SKILL.md` §2.4)

The task tools (`TaskCreate` / `TaskUpdate` / `TaskList` / `TaskGet`) are Claude Code built-ins riding the agent-teams feature. The widget is the channel that actually gets followed — the harness re-injects task state as reminders — while `TaskBoard.md` stays the durable, git-diffable, hook-readable layer. The sync hooks keep the two aligned so neither is hand-maintained twice.

## Availability

- **Deferred loading:** current CLI builds don't preload the task tools. Not loaded? Run `ToolSearch` with `select:TaskCreate,TaskUpdate,TaskList,TaskGet` once — then call them normally. **A model that hasn't run that search truthfully reports "no task tools" — that's invisibility, not absence.** Always verify with the actual ToolSearch call.
- **The gate is the MODEL, not the version** (root-caused 2026-07-14 by probe matrix + `--debug-file` diff): a server-delivered feature config withholds the task family from **interactive** sessions whose main model is **Sonnet 5, Fable 5, or Opus 4.8** — ToolSearch reports "No matching deferred tools found" — while **Haiku 4.5 interactive sessions have the widget** (TaskList executes) and **headless (`claude -p`) sessions have it on every model**. Verified on both 2.1.206 and 2.1.208: CLI version is irrelevant, as are account, env, permission mode, directory and teammate backend (all ruled out empirically). Presumably a temporary rollout pause for the bigger models. **Re-test with the session's real model** — a haiku probe proves nothing for a Fable/Opus CEO pane.
- A pane **resumed after its team died** also cannot load them (team infra doesn't rehydrate on `/resume` — documented limitation). Task **data** survives resume on disk (`~/.claude/tasks/session-<8hex>/`); only the tools drop.
- In a session without the tools AND without a Registrar (below), every task-keyed hook (review gate · completion logger · task-sync) is **dormant, fail-open** — completion runs on the honour system and the board is hand-kept, exactly the pre-0.9.0 discipline. Everything re-arms automatically the day the registry exposes the tools again.

## The Registrar fallback (widget-gated sessions)

**Verified working 2026-07-14:** a **haiku teammate of a gated lead gets the full widget** — its session fetches its own model-keyed config, and the task list is shared team state, so its TaskCreate/TaskUpdate calls land on the same list, fire the same sync hooks (in its session — the board updates mechanically), and face the same L2 completion gate. The proxy costs one cheap teammate and a message round-trip per lifecycle batch.

- **When:** the CEO's own ToolSearch genuinely finds no task tools. Not needed otherwise — direct calls beat the hop.
- **Why a teammate, not a one-shot subagent:** verified — an unnamed haiku subagent gets NO task tools (it runs inside the lead's session and shares its gated registry); only a **named teammate** is a separate process that fetches its own model-keyed config.
- **Spawn:** `Agent(subagent_type:"Registrar", name:"Registrar", model:"haiku", run_in_background:true)` — the standing file `templates/registrar.md` → `.claude/agents/Registrar.md` (recruit copies it at activation). Wait for its `READY tools=loaded` report.
- **Drive it** with literal commands via `SendMessage(to:"Registrar", …)` — protocol table in the agent file: `CREATE subject="…" description="…"` · `ASSIGN id owner` · `STATUS id pending|in_progress` · `COMPLETE id` · `LIST` · `GET id`. Batch several commands per message; it replies one line per command, failures verbatim (a gate-blocked COMPLETE comes back word for word — that's the gate working through the proxy).
- **Retire it** at closeout like any teammate — or permanently the day the CEO's own session has the tools again.

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
