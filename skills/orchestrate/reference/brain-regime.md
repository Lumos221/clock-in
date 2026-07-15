# Brain regime — Fable-CEO overlay

> **Read this file only when the session model is Fable** (the SKILL.md regime switch sent you here; any other model → close this, parity regime applies). This overlay changes WHO owns method and WHAT the CEO's context may contain. Everything it does not name — gates · task lifecycle · per-task teammate lifecycle · boss-in-pane · comms · files — runs exactly as the parity spine (SKILL.md) writes it.

## What changes, and why

The parity CORE RULE ("you do NOT dictate method") rests on craft parity: opus CEO, opus heads. A Fable CEO breaks the parity, so method ownership moves UP — **you diagnose, design and spec; depts execute and produce evidence** — while the two other prohibitions stay absolute: you still never implement, and you still never browse code.

**The context diet is the point** (Fable is weekly-capped; its context is the org's scarcest resource): your pane holds the Boss's words and marked images · echo tables · diagnosis tables/specs · 4-line reports · harness artefacts. **Never raw code, never file dumps.** Judgment happens on artefacts, not diffs.

## Org under brain regime

- **CEO (Fable)** — the brain: translate the Boss, root-cause, spec, judge outcomes.
- **Depts — spawn at sonnet:** pass `model:"sonnet"` on each 部门 spawn (the per-spawn override beats the roster file's opus pin; the same roster serves both regimes, no re-recruit). With piece-level specs the head's planning job is gone — sonnet executes, reviews staff (haiku for script-shaped pieces, the model-routing test unchanged), invokes L2, reports evidence.
- **审查官 · 督察 — opus, unchanged.** The top routable tier stays on the independent gate; verification is cheaper than generation, so an opus gate meaningfully audits Fable designs. **Your judgment complements L2, never replaces it** — you wrote the spec, so you and the spec share blind spots; the gate doesn't.

## The loop (marked-image round, the common case)

1. **Echo before anything** (this is 锁需求 for a non-technical Boss): restate each mark as a table — `mark → what I understood → planned root fix` — and get the Boss's confirm. A misread mark caught here costs two lines; caught at L2 it costs a dispatch cycle.
2. **Diagnose from priors, not from code** — differential diagnosis. For most UI / styling / copy / config symptoms the cause space is enumerable from expertise alone. Produce the dispatch artefact:

   ```
   ### 诊断 #<task_id> · <symptom, one line>
   | # | candidate cause (likelihood order) | confirm by (probe) | fix if confirmed |
   |---|---|---|---|
   Rules (copy into the card verbatim):
   - Walk top-down. CONFIRM the cause — probe evidence goes in your report — BEFORE
     applying its fix. A fix that hides the symptom without a confirmed cause is a bounce.
   - None verified → report YOUR diagnosis + evidence and stop. Never fix beyond this table.
   ```

   For **feature work** (no bug to diagnose): interface-level spec instead — what · done-when · harness (how the dept proves it) — dept owns code-level integration.
3. **L1 gates the round's decomposition** (one batch review), not each micro-spec.
4. **Dispatch** per the parity spine (§2.4 unchanged: TaskCreate, worktrees, sonnet spawns as above).
5. **Judge what comes back from artefacts:** the report's confirmed-cause evidence + harness output + after-state. For cosmetic acceptance the **Boss's eyes are the cheapest, best judge** — end visual loops with the Boss looking at the panel, not with Fable vision tokens.

## The escalation ladder (descend ONLY when a rung fails)

| Rung | What | CEO context cost |
|---|---|---|
| ① **Hypothesis dispatch** (default) | diagnosis table from priors; dept discriminates | zero code |
| ② **Dept diagnosis** | table exhausted → the dept (which has now read the code) proposes its own root cause + evidence; CEO sanity-checks the 5-line report against intent | zero code |
| ③ **Commissioned read** | Explore/subagent on a cheap model carrying a **sharp discriminating question** ("dump the row container's computed flex props"), conclusions only. Direct `Read` = bounded excerpt (offset/limit), ONLY when exactness is load-bearing and a relay might garble it | conclusions only |

Rung ① fits UI drift, styling, copy, config-shaped bugs, interface specs. Deep cross-module bugs and novel architecture live at ② and ③ — expect that, don't force ①.

## Boundaries (unchanged from parity)

You still never: implement · run suites · hand-edit the board for completions · skip or self-approve 审查 · gatekeep the Boss. 报告即停, the Boss Board, 红线 and the 督察's independence read exactly as SKILL.md writes them.
