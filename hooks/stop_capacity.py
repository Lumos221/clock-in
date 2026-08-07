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
  b. pending card owner:None whose card `dept:` names EXACTLY ONE live desk and whose
     `blocked_on` is empty                    → prose-designated, unclaimable — ASSIGN
  c. no Registrar while owner-set pending cards wait (a dept's CLAIM has no desk)
                                              → respawn the Registrar
  d. idle desk + nothing pending at all       → release the pane
  e. a seat that has closed `seat_cards_max` cards → rotate it. Holding none: retire now
     and spawn `<Dept>-<NNN>` for the next card (one card per seat). Still holding work: the seat is on its LAST card — queue nothing more
     onto it, retire at the boundary. The old "only between cards" gate was a mute
     button: a queue-fed seat never HAS a between-cards moment, so the one pattern the
     counter existed to catch (a seat with four closed cards
     and two more in progress, never flagged) was exactly the one it never spoke about.
  f. an in_progress card whose owner is not in members[] → the seat is gone and the card
     still claims to be worked on. This is (a) read the other way round, and it was the
     missing half: the sweep asked which desks had no card, never which cards had no
     desk, so a pane that died holding work left that card frozen and unreported.
  g. more open cards ASSIGNed to one exact handle than that seat may still close →
     the tail will strand. A seat retires at `seat_cards_max` closed and its successor
     cannot CLAIM the dead handle's cards (owner match is exact), so a queue deeper
     than the seat's remaining room is a re-ASSIGN debt being written now. The closed
     counter (e) watches the past; nothing watched the queue — field case 2026-08-07,
     five cards on one seat, counter at zero, silence.

A recorded hold is not a stall: a card carrying `blocked_on` has already been answered
by the CEO in writing, and re-raising it is the sentinel arguing with its own doctrine.

Zero tokens when healthy (silent exit); one block per state-signature when not — the
signature covers the TRIGGER set (idle desks + unassignable cards + registrar state),
never the whole pending list, so an unrelated card appearing elsewhere cannot re-arm
the identical alarm. Acting on the nudge (or the trigger moving) re-arms it and
ignoring it stays silent. Liveness = presence in
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
SEAT_CARDS_MAX = 3      # cards one seat may close before it should be retired


def base(handle):
    return SUFFIX.sub("", handle or "")


def team_and_tasks(session_id, cwd=None):
    """(team_cfg, tasks) for this project's lead team, else (None, None). tasks = list
    of dicts with id/status/owner/subject/blockedBy.

    Both stores resolve through hooklib on the session's OWN cwd (never a pierced
    root — see hooklib.team_key): the store key does not follow a resume, and the exact
    cwd match is what keeps this lead-only."""
    team = hooklib.team_config(session_id, cwd) if hooklib else None
    if not team:
        return None, None
    tasks_dir = hooklib.tasks_dir(session_id, cwd)
    tasks = []
    try:
        names = os.listdir(tasks_dir) if tasks_dir else []
    except Exception:
        return team, None  # widget-gated: no store, no judgement
    if not names:
        return team, None
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


def card_facts(tb_text, task_id):
    """(durable #NNN, dept prose, blocked_on) for this platform id; ('','','') if the
    card can't be found. The durable number is what the Boss's board speaks — a nudge
    naming only the widget id ("#36") names nothing they can look up."""
    if not tb_text or hooklib is None:
        return "", "", ""
    span = hooklib.tb_card_span(tb_text, str(task_id))
    if not span:
        return "", "", ""
    block = tb_text[span[0]:span[1]]
    num = re.search(r"^###\s+#(\d+)", block)
    dept = re.search(r"\*\*dept:\*\*\s*([^\n]+)", block)
    held = re.search(r"\*\*blocked_on:\*\*\s*([^\n]+)", block)
    return (num.group(1) if num else "",
            dept.group(1).strip() if dept else "",
            hooklib.tb_clean(held.group(1)) if held else "")


def dept_target(dept_field, depts):
    """The single live handle this dept field ASSIGNS to, or '' when it is prose.

    A field is an assignment target only when it reduces to one handle: strip trailing
    parentheticals ("Frontend (sonnet seat, diagnosis leg)" is still Frontend) and the
    remainder must BE a live dept. Anything carrying a second dept, a conjunction or a
    narrative clause — "Backend-Engine (types) + Backend-IO (parse/render) — CEO writes
    the field-model spec before dispatch" — is a card the CEO still has to SPLIT, and
    "ASSIGN them or the queue never moves" is an instruction nobody can obey.

    Counting how many live depts the prose MENTIONS is not enough: that card names two
    depts but only one of them was live, so it read as a single target anyway."""
    s = re.sub(r"\([^)]*\)", " ", dept_field or "")
    s = re.sub(r"\s+", " ", s).strip(" ·,;")
    for d in depts:
        if s.lower() in (d.lower(), base(d).lower()):
            return d
    return ""


def run(data, text):
    """Dispatcher contract: return the block reason (str) to nudge, else None."""
    if data.get("hook_event_name") != "Stop":
        return None
    if data.get("stop_hook_active"):
        return None
    if hooklib is None:
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
    team, tasks = team_and_tasks(str(data.get("session_id") or ""),
                                 data.get("cwd") or "")
    if not team or tasks is None:
        return None

    try:
        seat_max = float(cfg.get("seat_cards_max", SEAT_CARDS_MAX))
    except Exception:
        seat_max = SEAT_CARDS_MAX
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
    # Frontend-2 — second lanes are deliberate and each
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

    # (e) ACCUMULATION — computed before the idle list so a fat seat is never ALSO
    # offered new work by (a). One card per seat is the design; queue-pull and
    # re-tasking route around it, so the closed-card count is what actually catches
    # it however it happened. The point is not token cost but QUALITY — a seat
    # carrying several cards' abandoned approaches re-proposes them, the same way a
    # decision left in prose re-teaches its own dead design. A seat mid-card is not
    # told to retire NOW (that is noise) — it is told it is on its last card, because
    # waiting for a between-cards moment on a queue-fed seat means waiting forever.
    closed = {}
    for t in tasks:
        o = str(t.get("owner") or "").strip().lower()
        if o and t.get("status") == "completed":
            closed[o] = closed.get(o, 0) + 1
    fat = [(d, closed.get(d.lower(), 0)) for d in depts
           if closed.get(d.lower(), 0) >= seat_max]
    fat_names = {d.lower() for d, _ in fat}
    fat_idle = [(d, n) for d, n in fat if d.lower() not in doing_owners]
    fat_busy = [(d, n) for d, n in fat if d.lower() in doing_owners]

    idle = [d for d in depts
            if d.lower() not in doing_owners
            and base(d).lower() not in pane_exempt
            and d.lower() not in fat_names]

    # prose-designated but unclaimable: pending, unowned, card dept names a live desk
    tb_text = ""
    try:
        tb_text = open(os.path.join(root, cfg.get("taskboard", "docs/TaskBoard.md")),
                       encoding="utf-8").read()
    except Exception:
        pass
    # Prose-designated but unclaimable — with two exemptions the field taught on
    # 2026-07-26, when this fired twice on five cards that were all deliberate holds:
    #   · a non-empty `blocked_on` IS the CEO recording why the queue is not moving.
    #     Nagging a hold that has been written down inverts the discipline this exists
    #     to enforce, and no reply can clear it because nothing is wrong.
    #   · ASSIGN takes exactly ONE owner, so the field must REDUCE to one handle
    #     (dept_target). "Engine (types) + IO (render) — CEO writes the spec" is a card
    #     still to be SPLIT, and ASSIGN cannot act on it.
    unassigned = []
    for t in pending:
        if t.get("owner"):
            continue
        num, dept_field, held = card_facts(tb_text, t.get("id"))
        if held or not dept_target(dept_field, depts):
            continue
        unassigned.append("#%s (widget %s)" % (num, t.get("id")) if num
                          else "#%s" % t.get("id"))

    assigned_pending = [t for t in pending if t.get("owner")]

    # (f) STRANDED WORK — the mirror of (a), and the half this never looked at. It asks
    # which desks have no card; it never asked which cards have no desk. A seat that dies
    # or is released while holding an in_progress card leaves that card saying someone is
    # working on it, forever: it is not pending, so (a) never offers it to an idle desk,
    # and its owner is not in members[], so no idle judgement is ever made about it. The
    # card is simply not moving and nothing on the board says so. Field case 2026-08-04:
    # a seat's pane closed at 16:01 and its card sat in_progress behind it for three
    # hours in silence, while the sentinel reported a healthy team.
    live_handles = {str(m.get("name", "")).strip().lower()
                    for m in team.get("members", []) if isinstance(m, dict)}
    ext = hooklib.externals(cfg) if hooklib else set()
    stranded = []
    for t in tasks:
        if t.get("status") != "in_progress":
            continue
        owner = str(t.get("owner") or "").strip()
        # A 分公司 runs its own session and never appears in members[] — its cards are
        # not stranded, they are simply not on this team's lifecycle.
        if not owner or owner.lower() in live_handles or base(owner).lower() in ext:
            continue
        num, _, _ = card_facts(tb_text, t.get("id"))
        stranded.append("#%s (%s)" % (num, owner) if num
                        else "widget %s (%s)" % (t.get("id"), owner))

    # (g) OVERQUEUE — see the docstring. Fat seats are skipped: (e) already gives that
    # seat its order, and two alarms about one desk teach the reader to skim both.
    open_by = {}
    for t in tasks:
        o = str(t.get("owner") or "").strip()
        if o and t.get("status") in ("pending", "in_progress"):
            open_by[o] = open_by.get(o, 0) + 1
    overq = []
    for o, n in sorted(open_by.items()):
        ol = o.lower()
        if ol in fat_names or base(o).lower() in ext or ol.startswith("registrar"):
            continue
        room = max(int(seat_max) - closed.get(ol, 0), 0)
        if n > room:
            overq.append((o, n, room))

    problems = []
    if idle and pending:
        problems.append(
            "idle desk(s) %s + %d unblocked pending card(s) — ASSIGN (owner=<handle>, "
            "keep pending) or dispatch directly; nothing coming → release the desk"
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
    if fat_idle:
        problems.append(
            "seat(s) %s have each closed %s cards and hold none — retire them (shutdown "
            "request) and spawn '<Dept>-<NNN>' for the next card; a seat carrying "
            "several cards' dead ends re-proposes them"
            % (", ".join("%s (%d)" % (d, n) for d, n in fat_idle[:4]),
               "≥%d" % seat_max if len(fat_idle) > 1 else str(fat_idle[0][1])))
    if fat_busy:
        problems.append(
            "seat(s) %s have each closed %s cards and STILL hold work — treat the card "
            "in hand as its LAST: queue nothing more, and when it lands retire the seat "
            "(shutdown request) and spawn '<Dept>-<NNN>' fresh"
            % (", ".join("%s (%d)" % (d, n) for d, n in fat_busy[:4]),
               "≥%d" % seat_max if len(fat_busy) > 1 else str(fat_busy[0][1])))
    if stranded:
        problems.append(
            "card(s) %s are in_progress under a seat no longer on the team — re-ASSIGN "
            "to a live desk, or set them back to pending so the queue can reach them"
            % ", ".join(stranded[:5]))
    if overq:
        problems.append(
            "queue too deep: %s — a seat retires at %d closed and its successor cannot "
            "CLAIM a dead handle's cards; keep each queue within what the seat can "
            "still close, the tail goes owner-less pending or to fresh '<Dept>-<NNN>' "
            "seats" % (", ".join("%s holds %d open / can close %d more" % x
                                 for x in overq[:4]), int(seat_max)))
    if assigned_pending and not registrar_live:
        problems.append(
            "%d ASSIGNed pending card(s) but no live Registrar — depts cannot CLAIM; "
            "respawn it (Agent subagent_type:\"clock-in:Registrar\", name:\"Registrar\", "
            "model:\"haiku\", run_in_background:true)" % len(assigned_pending))
    if not problems:
        return None

    # The signature covers the TRIGGER set, never the whole pending list. Hashing every
    # pending id meant any unrelated card born or completed anywhere on the board
    # re-armed the nudge, so "one per state" repeated the identical five-card alarm turn
    # after turn. Same complaint → same signature → silent.
    sig = hashlib.md5(json.dumps([sorted(idle), sorted(unassigned), registrar_live,
                                  bool(pending), bool(assigned_pending),
                                  sorted(d for d, _ in fat_idle),
                                  sorted(d for d, _ in fat_busy),
                                  sorted(stranded),
                                  sorted(o for o, _, _ in overq)],
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
