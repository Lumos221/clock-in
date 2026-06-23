#!/usr/bin/env python3
"""PostToolUse hook — auto-append a finished task to docs/BACKLOG.md the moment it's
marked `completed`. Mechanical task-logging: no agent has to remember to run a script.

It reads the task's card from TaskBoard.md (by task_id) for the dept + name, stamps the
short git sha, and appends via the SHARED `log.py` formatter (so the row format has one
source of truth). Fail-open and only acts inside an active orchestrate project — a hook
that errors must never disrupt the run. Pairs with pretool_review_gate.py: that one
blocks a completion without a 审查-pass; this one records the completion once it happens."""
import sys, json, os, re, subprocess
from datetime import datetime

# plugin layout: this hook is at <plugin>/hooks/, log.py at <plugin>/skills/orchestrate/scripts/
SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "orchestrate", "scripts")
sys.path.insert(0, SCRIPTS)
try:
    import log as tasklog  # shared HEADER + row(); single source of the row format
except Exception:
    tasklog = None


def find_root(start):
    d = os.path.abspath(start or os.getcwd())
    if os.path.isfile(d):
        d = os.path.dirname(d)
    while True:
        if os.path.exists(os.path.join(d, ".claude", "orchestrate.json")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def card_for(taskboard_text, task_id):
    """(dept, name) for the card whose task_id matches, else (None, None)."""
    for block in re.split(r"(?m)^#{2,3}\s+", taskboard_text):
        if re.search(r"task_id:\*\*\s*%s\b" % re.escape(task_id), block):
            first = block.splitlines()[0] if block.splitlines() else ""
            name = first.split("·", 1)[-1].strip() if "·" in first else first.strip()
            m = re.search(r"dept:\*\*\s*([^\n]+)", block)
            dept = m.group(1).strip().strip("`") if m else None
            return dept, name
    return None, None


def main():
    if tasklog is None:
        return
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    if data.get("tool_name") != "TaskUpdate":
        return
    ti = data.get("tool_input", {}) or {}
    if ti.get("status") != "completed":
        return
    root = find_root(data.get("cwd"))
    if not root:
        return
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
    except Exception:
        return
    if not cfg.get("active"):
        return
    task_id = str(ti.get("taskId", ""))
    if not task_id:
        return
    backlog = os.path.join(root, cfg.get("backlog", "docs/BACKLOG.md"))
    tb = os.path.join(root, cfg.get("taskboard", "docs/TaskBoard.md"))
    dept = name = None
    if os.path.exists(tb):
        try:
            dept, name = card_for(open(tb, encoding="utf-8").read(), task_id)
        except Exception:
            pass
    sha = ""
    try:
        sha = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        pass
    d = {"task_id": task_id, "dept": dept, "task": name, "status": "done", "sha": sha}
    try:
        os.makedirs(os.path.dirname(backlog) or ".", exist_ok=True)
        fresh = not os.path.exists(backlog) or os.path.getsize(backlog) == 0
        with open(backlog, "a", encoding="utf-8") as f:
            if fresh:
                f.write(tasklog.HEADER)
            f.write(tasklog.row(d, datetime.now().strftime("%Y-%m-%d")))
    except Exception:
        return


if __name__ == "__main__":
    main()
