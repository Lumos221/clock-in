# Token-saving orchestrate — opus brain, cheap hands

**Date:** 2026-07-04 · **Status:** design approved, pending spec review · **Target release:** clock-in 0.5.0

## Problem

Today every producing 部门 runs on **sonnet** and does *both* the thinking (how to build its
slice) and the typing (writing the code) at one tier. The Boss wants each model used where it is
strongest: **the smart model plans, the cheaper model implements** — maxing out every model's
capability and saving tokens on the bulk (implementation), without weakening the quality gates
that make founder-mode safe.

## Core decisions (locked with the Boss)

1. **The split lives *inside each task*** — a two-stage plan→implement split, **keeping the full
   founder-mode spine and both 审查 gates**. Not a stripped-down "lean mode," not a routing-only
   re-tune.
2. **Dept = opus brain + cheap hands.** Every producing 部门 runs on **opus** (the brain): it plans
   its slice, writes precise per-piece specs, delegates the *typing* to cheap **hands** (subagent
   staff), reviews their output, then reports up. The low-volume judgment stays opus; the
   high-volume typing goes cheap. This is **uniform** — every producing dept, not a per-task or
   per-domain escalation.
3. **Default hand = `sonnet`; `haiku` is opt-in.** The workhorse hand is sonnet (trustworthy for
   implementation that still needs in-the-moment judgment). `haiku` is used **only** for pieces
   that clear a hard bar: *the brain has already decided everything; this is pure transcription.*
   Any doubt → sonnet.
4. **The routable tiers are `haiku` · `sonnet` · `opus`.** `fable` is **not routable** by the CEO or
   the brain — it is a **Boss hand-switch only** (rarely available; the Boss just ran out of its
   weekly limit). It stays in the reference *menu* for education, marked non-routable. *(Parked,
   post-implementation: the Boss has specific requirements for when **fable is the CEO's model** —
   discussed separately.)*
5. **Route by tier alias.** `opus`→Opus 4.8 · `sonnet`→Sonnet 5 · `haiku`→Haiku 4.5. The Agent-file
   frontmatter `model:` *can* pin a full snapshot ID (e.g. `claude-sonnet-4-6`), but there is **no
   reason to** for our defaults: Opus 4.8 dominates 4.6 at equal price, and Sonnet 5 (intro $2/$10
   through 31 Aug 2026, more capable) beats pinning Sonnet 4.6.
6. **CEO orchestrates only — no method suggestions.** Since the CEO and every dept-head are now both
   opus, the CEO no longer "suggests a craft skill." Craft is **100% dept-owned**; the CEO's job is
   purely route / decompose / sequence. Remove the "CEO may *suggest* a method, dept may override"
   language from `SKILL.md` (§0 line 22, §7) and `department.md` (SOP) — the dept keeps its craft
   skills on hand; only the CEO-suggests framing goes.
7. **Keep both L1 and L2 gates.** They guard *different* failures (plan defects vs output defects);
   L2 structurally cannot catch what L1 catches. The opus-brain adds an **informal third layer**
   (brain reviews its hands before reporting), which makes L2 bounce *less* — cheaper in aggregate
   for free. L1 is unchanged (it is already the cheap, once-per-plan gate).
8. **L2 is dept-invoked; the CEO owns the task lifecycle** (fixes a real bug — see "Corrected L2
   flow"). The dept invokes the L2 Auditor itself; a FAIL bounces straight back to the dept
   (CEO uninvolved); a PASS goes up to the CEO, who makes the final merge/adjust call and is the
   **only** one to run `TaskUpdate`. The Auditor never mutates task state — it writes the marker and
   returns a verdict, nothing else.
9. **Auto-tally the refute/fail counts.** `orchestrate.json` stays **thresholds-only**; the
   `docs/reviews/*.refute` / `*.fail` marker files remain the single-source-of-truth ledger; a new
   Stop-time hook counts the files, compares to the thresholds, and surfaces at threshold (with a
   sentinel to flag once, not every turn).

## The model — two-stage inside each task

```text
CEO decomposes → per-dept task card (谁来做 · 做什么 · 预期产出)
  └─ 部门 (OPUS, the brain)
       ├─ plans its slice; writes precise per-piece specs
       ├─ spawns HANDS (cheap subagent staff), one per piece:
       │    ├─ hand A (haiku)  — pure transcription of an exact spec
       │    └─ hand B (sonnet) — implementation with judgment gaps
       ├─ reviews the hands' output  ← informal third layer
       └─ reports up ── SendMessage(team-lead)
  └─ 产出审查 (L2, opus Auditor) — the hard gate, per output
```

**Pragmatic floor.** A one-line edit is not worth a subagent round-trip — the brain types it
inline. Delegation is for pieces with enough typing-volume to pay for the handoff.

**Two-level model routing (who decides what):**

- The **CEO** picks the *dept's* tier — now fixed at **opus** for producing depts (pinned in the
  dept's frontmatter, like the other opus seats, so it survives a CEO slip).
- The **brain** picks each *hand's* tier, per piece, at spawn time — this is where the
  per-invocation `model:` lever now lives. Consistent with "dept owns craft": the dept decides how
  to decompose and tier its own hands; the CEO never dictates method.

## The per-piece tiering heuristic (this *is* "max out every model")

The brain picks each hand's tier from the nature of the piece:

| Piece | Tier | Why |
|---|---|---|
| Spec is **exact, zero judgment left** (rename sweep at named sites, template fill field-for-field, apply a literal diff the brain wrote, N test cases from an input→expected table) | **`haiku`** | mechanical transcription; cheapest *and* fewer tokens (older, denser tokenizer) |
| Spec is clear but has **judgment gaps** the hand must fill | **`sonnet`** | the workhorse hand — adaptive thinking |
| Piece is **too novel to spec precisely** | brain does it **inline on `opus`** | don't hand a bad spec to a cheap model |

`fable` is **not** a routable tier — the CEO and brain top out at `opus`. A truly un-opus-able task
is a Boss call, not an auto-escalation.

**The crux / the central risk.** Spec precision is what makes cheap hands safe. A sloppy spec →
haiku produces wrong code → L2 bounce → rework costs *more* than sonnet-once. Two catches guard it:
the brain's own review, then L2. A **haiku bounce is treated as proof the spec was not actually
decision-free** → the brain tightens it or moves that piece to sonnet. `haiku` is never
blind-trusted; it is trusted for a bounded transcription and then checked.

## The model reference file (SSOT rewrite)

`skills/orchestrate/reference/model-routing.md` is rewritten as the single source of truth, in
three cleanly-separated parts so the durable heuristic never rots when prices move:

1. **Durable heuristic** — the two-stage model, the per-role table, the per-piece tiering bar, the
   escalation mechanics. Stable; changes only when the *policy* changes.
2. **Volatile model menu** — a **dated** table of the four aliases → current snapshot, price,
   character (context window, adaptive vs extended thinking, tokenizer), marked *"verify/refresh —
   volatile."* One-line refresh when snapshots or prices move.
3. **Alias-first principle** — route by tier; the menu is *education* (what each alias costs and is
   good at, so the brain picks well per piece), **not** a list of IDs to pin.

**Division of labour, stated in the file:** the **file carries the facts + heuristic** (a model
cannot reliably recall its own successors' pricing — verified live during this design); the
**brain carries the per-piece judgment**. Neither hardcode the pick nor make the brain guess facts.

**The dated menu (as of 2026-07-04):**

| Alias | Snapshot now | Input / Output $/MTok | Character |
|---|---|---|---|
| `haiku` | Haiku 4.5 | $1 / $5 | fastest, no adaptive thinking, 200k ctx, older (denser) tokenizer |
| `sonnet` | Sonnet 5 | $3 / $15 (intro **$2 / $10 through 31 Aug 2026**) | adaptive thinking, 1M ctx |
| `opus` | Opus 4.8 | $5 / $25 | deepest judgment, adaptive thinking, 1M ctx — the brain, and the top routable tier |
| `fable` | Fable 5 | $10 / $50 | most capable — **Boss hand-switch only, not routable**; rarely available (weekly limit) |

## Gates — keep both; the new structure adds a third informal layer

- **L1 (plan gate, per planning round).** Unchanged. Gates the CEO's cross-domain decomposition:
  完整 (no missing workstream) · 拆解合理 (non-overlap + dependency order) · 不越界 (scope/法务) · 可行
  · 风险已列. **L2 cannot substitute** — it only reviews outputs that *were* produced; a plan-level
  completeness gap is invisible to it. The opus-brain only sees its own slice, so it can't
  substitute either. L1 is the *cheap* gate: one bounded Auditor call, reads the plan (not the
  codebase), rarely bounces. CEO-invoked; **no task-state mutation** — it never had the L2 bug.
- **L2 (output gate, per output).** Contract-quality unchanged, but the **flow is corrected** (below)
  and it is cheaper in practice: the brain's internal review filters defects before L2 runs, so L2
  bounces less (same #calls, fewer bounce→rework→re-review cycles).
- **Informal third layer** — the brain reviews its hands' output before reporting. Not a formal
  gate (the brain isn't independent of its hands), and it doesn't need to be — L2 is the
  independent check on the dept's aggregate output.

Three layers, three jobs: brain-review (informal, inside dept) → L2 (formal, per output) → L1
(formal, per plan, at the top).

### Corrected L2 flow (fixes a real bug)

**The bug (current code):** the dept reports to the CEO *first*, the CEO invokes L2, and the
one-shot **Auditor subagent runs `TaskUpdate(status:completed)`** — completing a task the *CEO*
created. A subagent can't reliably update the lead's task list, so completions misfire; and the
dept-reports-then-CEO-invokes-L2 double-hop double-surfaces the same item (the "duplicated pin").

**The fix (dept-invoked L2; CEO owns the lifecycle):**

```text
dept finishes (hands done, brain-reviewed, committed in worktree)
  └─ dept invokes L2 Auditor ── Agent(subagent_type:"Auditor", output + <id> + <dept>)
       ├─ FAIL → Auditor writes docs/reviews/<dept>.<id>.<n>.fail, bounces to the DEPT
       │          dept reworks, re-invokes. CEO uninvolved (tally surfaces fails at threshold)
       └─ PASS → Auditor writes docs/reviews/<id>.pass, returns verdict
                 dept reports UP to CEO: "L2 passed + sha"
                   └─ CEO's final call: verify .pass → MERGE (FF) or SEND BACK (adjust)
                        └─ CEO sets card done + TaskUpdate(status:completed)  ← CEO only
```

- **Auditor never mutates task state** — writes the marker + returns the verdict, nothing else. The
  card-status + `TaskUpdate` move to the CEO, who owns the task. Sidesteps "can a subagent update the
  lead's list?" entirely.
- **Independence preserved** — it lives in the fresh instance + the Auditor's opus-pinned contract,
  not in *who* invokes it. Dept *requesting* a review ≠ dept self-reviewing. And the CEO's final
  merge call on pass is a new independent checkpoint the old flow lacked. Both old protections hold
  (producer doesn't self-review; CEO doesn't rubber-stamp).
- **The completion-gate hook is unchanged** and still enforces `.pass` before `completed` — now
  tripped by the CEO. The CEO **verifies the `.pass` exists** before merging, so a dept can't fake a
  pass (forging a marker still leaves a trace + trips the tally).
- **L1 unchanged** — CEO-invoked (it gates the *CEO's* plan), no task mutation.

### Marker anchor (resolved — deterministic via git)

Worktrees are **common** here and nested at `<project>/.claude/worktrees/<branch>/`. With the old
anchor (walk up for the nearest `.claude/orchestrate.json`), the write and the check agree *only by
coincidence* of that layout — and break the moment `orchestrate.json` becomes git-tracked (a
worktree checkout then shadows the main marker, so `root` resolves to the worktree and the `.pass`
lands where the CEO's main-tree hook never looks → completion blocked forever). Too fragile to leave
load-bearing on a gitignore, given how often worktrees are used.

**Fix — anchor markers to the main worktree via git, from both sides:**

```text
git rev-parse --git-common-dir   →  <main>/.git   (the SHARED git dir, from any linked worktree)
main root  =  dirname(git-common-dir)
markers    =  <main root>/docs/reviews/
```

`--git-common-dir` returns the shared git dir regardless of which worktree you're in, so its parent
is always the main worktree. The **Auditor** writes `.pass`/`.fail` there (not its local worktree);
the **completion-gate hook** resolves the same way (hardening — the CEO is normally in main). Write
== check becomes a git invariant, independent of layout and of `orchestrate.json`'s tracked/ignored
status.

## Auto-tally hook

- **`orchestrate.json` unchanged** — still holds only `thresholds` (`chaos_ceo_refutes: 3`,
  `retune_after_bounces: 3`, `fire_after_more_fails: 3`, …). It is **not** a counter store.
- **The marker files are the ledger** — `docs/reviews/plan.<n>.refute` (L1/CEO) and
  `docs/reviews/<dept>.<id>.<n>.fail` (L2/per-dept) accumulate append-only. Single source of truth;
  cannot drift from a stored number.
- **New hook** counts those files at the CEO session's **Stop** (same integration point as the Boss
  Board hook), compares each count to its threshold, and surfaces at threshold:
  - 3 `plan.*.refute` → `⚠ CEO has 3 L1 refutes — 人事部 escalation` in the Boss's view.
  - 3 `<dept>.*.fail` → `⚠ <dept> at retune threshold`.
- **Sentinel** — a small file (e.g. `docs/reviews/.flagged-refute-3`) so each breach flags **once**,
  not every turn. Also a file, not `orchestrate.json`.

Clean split, matching the plugin's shape everywhere else: `orchestrate.json` = policy (thresholds);
`docs/reviews/` = facts (counts); the hook compares them.

## Files changed

| File | Change |
|---|---|
| `skills/orchestrate/reference/model-routing.md` | **Rewrite** (SSOT): two-stage model · per-role table (producing dept = opus; hands = sonnet default / haiku opt-in) · routable tiers = haiku/sonnet/opus, `fable` non-routable (Boss hand-switch) · per-piece tiering bar · dated volatile menu · alias-first + pinning note · two-level routing (CEO picks dept, brain picks hands) · keep escalation mechanics |
| `skills/orchestrate/SKILL.md` | §2.5 (部门 execute) — reframe as brain plans → specs → delegates typing to cheap hands → reviews. **§2.6 (L2)** — rewrite to the corrected flow: dept-invoked → fail-bounces-to-dept → pass-to-CEO → CEO owns TaskUpdate + merge. §3 (comms) — reflect dept↔Auditor loop. §8 (Workers) — hands = cheap subagent staff; brain = opus teammate; the brain picks hand tier at spawn; update "Pick the kind" + staff/model pointers. **§0 line 22 + §7** — remove the "CEO may *suggest* a method, dept may override" clauses (CEO orchestrates only) |
| `skills/orchestrate/templates/auditor.md` | **L2 section** — invoked by the dept; Auditor writes the marker + returns the verdict **only**; remove its card-status-set + `TaskUpdate` steps (move to CEO). **Anchor markers to the main worktree via `git rev-parse --git-common-dir`** (not the local worktree). L1 section unchanged |
| `hooks/pretool_review_gate.py` | Resolve the project root via `git rev-parse --git-common-dir` → parent (hardened, worktree-invariant) instead of the nearest-`orchestrate.json` walk; keep fail-open. Add/adjust `scripts/test_*` coverage for the worktree case |
| `skills/orchestrate/templates/department.md` | Frontmatter `model: opus` (pinned, producing dept). Body: the brain/hands protocol + the pragmatic floor + pointer to model-routing.md's tiering bar. **Report-and-stop / SOP** — invoke L2 before reporting; on pass report up, on fail rework in place. Drop "the CEO may *suggest* a method"; craft is wholly dept-owned |
| `skills/recruit/SKILL.md` | Check/adjust any "sonnet-default dept" wording so recruit pins `model: opus` on producing depts (follows the template) |
| `hooks/stop_refute_tally.py` (new) + `hooks/hooks.json` | Stop-time count-and-compare + sentinel; registered |
| `CHANGELOG.md` · `.claude-plugin/plugin.json` | Version → **0.5.0**; changelog entry |

## Success criteria

- The **bulk of output tokens lands on hands** (haiku/sonnet); opus is a thin planning/review
  layer. If a dept's opus token share is high, the split isn't paying off — that's the signal to
  push more typing down.
- No weakening of quality: both gates intact; the informal brain-review is *additive*.
- The model reference is refreshable in one edit when prices/snapshots move, and routing never
  breaks on a stale price table (alias-first).

## Non-goals

- No lean/stripped orchestrate mode. No removal of any gate, meeting, or oversight role.
- No change to L1's contract or cost. No CEO-writes-the-spec (that would break dept-owns-craft).
- No snapshot-pinning in our defaults (kept available via frontmatter, documented, but unused).

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| **Cost inversion** — cheap hand bounces → rework costs more than sonnet-once | The haiku bar (pure transcription only) + brain-review + L2; a haiku bounce → tighten spec or escalate to sonnet |
| **Opus idle cost** — ≤6 opus teammates each idle-ping on opus turns | Accepted by the Boss; offset by pushing the token *volume* to cheap hands (success criterion above) |
| **Stale price menu** | Dated + marked volatile; alias-first so routing survives staleness; one-line refresh |
| **Brain under-specs** and over-delegates | The bar is explicit; "too novel to spec" → brain does it inline on opus |
