<!-- Language switcher — restore once README.zh-CN.md is published:
     <div align="right"><strong>English</strong> · <a href="README.zh-CN.md">中文</a></div> -->

<!-- Drop a logo here when you have one: <p align="center"><img src="docs/assets/logo.png" width="120"></p> -->

<div align="center">

# 🕘 clock-in

**Run your Claude Code session like a founder-mode company.**

You stay the Boss. Your session becomes a CEO that delegates to a squad of specialist departments — with an independent Auditor gating every plan and output, and an independent HR watching the whole org, including the CEO.

[![version](https://img.shields.io/badge/version-0.1.0-3b82f6)](.claude-plugin/plugin.json)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-d97757)](https://docs.claude.com/en/docs/claude-code)
[![Agent Teams](https://img.shields.io/badge/Agent%20Teams-required-f59e0b)](#requirements)
[![license: MIT](https://img.shields.io/badge/license-MIT-22c55e)](LICENSE)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-22c55e)](#feedback)

</div>

<!-- ┌──────────────────────────────────────────────────────────────────────────┐
     │  HERO DEMO GOES HERE — this is the single biggest win for the README.     │
     │  Record ~15–25s: you say "clocking in" → CEO recruits departments →       │
     │  teammate panes spawn → a task flows through the L1 + L2 review gates →    │
     │  `/clock-in:brief` renders the morning-brief PDF.                          │
     │  Export to docs/assets/demo.gif, then uncomment the line below.           │
     └──────────────────────────────────────────────────────────────────────────┘ -->
<!-- <p align="center"><img src="docs/assets/demo.gif" alt="clock-in in action" width="820"></p> -->

---

## What it is

clock-in turns one Claude Code session into a small company. **You stay the Boss.** Your session becomes a **CEO** that breaks work into slices and hands them to specialist **department** teammates — while an independent **Auditor** gate-checks every plan *and* every result, and an independent **HR** watches the whole org, including the CEO.

The point: **real separation of powers**, so quality is enforced by *structure*, not by trust. Most "multi-agent" setups are one prompt wearing different hats. This one isn't.

> [!NOTE]
> clock-in thinks bilingually — roles carry Chinese names (e.g. 审查官 Auditor, 法务部 Legal, 人事部 HR) and the workflow has a Chinese shorthand. You never need to read them; everything works in plain English. They're labels, not a requirement.

---

## Quick start

### Requirements

| What | Why |
|---|---|
| **Claude Code** with **Agent Teams** enabled | The system is built on teammates. Without it, nothing spawns. |
| **Python 3** (standard library only) | Runs the hooks and scripts. No `pip install`. |
| **A git repo** (recommended) | Departments commit each step; reports carry commit SHAs. |
| **A Chromium-family browser** (optional) | Only for `/clock-in:brief` — renders the brief as PDF/PNG. Without one it opens as HTML. |

Enable Agent Teams in your Claude Code `settings.json`:

```json
{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
```

### Install

```text
# 1 · add the marketplace
/plugin marketplace add Lumos221/clock-in

# 2 · install the plugin
/plugin install clock-in@mycompany

# 3 · ensure Agent Teams is on (above), then restart Claude Code
```

Hooks **auto-wire on enable** — no manual `settings.json` hook setup needed.

### Run it

Open a project (ideally a git repo) and start it any of these ways:

> **`/clock-in:orchestrate`**  ·  or just say **"clocking in"**  ·  or **「开始上班」**

On the **first run** the CEO recruits the departments your project needs, scaffolds its source-of-truth files, and asks you to restart-and-resume (`claude -c`) so the new agent files load. After that, every run picks up the roster and runs the spine.

> [!TIP]
> **Skip it for small stuff.** Single-file tweaks or ≤3-step tasks don't need an org — just ask Claude directly. clock-in is for multi-part work.

---

## See it in action

Once you clock in, every piece of work flows down one spine — and **a task literally cannot be marked done until the Auditor has signed off**:

```
锁需求 → 起草方案 → Boss过目 → 方案审查 → 派发 → 部门执行 → 产出审查 → 汇总 → 报告

lock      draft     Boss      plan       dispatch  depts     output     consol-  report
reqs   →  plan   →  reviews → review  →  to depts → execute → review  →  idate  → to Boss
                              [L1 gate]                       [L2 gate]
```

<!-- SCREENSHOT SPOT — an annotated capture of the running org (CEO + a couple of
     department panes + a docs/reviews/*.pass marker) lands well right here.
     Export to docs/assets/run.png and uncomment: -->
<!-- <p align="center"><img src="docs/assets/run.png" alt="an orchestration run" width="820"></p> -->

### Let it run all night — wake up in the loop
Render a one-glance brief of **what shipped, what's queued, and what needs you** with `/clock-in:brief`:

<p align="center">
  <img src="docs/assets/brief-example.png" alt="Example CEO morning brief — shipped, queued, and needs-you lists" width="620">
</p>
<p align="center"><sub>A real brief from <code>/clock-in:brief</code> — shipped · queued · needs-you, footed with the run's gate status.</sub></p>

| Command | What it does |
|---|---|
| `/clock-in:orchestrate` | Start or resume founder-mode orchestration (= "clocking in" / 「开始上班」). |
| `/clock-in:recruit` | Build or extend the department roster. |
| `/clock-in:brief` | Render the CEO morning brief (PDF / PNG / HTML) and open it. |

---


## How it works

```
Boss (you) ─── can reach any department directly
│
├─ CEO (main session) ── routes · decomposes · sequences
│  └─ Departments (teammates) ── own their method + quality bar; do the work
│     ├─ staff (subagents) ─────────── one-shot grunt work
│     └─ Prof_ / Spec_ (subagents) ─── outside expertise, required by depts, hired by HR
│
├─ Auditor / 审查官 (subagent) ── independent review: L1 plan + L2 output
│
└─ HR / 人事部 (teammate) ─── independent oversight; authors agent files;
                              reports to the Boss directly
```

**Who owns what**

- **CEO** — *who* does it, *what* the slice is, the done-when bar, cross-dept sequence.
- **Department** — *how* (its method), its own quality bar, proposing its next steps.
- **Boss (you)** — the product-quality floor, big forks, red-line calls, direct access.

**The two gates** — the Auditor is an independent subagent running two hard checks:

- **L1 · Plan** (before any work): passes only if the plan is feasible, complete, well-decomposed, risks-listed, and in scope. Otherwise it writes a `.refute` marker with reasons and the CEO must revise.
- **L2 · Output** (before "done"): passes only if the output meets acceptance criteria + the department's quality bar, is correct (tests pass), stays in bounds, and is traceable. Otherwise it writes a `.fail` marker and the work bounces back.

A hook reads these markers mechanically — a task cannot be marked `completed` without a matching `docs/reviews/<id>.pass`. **HR** then counts the bounces: 3 → retune, 3 more → fire & re-hire; CEO plan-refutes are tracked and escalated to you.

---

## Why it's different

- **A CEO that orchestrates, not implements.** It decides *who does what, in what order*, holds the only cross-domain view, and stays out of the craft.
- **A hard 2-layer review gate.** An independent Auditor must pass the *plan* (L1) before any work starts, and every *output* (L2) before it merges — enforced by a hook, not by vibes. No recorded pass, no "done".
- **Independent HR oversight.** HR counts bounces, retunes or fires underperformers, and escalates chaos **straight to you** — including when the problem is the CEO.
- **Founder-mode direct access.** Drop into any department's pane and work with it directly; it reports back to the CEO afterwards. You never lose control as it scales.
- **Context-lean by design.** A tiny source-of-truth compass loads each session; the append-only history never auto-loads.
- **Safety backstops.** A hook blocks genuinely irreversible shell ops (`rm -rf`, `git push --force`, `drop table`…); the Legal department owns the compliance red line.

---


## Reference

<details>
<summary><strong>Departments</strong> — HR recruits only what the project needs</summary>

| Department | Handle | What it does | Default owned files |
|---|---|---|---|
| 研发部 | `RnD` | Features, architecture, code | `src/` `lib/` `app/` |
| 测试部 | `QA` | Tests, coverage, bug verification | `tests/` `**/*.test.*` |
| 运维部 | `Ops` | CI/CD, deploy, infra, security | `.github/` `infra/` `Dockerfile` |
| 数据部 | `Data` | Data analysis, stats, ETL | `data/` `notebooks/` |
| 产品文档部 | `Docs` | Product docs, README, i18n | `README*` `docs/product/` |
| 法务部 | `Legal` | Compliance, licensing, privacy | `LICENSE*` `PRIVACY*` |
| 财务部 | `Fin` | Cost, ROI, investment analysis | `docs/财务/` |
| 人事部 | `HR` | Independent oversight + HR (always recruited) | `.claude/agents/` |

**Experts**, hired on demand by HR: `Prof_<domain>` (academic, e.g. `Prof_CompSci`) and `Spec_<domain>` (specialist, e.g. `Spec_Frontend`). Rule of thumb — a typical web app uses RnD + QA + Ops + Docs + HR.

</details>

<details>
<summary><strong>Artifacts &amp; files</strong> — source of truth ≠ log</summary>

| File | Role | Loaded |
|---|---|---|
| `docs/SoT.md` | Source of truth — the compass (goal · now · pointers) | **each session** (kept small) |
| `docs/TaskBoard.md` | Live board — active cards + last ~5 shipped | while orchestrating |
| `docs/BACKLOG.md` | Finished-task log — auto-appended by a hook | never (on-demand) |
| `docs/DECISIONS.md` | Decision log — every significant call + why | on-demand |
| `docs/reviews/` | Review markers — `.pass` / `.fail` / `.refute` | hooks read these |
| `docs/<domain>/` | Department work products; canonical ones earn a SoT pointer | on-demand |
| `.claude/orchestrate.json` | Activation marker + config + roster + thresholds | hooks check at start |

</details>

<details>
<summary><strong>Model routing</strong></summary>

| Model | Used for |
|---|---|
| **opus** | Auditor, Legal, HR, all experts, RnD when architecturally hard |
| **sonnet** | RnD routine coding, QA, Ops, Data, Docs |
| **haiku** | Only truly trivial grunt work (staff subagents) |

When in doubt the system goes up a tier, not down.

</details>

<details>
<summary><strong>Configuration</strong> — <code>.claude/orchestrate.json</code></summary>

Written on first activation. Key fields:

- `active` — hooks only act when `true`. Set `false` to disable without uninstalling.
- `roster` — which departments are recruited.
- `redlines` — signed legal/compliance boundaries (e.g. "GDPR applies").
- `thresholds` — escalation points (bounces before retune, fails before firing, etc.).

</details>

<details>
<summary><strong>What's in the box</strong></summary>

```
clock-in/                       ← the plugin (= repo root)
├── .claude-plugin/             ← marketplace.json (mycompany) + plugin.json
├── commands/                   ← /clock-in:brief
├── skills/
│   ├── orchestrate/            ← the CEO playbook (SKILL + templates + reference + scripts)
│   └── recruit/                ← HR's roster builder
├── hooks/                      ← auto-wired on enable
│   ├── session_start.py            ← arms CEO mode + injects the SoT each session
│   ├── pretool_review_gate.py      ← blocks an unreviewed task completion
│   ├── pretool_accident_guard.py   ← blocks irreversible shell ops
│   └── posttool_backlog_log.py     ← auto-logs a completed task
└── bin/
    └── orchestrate-brief       ← renders the morning brief (PDF/PNG/HTML)
```

</details>

---

## Status &amp; caveats

> [!WARNING]
> **Early sketch (v0.1.0).** It works — I use it daily — but expect rough edges.
>
> - **The workflow is still being refined.** Structure and mechanics may change between versions.
> - **Token usage isn't tracked or optimised yet.** I run this on a Max 20× plan and never hit the cap; on a lighter plan your mileage may vary. Token tracking comes once the core is stable.
> - **Not yet battle-tested** on large, long-running projects.

---

## Feedback

This is a personal experiment, shared in the hope it helps someone and improves with other eyes. **Issues and PRs are very welcome** — especially concrete reports of where the orchestration breaks down on real work.

## Credits

Inspired by [edict](https://github.com/cft0808/edict) (Tang-dynasty 三省六部 / six ministries) and [Paul Graham's founder mode](https://paulgraham.com/foundermode.html).

## License

[MIT](LICENSE) — Lumos, 2026.
