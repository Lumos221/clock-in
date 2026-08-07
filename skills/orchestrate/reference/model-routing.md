<!-- SINGLE SOURCE OF TRUTH for model + effort routing. Everything else POINTS here (SKILL.md ·
departments.md · teammates.md · dispatch-artefacts.md · templates · recruit) and MUST NOT restate a
rule. Change routing here; the pointers don't move. -->

# Model and effort routing

**Two dials, two questions.** When a run comes back wrong, Anthropic's own diagnosis is: did it not *know* enough (raise the model), or not *try* hard enough (raise the effort). Route by that split before the task runs, not after it fails.

- **MODEL** = how much judgment the task leaves open — what must be *decided* that the spec doesn't say.
- **EFFORT** = how much search before it is safe to commit — how far to look before answering.
- **CAPABILITY** (dial 3) = what the seat must be *able* to do. Not a preference; a hard filter.

They are independent. A precisely-specified task can still need a long search (find the one call site in 400 files); an under-specified one can be answered in a sentence (which of these two designs). Set each from its own question.

## Look it up, then ask whether this card is the usual card

`docs/board/routing.json` carries the default per **部门 × task class**. **recruit seeds it** at roster build (it has just read every dept's standing work); **the CEO edits it directly** after that — it is a small JSON file, and a table only one pass may touch is a table that rots between passes.

**The CEO's per-card job is classification, not derivation** — and classification includes noticing that this card is not what that desk usually gets. On a hit, follow it. On an exception, override at dispatch and **record it on the card**. "No need to think" ≠ "not allowed to think"; capability constraints cannot be overridden at all.

- A homogeneous 部门 needs one `default` row. One with distinct work kinds (Legal: finding vs judging) splits by task class. **≤3 classes per 部门.**
- **A task class is a label on the CARD, not a second desk.** `Legal` + `judge` is still 法务部, still handle `Legal-<卡号>` — the class picks the tier, it does not mint a seat. Name it on the spawn the way you name the other dispatch facts: `class=judge`, same `=` as `effort=`.
- Git-tracked, so any terminal reads it and the Boss Board renders it.

**Both dispatch paths read it, and only the silent case is blocked.** `bridge dispatch` looks the row up and applies it. Internally a spawn guard compares the row against the brief's pin **when the spawn names no model** — the case nobody catches, where the seat comes up a tier under what the work needs and looks correct. **A spawn that names a model always passes**: naming a tier is the decision, and refusing it would bill you for the judgment this rule grants you.

```json
{
  "version": 3,
  "default": { "model": "sonnet", "effort": "high" },
  "departments": {
    "Legal": {
      "default": { "model": "sonnet", "effort": "high" },
      "task_classes": {
        "info":  { "model": "sonnet", "effort": "medium" },
        "judge": { "model": "opus",   "effort": "high" }
      }
    }
  },
  "seats": { "Vera": { "serves": ["RnD"], "model": "deepseek-v4-flash", "effort_cap": "high" } }
}
```

**Seat identity and capabilities live in `docs/board/seats/*.json`, never here** — routing.json says which seat serves which 部门 and at what tier; the registry says what that seat can do. One fact, one file.

## Dial 1 — MODEL

| The task | Model |
|---|---|
| **Fully specifiable in advance** — a deterministic script could do it: codemod at named sites, apply a literal diff, fill a template field-for-field | **`haiku`** — the model stands in for the script |
| **Specified, but decisions remain** — edits you can describe precisely, questions about code already in context | **`sonnet`** — the workhorse |
| **Under-specified, or coherence across many files, or being wrong is expensive to unwind** — architecture, subtle bugs, unfamiliar domain | **`opus`** |

**Any doubt → up one tier.** Under-powering a role buys a 审查 bounce and a rework, which costs more than the tier you skipped and delivers later.

`fable` is not on this dial and you never route to it. Two situations are worth *asking* the Boss about, below.

The middle two rows are Anthropic's published Claude Code split; the `haiku` row and the doubt rule are ours.

## Dial 2 — EFFORT

Effort governs **all** tokens — thinking, tool calls, text. Lower effort means *fewer tool calls*, so it is the dial for "how far should this look" and the wrong dial for "how hard is this to get right".

| Level | Anthropic's use case | Ours |
|---|---|---|
| `low` | simpler tasks needing speed and lowest cost, such as subagents | lookups · classification · a mechanical write path |
| `medium` | agentic tasks balancing speed, cost, performance | bounded implementation against a spec |
| `high` | complex reasoning, difficult coding, agentic tasks | **the default for anything open-ended** |
| `xhigh` | long-running agentic work (30+ min), million-token budgets | deep derivation where being wrong is expensive |
| `max` | the deepest possible reasoning | the Boss's word, on a named task |

`high` is the default on Opus 5 and Sonnet 5. Start there and move on evidence — up for demanding agentic work, down "liberally as your primary control for token cost" where evals show quality holds.

**Detection work caps at `high`.** Review, bug-finding, audit — anything scored on what it *catches* — does not improve monotonically. CodeRabbit measured Opus 5 at `xhigh` on their review bench: precision **35.2% → 39.3%**, known issues caught **61.1% → 55.2%**, **4× the nitpicks**. A gate is a recall instrument; an 审查官 that misses a defect has failed at its only job. Raising it is a mistake dressed as rigour.

**Set it once per seat and hold it.** Changing effort mid-conversation invalidates the cached prefix, so the seat re-reads its whole history. A seat is spawned per card, so choosing at spawn IS choosing for that card.

## Dial 3 — CAPABILITY (hard; never overridden)

| Requirement | Rule |
|---|---|
| Multimodal — mockups, screenshots, image I/O | must route to a Claude-family seat; `deepseek-v4-flash` has none |
| High agentic depth | flash allowed, effort capped `high` |
| Architecture · under-specified · deep debugging | `opus` (the top tier you may route to on your own) |

Capabilities are **self-reported** in `seats/*.json` and **audited by the 督察 at roster audit** — models drift after upgrades; a self-report is not trusted forever.

## Who runs on what

| Seat | Model | Effort |
|---|---|---|
| **CEO** (main session) | the Boss's | the Boss's |
| **部门 head** (teammate) | `sonnet` baseline; `opus` where the card is judgment-heavy | **inherits the CEO's — see below** |
| **法务部** — owns the 红线 | `sonnet` to *find* the law, `opus` to *judge* it | inherited |
| **审查官 · 督察** (one-shot) | `opus` | `high` — never higher (detection cap) |
| **experts** `Prof_` · `Spec_` (one-shot) | by dial 1, on the expert's actual work | by dial 2 |
| **书记处 Registrar** | `haiku` | n/a — no effort ladder |
| **staff** (the subagents a head spawns) | by dial 1, per piece | by dial 2, per piece |

- **Nothing in this org branches on the CEO's own tier.** Your model is whatever the Boss started the session on; it sets no rules, unlocks no shortcut, and there is no second way to run the company hiding behind it. Don't go looking for your model, and don't reason from it.
- **Legal is the clearest case of dial 1.** Finding the law is a lookup. Judging it is a liability that cannot be bounced and redone the way everything else can. The brief pins the common case; **raising it for a judgment card is the CEO's call at dispatch** — a cheap head does not get to decide it is out of its depth.
- **The Registrar's `haiku` is an availability pin, not a cheapness pin.** It is the tier that still has its tools when the others are rate-limited, and the task desk is the org's single write-path. Do not "upgrade" it.
- **An expert's tier follows its work, not its prefix.** `Prof_` usually lands on `opus` and `Spec_` usually on `sonnet` because of what they are asked to do, not what they are called. A bounced expert re-runs one tier up; one wasted attempt is the cap.
- **Staff top out at `opus`.** A `haiku` bounce → redo on `sonnet`, never retry `haiku`.

## How each dial actually reaches a seat

**The path, not the role, decides.** The same 部门 brief is a one-shot without `name:` and a teammate with it.

| Spawned | Model | Effort |
|---|---|---|
| **no `name:`** — staff · expert · 审查官 · 督察 · a 部门 one-shot | `model:` in the file, or on the call | **`effort:` in the file, or on the call — works** |
| **with `name:`** — a 部门 teammate | `model:` in the brief, overridable on the call | **cannot be set; the seat takes the LEAD's live level** |

So write `effort:` in every brief: it is live on the first row and inert on the second. On the teammate path the spawn drops it (as it drops `skills` and `mcpServers`), and an `effort` *parameter* on `Agent` is accepted, discarded, and never shown to a hook.

> **The CEO's own `/effort` is the round's level.** Set it before a batch of dispatches, not during. That is currently the only lever that reaches a teammate.

`orchestrate-effort <seat> <level>` sets one running seat, at a price: the level enters the rendered prompt, so the seat re-reads its history, **and the command queues behind the seat's current turn** — a dept's first turn IS its card, so it lands after the work it was meant for. Treat it as a mid-life correction on a long-running seat, never as spawn configuration. (Spawn-time per-seat effort is **suspended** for exactly this reason; `effort=<level>` in a spawn description is recorded, not applied.)

**Never type `/effort` into a pane by hand.** It writes the level into the machine-global `~/.claude/settings.json` on its way past, re-defaulting every future session. `orchestrate-effort` captures that value and puts it back.

## The gradient — a head's tier and a head's freedom move in opposite directions

Two stages inside each 部门: the **head** plans its slice and writes per-piece specs, **staff** do the typing, the head reviews and reports up. Most output tokens should land on staff; a head whose own share stays high is not paying off the split. (Floor: a one-line edit isn't worth a subagent round-trip.)

How much a head may *decide* is set by the gap between its tier and the CEO's:

- **A head at the CEO's tier must be handed method, and then the CEO cannot gate it** — with a peer on the other end there is nothing to meaningfully audit, and the CEO degrades from judging into routing.
- **A cheap head must be handed specs, and then the CEO can gate it.** The echo table, the 诊断 table and piece-level specs are what "handed specs" looks like written down.
- **There is no configuration where a head is both cheap and free.** That combination is the one to watch for.

Re-pinning a head to `opus` buys craft and costs the gate: do it where a dept's standing work is genuinely judgment-heavy, and expect to owe L2 more scrutiny for as long as it runs.

**Low effort is not licence to widen a head's freedom.** Effort buys search depth; the gradient governs judgment scope.

**Downward is the head's call. Upward never is.** A head spawns cheaper staff for grunt work inside its own task, and needs nobody's permission. A head that hits a judgment call **above its own tier hands it to the CEO** — it does not commission an expert to think for it and does not decide anyway. Expecting a cheap head to notice it is out of its depth *and* correctly commission its own replacement is expecting the judgment we just said it lacks.

## `fable` — you never route to it, you ask

**Fable is the Boss's to spend, not yours to route.** It is weekly-capped, that cap is shared with everything else they run on it, and a spawn that eats it is invisible until the cap is already gone. So the tier is theirs to approve, every time. What you decide is only whether the question is worth putting in front of them.

**One situation is worth asking about. Nothing else is.**

| Situation | What you would be asking for | The bar (both halves) |
|---|---|---|
| **Ceiling bounce** — a task already on `opus` bounces again on **competence** | the **producer**, a fresh spawn at fable, **never a resume** | `opus` has actually run and failed **and** the bounce is competence, not a fixable miss. "This looks hard" is not a ceiling. |

**The 督察 stays on `opus`, whatever it is looking at.** A 复盘 after repeated 封驳 is detection work, and detection is where the effort cap already applies: what a review misses is what it costs you, and reaching for a scarcer tier buys no recall. Its verdict is a root cause plus a fix, not a design — nothing in that job needs the tier the producer might.

**How to ask.** One `@BOSS[<dept>#<task_id>]` line naming what you would spawn, which bar it clears, and **what you will do instead if they say no**. Then get on with the rest of the round: an ask is not a reason to park work they never asked you to hold.

**Their word, and only their word, unblocks it.** Approved → spawn once, and name that spawn in your report. Refused, or not answered yet → run the fallback you already stated: `opus`, or a re-scope (督察 verdict ③).

**One attempt per approval, ever.** A fable bounce ends the ladder — next is a re-scope or a second trip to the Boss, never a second fable spawn on the same approval. **Unavailable → report it and fall back to `opus`, never silently substitute.**

**A tier they pinned themselves is already their word.** A 部门 whose brief carries `model: fable` was designated by them, so spawn it without asking again — and **still name it in the report**. They should never learn of a fable spawn from a bill.

**`fable` never appears in `routing.json`.** The table is a standing default the CEO applies without thinking; this tier is the one that must never be spent without thinking. Their two paths in are a brief pin and a per-card approval.

**Mechanically held.** `pretool_spawn_guard` blocks any spawn carrying `model: "fable"` unless the same call carries the literal string **`BOSS-APPROVED-FABLE`**. The guard reads the marker, not their mind: **write it only on a spawn they actually approved.**

## Escalation — how, not just when

A running teammate's model **cannot be changed** (`/model` is human-operator-only; model is fixed at spawn). To move a task up a tier: finish its handover → stop the agent → **spawn fresh at the higher tier**, never a resume. A **competence bounce** warrants it; a **fixable miss** does not. **Never route by a worker's self-reported confidence** — escalation is judged externally, by the CEO at spawn or by the 审查 bounce.

## The menu — verify before trusting

Route by **alias**; it resolves to the current best-in-tier snapshot, so routing doesn't rot when snapshots move. $/MTok in / out.

| Alias | Snapshot | $ in/out | Knowledge to | ctx / max out | Effort |
|---|---|---|---|---|---|
| `haiku` | Haiku 4.5 | 1 / 5 | Feb 2025 | 200k / 64k | **none** |
| `sonnet` | Sonnet 5 | 3 / 15 (intro **2 / 10 until 31 Aug 2026**) | Jan 2026 | 1M / 128k | all five, default `high` |
| `opus` | Opus 5 | 5 / 25 | **May 2026** | 1M / 128k | all five, default `high` |
| `fable` | Fable 5 | 10 / 50, **slower** | Jan 2026 | 1M / 128k | all five; thinking always on; weekly-capped |
| `deepseek-v4-flash` | DeepSeek-V4-Flash-0731 | 0.14 / 0.28 | — | 1M | capped `high`; **no multimodal** |

- **`opus` knows more recent things than `fable`** — May 2026 vs Jan 2026, four months of library and API drift. For a coding org that is a real argument for `opus`, separate from price.
- **Token counts compare directly across `sonnet` · `opus` · `fable`** (one tokenizer, ~555k words/1M tokens vs ~750k on the 4.6 generation). **A cost baseline measured on 4.6 under-counts by ~30%** — re-measure, don't scale.
- **Two rot dates:** Sonnet's intro price ends **31 Aug 2026** (the default gets 50% dearer, no code change). **Opus 5 draws a separate rate-limit bucket from the Opus 4.x pool.**
- Pinning a full snapshot ID works but buys nothing — the alias already lands on best-in-tier at the same price. **Snapshots or prices move → edit here, pointers don't.**

## Sources — re-read before changing a rule

- Anthropic, **Effort** — `platform.claude.com/docs/en/build-with-claude/effort` (levels, per-model recommendations, the cache warning).
- Anthropic, **Claude Code effort level and model selection** — `claude.com/blog/claude-model-and-effort-level-in-claude-code` (know-enough vs try-hard-enough; effort as a standing preference).
- CodeRabbit, **Claude Opus 5 benchmark** — `coderabbit.ai/blog/opus-5-model-review` (the precision/recall/nitpick trade behind our detection cap).
