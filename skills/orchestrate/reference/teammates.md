# Workers — spawning, lifecycle, bursts (detail for `SKILL.md` §7)

## Spawn mechanics

**Teammate** — `Agent(subagent_type=<id>, name=<id>, run_in_background:true)`:
- `<id>` = the 部门's **ASCII handle** (研发部→`RnD` · 测试部→`QA` · 运维部→`Ops` …), regex `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$` (≤64 chars). A Chinese name fails spawn validation — keep the 部门名 as the in-file label.
- the `name` is what makes it a teammate: a `<id>@session` identity, a `members` roster slot, its own pane, `SendMessage(to:"<id>")` addressability. `run_in_background:true` just keeps the lead non-blocking. The team forms on the first teammate; cleanup is automatic.
- **liveness = presence in the config's `members[]`** (a clean shutdown removes the entry; a lingering entry = alive or zombie, and both get the shutdown-first flow). **`isActive` is a busy-flag, not liveness** — a demonstrably responsive Registrar sat `isActive:false` between commands. Every hook that judged liveness by `isActive` skipped exactly the idle teammates it existed to catch (fixed 0.9.25).
- **Only the CEO (lead) spawns teammates.** A non-lead passing a `name` **orphans** (live — possibly with a pane — but unmanaged: on nobody's roster, in nobody's member list): no nested teams. Dept briefs carry the matching prohibition.
- **External terminal seats are not teammates**: dispatch them via bridge
  (`reference/external-seats.md`); **never `Agent(...name=...)` one** — that mints
  a fake seat (right name, wrong model, no brief).
- **nickname（花名）是显示名，不是 handle — and every dept spawn carries one.** The
  handle stays `<dept>-<卡号>` (the numeric suffix is what the stall/capacity checks
  reduce back to the dept — never replace it with a word). Write `nickname=Lisa` in
  the spawn's `description`, same line as `effort=high` and the same `=` separator
  (中文键 `花名=阿岚` 也认; `:` also parses, template uses `=`); the board then wears
  it on task cards and the Departments roster (`Frontend · Lisa`) while the card
  number stays on the card. **The CEO picks the name, never the code:** the Boss
  points at seats by 花名, and only the namer knows who they mean — a code-assigned
  name is one nobody at the helm can resolve. 花名由 CEO 起，同部门内不重名；外部
  contractor 席位共用同一套人名池。

**Subagent** — `Agent(subagent_type=<role>)` with **no `name`**: foreground returns its result once; add `run_in_background:true` for a **background subagent** (async, notifies on completion, final message auto-returns; `SendMessage(to:"main")` is its channel — background subagents only, teammates report to `team-lead`). **Never pass `name:` on a one-shot** (staff · expert · 审查官 · research burst) — naming converts it into a standing teammate (from a non-lead, an orphan).

**New agent files load only at the next session start, and spawning one early FAILS SILENTLY.** A definition written mid-session is not registered for the teammate path, and the spawn does not error: it echoes your `agentType` string into the roster and the pane title, then falls back to the default teammate model with **no brief at all**. You get a seat named `Legal` that is not Legal — right name, right pane title, wrong model, none of its instructions. Created a file (the activation roster, a new expert, a re-hire)? **Restart + resume** (`claude -c` keeps the conversation) before spawning it. Urgent one-off → spawn `general-purpose` with the role inlined; the named file takes over next session. **The pane title is not evidence the brief loaded — the model line is:** check the spawned seat's model against its file, and if they disagree, that seat is a shell. Kill it.

## Lifecycle — a teammate lives per task

Nothing is lost unless you make a *fresh* `Agent()` call or *shut an agent down*. Any spawned agent resumes losslessly from its transcript via `SendMessage` (teammate → by name; **background subagent → by the `agentId` from its spawn result, which you MUST capture** — an agent isn't told its own id).

The unit of a teammate's life is the **task**, not the project — standing idle panes rot into corpses, and the duplicate spawns they force are worse:

- **Spawn at dispatch** (card ready, `TaskUpdate` → owner + `in_progress`). **A teammate has no effort of its own — it runs at YOUR live level**, so the round's level is a decision you make with `/effort` before a batch, not per seat (`reference/model-routing.md`).
- **Mid-task — always resume, never kill:** rework after a bounce, a clarification → `SendMessage`; a fresh `Agent()` re-derives from disk (commits / BACKLOG / `.fail`) and throws away the reasoning.
  - **Mid-task bloat → rotate at the card boundary, never push to auto-compact.** A seat cannot see its own context %, and nobody can watch four panes — the seat-context sentinel reads each teammate's transcript and tells YOU (50% of window = give the next card a fresh seat; 70% = rotate at the current card's boundary). On the rotate call: have the seat checkpoint — commit WIP + write `docs/handover-<Dept>.md` (state · tried-and-abandoned approaches · next step) — then retire it and spawn fresh `<Dept>-<NNN>`; the handover turns "a fresh spawn throws away the reasoning" into "a fresh seat inherits the distilled reasoning". A seat that reaches passive auto-compact has already degraded (it re-proposes its own dead ends) and the compact summary is lossy — that outcome is a process failure, not a cost question.
- **At the clean boundary** — L2 `.pass` verified, merged, `TaskUpdate→completed`, report received — **release it: ask it to shut down** (cleanup is automatic). Shutdown here loses nothing: everything that matters is already externalised (commits · board · BACKLOG · its report).
  - **A shutdown is not done until you have checked it — confirm by state, never by reply.** The entry is gone from `members[]`, or its process is gone. A polite "acknowledged, shutting down" is evidence of nothing: shutdown is the harness's own protocol, carried in `SendMessage`'s tool description, and a seat that never reported has never loaded that tool — it cannot answer and says so in prose instead (`docs/KNOWN-ISSUES.md` §3; re-ask with the reply pasted in and it goes). A seat still listed after a *well-formed* approve is the harness-side failure (§2) — treat it as dead for planning and expect the pane to need closing by hand.
  - A dept that goes idle with unreported work gets ONE mechanical stderr nudge to report (Stop/TeammateIdle hook; suppressed while `orchestrate-pane` marks the Boss in its pane) — the CEO's manual prompt is the fallback, not the routine.
- **Next task for the same dept → fresh spawn, same handle** — clean context; it catches up from SoT + the card + CANON + commits. One exception: the next card is dispatch-ready in the same turn the report lands → hand it to the live teammate (zero idle time, no churn) — **but only if the seat is under the context warn threshold AND has closed fewer than `seat_cards_max` cards.** This exception is how seats quietly accumulate forever (the capacity counter only sees a seat "between cards", and a queue-fed seat never is); the sentinels now flag both, and their nudge outranks the zero-idle-time saving.
- **No corpse panes:** a graceful release frees the handle. A spawn failing because the name is taken usually means the previous instance is still alive — shut it down first; **never let the harness auto-mint a suffix** (that's how corpse panes multiply). Field-observed exception: a pane killed *externally* (Boss closed the terminal pane) can leave a zombie member entry that still blocks the name — send it a shutdown request, re-try once, and only then spawn suffixed, noting the zombie for closeout.
- **Deliberate second lanes are NOT corpses:** when a dept has more than one card, an **explicitly suffixed** spawn of the same dept on **file-disjoint cards** with CEO-pinned scopes is elastic capacity without re-cutting ownership. **Suffix with the durable card number** (`Frontend-358`, not `Frontend-2`): the number is what makes the seat legible and, being numeric, still reduces to the dept for every roster/brief/stall check — a slug does not. Two card-numbered seats never collide, so a sequenced next card spawns the moment you tell the current one to stop instead of waiting for a bare name to free up. The spawn guard passes an explicit suffix that matches no live member exactly; it blocks bare-name respawns over a live handle (the accidental supersede) and exact-name collisions. Each lane is ASSIGNed by its exact handle, judged idle on its own, and released at its own clean boundary.
- **Replacing a live teammate (tier change, fresh respawn): wait for confirmed termination before spawning the same handle.** A shutdown request is processed only when the teammate's turn ends — a mid-think dept can hold its name for minutes (field case: `Backend-Engine-2` minted while its predecessor was 6 minutes into a turn, still burning opus on a reassigned task). A PreToolUse guard blocks the collision at spawn time. Truly can't wait → spawn suffixed deliberately and treat the predecessor's output as void (release it on sight). Session start flags any live pane holding no open task.
- **The Registrar is infrastructure, not a dept:** it is the team's task desk — CEO lifecycle proxy + dept claim desk, sender-ACL'd — retire it at closeout (`reference/task-widget.md`).

## Experts (Prof_ / Spec_ — reusable subagents)

Domain knowledge a 部门 invokes outside its field. No expert exists → the dept tells the CEO → CEO checks the roster, else invokes the **督察 to create one**. Full lifecycle · auto-match · naming: `reference/departments.md`.

## Workflow — the CEO's burst engine (not a worker kind)

A *bounded* parallel fan-out that isn't department-shaped — review N files, research N questions, verify N findings (split → run → collect → verify). Teammates = a dept driving its task in its own pane; Workflow = one-shot bursts. Agents that **write in parallel** pass `isolation:"worktree"` (own checkout each); read-only bursts don't.

## Model and effort routing

→ `reference/model-routing.md`. Two dials: **model** = how much judgment the task leaves open, **effort** = how much search before it is safe to commit. Every standing role carries a `model:` pin in its own frontmatter, so a param-less spawn is always valid; the CEO overrides at dispatch when the task's judgment demand differs from the seat's baseline. Effort: a subagent honours `effort:` in its own file; a teammate cannot be given one and inherits the CEO's live level. Tiers, the detection cap, and why `fable` is never routed without the Boss's word live in that file, not here.
