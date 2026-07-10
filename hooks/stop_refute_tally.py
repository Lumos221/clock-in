#!/usr/bin/env python3
"""Stop / SubagentStop hook — auto-tally the 审查 ledger and surface threshold
crossings on the Boss Board.

The 审查官's markers under docs/reviews/ ARE the counter (append-only): `plan.<n>.refute`
= L1 refutes against the CEO; `<dept>.<id>.<n>.fail` = L2 bounces, counted PER TASK —
not per dept career. A dept isn't an employee accruing strikes: consecutive bounces on
one task share one root cause, so the useful move is to stop the rework loop early and
diagnose, not to accumulate a discipline file. `bounce_diagnose` (default 2) halts the
loop for a one-shot 督察 (Inspector) 复盘; `bounce_escalate` (default 3) puts the task
on the Boss Board as stuck.

Counts self-expire: task completion archives that task's markers (posttool hook), and a
sentinel whose count has dropped back below threshold is re-armed (deleted) — no manual
reset ritual, nothing to remember. orchestrate.json stays thresholds-only; the files are
the ledger; this hook just compares. Fail-open: any error → no-op. Never blocks a turn
(always exit 0)."""
import sys, os, json, glob

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
try:
    import board
    import hooklib
except Exception:
    board = hooklib = None


def _sentinel(root, key):
    return os.path.join(root, "docs", "reviews", ".tally", key)


def _flag_once(root, key, dept, text):
    """Raise a Boss-Board item once per sentinel key — idempotent across turns even if
    the Boss dismisses the item; board dedup covers the still-open case."""
    sent = _sentinel(root, key)
    if os.path.exists(sent):
        return
    try:
        board.board_add(root, dept, "needs", text)
        os.makedirs(os.path.dirname(sent), exist_ok=True)
        open(sent, "w").close()
    except Exception:
        pass


def _unflag(root, key):
    """Re-arm a sentinel whose count dropped below threshold (ledger archived) — the
    next crossing must flag again; a permanent sentinel would go silent for good."""
    try:
        sent = _sentinel(root, key)
        if os.path.exists(sent):
            os.remove(sent)
    except OSError:
        pass


def _roster_handles(roster):
    """Lower-cased canonical handles from orchestrate.json's `roster` — entries may be
    plain strings or dicts (recruit has used both shapes)."""
    hs = set()
    for r in roster or []:
        if isinstance(r, str):
            h = r
        elif isinstance(r, dict):
            h = r.get("handle") or r.get("name") or r.get("id") or ""
        else:
            h = ""
        if h:
            hs.add(str(h).lower())
    return hs


def _known_handles(root, roster):
    """Every legitimate marker handle, lower-cased: the roster (standing teammates)
    PLUS the filenames under .claude/agents/ — the design-native registry that also
    covers project-local patterns (on-demand depts, experts) without inventing a new
    config key. Field report 2026-07-10: Fin/Prof_/Spec_ lived outside `roster` and
    would have false-flagged as aliases on a legitimate bounce."""
    hs = _roster_handles(roster)
    try:
        for f in os.listdir(os.path.join(root, ".claude", "agents")):
            if f.endswith(".md"):
                hs.add(f[:-3].lower())
    except OSError:
        pass
    return hs


def tally(root, thresholds, roster=None):
    """Count the ledger and flag threshold crossings. Pure of stdin/plumbing so it's
    directly testable. thresholds = orchestrate.json's `thresholds` dict; roster (its
    `roster` list, optional) arms the alias detector."""
    rev = os.path.join(root, "docs", "reviews")
    if not os.path.isdir(rev):
        return
    th = thresholds or {}

    # L1 — CEO plan refutes (plan.<n>.refute); the whole org has one CEO.
    refute_t = int(th.get("chaos_ceo_refutes", 3))
    n_ref = len(glob.glob(os.path.join(rev, "plan.*.refute")))
    l1_key = "ceo-refute-%d" % refute_t
    if n_ref >= refute_t:
        _flag_once(root, l1_key, "督察",
                   "⚠ CEO 已累计 %d 次 L1 封驳 (阈值 %d) — direction problem: Boss call needed (approve as-is / reframe)" % (n_ref, refute_t))
    else:
        _unflag(root, l1_key)

    # L2 — per-TASK bounces (<dept>.<id>.<n>.fail). Dept keys lower-cased: the same
    # dept has shown up under inconsistent casing across files ("Frontend" vs
    # "frontend") — raw-string grouping would fracture one task's count into buckets.
    diagnose_t = int(th.get("bounce_diagnose", 2))
    escalate_t = int(th.get("bounce_escalate", 3))
    counts = {}
    display = {}
    prefixes = {}  # dkey -> (raw, total file count) — for the alias detector below
    for f in sorted(glob.glob(os.path.join(rev, "*.fail"))):
        parts = os.path.basename(f).split(".")
        if len(parts) != 4 or parts[0] == "plan" or not parts[0]:
            continue  # not a <dept>.<id>.<n>.fail marker
        dept_raw, task_id = parts[0], parts[1]
        k = (dept_raw.lower(), task_id)
        counts[k] = counts.get(k, 0) + 1
        display.setdefault(k, dept_raw)
        raw, n = prefixes.get(k[0], (dept_raw, 0))
        prefixes[k[0]] = (raw, n + 1)
    for (dkey, tid), n in counts.items():
        dept = display[(dkey, tid)]
        esc_key = "%s.%s.escalate" % (dkey, tid)
        diag_key = "%s.%s.diagnose" % (dkey, tid)
        if n >= escalate_t:
            _flag_once(root, esc_key, dept,
                       "⚠ task %s (%s) 已连续 %d 次 L2 封驳 — 复盘后仍卡: Boss decision (re-scope / drop / take over)" % (tid, dept, n))
        elif n >= diagnose_t:
            _flag_once(root, diag_key, dept,
                       "⚠ task %s (%s) 已连续 %d 次 L2 封驳 — 停止盲目返工: CEO invoke the 督察 (Inspector) to 复盘 now" % (tid, dept, n))
        if n < diagnose_t:
            _unflag(root, diag_key)
        if n < escalate_t:
            _unflag(root, esc_key)

    # Alias detector — a marker written under an unknown handle (legacy alias like
    # "web" for "Frontend") splits one task's count across buckets and silently evades
    # the circuit breaker (real incident: web.40.1.fail, 2026-07-07). The Auditor's
    # contract says to normalize, but this catch must not depend on an agent obeying
    # prose — surface any unknown prefix the moment it appears in the ledger.
    known = _known_handles(root, roster)
    if known:
        for dkey, (raw, n) in prefixes.items():
            key = "alias-%s" % dkey
            if dkey not in known:
                _flag_once(root, key, "督察",
                           "⚠ 审查 ledger holds a non-roster handle '%s' (%d file(s)) — markers under an alias split per-task counts and evade the circuit breaker; normalize to the roster handle" % (raw, n))
            else:
                _unflag(root, key)
        for s in glob.glob(os.path.join(rev, ".tally", "alias-*")):
            if os.path.basename(s)[len("alias-"):] not in prefixes:
                _unflag(root, os.path.basename(s))  # alias gone (renamed/archived) → re-arm


def run(data, text=None):
    """`text` is accepted for dispatcher signature parity; the tally reads the ledger,
    not the transcript."""
    if board is None or hooklib is None:
        return
    if os.environ.get("BOSS_BOARD_SKIP_SERVER"):
        board._SKIP_SERVER = True
    root = hooklib.find_root(data.get("cwd") or os.getcwd())
    if not root:
        return
    # Pierce a linked worktree to the main checkout: the 审查官 writes the ledger to the
    # MAIN tree's docs/reviews/, so counting a worktree's checked-out copy would tally
    # stale files and raise flags on a board the Boss never watches.
    root = board.main_checkout(root)
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
    except Exception:
        return
    if not cfg.get("active"):
        return
    tally(root, cfg.get("thresholds", {}), cfg.get("roster"))


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    run(data)


if __name__ == "__main__":
    main()
