# Workers — spawning, lifecycle, bursts (detail for `SKILL.md` §7)

## Spawn mechanics

**Teammate** — `Agent(subagent_type=<id>, name=<id>, run_in_background:true)`:
- `<id>` = the 部门's **ASCII handle** (研发部→`RnD` · 测试部→`QA` · 运维部→`Ops` …), regex `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$` (≤64 chars). A Chinese name fails spawn validation — keep the 部门名 as the in-file label.
- the `name` is what makes it a teammate: a `<id>@session` identity, a `members` roster slot, its own pane, `SendMessage(to:"<id>")` addressability. `run_in_background:true` just keeps the lead non-blocking. The team forms on the first teammate; cleanup is automatic.
- **liveness = presence in the config's `members[]`** (a clean shutdown removes the entry; a lingering entry = alive or zombie, and both get the shutdown-first flow). **`isActive` is a busy-flag, not liveness** — field-proven 2026-07-19: a demonstrably responsive Registrar sat `isActive:false` between commands. Every hook that judged liveness by `isActive` skipped exactly the idle teammates it existed to catch (fixed 0.9.25).
- **Only the CEO (lead) spawns teammates.** A non-lead passing a `name` **orphans** (live — possibly with a pane — but unmanaged: on nobody's roster, in nobody's member list): no nested teams. Dept briefs carry the matching prohibition.

**Subagent** — `Agent(subagent_type=<role>)` with **no `name`**: foreground returns its result once; add `run_in_background:true` for a **background subagent** (async, notifies on completion, final message auto-returns; `SendMessage(to:"main")` is its channel — background subagents only, teammates report to `team-lead`). **Never pass `name:` on a one-shot** (staff · expert · 审查官 · research burst) — naming converts it into a standing teammate (from a non-lead, an orphan).

**New agent files load only at the next session start.** Created one (the activation roster, a new expert, a re-hire)? **Restart + resume** (`claude -c` keeps the conversation) before spawning it. Urgent one-off → spawn `general-purpose` with the role inlined; the named file takes over next session.

## Lifecycle — a teammate lives per task

Nothing is lost unless you make a *fresh* `Agent()` call or *shut an agent down*. Any spawned agent resumes losslessly from its transcript via `SendMessage` (teammate → by name; **background subagent → by the `agentId` from its spawn result, which you MUST capture** — an agent isn't told its own id).

The unit of a teammate's life is the **task**, not the project — standing idle panes rot into corpses, and the duplicate spawns they force are worse:

- **Spawn at dispatch** (card ready, `TaskUpdate` → owner + `in_progress`).
- **Mid-task — always resume, never kill:** rework after a bounce, a clarification → `SendMessage`; a fresh `Agent()` re-derives from disk (commits / BACKLOG / `.fail`) and throws away the reasoning. Mid-task bloat → ask the Boss to `/compact` the pane.
- **At the clean boundary** — L2 `.pass` verified, merged, `TaskUpdate→completed`, report received — **release it: ask it to shut down** (cleanup is automatic). Shutdown here loses nothing: everything that matters is already externalised (commits · board · BACKLOG · its report). A dept that goes idle with unreported work gets ONE mechanical stderr nudge to report (Stop/TeammateIdle hook; suppressed while `orchestrate-pane` marks the Boss in its pane) — the CEO's manual prompt is the fallback, not the routine.
- **Next task for the same dept → fresh spawn, same handle** — clean context; it catches up from SoT + the card + CANON + commits. One exception: the next card is dispatch-ready in the same turn the report lands → hand it to the live teammate (zero idle time, no churn).
- **No corpse panes:** a graceful release frees the handle. A spawn failing because the name is taken usually means the previous instance is still alive — shut it down first; **never let the harness auto-mint a suffix** (that's how corpse panes multiply). Field-observed exception: a pane killed *externally* (Boss closed the terminal pane) can leave a zombie member entry that still blocks the name — send it a shutdown request, re-try once, and only then spawn suffixed, noting the zombie for closeout.
- **Deliberate second lanes are NOT corpses** (Boss's rule, 2026-07-19): when a dept's queue stacks, an **explicitly suffixed** spawn of the same dept (`Frontend-2`) on **file-disjoint cards** with CEO-pinned scopes is elastic capacity without re-cutting ownership. The spawn guard passes an explicit suffix that matches no live member exactly; it blocks bare-name respawns over a live handle (the accidental supersede) and exact-name collisions. Each lane is ASSIGNed by its exact handle, judged idle on its own, and released at its own clean boundary.
- **Replacing a live teammate (tier change, fresh respawn): wait for confirmed termination before spawning the same handle.** A shutdown request is processed only when the teammate's turn ends — a mid-think dept can hold its name for minutes (field case: `Backend-Engine-2` minted while its predecessor was 6 minutes into a turn, still burning opus on a reassigned task). A PreToolUse guard blocks the collision at spawn time. Truly can't wait → spawn suffixed deliberately and treat the predecessor's output as void (release it on sight). Session start flags any live pane holding no open task.
- **The Registrar is infrastructure, not a dept:** it is the team's task desk — CEO lifecycle proxy + dept claim desk, sender-ACL'd — retire it at closeout (`reference/task-widget.md`).

## Experts (Prof_ / Spec_ — reusable subagents)

Domain knowledge a 部门 invokes outside its field. No expert exists → the dept tells the CEO → CEO checks the roster, else invokes the **督察 to create one**. Full lifecycle · auto-match · naming: `reference/departments.md`.

## Workflow — the CEO's burst engine (not a worker kind)

A *bounded* parallel fan-out that isn't department-shaped — review N files, research N questions, verify N findings (split → run → collect → verify). Teammates = a dept driving its task in its own pane; Workflow = one-shot bursts. Agents that **write in parallel** pass `isolation:"worktree"` (own checkout each); read-only bursts don't.

## Model routing

→ `reference/model-routing.md` — standing roles are opus, pinned in their frontmatter; the only per-spawn model call is a **head choosing its staff's tier** (default sonnet / opt-in haiku).
