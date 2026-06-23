# clock-in

**Run your Claude Code session like a founder-mode company.**

You say `clocking in`. Your session becomes the **CEO** — It spins up a squad of department **teammates**, decomposes work, sequences tasks, and has them report back. An independent **Auditor** hard-gates every plan and every output. An independent **HR** watches everyone (including the CEO) and escalates chaos straight to you. You stay the **Boss**: direct access to any department, any time.

---
> [!WARNING]
> Early sketch (v0.1.0)
> 
> This plugin is under active development. It works, I use it daily, but expect rough edges.
> 
> **A few things to know:**
> 
> - **The overall workflow is still being refined.** The structure and mechanics may improve (expected) between versions.
> 
> - **Token usage is not yet tracked or optimized.** I develop and run this on a Max 20× plan and never hit usage limit. If you're on a lighter plan, your mileage may vary. Token tracking will be prioritized once core features are stable.
> - **[Feedback and PRs](#feedback) very welcome.** If something breaks or feels wrong, open an issue.

---

## Why

Most "multi-agent" setups are one prompt pretending to be a team. This models an actual org with real separations of power:

- **A CEO that orchestrates, not implements.** It decides *who does what* and *in what order*, holds the only cross-domain view, and stays out of the craft.
- **A hard 2-layer review gate.** An independent **审查官 (Auditor)** must pass the *plan* (L1) before any work starts, and each *output* (L2) before it merges — enforced by a hook, not by vibes: a task literally cannot be marked done without a recorded pass.
- **Independent HR oversight.** A **人事部 (HR)** teammate counts bounces, retunes or fires underperformers, and reports chaos *straight to you* — including when the problem is the CEO.
- **Founder-mode direct access.** Drop into any department's pane and work with it directly; it reports back to the CEO afterwards.
- **Context-lean by design.** A tiny source-of-truth compass loads each session; the append-only history never auto-loads.
- **Safety backstops.** A hook blocks genuinely irreversible shell ops (`rm -rf`, force-push, drop-db); 法务部 owns the legal/compliance **红线 (red line)**.

---

## Requirements

| Need | Why |
|---|---|
| **Claude Code with Agent Teams enabled** — **mandatory** | The whole system is built on teammates. Without it, nothing spawns. |
| **Python 3** (standard library only) | Runs the hooks and the two scripts. No `pip install`. |
| **A git repo for your project** (recommended) | Departments commit each step; reports carry SHAs. |
| **macOS / Linux / Windows** (optional browser) | Only for the morning brief: any headless **Chromium-family browser** (Chrome / Edge / Brave / Chromium …) renders the PDF/PNG; without one it opens as styled **HTML** in your default browser. |

Enable Agent Teams in your `settings.json`:

```json
{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
```

---

## Install

```text
# 1. add this marketplace
/plugin marketplace add Lumos221/clock-in

# 2. install the plugin
/plugin install clock-in@mycompany

# 3. make sure Agent Teams is on (see Requirements), then restart Claude Code
```

The plugin's hooks **auto-wire on enable** — no manual `settings.json` hook setup needed.

---

## Quick start

In a project (ideally a git repo), start it any of these ways:

> **`/clock-in:orchestrate`**  ·  or say **"clocking in"**  ·  or **「开始上班」**

On the **first run** in a project, the CEO will:

1. Write a `.claude/orchestrate.json` **marker** — the hooks only act when this exists.
2. **Recruit** only the departments the project needs (always plus HR and the Auditor), generating agent files under `.claude/agents/`.
3. Scaffold `docs/SoT.md`, `docs/TaskBoard.md`, `docs/DECISIONS.md`.
4. Ask you to **restart + resume** (`claude -c`) so the new agent files load, then start orchestrating.

After that it runs the spine:

```
锁需求 → 起草方案 → Boss过目 → 方案审查 [L1 gate] → 派发 → 部门执行 → 产出审查 [L2 gate] → 汇总 → 报告
lock reqs → draft plan → Boss reviews → plan review → dispatch → depts execute → output review → consolidate → report
```

**Skip it** for single-file tweaks or ≤3-step tasks — it's for multi-part work.

---

## Commands

| Command | Does |
|---|---|
| `/clock-in` | Start founder-mode orchestration (same as saying **"clocking in"** / **「开始上班」**). |
| `/recruit` | Build or extend the department roster (人事部 recruiting). |
| `/brief` | Render the CEO morning brief (PDF / PNG / HTML) and open it. |

---

## How it works

```
Boss (you) ─── can reach any dept directly (founder mode)
├─ CEO (main session) ── routes · decomposes · sequences — does NOT gatekeep
│  ├─ 部门 / departments (teammates) ── own method + quality bar; do the work
│  │  ├─ staff (subagents) ─────────── one-shot grunt work
│  │  └─ Prof_ / Spec_ (subagents) ─── outside expertise, created by HR, invoked by a dept
├─ 审查官 / Auditor (subagent) ── independent review: L1 plan (refute) + L2 output (bounce)
└─ 人事部 / HR (teammate) ─── independent oversight + HR; authors agent files; reports to Boss directly
```

**Who owns what**

| Who | Owns |
|---|---|
| **CEO** | who does it · what the slice is · the done-when bar · cross-dept sequence |
| **Department** | *how* (method) · its quality bar (领域标杆) · proposing its domain's next steps |
| **Boss (you)** | the product-quality floor · big changes / forks / red-line calls · direct access |

**Key mechanisms**

| Mechanism | How |
|---|---|
| **Review gate** | Auditor hard-gates the plan (L1, pass-or-refute) and each output (L2, pass-or-bounce). A hook blocks marking a task done without `docs/reviews/<id>.pass`. |
| **Auto-log** | A hook appends each completed task to `BACKLOG.md` from its TaskBoard card — mechanical, no agent step. |
| **Bounce counter** | L2 bounces auto-counted per dept from `docs/reviews/<dept>.*.fail`. 3 → retune; 3 more → fire & re-hire. L1 refutes count against the CEO. |
| **Founder direct access** | Boss works with any dept directly in its pane; the dept reports what changed to the CEO. |
| **红线 (red line)** | 法务部 owns legal/compliance boundaries — raised only on real risk, escalated to the Boss. |
| **Teammate cap** | ≤6 concurrent. Assign to an existing dept first; recruit only if none fits. |

---

## The artifact model (source of truth ≠ log)

Everything the org knows lives in version-controlled files, split so context stays lean:

| File | Role | Loaded |
|---|---|---|
| `docs/SoT.md` | source of truth — the compass (goal · now · pointers) | **each session** (it's small) |
| `docs/TaskBoard.md` | live board — active cards + the last ~5 shipped | while orchestrating |
| `docs/BACKLOG.md` | finished-task log — auto-appended on completion | **never** (on-demand) |
| `docs/DECISIONS.md` | decision log — every significant call + why | on-demand |
| `docs/<domain>/` | department work products; the canonical one earns a SoT pointer | on-demand |

**Naming:** departments are `RnD` · `QA` · `Ops` · `Legal` · `HR` (ASCII handles; the Chinese 部门名 stays as the in-file label). Reusable experts are prefixed `Prof_` (academic) or `Spec_` (domain specialist).

---

## What's in the box

```
clock-in/                          ← the plugin (= the repo root)
├── .claude-plugin/                ← marketplace.json (mycompany) + plugin.json (clock-in)
├── commands/                      ← /brief
├── skills/
│   ├── orchestrate/   ← the CEO playbook (SKILL.md + templates + reference + scripts)
│   └── recruit/       ← HR's roster builder (pick depts, generate agent files)
├── hooks/             ← auto-wired on enable
│   ├── pretool_review_gate.py     ← blocks an unreviewed task completion
│   ├── pretool_accident_guard.py  ← blocks irreversible shell ops
│   ├── posttool_backlog_log.py    ← auto-logs a completed task
│   └── session_start.py           ← arms CEO mode + injects the SoT each session
└── bin/
    └── orchestrate-brief          ← renders the morning brief (PDF/PNG/HTML)
```

---


## Feedback

This is a personal experiment, shared in the hope it helps someone and improves with other eyes. **Issues and PRs are very welcome** — especially concrete reports of where the orchestration breaks down on real work.

## Credits

Inspired by [edict](https://github.com/cft0808/edict) (Tang dynasty 三省六部 / six ministries), and [Paul Graham's founder mode](https://paulgraham.com/foundermode.html).

## License

[MIT](./LICENSE)
