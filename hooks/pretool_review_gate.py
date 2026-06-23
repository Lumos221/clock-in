#!/usr/bin/env python3
"""PreToolUse hook — 产出审查 gate (Layer 2): block marking a task `completed`
unless an independent 审查-pass record exists for it. exit 2 = block (stderr is the
reason fed to the model); exit 0 = allow. Fail-open (any error → allow).

The 审查官 (Auditor) does the REAL review (judging quality is an agent's job, not a
regex). On a PASS it writes docs/reviews/<taskId>.pass. This hook only enforces that
the STEP happened: no task reaches `completed` without that record. 不过审查不准过.
The hook guarantees the step; the 审查 bars + Phase-3 tests guarantee the quality.

A deliberate override is still possible (write the .pass yourself) but it leaves a
trace — silent skipping is what this prevents. Only acts when an active
.claude/orchestrate.json marker exists (cwd-based lookup; covers teammates)."""
import sys, json, os


def find_marker(start):
    if not start:
        return None
    d = os.path.abspath(start)
    if os.path.isfile(d):
        d = os.path.dirname(d)
    while True:
        m = os.path.join(d, ".claude", "orchestrate.json")
        if os.path.exists(m):
            return m
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    if data.get("tool_name", "") != "TaskUpdate":
        return
    ti = data.get("tool_input", {}) or {}
    if ti.get("status") != "completed":
        return  # only gate the completion transition
    marker = find_marker(data.get("cwd") or os.getcwd())
    if not marker:
        return
    try:
        cfg = json.load(open(marker, encoding="utf-8"))
    except Exception:
        return
    if not cfg.get("active"):
        return
    task_id = str(ti.get("taskId", ""))
    root = os.path.dirname(os.path.dirname(marker))  # project root = parent of .claude
    passfile = os.path.join(root, "docs", "reviews", "%s.pass" % task_id)
    if not os.path.exists(passfile):
        sys.stderr.write(
            "🛑 产出审查 gate: task %s has no recorded 审查-pass. An INDEPENDENT reviewer "
            "(the 审查官 / Auditor) must pass 产出审查 and write "
            "docs/reviews/%s.pass before this task can be marked completed. 不过审查不准过." % (task_id, task_id))
        sys.exit(2)
    return  # allow


if __name__ == "__main__":
    main()
