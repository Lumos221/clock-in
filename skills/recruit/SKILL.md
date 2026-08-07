---
name: recruit
description: 督察 recruiting — build or extend a project's department roster, picking from the 部门 menu or hiring a domain 专家, and generate agent files. Triggers — 组建花名册, 盘点花名册, 部门审计, 部门改组/重组.
---

# Recruiting (a 督察 function)

Build or extend a project's company department roster. Generate each agent file (`<project>/.claude/agents/<id>.md`) from `department.md` (`orchestrate/templates/department.md`), one self-contained identity per 部门.

> All `orchestrate/…` paths below are in the sibling **orchestrate skill** — resolve them at `../orchestrate/…` relative to this skill's directory (e.g. `../orchestrate/reference/departments.md`), not under the project root.

## Which pass — decide this FIRST, and it is not a judgment call

| The project | You run | You may NOT |
|---|---|---|
| No `roster` in `.claude/orchestrate.json` | **Build** (Steps below) | — |
| Has a roster (**this is an active company**) | **Upgrade only** — reconcile files to the current templates | add · disband · merge · re-cut · re-tier any 部门 |
| Has a roster **and** the invocation says so in words | whatever it names, and nothing else | anything it did not name |

**An active project's 花名册 is a live org chart, and changing it moves 权责.** The upgrade pass exists to make existing briefs match the current templates — nothing more. **默认不重组**: no roster change without an explicit instruction naming it, and 改组 has its own scan-then-ask protocol below that ends in a report, never in an edit.

**When the instruction names a subset of the upgrade steps, run exactly those.** Not the ones that "obviously also need doing" — say what you noticed, in the handover, and stop.

## Steps

1. **Read the menu:** `orchestrate/reference/departments.md`. Pick the 部门 this project actually needs. **Recruit only what's needed** (e.g., a typical web app: 研发部 + 测试部 + 运维部 + 产品文档部).
2. **The three standing agents ship with the plugin — never copy them into the project.** 审查官 (Auditor) · 督察 (Inspector) · 书记处 (Registrar) live in the plugin's `agents/` dir (plugin-scope subagent definitions), update with every plugin release, and are **not** in `roster`. **A project copy under `.claude/agents/` shadows the plugin version and pins an outdated contract** — a session-start sentinel flags any it finds; archive them (upgrade pass, below).
3. **Generate each agent file** — 部门 from `orchestrate/templates/department.md`, expert from `expert.md`. Fill every `<placeholder>` (handle · owned files · 领域标杆).

   - **The brief is a THIN PROJECT SHELL**: identity + project fields + the `orchestrate-sop` FIRST-ACTION pointer. Nothing else. **Never inline SOP / report / queue rules** — the doctrine reads live at every spawn (`department-sop.md` core + `department-sop-teammate.md` for standing seats), so a copy here fossilises AND reaches one-shots the pane rules don't apply to.
   - **Both dials go in the frontmatter, both by `orchestrate/reference/model-routing.md`.** Never leave either field out: `model:` is what every param-less spawn gets, and `effort:` is live whenever this brief is invoked one-shot. Do not re-derive the tiering rules here — the reference owns them.
   - **Tools are a `disallowedTools` denylist** — copy the template's verbatim; everything not denied flows in, MCP and future tools included. Per-dept changes only on the Boss's word.
   - **Language: whatever reads clearest to that teammate. Keep it short.**
4. **Register it** in `.claude/orchestrate.json` — **`roster`** for a standing dept that holds a pane, **`onDemand`** for one that is invoked and returns (experts always; a dept like 财务部 whose whole job is to answer when asked). A file in neither register is invisible to every check that reads them. Then **stamp the template version**: `briefs_template_hash` = sha256 of `orchestrate/templates/department.md`, first 12 hex chars (`shasum -a 256 <file> | cut -c1-12`) — the session-start sentinel compares it against the shipped template and prescribes an upgrade pass when briefs fall behind. (orchestrate writes the marker first; if you're running **standalone** and it's missing, create it from `orchestrate/templates/orchestrate.json`.)
5. **Seed the routing table** — `docs/board/routing.json`, one row per 部门 you just recruited. You seed it because you have just read every dept's standing work; **the CEO edits it directly from then on** — it is a small JSON file, not a gated artefact, and a table only recruit may touch is a table that rots between passes. Model + effort by the two dials in `orchestrate/reference/model-routing.md`; a homogeneous dept needs only its `default`, one with distinct work kinds splits by task class (**≤3**). A dept with no row falls through to the file's global `default`, which is a fallback, not a row.
   > **A task class is a label on the CARD, not a second desk.** `Legal` with classes `info` and `judge` is one department: the CEO classifies the card, the table answers with a tier. It does not mean a `Legal-info` seat and a `Legal-judge` seat — the handle stays `<Dept>-<卡号>`.
6. **Boundary check:** if owned files overlap — **including against the existing roster's owned files, not just the new 部门s** — merge into one 部门 or re-cut.

## Upgrading an existing project (run after a plugin update)
`/recruit` in a project that already has a roster **reconciles it to the current templates** — an upgrade pass, not a re-interview:
1. **Legacy standing-agent copies (pre-0.9.16):** `.claude/agents/Auditor.md` / `Inspector.md` / `Registrar.md` in the project are superseded by the plugin-scope agents and **shadow them** — they must go. **Diff each against the plugin's `agents/<Name>.md` first:** content in the project copy that is NOT in the plugin version is project-local drift (e.g. a Boss-signed amendment) — **report it to the Boss** (project-independent rules get folded upstream into the plugin agent; project-specific ones move to a project file), **never silently drop it**. Then archive the copies to `.claude/agents/archive/`.
2. **List what regeneration would DROP, before regenerating anything.** For each file, compare its sections against the template's. Anything the template has no slot for is **project-local content someone put there on purpose** — a Boss-signed section, a 复盘-derived discipline, a contract registry. **Never regenerate over it silently.** Two outcomes only: fold it into a section the template does have, or keep it verbatim as an extra section and say so in the handover. Same rule as Step 1's standing agents — and these files are older and carry more.
   > Field state: one project's `Frontend.md` carries a `## Contract registry (Boss …, unskippable)` the template has no slot for, and its `Prof_Academic.md` is **27k characters** of 取证纪律 written out of a 复盘. Regeneration by field-list would have deleted both.
3. **Dept files — PATCH what changed; rebuild only what is not already a thin shell.** Compare each `.claude/agents/<handle>.md` against `department.md` section by section. A brief that already has the template's sections and nothing fossilised needs the **changed sections replaced and nothing else touched** — usually one paragraph. Only a pre-0.9.16 brief, which carries inlined SOP/report/queue sections, is rebuilt: those sections are dropped by construction (the doctrine reads live via `orchestrate-sop`) and the project fields carry over. **"Regenerate" is not a licence to retype a file whose content is already correct** — every retype is a chance to lose a line nobody notices is gone. Refresh the `briefs_template_hash` stamp (Step 4 of the build pass).
4. **Expert files** (`Prof_*` · `Spec_*` and anything else in `.claude/agents/` that is not in `roster` — enumerate the DIRECTORY, the roster will not tell you they exist). Same rule: patch, don't rebuild. An expert that has grown its own coherent format (取证纪律 · 输出格式 · 红线) is **better than the template, not behind it** — leave the body alone. What they usually need is frontmatter only: an `effort:` (a one-shot honours it, so a missing one is a real loss) and a `model:` re-checked against the work the brief describes, since pre-0.9.132 experts were pinned **by prefix**, which the routing rule has never said to do.
   > **Two registers, not one.** `roster` = standing depts that hold a pane. **`onDemand`** = depts and experts that are invoked and return (a 财务部 that signs off on pricing when asked is not idle, it is on-demand). A file listed in neither is a finding — every roster-driven check is blind to it — but **report it, never fix it**: which register it belongs in is a roster call and needs the Boss's word.
5. **Retired roles:** a pre-0.6.0 `.claude/agents/HR.md` (人事部 teammate) is superseded by the Inspector — archive it (`.claude/agents/archive/`) and remove `HR` from `roster`.
6. **Routing table:** create or reconcile `docs/board/routing.json` against the roster you just regenerated (Step 5 of the build pass). An existing project usually has no table, or a stub with an empty `departments` — filling it is the point of running this. Keep any row the Boss has tuned.
7. **Thresholds:** reconcile `.claude/orchestrate.json` `thresholds` to the current template's keys — add missing keys at their defaults, drop keys the template no longer has, keep the Boss's tuned values for keys that survive.
8. **Docs:** if `docs/TaskBoard.md` lacks the `<!-- SHIPPED:START -->`/`<!-- SHIPPED:END -->` markers, add the machine-owned *Recently shipped* block (move any existing shipped lines inside) — the completion hook maintains it from then on. Merge any per-dept `docs/复盘-<dept>.md` into one `docs/复盘.md` (add the dept to each row; archive the originals). If `docs/SoT.md` exceeds its ~15-line cap or restates decisions, flag it to the Boss — **don't rewrite the CEO's SoT content yourself**.
9. **Restart + resume** (`claude -c`) — regenerated agent files load only next session. **The restart is for the BRIEFS only**; `orchestrate.json` and `routing.json` are data, read fresh, and take effect at once.

**A brief you just wrote CANNOT be spawned in the session that wrote it, and trying fails silently.** A mid-session definition is never registered for the teammate path: the spawn succeeds, echoes your `agentType` into the roster and the pane title, and quietly hands you the default model with none of the brief's content — a seat named `Legal` that is not Legal. **So the last step of every authoring pass is the handover, not a spawn:** name the files written and say they take effect after a restart. Cannot wait → spawn `general-purpose` with the role inlined, and say that is what you did.

## Hiring a domain 专家 (not on the menu)
When a project needs a specialty (e.g., cryptography, a specific legal regime, medicine, a framework), hire a 领域专家 with a **real job title** (e.g. "密码学专家", "欧盟数据法高级律师") — never an invented name. Template: **`orchestrate/templates/expert.md`**, not `department.md` — an expert is read-and-research, answers rather than edits, and carries both dials in its own frontmatter.

## Who runs this
The 督察 owns `.claude/agents/` authorship → **the 督察 authors the agent files; the CEO only spawns/disbands.** Exception — **activation**: the **CEO** runs this skill to author the initial roster (one bulk pass; the 督察 itself ships with the plugin, nothing to author for it). After that, every change (add 部门 · hire 专家 · re-hire after a 复盘 · 改组 · this upgrade pass) goes through the **督察 as a ONE-SHOT subagent** — a single re-hire is just regenerating one file.

```
Agent(subagent_type: "clock-in:Inspector", prompt: "<what to do>")   # NO name:
```

**Never pass `name:`.** That is the teammate path: it squats a pane it has no card for, lands on the members roster, and **drops the `effort: high` its file pins** (only the one-shot path honours that field). The 督察 needs neither the pane nor the roster — its independence comes from the fresh instance.

**It authors files and hands them over; it never spawns a seat.** Agent files register at CLI start, so the pass ends with a list of what changed and you restart (`claude -c`) before dispatching.

## 改组 / re-scope (督察 roster audit) — **scan first, restructure only on go**
Run when the roster drifts from the actual work: a domain keeps failing with no owner, two 部门 fight over files, or a 部门 has gone idle. Run by a one-shot 督察 at activation, on the `chaos_unowned_domain_fails` signal (see `orchestrate/reference/inspector.md`), or on demand ("scan the roster").

**Default to scan. Never restructure before the Boss has seen the scan and said go** — re-cutting moves 权责 and is high-risk.

### Mode A · Scan (read-only audit — changes nothing)
1. **Map work → owners.** From `docs/BACKLOG.md` + recent bounces (`docs/reviews/*.fail`) + the file tree, list the **functions** the project actually needs and map each to a current 部门. Cut by **职能/function**, not by code module — module-only cuts leave function-shaped gaps (e.g. 竞品调研 with no home).
2. **Diagnose four defects** (name them, don't fix yet):
   - **缺口 (gap):** a function/domain with no owner
   - **重叠 (overlap):** two 部门 with overlapping owned files
   - **空转 (dead):** a 部门 with **no live work across multiple rounds** — *not* merely idle (a teammate goes idle awaiting its next message after every leg; idle ≠ dead)
   - **命名漂移:** invented `x-expert` compounds instead of real job titles
3. **Report + verdict → STOP.** Output an audit: each 部门 + the defects found + a one-line verdict — **重组必要吗?** (necessary / not worth the churn / defer). Change nothing; wait for the Boss.

### Mode B · Restructure (act — only after the Boss says go)
4. **Fix each defect:** 缺口 → recruit one (Steps above); 重叠 → merge into one or re-cut the boundary; 空转 → disband (it writes `docs/handover-<部门>.md` first); 命名漂移 → normalize to real job titles.
5. **Boundary changes need sign-off** → propose the re-cut as a 董事会 **拍板项** (it moves 权责 structure).
6. **Migrate without disrupting work (保持现在的工作不变):**
   - in-flight tasks **keep their current owner until done** — never yank work mid-task;
   - re-assign **owned files**, not work-in-progress;
   - a departing / re-scoped 部门 writes `docs/handover-<部门>.md`;
   - re-point BACKLOG tasks to new owners **only at task boundaries**.
7. **Register** the new roster in `.claude/orchestrate.json` `roster` + regenerate the affected `.claude/agents/*.md`. (the 督察 **authors the files**; the **CEO executes** the actual teammate spawn / disband — only the lead manages the team.)
