# 督察 (Inspector) · CEO quick-reference

> The 督察's full contract lives in `.claude/agents/Inspector.md` (copied verbatim from
> `templates/inspector.md` at activation). This page is the **CEO-facing summary** — when
> to invoke it and what comes back. Like the 审查官 it is a **standing-file, one-shot
> subagent**: fresh instance per invocation, never a teammate, never in `roster`.

## Why one-shot, not a standing dept
Every 督察 job is a bounded single-context judgment — diagnose one stuck task, write one
agent file, one audit report. Its cross-generation memory is `docs/复盘-*.md` on disk, so
no session needs to persist. Independence comes from fresh instances plus an unfilterable
channel: its verdicts end with `@BOSS[Inspector]: …`, which the Stop hook lands on the
Boss Board — the CEO relays nothing and can suppress nothing.

## The circuit breaker (replaces the old retune→fire ladder)
L2 封驳 are counted **per task** (`docs/reviews/<dept>.<id>.*.fail`), auto-tallied by a
hook. Consecutive bounces on one task share one root cause — so the loop halts early for
a diagnosis instead of accruing a discipline file:

| Trigger (thresholds in `.claude/orchestrate.json`) | What happens |
|---|---|
| `bounce_diagnose` (default **2**) bounces on one task | Board flag: **stop the rework loop**. CEO invokes the 督察 one-shot with `task_id` + dept handle |
| the 复盘's fix is applied | task gets **one** more attempt |
| `bounce_escalate` (default **3**) | Board flag: task is stuck — **Boss decision** (re-scope / drop / take over) |
| `chaos_ceo_refutes` (default **3**) L1 refutes | Board flag straight to the Boss: the *direction* is the problem — matches SKILL §2.3's 3rd-refute rule |

The 复盘 returns exactly one 根因 + fix: ① dept prompt wrong → the 督察 rewrites
`.claude/agents/<dept>.md`, the **CEO respawns** (a fresh spawn re-derives from commits +
BACKLOG + the `.fail` reasons — replacing an agent is cheap; lost context is the only real
cost, and it's already externalised) · ② CEO brief unclear → **you** rewrite the card ·
③ task too hard → re-scope / split / bump the staff tier.

**No counter resets, ever.** Counts are per task and die with it: completion archives the
task's markers automatically; a sentinel whose count drops below threshold re-arms itself.

## Cross-task signal (the real "this domain is mis-cut")
Raw bounce totals never distinguished a bad dept from three hard tasks. The signal that
matters is in the 复盘 log: **the same root cause twice for one dept across generations**
→ the 督察 recommends a roster audit (改组 scan — `recruit` skill, Mode A; restructure
only after the Boss says go).

## Other invocations
- **Expert files** — a dept needs a Prof_/Spec_ that doesn't exist → CEO routes to the 督察.
- **Boss-invoked judgment** — any org-shaped read (is the CEO the problem · money burning ·
  boundary breaking). It judges from the ledger, never from self-reports.
