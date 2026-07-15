<!-- SINGLE SOURCE OF TRUTH for model routing. Everything else POINTS here (SKILL.md gist ·
departments.md · templates · recruit) and MUST NOT restate the policy. Change routing here; the
pointers don't move. -->

# Model routing

Route each model to what it's best at: **the smart model plans, the cheap model implements.** Do the
job well first — token-saving is the byproduct; under-powering a role just buys 审查 bounces + rework
(worse output *and* not actually cheaper).

## Two-stage inside each 部门: the head plans, staff implement

A **部门 is a unit of two parts** — its **head** (the teammate/pane, on **opus**) and the **staff** it
spawns (one-shot subagents, cheap). The head plans its slice, writes a **precise per-piece spec**,
delegates the *typing* to staff, reviews their output, then reports up. The low-volume judgment
(planning + review) stays opus; the high-volume typing goes cheap. **Most output tokens should land on
staff** — if a head's own opus share stays high, the split isn't paying off. (Floor: a one-line edit
isn't worth a subagent round-trip — the head types it inline.)

## Who runs on what

| Role | Model | Where it's pinned |
|------|-------|-------------------|
| **CEO** (main session) | the Boss's model | not spawned |
| **部门 head** — the teammate/pane; every dept incl. 法务部 | **opus** | frontmatter — `department.md` |
| **审查官 · 督察 · experts** — subagents, not 部门 | **opus** | frontmatter — `auditor.md` · `inspector.md` · `expert.md` |
| **staff** — subagents the head spawns; the typing | **sonnet** / **haiku** (tiering below) | the **head** sets `model:` per one-shot `Agent` call |

**The only per-spawn model decision in the whole org is a head choosing each staff spawn's tier.**
Every standing role is opus, pinned once at recruit; the CEO orchestrates and makes no model call.

**Brain-regime exception (Fable CEO — `reference/brain-regime.md`):** dept spawns carry `model:"sonnet"` (the per-spawn override beats the opus pin; the roster is unchanged and serves both regimes). 审查官/督察 stay opus. This is the one place the CEO makes a model call.

## The staff tier — per piece (the head's call)

| The piece | Tier |
|---|---|
| A **deterministic script could do it** in principle — codemod/regex rename at named sites · apply a literal diff the head wrote · fill a template field-for-field · expand an explicit input→expected table | **`haiku`** — the model stands in for the script; cheapest, denser tokenizer |
| Needs a **model to decide** anything the spec left open | **`sonnet`** — the workhorse tier |
| **Too novel to spec precisely** | the head does it **inline on opus** |

**The haiku test is "could a script do this?"** If it needs a *model* to judge, it's
sonnet; **any doubt → sonnet.** **A haiku bounce → redo the piece on sonnet, never retry haiku** — one
cheap wasted attempt is the cap; don't re-gamble a bounced piece (the head's review + L2 are the
catches). Routable tiers top out at **opus**; a truly un-opus-able task is a **Boss call** — **`fable`
is not routable** (a Boss hand-switch only).

## The menu — what each alias is (verify · volatile · as of 2026-07-04)

Route by **tier alias**; it resolves to the current best-in-tier snapshot, so routing doesn't rot when
snapshots move. $/MTok input / output.

| Alias | Snapshot | $ in / out | Character |
|---|---|---|---|
| `haiku` | Haiku 4.5 | 1 / 5 | fastest, no adaptive thinking, 200k ctx, denser tokenizer |
| `sonnet` | Sonnet 5 | 3 / 15 (intro **2 / 10 through 31 Aug 2026**) | adaptive thinking, 1M ctx |
| `opus` | Opus 4.8 | 5 / 25 | deepest judgment, adaptive thinking, 1M ctx — the top routable tier |
| `fable` | Fable 5 | 10 / 50 | most capable — **Boss hand-switch only, not routable**; rarely available (weekly limit) |

The frontmatter `model:` *can* pin a full snapshot ID (e.g. `claude-sonnet-4-6`), but there's **no
reason to** for our defaults: Opus 4.8 dominates 4.6 at equal price; Sonnet 5 (cheaper on intro, more
capable) beats pinning Sonnet 4.6. **Refresh this table when snapshots / prices move — one edit, here.**

## Escalation — how, not just when

A running teammate's model **cannot be changed** by the CEO (`/model` is human-operator-only; model is
fixed at spawn). To move a task up a tier: finish its handover → stop the agent → **spawn fresh at the
higher tier** — **never a resume** (a resume keeps the original model). A **competence bounce** (keeps
hitting the ceiling; re-derives from commits + handover + the `.fail`) warrants this; a **fixable
miss** (capable, just slipped) does not. **Never route by a worker's self-reported confidence** —
escalation is judged externally: the CEO at spawn, or the 审查 bounce.

**Boss-ordered override (the fable hand-switch, executed):** when the Boss explicitly names a tier
for a specific invocation ("run the 督察 on fable for task N"), the CEO **executes it** — pass
`model:` on that one `Agent` call (it overrides the frontmatter pin). The ban above is on the CEO's
*own initiative*, never on the Boss's order. If fable is unavailable (weekly limit — the spawn
fails), report it and fall back to opus; don't silently substitute.
