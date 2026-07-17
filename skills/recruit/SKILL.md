---
name: recruit
description: 督察 recruiting — build or extend a project's department roster, picking from the 部门 menu or hiring a domain 专家, and generate agent files. Triggers — 组建花名册, 盘点花名册, 部门审计, 部门改组/重组.
---

# Recruiting (a 督察 function)

Build or extend a project's company department roster. Generate each agent file (`<project>/.claude/agents/<id>.md`) from `department.md` (`orchestrate/templates/department.md`), one self-contained identity per 部门.

> All `orchestrate/…` paths below are in the sibling **orchestrate skill** — resolve them at `../orchestrate/…` relative to this skill's directory (e.g. `../orchestrate/reference/departments.md`), not under the project root.

## Steps

1. **Read the menu:** `orchestrate/reference/departments.md`. Pick the 部门 this project actually needs. **Recruit only what's needed** (e.g., a typical web app: 研发部 + 测试部 + 运维部 + 产品文档部).
2. **The three standing agents ship with the plugin — never copy them into the project.** 审查官 (Auditor) · 督察 (Inspector) · 书记处 (Registrar) live in the plugin's `agents/` dir (plugin-scope subagent definitions), update with every plugin release, and are **not** in `roster`. **A project copy under `.claude/agents/` shadows the plugin version and pins an outdated contract** — a session-start sentinel flags any it finds; archive them (upgrade pass, below).
3. **Generate each agent file** from `department.md` — fill every `<placeholder>` (handle · owned files · 领域标杆 · `model` per `orchestrate/reference/model-routing.md`). The brief is a **thin project shell**: identity + project fields + the `orchestrate-sop` FIRST-ACTION pointer — the SOP doctrine itself lives in `orchestrate/reference/department-sop.md` and is read live at every spawn, so **never inline SOP/report/queue rules into a brief** (they'd fossilise). Write it in whatever **language** reads clearest to the teammate; keep it short.
4. **Upsert the roster** into `.claude/orchestrate.json` `roster`, and **stamp the template version**: `briefs_template_hash` = sha256 of `orchestrate/templates/department.md`, first 12 hex chars (`shasum -a 256 <file> | cut -c1-12`) — the session-start sentinel compares it against the shipped template and prescribes an upgrade pass when briefs fall behind. (orchestrate writes the marker first; if you're running **standalone** and it's missing, create it from `orchestrate/templates/orchestrate.json`.)
5. **Boundary check:** if owned files overlap — **including against the existing roster's owned files, not just the new 部门s** — merge into one 部门 or re-cut.

## Upgrading an existing project (run after a plugin update)
`/recruit` in a project that already has a roster **reconciles it to the current templates** — an upgrade pass, not a re-interview:
1. **Legacy standing-agent copies (pre-0.9.16):** `.claude/agents/Auditor.md` / `Inspector.md` / `Registrar.md` in the project are superseded by the plugin-scope agents and **shadow them** — they must go. **Diff each against the plugin's `agents/<Name>.md` first:** content in the project copy that is NOT in the plugin version is project-local drift (e.g. a Boss-signed amendment) — **report it to the Boss** (project-independent rules get folded upstream into the plugin agent; project-specific ones move to a project file), **never silently drop it**. Then archive the copies to `.claude/agents/archive/`.
2. **Dept files:** regenerate each roster 部门's `.claude/agents/<handle>.md` from the current `department.md` (thin shell), carrying over **only** its project-specific fields (handle · description · role · 领域标杆 · owned files · Done). A pre-0.9.16 brief carries inlined SOP/report/queue sections — regeneration drops them by construction (doctrine now reads live via `orchestrate-sop`). Refresh the `briefs_template_hash` stamp (Step 4 above).
3. **Retired roles:** a pre-0.6.0 `.claude/agents/HR.md` (人事部 teammate) is superseded by the Inspector — archive it (`.claude/agents/archive/`) and remove `HR` from `roster`.
4. **Thresholds:** reconcile `.claude/orchestrate.json` `thresholds` to the current template's keys — add missing keys at their defaults, drop keys the template no longer has, keep the Boss's tuned values for keys that survive.
5. **Docs:** if `docs/TaskBoard.md` lacks the `<!-- SHIPPED:START -->`/`<!-- SHIPPED:END -->` markers, add the machine-owned *Recently shipped* block (move any existing shipped lines inside) — the completion hook maintains it from then on. Merge any per-dept `docs/复盘-<dept>.md` into one `docs/复盘.md` (add the dept to each row; archive the originals). If `docs/SoT.md` exceeds its ~15-line cap or restates decisions, flag it to the Boss — **don't rewrite the CEO's SoT content yourself**.
6. **Restart + resume** (`claude -c`) — regenerated agent files load only next session.

## Hiring a domain 专家 (not on the menu)
When a project needs a specialty (e.g., cryptography, a specific legal regime, medicine, a framework), hire a 领域专家 with a **real job title** (e.g. "密码学专家", "欧盟数据法高级律师") — never an invented name. Same `department.md` template; owned files per the project.

## Who runs this
The 督察 owns `.claude/agents/` authorship → **the 督察 authors the agent files; the CEO only spawns/disbands.** Exception — **activation**: the **CEO** runs this skill to author the initial roster (one bulk pass; the 督察 itself ships with the plugin, nothing to author for it). After that, every change (add 部门 · hire 专家 · re-hire after a 复盘 · 改组) goes through a one-shot **督察** invocation; a single re-hire is just regenerating one file from `department.md`.

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
