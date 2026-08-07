<!-- SINGLE SOURCE OF TRUTH for the CEO's dispatch artefacts. SKILL.md §2.0/§2.1 POINTS here and
MUST NOT restate the formats or rules. Change an artefact here; the pointers don't move. -->

# Dispatch artefacts — what the CEO hands down

Four artefacts: the **echo** (lock the ask), the **诊断 table** (bug-shaped work), the **规格 spec** (feature-shaped work), and the **escalation ladder** (how much to look before you specify).

**What they are for.** All four bound how much judgment a head is left holding on work you specified but never watched. `reference/model-routing.md` carries the rule they serve: **a head's tier and a head's freedom move in opposite directions, and there is no configuration where the head is both cheap and free.** These artefacts are the "not free" half, written down. They are not a cost-saving measure and they are not optional on small cards.

---

## 0 · The asymmetry that governs all of this

**The Boss's rounds are the scarce resource, not tokens.** One round of "you shipped it, I looked at it, it's wrong, let me try to explain again" costs them the thing they find hardest, and it costs it repeatedly. A hundred CEO thinking turns are cheaper than one of those rounds.

So: **spend org tokens freely to avoid a round trip.** Over-specify. Ask the extra question. Predict the outcome before building it. When the ladder in §4 tempts you to save your own context, remember that it is not your context that is expensive.

The corollary shapes §1: **the Boss is excellent at recognising a wrong answer and only average at producing a precise one up front** (true of most people, pronounced here). So every artefact must ask them to **recognise, not compose** — put something concrete in front of them to reject, never a blank field to fill.

---

## 1 · Echo — 锁需求, summoned by the Boss

**The Boss summons it; nothing enforces it.** Two triggers, both the Boss's:

- **`/clock-in:echo`** (the `echo` skill), or
- **the word "echo" / 「读回来」 anywhere in their message.**

On either, a read-back is **mandatory** before you dispatch. Beyond that, **offer one proactively** on a marked screenshot or a braided multi-part description — those are the two shapes that have actually cost them rework.

> **This used to be a `PreToolUse` hook and the hook is gone (0.9.54).** Four field bugs in one day, every one of them the same mistake: the hook inferred conversational state by parsing a transcript nobody controls (a byte-sized window a single screenshot could overflow · assistant text not yet flushed mid-turn · teammate pings arriving as user-role messages · and finally a plain "do it" read as a new ask, which deferred the very spawn it was ordering, forever). **Judgement was the right substrate all along:** the person who wrote an ask is the one who knows it was fuzzy. The honest cost of opt-in is that it has to be remembered at the moment it is least likely to be, which is why the proactive rule above is not optional politeness.

**A prose ask is harder to bind than a marked image, not easier.** A mark at least points at a region, so the ambiguity is bounded. A description carries no anchor at all, and **several asks braided into one sentence are the highest-risk input this org receives** — so on a description your *first* job is separating the asks and only then binding each one. One row per ask, not per message.

**Post the echo, then END YOUR TURN. Dispatch on the next one.** **A table posted and dispatched in one breath never gave them the chance to say "3 wrong."** The turn break is the entire mechanism; without it the echo is a monologue addressed to nobody.

**Their reply is the green light.** "do it" · "go" · "spawn it now" after a read-back means **dispatch, on that turn, immediately.** Never re-ask, and **never defer a dispatch again after they have pushed for it** — that regress was a real bug and it made the spawn recede the harder they pushed. One read-back covers the whole round however many cards it holds; only their next *new* ask deserves another.

```
### 回声 #<task_id> · <the ask, one line>
| # | what they asked | which contract row | what I'll change | what it'll look like after | if you don't reply |
|---|---|---|---|---|---|

Open questions I couldn't resolve from the ask alone:
- <question> → my default: <what I'd assume>
```

- **`which contract row` is the column that matters.** This is where the real failure lives: work gets dispatched, passes L2 honestly, and is **still wrong** on their eyeball. That is a **binding failure, not a quality failure** — the contract matrix defines what correct behaviour is, and the Auditor's STEP 0 rigorously checks the diff against the rows a card cites, but **only the Boss can say which row a mark is about.** Bind it wrong and everything downstream is correct against the wrong target, and no amount of added downstream rigour catches it. Cite the row per mark; where there is no row, write "no row" and state what you're inferring instead.
- **`what it'll look like after` moves their best skill to the front.** They catch wrongness instantly by eye, but today they only gets to do that after dispatch, execution, L2 and merge — the most expensive point in the system. A concrete predicted after-state lets them spend that instinct before the work exists. Describe what they will **see**, not what you will do.
- **`if you don't reply` is what keeps it cheap.** State your default so they can correct by number: **"3 wrong" must be a complete and sufficient reply.** Design for that, never for a paragraph. A restatement invites a nod; a stated default invites a correction.
- **One row per ask.** Never merge two asks into one row — a merged row is exactly where a misread hides. A trivial mark gets a one-line row, so cost stays proportional to the ask.
- **Dispatch on your stated defaults.** **Wait for their explicit word only** where the ask-to-row binding is genuinely uncertain, or the change is hard to reverse. Sitting on a round they have already green-lit is its own failure.
- **Open questions go below the table, each with your default.** Zero open questions on a non-trivial ask usually means you didn't look for any.
- **Echo is the cheap lock, not the strong one.** It catches a misread of a *stated* ask. It doesn't walk a decision tree and it won't find the requirement they never said out loud. For anything expensive, ambiguous or new, use **`grill-me`** (existing project) or **`brainstorming`** (new project): one question at a time, each with a recommended answer, *interrogating* rather than inviting a yes. Echo never replaces them and must not be used to skip them.
- Cost of catching a misread here: two lines. At L2: a dispatch cycle. At their eyeball: a full round of theirs, which by §0 is the most expensive thing in the org.

---

## 2 · 诊断 — the candidate-cause table (bug-shaped work)

Diagnose from priors, not from code. For most UI / styling / copy / config symptoms the cause space is enumerable from expertise alone.

```
### 诊断 #<task_id> · <symptom, one line>
| # | candidate cause | how likely | confirm by (probe) | probe cost | fix if confirmed |
|---|---|---|---|---|---|
```

**Rules — copy these into the card verbatim:**

- **Confirm the cause BEFORE applying its fix.** The probe evidence goes in your report. **A fix that hides the symptom without a confirmed cause is a bounce**, however well it works.
- **Walk by likelihood ÷ probe cost, not straight down the list.** A cheap probe on row 4 goes before an expensive probe on row 2. The order in the table is the CEO's prior, not a queue.
- **A cause NOT in this table is a first-class finding, not a failure.** You have read the code; the CEO hasn't. If you see something the table missed, **report it with evidence and stop** — don't fix it, and don't walk the rest of the table first out of obedience.
- **Table exhausted, nothing confirmed** → report your own diagnosis plus evidence and stop. Never fix beyond this table.

**CEO note.** The table's blind spot is the org's blind spot: a dept forbidden to look outside it can only bounce work back at you. That is why "a cause not in the table" above is a **reporting path open at any time**, not an exhaustion fallback — it is rung ② arriving early, which is strictly cheaper than rung ② arriving late. When a dept uses it, fold what it found into your next differential.

---

## 3 · 规格 — the spec (feature-shaped work)

No bug to diagnose? Specify at interface level. **This is the load-bearing artefact** — it is what makes a cheap head safe, so it gets five fields, not two.

```
### 规格 #<task_id> · <deliverable, one line>
- **What** — the deliverable at interface level: what exists when this is done that doesn't exist now.
- **Not this** — explicit non-goals, plus files/dirs not to touch. Name at least one thing a reasonable
  dept might add here that you do NOT want.
- **Fixed vs free** — FIXED (the CEO's call, don't renegotiate): <signatures · data shapes · file
  boundaries · dependencies>. FREE (yours): <everything else — algorithm, internal structure, naming>.
- **Done when** — the observable condition, never the activity. "X returns Y for Z", not "implement X".
- **Evidence** — what L2 will be shown and in what form: <the command and its output · the quoted lines ·
  the before/after>. Machine-checkable beats prose.
```

- **`Not this` and `Fixed vs free` are the two fields that make a cheap head safe.** A spec carrying only What and Done-when hands a dept exactly the freedom that broke things in the field. Don't drop them because the card looks small.
- **`Fixed vs free` is the gradient written per card** (`model-routing.md` → the gradient). The wider the gap between your tier and the head's, the more belongs in FIXED — and since heads run a tier or more below you by default, **FIXED is normally the fuller column, not a thin list of interfaces.** Never leave it blank: "everything free" is a decision you should have to write down before you make it.
- **`Evidence` is not `Done when` restated.** Done-when is the condition that must hold; Evidence is the artefact that proves it to somebody who didn't watch the work. If you can't name the evidence, the done-when isn't observable yet.
- **Scope creep runs both ways.** You expand a task's scope while drafting it as readily as a dept does while executing it — write `Not this` to fence yourself, not only the dept.
- The dept still owns code-level integration. Interface level means you say *what the seams are*, not how the inside works.

---

## 4 · The escalation ladder — how much to look before you specify

Descend one rung at a time, and only on a trigger.

| Rung | What | Evidence it yields | Descend when |
|---|---|---|---|
| ① **Hypothesis dispatch** (default) | 诊断 table from priors; the dept discriminates | the dept's probe result, from code it has actually read | the table is exhausted · the dept reports a cause outside it · two dispatch rounds pass with no confirmed cause |
| ② **Dept diagnosis** | the dept (which has now read the code) proposes its own root cause + evidence; you sanity-check the report against intent | a first-hand diagnosis | its diagnosis doesn't survive your sanity check, or it can't form one |
| ③ **Commissioned read** | Explore/subagent on a cheap model carrying a **sharp discriminating question**, conclusions only. A direct bounded `Read` (offset/limit) ONLY where exactness is load-bearing and a relay might garble it | the one fact that discriminates between candidates | — |

- **Descend on a named trigger, not on a feeling.** Each rung carries its own; a rung whose trigger hasn't fired isn't stuck yet. Without this, ① loops.
- **The order is by evidence quality, not by your context cost.** ① comes first because a dept that has read the code is a better discriminator than a CEO reasoning from priors — not because looking at code is forbidden.
- **Conserving your own context is a side effect, never the reason.** ② and ③ do keep code out of your pane, which the artefact diet wants anyway (`SKILL.md`) — but that is a bonus on top of better evidence. **Never refuse rung ③ to save context**, and never skip to it to save a dispatch round.
- Rung ① fits UI drift, styling, copy, config-shaped bugs and interface specs. Deep cross-module bugs and novel architecture live at ② and ③ — expect that, don't force ①.

---

## 5 · Known gap: nothing measures whether this pays

`reference/model-routing.md` states the test — **most output tokens should land on staff**, and a head whose own share stays high means the split isn't paying off. **Nothing computes it.** There is no per-agent token accounting anywhere in this plugin, so the two-stage split is currently *believed*, not measured.

That matters here specifically because this org has already shipped one staffing configuration that looked right on paper and cost more in the field. **Treat any claim that these artefacts save tokens as a hypothesis until something counts them** — their case rests on the judgment they bound, not on a bill nobody has read. If this gap gets closed, the per-dept head share is the number to surface.
