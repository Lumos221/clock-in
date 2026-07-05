#!/usr/bin/env python3
"""Stop / SubagentStop hook — auto-tally the 审查 ledger and surface HR-worthy
thresholds on the Boss Board.

The 审查官's markers under docs/reviews/ ARE the counter (append-only): `plan.<n>.refute`
= L1 refutes against the CEO, `<dept>.<id>.<n>.fail` = L2 bounces per dept. 人事部 used to
tally these by hand (`ls | wc -l`); this hook does it every turn and, when a documented
threshold in orchestrate.json is first crossed, raises ONE Boss-Board item via board.py —
the same channel dept `@BOSS` asks use. A sentinel per (metric, level) under
docs/reviews/.tally/ makes it flag-once, even across a Boss dismissal.

orchestrate.json stays thresholds-only (no counters); the files are the ledger; this hook
just compares. Fail-open: any error → no-op. Never blocks a turn (always exit 0)."""
import sys, os, json, glob

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "skills", "orchestrate", "scripts")
sys.path.insert(0, SCRIPTS)
try:
    import board
except Exception:
    board = None


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


def _flag_once(root, key, dept, text):
    """Raise a Boss-Board item once per (metric, level). The sentinel makes it idempotent
    across turns even if the Boss dismisses the item; board dedup covers the still-open case."""
    sent = os.path.join(root, "docs", "reviews", ".tally", key)
    if os.path.exists(sent):
        return
    try:
        board.board_add(root, dept, "needs", text)
        os.makedirs(os.path.dirname(sent), exist_ok=True)
        open(sent, "w").close()
    except Exception:
        pass


def tally(root, thresholds):
    """Count the ledger and flag any first-crossed threshold. Pure of stdin/plumbing so
    it's directly testable. thresholds = orchestrate.json's `thresholds` dict."""
    rev = os.path.join(root, "docs", "reviews")
    if not os.path.isdir(rev):
        return
    th = thresholds or {}

    # L1 — CEO plan refutes (plan.<n>.refute); the whole org has one CEO.
    refute_t = int(th.get("chaos_ceo_refutes", 3))
    n_ref = len(glob.glob(os.path.join(rev, "plan.*.refute")))
    if n_ref >= refute_t:
        _flag_once(root, "ceo-refute-%d" % refute_t, "人事部",
                   "⚠ CEO 已累计 %d 次 L1 封驳 (阈值 %d) — 人事部 escalation over the CEO" % (n_ref, refute_t))

    # L2 — per-dept output bounces (<dept>.<id>.<n>.fail).
    retune_t = int(th.get("retune_after_bounces", 3))
    fire_t = retune_t + int(th.get("fire_after_more_fails", 3))
    counts = {}
    for f in glob.glob(os.path.join(rev, "*.fail")):
        dept = os.path.basename(f).split(".", 1)[0]
        if dept and dept != "plan":
            counts[dept] = counts.get(dept, 0) + 1
    for dept, n in counts.items():
        if n >= fire_t:
            _flag_once(root, "%s-fail-%d" % (dept, fire_t), "人事部",
                       "⚠ %s 已累计 %d 次 L2 封驳 (阈值 %d) — 人事部 fire & re-hire" % (dept, n, fire_t))
        elif n >= retune_t:
            _flag_once(root, "%s-fail-%d" % (dept, retune_t), "人事部",
                       "⚠ %s 已累计 %d 次 L2 封驳 (阈值 %d) — 人事部 retune" % (dept, n, retune_t))


def main():
    if board is None:
        return
    if os.environ.get("BOSS_BOARD_SKIP_SERVER"):
        board._SKIP_SERVER = True
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    root = find_root(data.get("cwd") or os.getcwd())
    if not root:
        return
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
    except Exception:
        return
    if not cfg.get("active"):
        return
    tally(root, cfg.get("thresholds", {}))


if __name__ == "__main__":
    main()
