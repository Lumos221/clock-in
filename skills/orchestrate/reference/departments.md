# Department menu (what a **real company** needs)

Recruit only the few a project needs — not all of them every time. Each 部门 owns **non-overlapping files** (boundary = responsibility).
- **CEO** = this session (not in the table — that's you).
- **审查官** = the independent reviewer (`Auditor`). A **standing-file subagent**: `.claude/agents/Auditor.md` is created at activation (verbatim from `templates/auditor.md`), but it's invoked **without a `name`** (one-shot, fresh each review) — so it's **not a 部门/teammate** and is **not** in `roster`. Its full L1+L2 contract (bars + markers) lives in its file.
- **督察** = the independent inspector (`Inspector`) — same standing-file-subagent pattern (`templates/inspector.md` → `.claude/agents/Inspector.md`, one-shot, not in `roster`): 复盘 on stuck tasks · roster audits · authors dept/expert agent files (see `inspector.md`).

## Naming convention

Three categories — handle tells you what type it is at a glance:

| Type | Handle pattern | Example handles | Description starts with |
|---|---|---|---|
| **部门** (department) | Capitalized / abbreviation all-caps | RnD · QA · Legal · Fin | 中文部门名 |
| **教授** (academic expert) | `Prof_` prefix | Prof_CompSci · Prof_Econ | 中文专家名 |
| **专员** (domain specialist) | `Spec_` prefix | Spec_Frontend · Spec_DevOps | 中文专员名 |

Handles are ASCII-only (`^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`, ≤64 chars; Chinese fails spawn validation). The Chinese name stays as the in-file label.

## 部门 (departments — teammates)

| 部门 | Handle | Role | Default owned files |
|---|---|---|---|
| 研发部 | RnD | Features / architecture / code | `src/` `lib/` `app/` |
| 测试部 | QA | Tests / test coverage / bug verification | `tests/` `**/*.test.*` `spec/` |
| 运维部 | Ops | CI/CD / deploy / infra / security hardening | `.github/` `infra/` `Dockerfile` `deploy/` `*.yml` |
| 数据部 | Data | Data analysis / stats / reports / ETL | `data/` `notebooks/` `*.ipynb` `docs/数据/` |
| 产品文档部 | Docs | Product docs / README / copy / i18n | `README*` `docs/product/` `locales/` |
| 法务部 | Legal | Compliance / licensing / privacy / terms | `LICENSE*` `PRIVACY*` `TERMS*` `docs/合规/` |
| 财务部 | Fin | Cost (token→$) / investment·revenue ledger / ROI | `docs/财务/` |

(Oversight/HR is **not** a 部门: the **督察** — a one-shot subagent — authors `.claude/agents/` files and owns `docs/复盘.md`; see the bullet above.)

Departments run as **teammates** (addressable panes), spawned per task and released at its clean boundary — the roster agent file is what persists, not the pane. They own files and have a task on the board.

## Work products & the `docs/` layout

> The full artifact model (SoT · board · logs) is defined once in `SKILL.md` → "Files". This section is the **dept-boundary** subset: where a dept's outputs live, what's off-limits, which file is canonical.

A dept produces its outputs under its **own work-product folder**, `docs/<其领域>/` (e.g. 法务部 → `docs/合规/`, 财务部 → `docs/财务/`, 数据部 → `docs/数据/`). That folder is part of the dept's boundary — peers don't touch it. Code-producing depts (RnD/QA/Ops) work in code dirs; any notes/specs they write go in their `docs/<领域>/`.

**Orchestration files are off-limits to every dept** (no carve-out list to forget): `docs/SoT.md`, `docs/TaskBoard.md`, `docs/BACKLOG.md`, `docs/DECISIONS.md`, `docs/CANON.md` (read-first, but **machine-written** — never hand-edit), `docs/reviews/`, `docs/复盘.md`, `docs/handover-*.md`. These are owned by the **CEO / 审查官 / 督察** per their roles — a 部门 only edits **its own task card's `status`** on `TaskBoard.md`, nothing else there.

**Canonical file — which output "matters" (earns a `docs/CANON.md` row):** the current authoritative answer to a question the project acts on, superseding the dept's rounds. Test: *would an outsider redo work, or lose a depended-on conclusion, if it vanished?* One row per answered question; not every dept has one; a **key binding decision** (no file) earns a row the same way (pointer `DECISIONS`). Mechanism + dept-facing how-to → `reference/canon.md`.
## 专家 (experts — reusable subagents)

Experts are the company's **outside consultants** — brought in for a question, they answer and leave; no standing seat. Mechanically they're **subagents** (one-shot, no owned files, no board entry), invoked by a department when it hits a field outside its own.

Two types:
- **Prof_** — academic experts (real scholars): Prof_CompSci, Prof_Econ, Prof_Med. Use when a dept needs authoritative academic knowledge (which journals are definitive, what methodology is standard, what the literature says).
- **Spec_** — domain specialists: Spec_Frontend, Spec_DevOps, Spec_Security. Use when a dept needs craft expertise outside its own domain.

**Lifecycle (auto-match → fallback → create):**
1. Dept describes what it needs in an `Agent` call — Claude auto-matches to the right expert by reading `description` fields in `.claude/agents/Prof_*.md` / `Spec_*.md`
2. **Match found** → expert runs, returns answer, done
3. **Wrong match** → dept uses explicit `@Prof_CompSci` to override
4. **No expert exists** → dept tells CEO via SendMessage: "need a 计算机科学教授"
5. CEO checks roster (an existing expert may already fit — assign first)
6. No fit → CEO invokes the 督察 one-shot → it creates `.claude/agents/Prof_CompSci.md` from `templates/expert.md` (real job title, good `description` for auto-discovery)
7. Dept retries → works. File persists for reuse across sessions and depts.
8. Expert underperforms → the 督察 retunes the file (same authoring function, lighter touch)
9. Expert's output is part of the invoking dept's work — no separate 产出审查 for experts

**Key difference from departments:** experts don't own files, don't sit on the board, aren't teammates. They answer questions and return. The dept is accountable for how it uses the expert's output.

## Recruiting rules
- 高内聚低耦合, recruit by department — not by file or web pages. A department is a specific functional unit.
- **Only recruit what the project needs.** A web app is often just RnD + QA + Ops + Docs.
- **Assign first, recruit second:** when new work arrives, first check if an existing dept covers it. Only recruit a new dept if no existing one fits.
- **财务部:** recruit when the project involves cost / budget / ROI. It **computes cost** (estimates $ from each agent's token usage) and **keeps the ledger** (the Boss enters investment / revenue) under `docs/财务/`; produces P&L / ROI on demand.
- **Experts:** don't pre-create. When a dept needs one, the CEO invokes the 督察 to create the agent file. Give each a **real job title** (e.g. "计算机科学教授", "前端专员"), never an invented name.
- Overlapping boundaries → merge into one 部门, or re-cut file ownership.

## Model routing
→ **`reference/model-routing.md`** (single source of truth).

## 财务部 — honest limit
Cost (token→$) is auto-estimable; **investment / revenue is not** — the Boss must enter it in `docs/财务/FINANCE.md` for Fin to compute ROI / burn rate.
