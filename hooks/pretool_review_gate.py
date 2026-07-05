#!/usr/bin/env python3
"""PreToolUse hook — 产出审查 gate (Layer 2): block marking a task `completed`
unless an independent 审查-pass record exists for it. exit 2 = block (stderr is the
reason fed to the model); exit 0 = allow. Fail-open (any error → allow).

The 审查官 (Auditor) does the REAL review (judging quality is an agent's job, not a
regex). On a PASS it writes docs/reviews/<taskId>.pass. This hook only enforces that
the STEP happened: no task reaches `completed` without that record. 不过审查不准过.
The hook guarantees the step; the 审查 bars + Phase-3 tests guarantee the quality.

The 审查官 writes the .pass from wherever it runs — sometimes a linked worktree under
.claude/worktrees/ — while this check runs from the CEO's main tree. So both resolve
the project root the SAME worktree-invariant way: `git rev-parse --git-common-dir`
returns the shared git dir from any worktree, and its parent is always the main
worktree. Write and check therefore land in the same docs/reviews/. Falls back to
walking up for .claude/orchestrate.json (non-git project, or marker in a subdir).

A deliberate override is still possible (write the .pass yourself) but it leaves a
trace — silent skipping is what this prevents. Only acts when an active
.claude/orchestrate.json marker exists."""
import sys, json, os, subprocess


def _walk_root(start):
    """Fallback: nearest ancestor holding .claude/orchestrate.json."""
    d = os.path.abspath(start)
    if os.path.isfile(d):
        d = os.path.dirname(d)
    while True:
        if os.path.exists(os.path.join(d, ".claude", "orchestrate.json")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def project_root(cwd):
    """Main worktree via git's shared common dir (worktree-invariant) when it holds
    the marker; else walk up for it (non-git, or an orchestrate project nested in a
    larger repo)."""
    start = os.path.abspath(cwd or os.getcwd())
    if os.path.isfile(start):
        start = os.path.dirname(start)
    try:
        out = subprocess.run(
            ["git", "-C", start, "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, timeout=5)
        common = out.stdout.strip()
        if out.returncode == 0 and common:
            groot = os.path.dirname(common)  # parent of <main>/.git = main worktree
            if os.path.exists(os.path.join(groot, ".claude", "orchestrate.json")):
                return groot
    except Exception:
        pass
    return _walk_root(start)


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
    root = project_root(data.get("cwd") or os.getcwd())
    if not root:
        return
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
    except Exception:
        return  # no active marker at the resolved root → not our concern
    if not cfg.get("active"):
        return
    task_id = str(ti.get("taskId", ""))
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