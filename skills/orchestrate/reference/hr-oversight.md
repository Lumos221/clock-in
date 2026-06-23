# 人事部 · CEO quick-reference

> Full HR rules live in the HR teammate's own file (`.claude/agents/HR.md`, generated from `templates/hr.md`). This page is the **CEO-facing summary** — what the CEO needs to know about 人事部 without reading HR's full prompt.

## Standing
- Independent of CEO and all 部门. Manages everyone incl. CEO. Reports **directly to the Boss** (inline in their chat — CEO may not filter).
- Always present from activation. Model: **opus**.

## What triggers a Boss escalation

人事部 reports straight to the Boss when **any** chaos metric trips:

| Signal | Threshold | CEO action |
|---|---|---|
| Widespread failure | ≥2 depts near firing | systemic — expect Boss intervention |
| Idle burn | 3 rounds, 0 completions, cost rising | check if plan is stuck or wrong |
| Red-line storm | 红线 blocked ≥3× | boundary system breaking |
| **CEO failure** | ≥3 `docs/reviews/*.refute` (L1 refutes) / depts fight same file | **you are the problem** — 人事部 goes over your head |
| Deadlock | task ping-pongs ≥4 bounces | stuck — becomes Boss decision |

## HR ladder (CEO's view)

- **3 bounces** (per dept, auto-counted: `ls docs/reviews/<dept>.*.fail | wc -l`) → 人事部 runs 复盘. May blame the CEO's brief — be ready to rewrite.
- **3 more** after retune → fire & re-hire. 人事部 authors the replacement file; **CEO executes the respawn**.
- **Stalled task** → retry → escalate → block. A task at `chaos_pingpong` (4) bounces with no cause gets flagged to the Boss.

## Roster audit

人事部 owns the roster's shape. Unowned-domain failures (≥3×) trigger a scan → restructure proposal. See the `recruit` skill for the full 改组 process.

## Thresholds

All tuneable in `.claude/orchestrate.json` `thresholds`.
