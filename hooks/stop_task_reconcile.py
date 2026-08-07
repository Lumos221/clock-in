#!/usr/bin/env python3
"""Stop piece — reconcile the CARD STORE against the TASK WIDGET at turn end.
Advisory + self-healing: writes the cards, never blocks (returns None). Fail-open,
lead-only, inert off an active orchestrate project.

WHY. The task widget showed #342, #357 and #359 as in-progress while the board read
`todo` for the first two and had NO widget id at all for the third. Diagnosis, proven step by step rather than guessed:
  · `find_task` resolves widget id 59→#342 and 61→#357 correctly,
  · the widget store really does hold both at `in_progress` with dept owners,
  · and feeding `posttool_task_sync` the exact payload flips `todo`→`doing` first try.
So the mirror logic is sound and **the hook simply never ran for those calls** — the write
came from a session whose plugin hooks were not in play (a dept claims through the
Registrar, so the `TaskUpdate` happens in the Registrar's session, not the CEO's).

Chasing which session loads which hooks is the wrong fix. **The sync must not depend on
catching the tool call.** This is exactly the shape of the 0.9.46 problem — completions
missed `BACKLOG.md` because the tool-keyed hook didn't fire — and it gets the same answer:
a Stop-time reconciler keyed on DURABLE STATE that converges no matter who called what.

Three drifts healed, all forward-only:
  ① widget `in_progress` + card `todo` → card advances to `doing`,
  ② widget `owner` set + card `dept` empty → dept filled,
  ③ card with NO `task_id` whose durable `#NNN` leads a widget subject → the link is
     backfilled (that was #359: live in the widget, unlinked on the board).

**Never downgrades.** A card at `doing` while the widget still says `pending` means the
dept flipped its own status and the widget lagged — the dept is the more truthful witness
there, so leave it. `completed` is owned by `posttool_backlog_log` / `stop_done_sweep`;
this piece never retires anything.
"""
import os, re, sys, json, glob

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
try:
    import hooklib
except Exception:
    hooklib = None
try:
    import cardlib
except Exception:
    cardlib = None
try:
    import board
except Exception:
    board = None

ADVANCE = {"in_progress": "doing"}     # forward-only; pending never pushes a card back
CAP = 12
LEAD_RE = re.compile(r"#(\d+)")


def widget_tasks(session_id, cwd=None):
    """{id: {status, owner, subject}} from this project's task store, or {}.

    Resolved through hooklib.tasks_dir, NOT `session-<current id>` — the store key is
    the id the session carried when the store was born and does not follow a resume.
    Keying on the live id made this whole piece a no-op in the field (2026-07-26)."""
    d = hooklib.tasks_dir(session_id, cwd) if hooklib else None
    if not d:
        return {}
    out = {}
    for p in glob.glob(os.path.join(d, "*.json")):
        try:
            t = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id") or "").strip()
        if tid:
            out[tid] = {"status": str(t.get("status") or "").strip(),
                        "owner": str(t.get("owner") or "").strip(),
                        "subject": str(t.get("subject") or "")}
    return out


def reconcile(root, cfg, tasks):
    """Apply the three forward-only heals. Returns human-readable trace lines."""
    bdir, _ = cardlib.ensure_store(root, cfg)
    if not bdir:
        return []
    cards = cardlib.load(bdir)
    traces = []

    # ③ first: a card with no task_id can't be compared until it's linked. Match on the
    # durable #NNN leading a widget subject, and only when exactly one unlinked card wears
    # that number — an ambiguous number is what birthed ghost cards on 2026-07-20.
    unlinked = [c for c in cards if not cardlib.clean(str(c.get("task_id") or ""))]
    if unlinked:
        by_num = {}
        for tid, t in tasks.items():
            m = LEAD_RE.search(t["subject"])
            if m:
                by_num.setdefault(m.group(1), []).append(tid)
        for c in unlinked:
            num = str(c.get("id") or "").strip()
            ids = by_num.get(num) or []
            if len(ids) == 1 and str(c.get("status") or "").strip().lower() != "done":
                cardlib.set_fields(c, task_id=ids[0])
                traces.append("#%s ← widget id %s (was unlinked)" % (num, ids[0]))

    for c in cards:
        tid = cardlib.clean(str(c.get("task_id") or ""))
        if not tid or tid not in tasks:
            continue
        t = tasks[tid]
        status = (c.get("status") or "").strip().lower()
        if status == "done":
            continue
        # ① forward-only status advance
        target = ADVANCE.get(t["status"])
        if target and status != target:
            cardlib.set_fields(c, status=target)
            traces.append("#%s %s → %s (widget %s)"
                          % (c.get("id"), status or "—", target, t["status"]))
        # ② owner → dept when the card names nobody
        if t["owner"] and not cardlib.clean(str(c.get("dept") or "")):
            cardlib.set_fields(c, dept=t["owner"])
            traces.append("#%s dept ← %s (widget owner)" % (c.get("id"), t["owner"]))
    if traces:
        try:
            cardlib.regen_digest(root, cfg)
        except Exception:
            pass
    return traces


def run(data, text=None):
    if hooklib is None or cardlib is None:
        return None
    # CEO-only output: a teammate finishing a turn is a Stop in ITS OWN session, so
    # the event excludes nobody — only the session identity does.
    if not hooklib.is_lead(data.get("transcript_path") or ""):
        return None
    root = hooklib.find_root(data.get("cwd") or "")
    if not root:
        return None
    # A 分公司 runs its OWN session in a worktree, and `root` has been pierced to the
    # main checkout — so this would judge the CEO's board against the BRANCH's roster and
    # task store. Its own lane is not the CEO team's queue.
    if hooklib.local_office(data.get("cwd") or ""):
        return None
    if board is not None:
        try:
            root = board.main_checkout(root)
        except Exception:
            pass
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"),
                             encoding="utf-8"))
        if not cfg.get("active"):
            return None
    except Exception:
        return None
    tasks = widget_tasks(data.get("session_id"), data.get("cwd") or "")
    if not tasks:
        return None                      # widget-gated or not the lead — nothing to compare
    try:
        traces = reconcile(root, cfg, tasks)
    except Exception:
        return None
    if traces:
        shown = traces[:CAP]
        extra = "" if len(traces) <= CAP else "\n   … +%d more" % (len(traces) - CAP)
        sys.stderr.write("\n🔗 widget↔board reconciled (%d): %s%s\n"
                         % (len(traces), " · ".join(shown), extra))
    return None                          # advisory — never blocks
