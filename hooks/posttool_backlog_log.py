#!/usr/bin/env python3
"""PostToolUse hook — on a task's `completed` transition: (1) retire its 审查-pass
marker, (2) auto-append the finished task to docs/BACKLOG.md, (3) refresh the
machine-owned *Recently shipped* block on the TaskBoard digest, (4) retire the card
itself into the per-card store's done/ — stamped shipped-date + sha, so the durable
#NNN keeps its whole history as one file (only when its `task_id` is exactly this
one id — shared multi-id cards are never touched). Mechanical task-logging: no agent
has to remember to run a script, and the CEO no longer hand-copies shipped lines
between files or hand-deletes done cards.

The pass retirement closes a gate hole: platform task ids are small integers that
restart with each session, while docs/reviews/ persists — an unconsumed `<id>.pass`
would satisfy the review gate for a DIFFERENT future task that recycles the id,
silently voiding the hard gate. Consuming it on completion (archive, never delete)
keeps the record traceable and the gate honest.

The backlog row reads the task's card (by task_id) for the dept + name, carries the
card's durable #NNN (the id the Boss refers to — the platform id dies with the
session) into the task cell and the shipped line, stamps the short git sha, and
appends via the SHARED `log.py` formatter (so the row format has one source of
truth). Fail-open and only acts inside an active orchestrate project — a hook that
errors must never disrupt the run. Pairs with pretool_review_gate.py: that one
blocks a completion without a 审查-pass; this one records the completion once it
happens."""
import sys, json, os, re, subprocess
from datetime import datetime

# plugin layout: this hook is at <plugin>/hooks/, log.py at <plugin>/skills/orchestrate/scripts/
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
try:
    import hooklib, cardlib
except Exception:
    hooklib = cardlib = None
try:
    import log as tasklog  # shared HEADER + row(); single source of the row format
except Exception:
    tasklog = None
try:
    import board  # only for main_checkout (worktree piercing)
except Exception:
    board = None


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


SHIPPED_START = "<!-- SHIPPED:START -->"
SHIPPED_END = "<!-- SHIPPED:END -->"


def update_shipped(tb_path, line, keep=5):
    """Insert the freshly shipped one-liner at the top of the digest's machine-owned
    *Recently shipped* block (between the SHIPPED markers), trimming to `keep`.
    No markers (a pre-0.6.1 board, or a hand-restructured one) → no-op: the CEO
    curates that section by hand there. Atomic write; returns True on update."""
    try:
        text = open(tb_path, encoding="utf-8").read()
    except Exception:
        return False
    a = text.find(SHIPPED_START)
    b = text.find(SHIPPED_END)
    if a == -1 or b == -1 or b < a:
        return False
    inner = [l for l in text[a + len(SHIPPED_START):b].splitlines() if l.strip().startswith("-")]
    inner.insert(0, line)
    block = SHIPPED_START + "\n" + "\n".join(inner[:keep]) + "\n" + SHIPPED_END
    out = text[:a] + block + text[b + len(SHIPPED_END):]
    tmp = tb_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(out)
    os.replace(tmp, tb_path)
    return True


def main():
    if hooklib is None or cardlib is None:
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
    card = None
    try:
        bdir, _ = cardlib.ensure_store(root, cfg)
        if bdir:
            card = cardlib.find_task(cardlib.load(bdir), task_id)
    except Exception:
        bdir = None
    dept = name = label = None
    if card is not None:
        dept = cardlib.clean(card.get("dept", "")) or None
        name, label = card.get("name") or None, "#%d" % card["id"]
    else:
        # a completion no card claims retires nothing — leave a trace instead of
        # letting the drift hide (field case: task_id never filled at CREATE)
        try:
            hooklib.log_marker_misses(root, "task-sync", [
                "completion #%s matched no card (task_id never filled at CREATE?) — no card retired" % task_id])
        except Exception:
            pass
    sha = ""
    try:
        sha = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        pass
    # The card's durable #NNN is the id the Boss refers to (platform ids die per
    # session) — carry it into both durable records: the BACKLOG task cell and the
    # shipped line. Suppressed only when it would just repeat the platform id.
    proj = label if label and label != "#" + task_id else None
    d = {"task_id": task_id, "dept": dept,
         "task": ("%s %s" % (proj, name)) if proj and name else name,
         "status": "done", "sha": sha}
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        os.makedirs(os.path.dirname(backlog) or ".", exist_ok=True)
        fresh = not os.path.exists(backlog) or os.path.getsize(backlog) == 0
        with open(backlog, "a", encoding="utf-8") as f:
            if fresh:
                f.write(tasklog.HEADER)
            f.write(tasklog.row(d, today))
    except Exception:
        pass
    try:
        # `date · #<proj> · #<tid> · dept · name · sha` — the renderer pills the
        # leading ids. Legacy 5-field lines (no proj) keep the old shape. A
        # completion NO card claims writes no tail line at all (0.9.38): the tail
        # is the Boss's ship glance, and card-less completions are CEO bookkeeping
        # chores (window closes, marker banking) — dash-filled lines were noise
        # (her 2026-07-21 screenshot). The BACKLOG row above keeps the full ledger.
        if card is not None:
            if proj:
                line = ("- %s · %s · #%s · %s · %s · %s"
                        % (today, proj, task_id, dept or "—", name or "—", sha or "—"))
            else:
                line = ("- %s · #%s · %s · %s · %s"
                        % (today, task_id, dept or "—", name or "—", sha or "—"))
            update_shipped(tb, line)
    except Exception:
        pass
    try:
        # card retirement happens HERE, after the card fed dept/name and the shipped
        # line landed — never in the sync hook, which would race this one. The card
        # moves to done/ wearing its shipped date + sha: per-card history, one file.
        if card is not None and bdir:
            cardlib.retire(card, bdir, "done", status="done", shipped=today, sha=sha or "")
            cardlib.regen_digest(root, cfg)
    except Exception:
        pass


if __name__ == "__main__":
    main()
