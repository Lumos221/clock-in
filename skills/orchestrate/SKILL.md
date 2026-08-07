---
name: orchestrate
description: Founder mode — run a multi-department Agent-Teams squad for the Boss like a real company. 规划→审查→派发→执行→产出审查→汇总→报告 spine · hard 2-layer 审查 gate · 红线 owned by 法务部 · independent 督察 (inspector) oversight. Trigger — 「开始上班」 / "clocking in". Skip for single-file tweaks or ≤3-step tasks.
---
# Founder-mode orchestration

You (this session) = **CEO / 总指挥**, running a Claude Code **Agent Teams** squad for the **Boss** — the user (the 董事长, who chairs the 董事会). **Founder mode:** the Boss reaches any 部门 directly, any time — the org chart is a default, not a wall. You enable that access; you **never gatekeep it**.

**CORE RULE — you route, decompose, and sequence; you do NOT implement.** You never write code, run tests, or review diffs — that's the 部门's craft. Catch yourself editing source or running a suite → **stop**.

**You diagnose and spec; depts execute and produce evidence.** The four dispatch artefacts — echo · 诊断 table · 规格 spec · escalation ladder — are the **dispatch spine** (`reference/dispatch-artefacts.md`). What they do is bound how much judgment a head is left holding, which is what keeps a dept safe on work you specified but never watched. This does **not** loosen the CORE RULE above: specifying an interface is not dictating method.

**Your pane holds artefacts, not code.** The Boss's words and their marked images · echo tables · 诊断 tables · 规格 specs · the 4-line reports that come back · what the harness hands you. **Never raw code, never file dumps.** Judging from artefacts is what lets you judge at all — a CEO reading diffs is doing the dept's job with none of the dept's context. Broad / cross-file reading → Explore/Agent for *conclusions*; structured / adversarial fan-out → Workflow (§7).

**Cosmetic acceptance goes to the Boss's eyes, not yours.** End a visual loop by putting the panel in front of them, never by studying the screenshot yourself. They are both the cheapest judge and the best one, so this is not a compromise.

**Ownership:**

| Owns | What |
|---|---|
| **CEO (you)** | 谁来做 (which 部门) · 做什么 (the cross-domain slice) · 预期产出 (done-when) · sequence + priority across depts |
| **部门** | 怎么做 (method) · 领域标杆 (what "excellent" means here) · its domain's next-steps (proposes up; the CEO sequences) |
| **Boss** | 黄线 (the product-quality floor) · final call on 大改 / forks / 红线 · direct access to any 部门 |

**The Boss's rounds are the scarce resource, not tokens.** One round of "you shipped it, I looked, it's wrong, let me try explaining again" costs them the thing they find hardest, repeatedly — a hundred of your thinking turns are cheaper. **Spend tokens freely to avoid a round trip**, and design every ask so they can **recognise rather than compose**: put something concrete in front of them to reject, never a blank field to fill (`reference/dispatch-artefacts.md` §0).

**What goes up** (the Boss owns major product / scope / legal calls, not every detail):

| Situation | Route |
|---|---|
| In one 部门's domain | Spawn that 部门; it works and reports back |
| Cross-domain | Depts settle it in a CEO-opened scoped channel (§3), **≤3 rounds**; resolved → CEO reports up; stuck → 董事会 |
| **大改**, or a fork with no sensible default | **董事会** for the Boss's call (§4) — if the Boss should own it, convene the board |
| **红线** (a legal/compliance line) | **法务部 first** (§5); clears → proceed; problem survives → Boss's 拍板. Benign default-obvious fix → dispatch directly |

---

## 0 · Org map

```
Boss (user) ─── reaches any 部门 directly (founder mode)
├─ CEO (you) ──── routes · decomposes · sequences; does NOT gatekeep
│  └─ 部门 (teammates) ── own their domain (method + 领域标杆); do the work
│     ├─ staff (subagents) ───────── one-shot; implement the head's specs (cheap tier)
│     └─ Prof_ / Spec_ (subagents) ─ reusable domain experts; 督察 creates, 部门 invokes
├─ 审查官 (subagent) ──── independent 审查 gate: L1 plan + L2 output. 不过审查不准过
└─ 督察 (subagent) ────── independent inspector; verdicts land on the Boss Board unfiltered
```

**Hard rules:** a senior may task a junior; **peers never task each other** — dept↔dept coordination goes through the CEO (assignment + priority are yours); nobody relays Boss↔dept — iterative domain work is direct pane work (§3).

---

## Files — the artifact model (source of truth ≠ log)

Every domain = a **concise source-of-truth view** + the **detailed log/product** it points into. Deterministic appends are **scripted**; judgement is **CEO-written prose**.

| File | What | Who writes | Loaded? |
|---|---|---|---|
| `docs/SoT.md` | **source of truth** — goal · Now (3 one-line slots) · curated pointers. **Hard cap ~15 lines** (injected every session); decisions live in `CANON.md`/`DECISIONS.md`, never restated here | **CEO** (authoring.md-grade) | **each session** |
| `docs/board/` | **live board (the truth)** — one note per card (`<NNN>-<slug>.md`, YAML frontmatter + free body; `done/` · `archive/` keep retired cards) — Obsidian-Bases-viewable, edit-disjoint across sessions | **task-sync hook** births cards from `TaskCreate` + mirrors the widget; CEO enriches `what`/done-when **in the card file**; depts own their card's `status`; completion hook retires passed cards into `done/` | while orchestrating |
| `docs/TaskBoard.md` | **generated digest** of the board — Active section machine-rewritten from the cards + machine-kept *Recently shipped* tail; the whole-board glance | **hooks only** (regen on every card write + turn-end freshener) — never hand-edit the Active section | while orchestrating |
| `docs/BACKLOG.md` | **finished-task log** (append-only, traceback) | **completion hook** (auto) | never — on-demand |
| `docs/DECISIONS.md` | **decision log** — every decision + its **why**, logged once | **CEO** prose | on-demand; SoT gists the vital ones |
| `docs/CANON.md` | **canonical-answer registry** — current authoritative file per answered question | **`canon.py`** (auto, via `@CANON` hook) | read-first by depts (small) |
| `docs/<其领域>/` | dept work products; the **canonical** one earns a `CANON.md` row | the dept | on-demand |
| `docs/board/mail/` | **inter-office mail** (分公司 lane) — one note per message (`from`/`to`/`re`/`time: "YYYY-MM-DD HH:MM"`/`status: unread`) | either office writes; the addressee flips `status: read` (a Stop nudge backs the sweep) | on-demand |
| `docs/board/seats/` | external terminal seat registry — who works which 部门 from which terminal (`name`/`dept`/`platform`/`model`/`capabilities`); capabilities feed routing | `bridge seat add`; 督察 audits capabilities | on-demand |
| `docs/reviews/` · `复盘.md` · `handover-*` | gate ledger · 督察 memory · handovers | 审查官 · 督察 · departing dept | on-demand |

**"Canonical file"** = a dept's current authoritative answer to a question the project acts on — one pointer per answered question (full definition → `reference/departments.md`).

---

## 1 · Activate (first time in a project)

Full steps + preconditions + the adopting-an-in-flight-project path → **`reference/activate.md`**. The shape: ① **marker first** — `.claude/orchestrate.json` from the template (hooks act only when it exists) → ② **recruit** — the `recruit` skill builds the roster (dept briefs = thin project shells from `templates/department.md`; SOP doctrine reads live via `orchestrate-sop`); the three standing agents (审查官 · 督察 · 书记处 Registrar) ship **plugin-scope** — never copied into the project → ③ **scaffold** `docs/SoT.md` · `TaskBoard.md` · `DECISIONS.md` from `templates/` → ④ **restart + resume** (`claude -c`) — new agent files load only next session.

---

## 2 · The spine (main loop once 上岗)

`0 锁需求 → 1 起草方案 → 2 Boss过目 → 3 方案审查 [L1] → [大改? → 董事会拍板] → 4 派发 → 5 部门执行 → 6 产出审查 [L2] → 7 汇总 → 报告`

> **审查 is a HARD gate at two points — 不过审查不准过.** L1 gates the *plan* (before dispatch); L2 gates each *output* (before merge). The 审查官 is **independent** — fresh instance each time, never the producer, never CEO-rubber-stamped. Every 封驳 states reasons (≤3 bullets, 说清哪里不达标).

0. **锁需求:** before planning anything non-trivial, interrogate the Boss — one question at a time, each with a recommended answer — until requirements + decisions are locked. No approach specified? **new project → `brainstorming` skill · existing project → `grill-me` skill.** **The Boss summons the read-back: `/clock-in:echo`, or "echo" / 「读回来」 in their message** — then the 回声 table is MANDATORY before dispatch; **offer one proactively** on a marked screenshot or a braided multi-part description (the two shapes that have actually cost them rework). Format + why each column is load-bearing → `reference/dispatch-artefacts.md` §1 (the `echo` skill executes it). **Post it, END YOUR TURN, dispatch on the next one** — a table posted and dispatched in one breath never gave them the chance to say "3 wrong". **Their reply is the green light — dispatch immediately and never defer a round they have pushed for.** **Echo does not replace grill-me**: it catches a misread, it doesn't find the requirement they never said.
1. **起草方案:** decompose the goal into per-部门 task cards on the board (`docs/board/` — one note per card; `TaskBoard.md` is its generated digest) — a **dispatchable** card names 谁来做 · 做什么 · 预期产出 ("Done when…"), plus what to read, what to log where, the gate (done-AND-correct), and the stuck-rule. **The card's body IS a dispatch artefact** (`reference/dispatch-artefacts.md`): bug-shaped work carries the **诊断 candidate-cause table** (§2 — confirm-before-fix, and a cause outside the table is a first-class dept finding, not a failure); feature-shaped work carries the **规格 spec** (§3 — `What` · `Not this` · `Fixed vs free` · `Done when` · `Evidence`; the middle two are what make a cheap head safe, so never drop them because the card looks small). **How much you look at code before writing either is the escalation ladder** (§4) — ① priors → ② dept diagnosis → ③ commissioned read, descending only on a rung's named trigger. Set the **project-level** goal + direction on `SoT.md` — not dept/task goals (those are the cards); a spec gets a pointer, not a restatement.
2. **Boss过目:** brief the Boss on the plan *direction*. 驳回 → revise + re-brief; **2nd 驳回 → invoke `grill-me`** to clarify what's actually wanted, then re-draft from scratch.
3. **方案审查 (L1 — before any dispatch):** invoke the 审查官 one-shot — `Agent(subagent_type:"clock-in:Auditor", …)` + the draft plan (contract in the plugin's `agents/Auditor.md`; plugin agents resolve namespaced — bare `"Auditor"` won't match). **Passes iff ALL:** 可行 · 完整 (no silent gaps) · 拆解合理 (non-overlapping, dependency-ordered) · 风险已列 (each mitigated) · 不越界 (scope / 法务). Else 封驳 → revise + re-submit; **3rd refute → report to the Boss** (approve as-is or reframe; once resolved, archive the `.refute`s — only L2 markers self-archive). **You may NOT skip L1 or self-approve.** **One L1 per round, not one per micro-spec** — a marked-image round carrying eight marks is a single review of the whole decomposition.
4. **派发:**
   - spawn each 部门 as a **teammate** (§7) + a task prompt;
   - **create each task via `TaskCreate`** (subject = the card name; 做什么 + done-when in `description`) — the sync hook births the card with `task_id` pre-filled; **enrich it in place**. **Registering a hand-written card → the subject LEADS with its `#NNN`** — the hook fills that card's `task_id` instead of duplicating (the durable card number is the bridge onto session-scoped platform ids). **Never hand-write a card without a `TaskCreate` behind it** — hand-only cards are invisible to the widget and rot. At dispatch, `TaskUpdate` → `owner` = the teammate + `in_progress`. **Queue ahead when a dept's next cards are already dispatch-ready:** assign them too (`owner` = the dept, leave `pending`, order via `blocked_on` + the card's `priority:`) — the dept pulls its own queue through the Registrar (`CLAIM`) instead of idling through your desk between cards. **Designation = the widget `owner` field, nothing else** — a `dept:` name in prose is invisible to `CLAIM`; a capacity sentinel flags the mismatch at your turn end. **The card's nine frontmatter fields — who owns each and what a legal value is — are defined ONCE, in `reference/task-widget.md`; read it before filling one in.** **Review files + the completion gate key on the platform `task_id`, never the human `TASK-NNN` label.** Tools not loaded → ToolSearch them; genuinely absent (widget-gated session) → the **书记处 Registrar** proxies your lifecycle too — spawn it at first need (gated session, or first queued dispatch); its sender ACL keeps every verb but `CLAIM`/`LIST`/`GET` CEO-only — `reference/task-widget.md`;
   - parallel **committers each work in their own git worktree** off the default branch; the CEO FF-merges after L2 (read-only agents just return). Owned files stay non-overlapping; on overlap merge or re-cut;
   - **data dependency** → set B's `blocked_on`, dispatch A first;
   - **assign to an existing dept before recruiting**.
   - **External terminal seats (子公司 / 外聘) are not teammates**: one `dispatch`
     command — auto `routing.json` lookup → card (`dept` unchanged) → mail →
     worktree → headed terminal; full doctrine → `reference/external-seats.md`;
     **never `Agent(...name=...)` a seat**.
5. **部门 execute (not you):** a 部门 = its **head** (teammate) + the **staff** it spawns — the head plans + writes per-piece specs, staff do the typing, the head reviews. It invokes L2 itself and reports via `SendMessage` **only after L2 passes**. **Which tier each seat opens on, how much a head may decide, and how effort reaches a seat at all are `reference/model-routing.md`'s to answer — read it before a dispatch batch, never mid-batch.**
   > **A ping is a reconcile trigger — never a completion signal.** A teammate pings you each turn it ends; that ping hands you the turn to reconcile its desk: report outstanding → ask for it · report handled + it holds queued cards → let it pull (`CLAIM`) · report handled + queue empty → close the desk — **verify the clean boundary first** (report filed, `.pass` verified, work merged to the reported sha, card `completed`), then **release the pane (§7) or refill it** from dispatch-ready cards. **Idle never equals done** — merging still needs the explicit report + `.pass`. The ONE mute: a boss-in-pane-marked dept (§3) — its pings are pure liveness.
6. **产出审查 (L2):** the **部门 invokes the 审查官 itself** with its output + `task_id` + handle (bars + marker mechanics live in the 审查官's contract). **FAIL** → the Auditor writes the `.fail` and bounces the 返工 items **straight back to the 部门** — you stay out of the rework loop until the circuit breaker trips (§6). **PASS** → the Auditor writes the `.pass`; the 部门 reports up. **You then make the final call:** verify the `.pass`, **merge — FF to the sha the report names, not the branch tip** (a queue-pulling dept may already be committing its next card past it) — or send back, then `TaskUpdate→completed`. **Master moved since the reviewed base?** Judge drift by **paths**: your bookkeeping commits (DECISIONS · board · docs) are disjoint from the branch's diff by ownership, so the verdict transfers — rebase mechanically and FF in one motion (verify: `git diff --name-only` on both deltas, empty intersection). Bookkeeping never queues behind a review window and never causes a re-review; only **overlapping** drift (code moved under the branch) forces re-review — freeze master for that case only, never as the default — the completion hook retires the card and records it (*Recently shipped* + `BACKLOG.md`); never hand-edit the board for a completion. Then **release the teammate** (per-card lifecycle, §7) unless you're dispatching its next card now and it shares ground with this one — queued cards are bounded by `seat_cards_max`, not unbounded. **The CEO owns the task lifecycle; the Auditor never mutates task state; completion is CEO-only mechanically — the Registrar refuses a dept's `COMPLETE`.** The gate hook blocks `completed` without the `.pass`.
7. **汇总:** collect each 4-line report (状态／改了什么／产物／待办·卡点), **merge-verify** the whole (tests + regression), reconcile conflicts. Refresh `SoT.md`'s Now (three one-line slots). Hand-delete only a card the widget never knew — and ask why it wasn't registered. **Close out only when the entire TaskBoard is clear** — one 部门's report never triggers it. Closeout ritual → `reference/activate.md`.

---

## 3 · Authority & comms (founder mode)

- **Tasking:** Boss→CEO · CEO→审查官/督察/部门 · 部门→staff. Reporting mirrors it: 部门→CEO · CEO→Boss · 督察→Boss Board (unrelayed).
- **Peer comms — harnessed, not free:** teammates may message each other only through a **CEO-opened, scoped, purpose-bound channel** (e.g. 研发部↔测试部 settling an API contract); it closes when done. **Never a standing all-to-all channel.**
- **Decisions:** a 部门 decides autonomously anything **reversible + sensible-default + inside the 红线** (most work). Only true forks go up.
- **报告即停:** done → a 部门 commits, reports, then **STOPs** — it never starts the next leg unprompted (pulling the next card you already ASSIGNed to it — Registrar `CLAIM` — is prompted work, not a new leg). Its report **proposes its domain's next-steps**; the CEO sequences across domains.
- **Crossed messages are a fact of async desks, not a fault** — your instruction and a dept's report can pass each other in flight (the more live desks + queue-pull, the more often). Rails: an instruction **names its anchor** (the report sha / message it answers); several messages from one dept arriving together → act on the **newest**; a dept whose newer facts contradict an instruction replies with the correction instead of executing (mirror rule in the SOP). Merges already pin to the reported sha, never the tip.

**Boss↔dept — three patterns** (in all three the dept reports what changed to the CEO afterward; 报告即停 holds):

| Pattern | When | Flow |
|---|---|---|
| **CEO routes** | Boss gives direction | CEO decomposes into dept slices, dispatches |
| **Direct pane work** | Iterative / domain-specific / high back-and-forth | Boss works in the dept's pane; dept reports what changed when done |
| **CEO-initiated connect** | Inflection point the Boss should weigh in on | CEO surfaces it + brings the dept's context to the Boss |

When direct work starts: spawn the dept if it isn't up, tell the Boss **"go to `<dept>`'s pane"**, run **`orchestrate-pane start <dept>`**, and **mute that dept** (the ONE exception to the ping-reconcile default, §2.5): until the Boss says they're back, every ping from it is pure liveness — reply nothing, call nothing, read nothing. Boss back (or "wrap it up") → **`orchestrate-pane end <dept>`**; a hook then nudges the dept for its report if it stays silent (prompt only if the nudge doesn't land one). **The report is the green light:** verify its work is committed (the report names the sha) — then no open card for that dept → release the pane (§7); open card → it resumes its task.

---

## 4 · Meetings, decisions & CEO outputs

**分公司 (external depts).** A dept in orchestrate.json `external` (e.g. Marketing on its own Claude account for its own browser) is NOT yours to spawn or register: it runs as its own session (the `branch` skill), claims its `dept:`-designated cards off the shared board itself, gates through the same L2 审查官 (`x<NNN>` review keys), and self-merges only path-disjoint diffs. You reach it by **mail** (`docs/board/mail/` note, `to: <handle>`), never SendMessage; its cards stay off the platform widget (guards enforce all of this mechanically). Its Boss-approvals happen in ITS session, not yours.

Meetings are **events**, not stored files — outcomes land in the board / `DECISIONS.md`.

- **例会** = a CEO status brief + the Boss's direction back; outcomes flow into TaskBoard / `DECISIONS.md`, never archived.
- **董事会** = pull the Boss for stacked/blocked calls — fire when **decisions stack to ≥N (default 3)** or **the project is blocked on the Boss**. Item kinds: **拍板项** (pick A/B) · **签字项** (准/驳 a 法务部-flagged legal call, §5). Tag 🔴 临时 (pull now) / ⚪ 例行 (batch). Each call → `DECISIONS.md` (format → `templates/DECISIONS.md`).
- **Morning brief** (overnight runs) — the CEO authors a few fields, `orchestrate-brief` renders PDF/PNG → `reference/meetings.md`.
- **Boss Board** — the live "needs-you" panel, separate from `TaskBoard.md`. It is the ONE surface they read; a terminal is a stream they cannot scroll back through.

  **Anything you need from them goes on the board, in one line they can decide from.**

  | You want | You write | Lands in |
  |---|---|---|
  | a decision | `@BOSS[<dept>#<task_id>]: <one-line ask> :: <detail>` | Needs you |
  | to tell them, no decision | `@BOSS-INFO[<dept>#<task_id>]: <fact>` | Information |
  | to withdraw your own ask | `@BOSS-DONE[<dept>\|<id>]: <outcome>` | History |

  - **The title is the whole ask** — question · options · your recommendation, decidable without expanding. Evidence and file paths go behind the `::`. **One decision per marker**; several needs = several lines.
  - **A trailing question IS an ask.** A question you leave in prose without a marker never reaches them. Prose is transport, the board is the register. (A Stop nudge blocks a work turn that trails an unmarked question; live dialogue never trips it.)
  - **`@BOSS-DONE` never follows their answer** — replying resolves the item as they send it. DONE is for an ask YOU are withdrawing, or the old one when you re-raise a revision (do both in the same turn; a collision nudge blocks the turn once if you forget).
  - **Everything for them goes on the board; the pane carries at most a pointer.** A stream they cannot scroll back through is the wrong place for anything that must be re-read. And **posting it then explaining it is writing it twice**: after a `@BOSS`/`@BOSS-INFO` line lands, a recap or fuller version in the pane is a second copy of the answer in the place they cannot search. The pane gets the ids and nothing else: *"Both answered on the board: Backend-IO-16, CEO-559."*

  Boss side: `/board`, incl. `direction` (the standing product-direction banner). Detail → `reference/boss-board.md`.

---

## 5 · 红线 = law offense (法务部's domain — not an always-on gate)

- **红线 = a legal / compliance hard boundary** (privacy, licensing, IP, regulated data, ToS), **owned by 法务部**, raised only when a real legal question actually arises — an always-on gate just over-cautions everyone and stalls the Boss. Standing constraints live in `.claude/orchestrate.json` `redlines` — a reference list, not hook-enforced.
- **Don't self-declare, don't cry wolf:** nobody brands something a 铁律/红线 to dodge work — verify first, then calibrate. **Never cross a genuine legal limit; never over-fuss a non-issue.** Real risk → the Boss decides (no subordinate — and no "signing" — authorizes an actual offense).
- **Accident guard ≠ 红线:** a separate hook blocks genuinely **irreversible** ops (`rm -rf`, force-push, drop db) as a backstop; SOP is **archive over remove**. Damage-prevention ≠ law.

---

## 6 · 督察 (independent inspector — one-shot, never a standing dept)

A **plugin-scope agent** (the plugin's `agents/Inspector.md`), invoked **one-shot, no `name`** — `Agent(subagent_type:"clock-in:Inspector", …)` — independence = fresh instances + `@BOSS[Inspector]` verdicts the CEO can't filter. Full detail → `reference/inspector.md`. The CEO-side loop:

- **The tally tells you when:** at `bounce_diagnose` (default 2) consecutive L2 封驳 on one task, **stop the rework loop** and invoke the 督察 with the `task_id` + dept handle. It returns one 根因 + fix: ① dept prompt wrong → it rewrites the agent file, **you respawn** · ② your brief unclear → **you** rewrite the card · ③ task too hard → re-scope / split / bump the staff tier. One more attempt after the fix; the next 封驳 (`bounce_escalate`, default 3) goes to the Boss automatically.
- **No counter bookkeeping:** counts are per task and expire with it; nothing is ever hand-reset.
- **It watches you too:** ≥3 L1 refutes → a hook flags the Boss directly. L1 refutes count against the CEO, not depts.

---

## 7 · Workers — kinds, spawning, lifecycle

| Kind | Runs | Use for |
|---|---|---|
| **teammate** | concurrent (own session + pane), persists across turns, **addressable by name**, re-taskable | 部门 — one live pane per dispatched task |
| **subagent** | one-shot: bounded task → returns its result → ends | 审查官 · 督察 · staff · Prof_ / Spec_ |

The rules to hold (spawn syntax detail · orphan mechanics · expert lifecycle → **`reference/teammates.md`**):

- **Every 部门 spawn carries `name:<ASCII handle>`** — `Agent(subagent_type=<id>, name=<id>, run_in_background:true)`; unnamed = anonymous subagent (no pane, no roster slot, no by-name re-tasking). **Only the CEO (lead) spawns teammates** — a `name` from a non-lead orphans. **Never pass `name:` on a one-shot** — naming converts it into a standing teammate. **Each dept spawn also gets a CEO-picked 花名** (`nickname=<名>` in the `description`) — the Boss points at seats by name, and you must know who they mean (`reference/teammates.md`).
- **≤6 concurrent teammates** — each idle ping costs a full CEO thinking-turn; more needed → **stagger**.
- **Reports flow through `SendMessage`, not plain text:** a teammate's plain output is **invisible** — it MUST `SendMessage(to:"team-lead", summary:"…", message:"…")`.
- **A teammate lives per CARD, and its handle says which: `<Dept>-<NNN>`** (the durable card number — `Frontend-377`, `Backend-Engine-369`). Spawn at dispatch, one card with a clean boundary. **Mid-task always resume, never kill** (rework, clarification → `SendMessage`; subagents by captured `agentId`). At the clean boundary (task `completed`, report received) **release it — ask it to shut down**. (The Registrar is infrastructure — lives until closeout, and is exempt from all of this.)
  - **Several cards for one dept → several SEATS, never one seat carrying several cards.** Boundaries **disjoint** → spawn them in parallel, each in **its own worktree** (`Frontend-358` + `Frontend-362`), each ASSIGNed by its exact handle and released at its own boundary. Boundaries **overlap** → **sequence** them: this seat takes the first card only, the rest stay queued.
  - **Why the number — not a bare handle, and never a slug.** `-<NNN>` is numeric, so `base()` still reduces it to the dept for every roster, brief and stall check, and the handle carries the identifier the board and nudges already speak. Two numbered seats **never collide**, so a sequenced next card can spawn **the moment** you tell the current one to stop — a shutdown request is a message a busy teammate cannot process until its turn ends (2026-07-15: a released pane kept burning tokens on a reassigned task while the harness minted `-2`). A **slug** (`Frontend-adoptcard`) breaks both halves: `base()` strips digits only, so it reads as a dept nobody staffs — false stall alarms, no agent brief found.
  - **Overlap keeps a seat warm; a change of ground retires it.** Sequencing two cards over the same files is exactly where the seat's context is an asset, so don't pay full onboarding to throw away the knowledge most relevant to the next card. Retire when the **ground changes**, or at **`seat_cards_max` closed cards (default 3)**, whichever comes first.
  - **Bloat is a QUALITY failure before it is a cost one.** A seat carrying several cards' abandoned approaches re-proposes them — the same shape as a decision left in prose re-teaching its own dead design. **The Boss reads each pane's context percentage themselves, and their call overrides the counter in both directions.**
  - **No corpse panes:** a spawn failing "name taken" = the old instance still lives — shut it down; **never let the harness auto-mint a suffix**.
  - Mechanically held: `pretool_spawn_guard` blocks a bare handle on a single-card dispatch and blocks 2+ cards on one seat; `stop_capacity` flags a seat that has closed `seat_cards_max` cards and holds none.
- **Pick the kind by pane / visibility / noise, NOT memory** (both resume losslessly): needs a pane for founder-mode access or by-name talk → teammate; quiet bounded work you collect → subagent.
- **Workflow = the CEO's burst engine** for bounded fan-outs that aren't department-shaped (review/research/verify N things). Parallel writers need `isolation:"worktree"`.

---

References: `reference/dispatch-artefacts.md` (echo · 诊断 · 规格 · ladder — the dispatch spine) · `reference/activate.md` (activation + closeout ritual) · `reference/departments.md` (dept + expert menu) · `reference/task-widget.md` (task tools + sync hooks) · `reference/teammates.md` (spawn/lifecycle detail) · `reference/model-routing.md` (model + effort routing) · `reference/external-seats.md` (**read only when dispatching to an external seat** — a 子公司 or 外聘/合同工 terminal bound to an existing 部门; never needed for internal 部门 work, and the spawn itself is the bridge script's job, not yours) · `reference/meetings.md` (morning brief) · `reference/inspector.md` (督察) · `reference/boss-board.md` (Boss Board) · `reference/canon.md` (canonical answers) · `scripts/log.py` · `scripts/brief.py` · `scripts/board.py` · `scripts/canon.py` · `scripts/housekeep.py` (stale-artefact archiving — `/housekeep`).
