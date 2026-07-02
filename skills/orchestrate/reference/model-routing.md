<!-- SINGLE SOURCE OF TRUTH for model routing. Everything else POINTS here (SKILL.md gist ·
departments.md · templates · recruit) and MUST NOT restate the policy. Change routing here; the
pointers don't move. -->

# Model routing

**The CEO decides each spawn's model and passes it on the spawn call** (`model:` per-invocation — the
documented, highest-precedence lever below the env var). Do the job well first; token-saving is the
byproduct — under-powering a role just buys bounces + rework (worse output *and* not actually cheaper).

## Default sonnet; escalate to opus for a reason

Start every **producing** role on **sonnet**. Escalate to **opus** when the work is architecturally
hard / high-stakes up front, or a **competence bounce** shows sonnet hit its ceiling. The 审查 gate is
what makes starting cheap safe — a weak result is caught and reworked, never shipped. Producing roles
are gated; the opus seats below are not.

## Per role

| Role | Model | Why |
|------|-------|-----|
| **CEO** (main session) | Boss's model | not spawned — runs on whatever the Boss has set |
| **审查官** — L1 refute + L2 bounce | **opus** | *is* the gate; nothing reviews it. Weak here → bad work ships silently |
| **法务部 (Legal)** | **opus** | rigorous, zero-mistake, often irreversible; no seat overrules it |
| **人事部 (HR)** | **opus** | authors agents + oversight — a weak author compounds across the roster |
| **Experts — Prof_ / Spec_** | **opus** | consulted *for* judgment / synthesis — the brain by definition |
| **staff grunt** | **haiku** | truly trivial bounded work (search / format / token→$) — no quality to lose |

**Worker or brain, when unsure:** could a competent person answer by *finding and applying* the right
source? → sonnet. Must they *judge*, with no definitive source, where being wrong is costly? → opus.

## Escalation — how, not just when

A running teammate's model **cannot be changed** by the CEO: 
`/model` is human-operator-only. Model is fixed at spawn. So to move
a task sonnet → opus, you make sure teammate's handover's complete -> stop the teammate -> **spawn a fresh agent with `model: opus`** — **never a resume** (a resume keeps the original model).

- **Fixable miss** — sonnet is capable, just missed something → keep.
- **Competence bounce** — sonnet keeps hitting the ceiling → **fresh opus spawn** (re-derives from commits + handover file + the `.fail` bounce report).

**Never route by a worker's self-reported confidence.** Escalation is judged
**externally**: the CEO at spawn, or the 审查 bounce. Never the worker grading itself.

## Where the `model:` value lives (mechanics)

- **opus seats** (审查官 · 法务部 · 人事部 · experts) — pinned `model: opus` in the agent's own
  frontmatter: a guarantee that survives a CEO slip. (审查官 → `templates/auditor.md`; HR →
  `templates/hr.md`; Legal + experts → `templates/department.md` / `templates/expert.md`, pinned at recruit time.)
- **sonnet-default depts** — **no `model:` in the def**. The CEO passes
  `model: ` at spawn. Clean defs; the model decision lives here + with the CEO, never
  scattered across each file.