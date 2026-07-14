# Workers — spawning, lifecycle, bursts (detail for `SKILL.md` §8)

## Spawn mechanics

**Teammate** — `Agent(subagent_type=<id>, name=<id>, run_in_background:true)`:
- `<id>` = the 部门's **ASCII handle** (研发部→`RnD` · 测试部→`QA` · 运维部→`Ops` …), regex `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$` (≤64 chars). A Chinese name fails spawn validation — keep the 部门名 as the in-file label.
- the `name` is what makes it a teammate: a `<id>@session` identity, a `members` roster slot, its own pane, `SendMessage(to:"<id>")` addressability. `run_in_background:true` just keeps the lead non-blocking. The team forms on the first teammate; cleanup is automatic.
- **Only the CEO (lead) spawns teammates.** A non-lead passing a `name` **orphans** (live — possibly with a pane — but unmanaged: on nobody's roster, in nobody's member list): no nested teams. Dept briefs carry the matching prohibition.

**Subagent** — `Agent(subagent_type=<role>)` with **no `name`**: foreground returns its result once; add `run_in_background:true` for a **background subagent** (async, notifies on completion, final message auto-returns). **Never pass `name:` on a one-shot** (staff · expert · 审查官 · research burst) — naming converts it into a standing teammate (from a non-lead, an orphan).

**New agent files load only at the next session start.** Created one (the activation roster, a new expert, a re-hire)? **Restart + resume** (`claude -c` keeps the conversation) before spawning it. Urgent one-off → spawn `general-purpose` with the role inlined; the named file takes over next session.

## Lifecycle — resume, don't cold-respawn

Nothing is lost unless you make a *fresh* `Agent()` call or *shut an agent down*. Any spawned agent resumes losslessly from its transcript via `SendMessage` (teammate → by name; **background subagent → by the `agentId` from its spawn result, which you MUST capture** — an agent isn't told its own id).

- **Continue the SAME task** (rework after a bounce, a clarification) → **resume**; a fresh `Agent()` re-derives from disk (commits / BACKLOG / `.fail`) and throws away the reasoning.
- **At a clean task boundary** (passed 审查 + committed, next task independent) a **fresh lean spawn is preferred** — it catches up from BACKLOG + commits and sheds accumulated context.
- **Mid-task bloat (no clean boundary yet)** → ask the Boss to `/compact` the teammate's pane.
- **Never shut a teammate down mid-project to cut noise** (idle ≠ done-with; shutdown is terminal). Shut depts down only at true closeout.

## Experts (Prof_ / Spec_ — reusable subagents)

Domain knowledge a 部门 invokes outside its field. No expert exists → the dept tells the CEO → CEO checks the roster, else invokes the **督察 to create one**. Full lifecycle · auto-match · naming: `reference/departments.md`.

## Workflow — the CEO's burst engine (not a worker kind)

A *bounded* parallel fan-out that isn't department-shaped — review N files, research N questions, verify N findings (split → run → collect → verify). Teammates = standing domains re-tasked across rounds; Workflow = one-shot bursts. Agents that **write in parallel** pass `isolation:"worktree"` (own checkout each); read-only bursts don't.

## Model routing

→ `reference/model-routing.md` — standing roles are opus, pinned in their frontmatter; the only per-spawn model call is a **head choosing its staff's tier** (default sonnet / opt-in haiku).
