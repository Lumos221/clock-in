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
import sys, json, os, re, subprocess
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
try:
    import board                  # the ONE review-marker key parser
except Exception:
    board = None
try:
    import cardlib                # task_id → the card's durable #NNN
except Exception:
    cardlib = None


def card_meta(root, cfg, task_id):
    """(durable #NNN, stage clock) of the card carrying this platform task id.

    Platform ids restart per session while the card number does not, so a marker is
    legitimately keyed on either; the board has matched both since 0.9.58 and this gate
    had not caught up. The clock comes back too, because a recycled id is exactly what
    makes a marker's DATE load-bearing."""
    if cardlib is None:
        return "", ""
    try:
        cards = cardlib.load(cardlib.board_dir(root, cfg))
        card = cardlib.find_task(cards, task_id)
        if not card:
            return "", ""
        m = re.match(r"(\d+)-", os.path.basename(card.get("_path") or ""))
        return (m.group(1) if m else ""), cardlib.clean(card.get("since", "") or "")
    except Exception:
        return "", ""


def verdict(root, cfg, task_id):
    """('pass'|'evidence'|'stale'|'none', detail) for this task, by the board's rules.

    Reusing `board._review_markers` and `_stage_ts` rather than re-deriving them is the
    point: a gate that disagreed with the panel would show 已过审 on a card it then
    refused to let through.

    **A marker must be no older than the card's stage clock.** Platform ids restart every
    session, so a `115.pass` written weeks ago attaches to whatever card holds task 115
    now — a card it never saw. A durable #NNN is a permanent identity and needs no such
    proof; a task_id does.

    Where the panel and this gate deliberately differ: with NO clock to compare against,
    the panel refuses a task_id match (a missing chip costs nothing) while the gate allows
    it (a false refusal blocks finished work, and card-less projects have no clock at all).
    The asymmetry is chosen, not overlooked."""
    marks = board._review_markers(root)
    num, since = card_meta(root, cfg, task_id)
    if board.l2_verdict(marks, num, task_id, since, root) == "pass":
        return "pass", num
    # Not a second implementation of the rule — only a reason for the refusal, so the
    # message can tell "no review happened" apart from "the review is not about this leg".
    hit = marks.get(num) if num else None
    if hit is None and str(task_id).isdigit():
        hit = marks.get(str(task_id))
    if not hit or hit[0] != "pass":
        return "none", num
    # WHICH rejection this was. Reporting every one as `stale` is how a refusal caused by
    # evidence sent a CEO hunting for hooks that push the stage clock: it read "the marker
    # is older than the card" about a marker written four minutes earlier, and there was
    # no such bug to find. A gate that misnames its own reason costs more than one that
    # refuses — the refusal is one card, the wrong reason is a night.
    if len(hit) > 2:
        try:
            held = board.evidence_holds(
                root, board.marker_evidence(hit[2]),
                datetime.fromtimestamp(hit[1] - 86400).strftime("%Y-%m-%d"))
        except Exception:
            held = None
        if held is False:
            return "evidence", num
    if board._stage_ts(since) is None:
        return "pass", num       # no clock to check against: allow, see the asymmetry above
    return "stale", num


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
    if board is None:                      # packaging accident: keep the original check
        if os.path.exists(os.path.join(root, "docs", "reviews", "%s.pass" % task_id)):
            return
        state, card = "none", ""
    else:
        state, card = verdict(root, cfg, task_id)
    if state == "pass":
        return  # allow
    if state == "evidence":
        sys.stderr.write(
            "🛑 产出审查 gate: task %s has a `.pass`, but the commit and patch-id it names "
            "are both off the tree — rebased away, or on a branch this cannot see. Confirm "
            "which. Gone → the review does not cover what is on offer; run the round again. "
            "**Do not write the marker yourself.**" % task_id)
        sys.exit(2)
    if state == "stale":
        sys.stderr.write(
            "🛑 产出审查 gate: the only `.pass` for task %s predates card #%s's current "
            "stage — a verdict on an earlier leg, or on another card that held this id "
            "(platform ids restart each session). Re-submit to the 审查官 for THIS round; "
            "**do not write the marker yourself.**" % (task_id, card or "?"))
        sys.exit(2)
    sys.stderr.write(
        "🛑 产出审查 gate: task %s has no 审查-pass%s. 不过审查不准过 — the 审查官 must "
        "pass 产出审查 and write `%s.pass` or `<dept>.%s.<n>.pass` (both are read) first. "
        "**Do not write it yourself**: a producer signing its own review is what this "
        "gate exists to prevent."
        % (task_id, (" (card #%s either)" % card) if card else "", task_id, card or task_id))
    sys.exit(2)


if __name__ == "__main__":
    main()