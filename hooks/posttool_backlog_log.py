#!/usr/bin/env python3
"""PostToolUse hook — on a task's `completed` transition: (1) retire its 审查-pass
marker, (2) auto-append the finished task to docs/BACKLOG.md. Mechanical
task-logging: no agent has to remember to run a script.

The pass retirement closes a gate hole: platform task ids are small integers that
restart with each session, while docs/reviews/ persists — an unconsumed `<id>.pass`
would satisfy the review gate for a DIFFERENT future task that recycles the id,
silently voiding the hard gate. Consuming it on completion (archive, never delete)
keeps the record traceable and the gate honest.

The backlog row reads the task's card from TaskBoard.md (by task_id) for the dept +
name, stamps the short git sha, and appends via the SHARED `log.py` formatter (so the
row format has one source of truth). Fail-open and only acts inside an active
orchestrate project — a hook that errors must never disrupt the run. Pairs with
pretool_review_gate.py: that one blocks a completion without a 审查-pass; this one
records the completion once it happens."""
import sys, json, os, re, subprocess
from datetime import datetime

# plugin layout: this hook is at <plugin>/hooks/, log.py at <plugin>/skills/orchestrate/scripts/
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
try:
    import hooklib
except Exception:
    hooklib = None
try:
    import log as tasklog  # shared HEADER + row(); single source of the row format
except Exception:
    tasklog = None
try:
    import board  # only for main_checkout (worktree piercing)
except Exception:
    board = None


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


def _archive(src, arch):
    os.makedirs(arch, exist_ok=True)
    dst = os.path.join(arch, os.path.basename(src))
    if os.path.exists(dst):
        base, ext = os.path.splitext(dst)
        dst = "%s-%s%s" % (base, datetime.now().strftime("%Y%m%d-%H%M%S"), ext)
    os.replace(src, dst)
    return dst


def consume_pass(root, task_id):
    """Retire the task's whole review trail once it completes: the `.pass` (a recycled
    id in a later session must not reuse it against the review gate), its `.fail`
    markers (the per-task bounce count must not bleed into a future task with the same
    id), and its tally sentinels (runtime state — deleted, not archived). Archives are
    collision-safe; the 复盘 log keeps the lessons."""
    import glob
    rev = os.path.join(root, "docs", "reviews")
    arch = os.path.join(rev, "archive")
    moved = None
    src = os.path.join(rev, "%s.pass" % task_id)
    if os.path.exists(src):
        moved = _archive(src, arch)
    for f in glob.glob(os.path.join(rev, "*.%s.*.fail" % task_id)):
        if os.path.basename(f).split(".")[0] != "plan":
            _archive(f, arch)
    for s in glob.glob(os.path.join(rev, ".tally", "*.%s.*" % task_id)):
        try:
            os.remove(s)
        except OSError:
            pass
    return moved


def main():
    if hooklib is None:
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
    root = hooklib.find_root(data.get("cwd"))
    if not root:
        return
    if board is not None:
        root = board.main_checkout(root)  # ledger + backlog live in the MAIN checkout
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
    except Exception:
        return
    if not cfg.get("active"):
        return
    task_id = str(ti.get("taskId", ""))
    if not task_id:
        return
    try:
        consume_pass(root, task_id)
    except Exception:
        pass
    if tasklog is None:
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
