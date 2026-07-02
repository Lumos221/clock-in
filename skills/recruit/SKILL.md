---
name: recruit
description: 人事部 recruiting — build or extend a project's department roster, picking from the 部门 menu or hiring a domain 专家, and generate agent files. Triggers — 组建花名册, 盘点花名册, 部门审计, 部门改组/重组.
---

# Recruiting (a 人事部 function)

Build or extend a project's company department roster. Generate each agent file (`<project>/.claude/agents/<id>.md`) from `department.md` (`orchestrate/templates/department.md`), one self-contained identity per 部门.

> All `orchestrate/…` paths below are in the sibling **orchestrate skill** — resolve them at `../orchestrate/…` relative to this skill's directory (e.g. `../orchestrate/reference/departments.md`), not under the project root.

## Steps

1. **Read the menu:** `orchestrate/reference/departments.md`. Pick the 部门 this project actually needs. **Recruit only what's needed** (e.g., a typical web app: 研发部 + 测试部 + 运维部 + 产品文档部 + 人事部).
2. **Always include two standing roles:**
   - **人事部** (HR — independent oversight + HR; see `orchestrate/reference/hr-oversight.md`) — a **teammate**; generate from `orchestrate/templates/hr.md` and add to `roster`.
   - **审查官** (Auditor — the independent review gate; see `orchestrate/SKILL.md` §2.3/§6) — a **subagent**: copy `orchestrate/templates/auditor.md` → `.claude/agents/Auditor.md` **verbatim** (project-independent: no owned files, no customization, **not** in `roster`).
3. **Generate each agent file** from `department.md` — fill every `<placeholder>` (handle · owned files · 领域标杆 · `model` per `orchestrate/reference/model-routing.md`). SOP / 报告即停 / tools are template-fixed. Write it in whatever **language** reads clearest to the teammate; keep it short.
4. **Upsert the roster** into `.claude/orchestrate.json` `roster` (orchestrate writes the marker first; if you're running **standalone** and it's missing, create it from `orchestrate/templates/orchestrate.json`).
5. **Boundary check:** if owned files overlap — **including against the existing roster's owned files, not just the new 部门s** — merge into one 部门 or re-cut.

## Hiring a domain 专家 (not on the menu)
When a project needs a specialty (e.g., cryptography, a specific legal regime, medicine, a framework), hire a 领域专家 with a **real job title** (e.g. "密码学专家", "欧盟数据法高级律师") — never an invented name. Same `department.md` template; owned files per the project.

## Who runs this
HR owns `<project>/.claude/agents/` → **HR authors the agent files; the CEO only spawns/disbands.** Exception — **activation**: HR doesn't exist yet, so the **CEO** runs this skill to author the initial roster (incl. HR's own file). After that, **HR** authors every change (add 部门 · hire 专家 · re-hire · 改组); a single re-hire is just regenerating one file from `department.md`.

## 改组 / re-scope (人事部 roster audit) — **scan first, restructure only on go**
Run when the roster drifts from the actual work: a domain keeps failing with no owner, two 部门 fight over files, or a 部门 has gone idle. Triggered by 人事部 at activation, on the `chaos_unowned_domain_fails` signal (see `orchestrate/reference/hr-oversight.md`), or on demand ("scan the roster").

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
7. **Register** the new roster in `.claude/orchestrate.json` `roster` + regenerate the affected `.claude/agents/*.md`. (recruit **authors the files**; the **CEO executes** the actual teammate spawn / disband — only the lead manages the team.)
