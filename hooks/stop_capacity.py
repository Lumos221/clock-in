#!/usr/bin/env python3
"""Capacity sentinel (Stop, via stop_dispatch — LEAD session only): the mid-session
answer to "two desks sat idle with ready cards until the Boss nudged the CEO".

Doctrine alone failed three times in the field (idle-desk reports 07-18 ×2, 07-19),
and the 07-19 postmortem found the deeper holes: ASSIGN never happened (every pending
card owner:None — designation lived only in TaskBoard `dept:` prose, mechanically
unclaimable), and both existing mechanical checks keyed liveness on members[].isActive,
which is a BUSY-flag (a responsive Registrar sat isActive:false), so the idle
teammates they exist to catch were exactly the ones they skipped.

At each lead turn end, reconcile the roster against the platform task store:
  a. idle desk + unblocked pending cards      → assign/dispatch or release
  b. pending card owner:None whose TaskBoard card `dept:` names a live desk
                                              → prose-designated, unclaimable — ASSIGN
  c. no Registrar while owner-set pending cards wait (a dept's CLAIM has no desk)
                                              → respawn the Registrar
  d. idle desk + nothing pending at all       → release the pane

Zero tokens when healthy (silent exit); one block per state-signature when not — the
signature covers idle-set + pending-set + registrar-state, so acting on the nudge (or
the state moving) re-arms it and ignoring it stays silent. Liveness = presence in
members[] (clean shutdown removes the entry; a zombie deserves flagging too).
Boss-in-pane-marked depts are never called idle. Widget-gated sessions (no task
store) stay silent. Fail-open everywhere."""
import os, re, sys, json, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    import hooklib
except Exception:
    hooklib = None
try:
    import board  # main_checkout only
except Exception:
    board = None

SUFFIX = re.compile(r"-\d+$")


def base(handle):
    return SUFFIX.sub("", handle or "")


def team_and_tasks(session_id):
    """(team_cfg, tasks) for the LEAD session, else (None, None). tasks = list of
    dicts with id/status/owner/subject/blockedBy. leadSessionId must match — a
    teammate session or an unrelated one never does."""
    if not session_id:
        return None, None
    cfg_root = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    key = "session-%s" % session_id[:8]
    try:
        team = json.load(open(os.path.join(cfg_root, "teams", key, "config.json"),
                              encoding="utf-8"))
    except Exception:
        return None, None
    if str(team.get("leadSessionId", "")) != str(session_id):
        return None, None
    tasks_dir = os.path.join(cfg_root, "tasks", key)
    tasks = []
    try:
        names = os.listdir(tasks_dir)
    except Exception:
        return team, None  # widget-gated: no store, no judgement
    for fn in names:
        if not fn.endswith(".json"):
            continue
        try:
            t = json.load(open(os.path.join(tasks_dir, fn), encoding="utf-8"))
        except Exception:
            continue
        if isinstance(t, dict):
            tasks.append(t)
    return team, tasks


def card_dept(tb_text, task_id):
    """The TaskBoard card's `dept:` field for this platform id, '' if unfindable."""
    if not tb_text or hooklib is None:
        return ""
    span = hooklib.tb_card_span(tb_text, str(task_id))
    if not span:
        return ""
    m = re.search(r"\*\*dept:\*\*\s*([^\n]+)", tb_text[span[0]:span[1]])
    return m.group(1).strip() if m else ""


def run(data, text):
    """Dispatcher contract: return the block reason (str) to nudge, else None."""
    if data.get("hook_event_name") != "Stop":
        return None
    if data.get("stop_hook_active"):
        return None
    if hooklib is None:
        return None
    root = hooklib.find_root(data.get("cwd") or "")
    if not root:
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
    team, tasks = team_and_tasks(str(data.get("session_id") or ""))
    if not team or tasks is None:
        return None

    try:
        pane = json.load(open(os.path.join(root, ".claude", "boss-in-pane.json"),
                              encoding="utf-8"))
        pane_exempt = {base(k).lower() for k in pane}
    except Exception:
        pane_exempt = set()

    depts, registrar_live = [], False
    for m in team.get("members", []):
        if not isinstance(m, dict):
            continue
        name = str(m.get("name", ""))
        if not name or name == "team-lead":
            continue
        if base(name).lower().startswith("registrar"):
            registrar_live = True
            continue
        depts.append(name)

    open_ids = {str(t.get("id")) for t in tasks
                if t.get("status") in ("pending", "in_progress")}
    # Busy = EXACT handle owns an in_progress card (ASSIGN doctrine: owners are the
    # exact live handle). Base-matching would let a busy Frontend hide an idle
    # Frontend-2 — second lanes are deliberate (Boss's rule 2026-07-19) and each
    # lane earns its own idle judgement.
    doing_owners = set()
    pending = []
    for t in tasks:
        if t.get("status") == "in_progress" and t.get("owner"):
            doing_owners.add(str(t["owner"]).strip().lower())
        elif t.get("status") == "pending":
            blocked = any(str(b) in open_ids for b in (t.get("blockedBy") or []))
            if not blocked:
                pending.append(t)

    idle = [d for d in depts
            if d.lower() not in doing_owners
            and base(d).lower() not in pane_exempt]

    # prose-designated but unclaimable: pending, unowned, card dept names a live desk
    tb_text = ""
    try:
        tb_text = open(os.path.join(root, cfg.get("taskboard", "docs/TaskBoard.md")),
                       encoding="utf-8").read()
    except Exception:
        pass
    unassigned = []
    for t in pending:
        if t.get("owner"):
            continue
        dept_field = card_dept(tb_text, t.get("id"))
        if any(base(d).lower() in dept_field.lower() for d in depts if dept_field):
            unassigned.append("#%s" % t.get("id"))

    assigned_pending = [t for t in pending if t.get("owner")]
    problems = []
    if idle and pending:
        problems.append(
            "idle desk(s) %s + %d unblocked pending card(s) — ASSIGN (owner=<handle>, "
            "keep pending) for queue-pull or dispatch directly; a desk with nothing "
            "coming → release it (shutdown request)"
            % (", ".join(idle[:4]), len(pending)))
    elif idle:
        problems.append(
            "idle desk(s) %s with nothing pending — release them (per-task lifecycle; "
            "a fresh spawn beats a stale window)" % ", ".join(idle[:4]))
    if unassigned:
        problems.append(
            "card(s) %s carry a dept in TaskBoard prose but owner:None on the widget — "
            "prose is invisible to CLAIM; ASSIGN them or the queue never moves"
            % ", ".join(unassigned[:5]))
    if assigned_pending and not registrar_live:
        problems.append(
            "%d ASSIGNed pending card(s) but no live Registrar — depts cannot CLAIM; "
            "respawn it (Agent subagent_type:\"clock-in:Registrar\", name:\"Registrar\", "
            "model:\"haiku\", run_in_background:true)" % len(assigned_pending))
    if not problems:
        return None

    sig = hashlib.md5(json.dumps([sorted(idle), sorted(t.get("id") for t in pending),
                                  sorted(unassigned), registrar_live],
                                 default=str).encode("utf-8")).hexdigest()
    state = os.path.join(root, ".claude", "capacity-nudge-state")
    try:
        if open(state, encoding="utf-8").read().strip() == sig:
            return None
    except Exception:
        pass
    try:
        os.makedirs(os.path.dirname(state), exist_ok=True)
        with open(state, "w", encoding="utf-8") as f:
            f.write(sig)
    except Exception:
        return None  # can't cap → never risk a nudge loop
    return ("🛑 capacity: " + " · ".join(problems) +
            " (One nudge per state — acting on it or the state moving re-arms.)")


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    ret = run(data, None)
    if isinstance(ret, str) and ret:
        sys.stderr.write(ret)
        sys.exit(2)


if __name__ == "__main__":
    main()
