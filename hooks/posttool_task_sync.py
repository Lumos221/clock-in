#!/usr/bin/env python3
"""PostToolUse hook — the board follows the platform task list (the widget), not the
other way round. Since 0.9.28 the board's truth is the per-card store (cardlib:
docs/board/<id>-<slug>.md; TaskBoard.md is the generated digest), and this hook is
its main writer: `TaskCreate` births the card with `task_id` pre-filled AND the
durable #NNN minted at birth (want the subject's leading #NNN when that number is
free — the 0.9.26 card-face norm — else the next free number); a hand-written card
is FILLED, not duplicated — matched by exact name, by the durable card number the
subject leads with, or by normalised name (0.9.20; the exact-only match left
`task_id: —` on real cards while appending hook-dup minimal ones, so completions
retired the wrong card — refcheck field report); `TaskUpdate` mirrors the coarse
lifecycle onto the card (pending→todo · in_progress→doing · owner fills an empty
dept) and retires a cancelled/deleted task's card to archive/ (forward-proofing —
the CLI's status enum is currently just pending/in_progress/completed, verified in
2.1.206). Fine states (review/blocked) stay dept-written prose — the widget doesn't
know them, and this hook never overwrites what it only half understands: task_id
matching keeps the exactly-one-id contract (shared multi-id cards match nobody).
`completed` is NOT handled here — posttool_backlog_log.py owns that transition
(backlog row + shipped tail + card retirement), so the two hooks can never write
the same card on the same event.

A recycled id (platform ids restart each session; a stale active card may still
hold last session's `3`) detaches the old card — its task_id becomes `—`, a trace
lands in .claude/marker-misses.log — and a fresh card is born. A legacy single-file
board migrates lazily on the first actionable event (cardlib.ensure_store).
Fail-open: any error → no-op. Acts only inside an active orchestrate project."""
import sys, os, re, json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
try:
    import hooklib, cardlib
except Exception:
    hooklib = cardlib = None
try:
    import board  # only for main_checkout (worktree piercing)
except Exception:
    board = None

STATUS_MAP = {"pending": "todo", "in_progress": "doing"}
RETIRE = {"deleted", "cancelled"}
DONE_WHEN_PLACEHOLDER = "<CEO fills — acceptance criterion from the dispatch spec>"


def _norm(s):
    """Normalise a card name / CREATE subject for matching: strip a leading card
    number (#NNN), treat the heading separator as whitespace, collapse runs,
    casefold. '#130 · REDEEM — X' and '#130 REDEEM — X' become the same string."""
    s = re.sub(r"^#\d+\s*", "", (s or "").strip())
    return re.sub(r"\s+", " ", s.replace("·", " ")).strip().casefold()


def _card_number(s):
    """The leading durable number ('#130 · SUBJECT' → 130), else None."""
    m = re.match(r"#(\d+)\b", s or "")
    return int(m.group(1)) if m else None


def extract_id(resp):
    """Task id from a tool_response of any plausible shape: dict keys (id/taskId/
    task_id), a nested `task` dict, content blocks, or the first `#N` / `task N` in a
    string ("Created task #7"). None when nothing id-like is present."""
    if isinstance(resp, dict):
        for k in ("id", "taskId", "task_id"):
            v = resp.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        t = resp.get("task")
        if isinstance(t, dict):
            return extract_id(t)
        c = resp.get("content")
        if isinstance(c, list):
            for b in c:
                if isinstance(b, dict) and b.get("type") == "text":
                    got = extract_id(b.get("text", ""))
                    if got:
                        return got
    if isinstance(resp, str):
        m = re.search(r"#(\d+)\b", resp) or re.search(r"\btask\s+(\d+)\b", resp, re.I)
        if m:
            return m.group(1)
    return None


def _head(card):
    return "#%d · %s" % (card["id"], card.get("name") or "")


def on_create(root, cfg, ti, resp):
    tid = extract_id(resp)
    if not tid:
        return
    subject = (ti.get("subject") or ti.get("description") or "").strip().splitlines()
    subject = subject[0].strip() if subject else ""
    if not subject:
        subject = "task %s" % tid
    bdir, _ = cardlib.ensure_store(root, cfg)
    if not bdir:
        return
    cards = cardlib.load(bdir)

    holder = cardlib.find_task(cards, tid)
    if holder:
        # duplicate/replayed event — same identity, nothing to do
        if subject and (subject in _head(holder)
                        or (_norm(subject) and _norm(subject) in (_norm(holder.get("name")),
                                                                  _norm(_head(holder))))):
            return
        # stale card holding a recycled id: detach it so the gate keys stay honest
        cardlib.set_fields(holder, task_id=cardlib.EMPTY)
        hooklib.log_marker_misses(root, "task-sync", [
            "task_id %s recycled by TaskCreate '%s' — stale card detached" % (tid, subject)])
        cards = cardlib.load(bdir)

    # 分公司 cards never join the platform lifecycle — registering one would pull the
    # branch's lane through the CEO team's gates. Not a fill candidate; a CREATE that
    # targeted one by number is refused with a trace instead of birthing a duplicate.
    unregistered = [c for c in cards if not cardlib.clean(c.get("task_id", ""))]
    external = [c for c in unregistered if hooklib.is_external(cfg, c.get("dept"))]
    unregistered = [c for c in unregistered if c not in external]
    sub_num_probe = _card_number(subject)

    def _targets(c):
        if sub_num_probe is not None and c["id"] == sub_num_probe:
            return True
        return (subject in (c.get("name"), _head(c))
                or (_norm(subject) and _norm(subject) in (_norm(c.get("name")),
                                                          _norm(_head(c)))))
    hit = next((c for c in external if _targets(c)), None)
    if hit is not None:
        hooklib.log_marker_misses(root, "task-sync", [
            "TaskCreate '%s' targets external (分公司) card #%d — not registered; "
            "the branch session owns that lane" % (subject, hit["id"])])
        return

    # the CEO hand-wrote this card first, then registered it → fill, don't duplicate.
    # Match tiers: ① exact name/head equality (historic behaviour) ② the durable card
    # number the subject leads with — ids are unique in the store, so #NNN names at
    # most one card ③ normalised equality (separator/space/case drift, exactly one
    # candidate — ambiguity falls through to a birth, never a guess).
    for c in unregistered:
        if subject and subject in (c.get("name"), _head(c)):
            cardlib.set_fields(c, task_id=tid)
            cardlib.regen_digest(root, cfg)
            return
    sub_num = _card_number(subject)
    if sub_num is not None:
        hits = [c for c in unregistered if c["id"] == sub_num]
        if len(hits) == 1:
            cardlib.set_fields(hits[0], task_id=tid)
            cardlib.regen_digest(root, cfg)
            return
        if len(hits) > 1:
            # a duplicated durable number: filling would guess, birthing would
            # cascade (the 07-20 refcheck incident — dup #189 birthed ghost #190).
            # dedupe_ids heals the store at turn end; this CREATE just refuses.
            hooklib.log_marker_misses(root, "task-sync", [
                "TaskCreate '%s': #%d worn by %d cards — ambiguous, no card filled "
                "or born; dedupe sweep renumbers at turn end" % (subject, sub_num, len(hits))])
            return
    sub_norm = _norm(subject)
    if sub_norm:
        hits = [c for c in unregistered
                if sub_norm in (_norm(c.get("name")), _norm(_head(c)))]
        if len(hits) == 1:
            cardlib.set_fields(hits[0], task_id=tid)
            cardlib.regen_digest(root, cfg)
            return

    desc = (ti.get("description") or ti.get("activeForm") or subject).strip()
    what = desc.splitlines()[0].strip()
    if len(what) > 160:
        what = what[:159] + "…"
    blocked = ti.get("blockedBy") or ti.get("blocked_by") or []
    blocked = ", ".join("#%s" % b for b in blocked) if isinstance(blocked, list) else ""
    owner = (ti.get("owner") or "").strip()
    # the durable face: the subject's leading #NNN when that number is free (then the
    # name drops the prefix); a claimed number would fork the Boss's referent, so the
    # subject stays whole and the card mints the next free number
    name = subject
    if sub_num is not None and sub_num not in cardlib.claimed_ids(bdir):
        name = re.sub(r"^#\d+\s*[·:—-]*\s*", "", subject).strip() or subject
    cardlib.new_card(bdir, name, want_id=sub_num, task_id=tid,
                     dept=owner or cardlib.EMPTY, what=what or cardlib.EMPTY,
                     blocked_on=blocked or cardlib.EMPTY,
                     **{"done-when": DONE_WHEN_PLACEHOLDER})
    cardlib.regen_digest(root, cfg)


def on_update(root, cfg, ti):
    tid = str(ti.get("taskId") or "").strip()
    if not tid:
        return
    status = ti.get("status")
    if status == "completed":
        return  # posttool_backlog_log.py owns the completed transition
    bdir, _ = cardlib.ensure_store(root, cfg)
    if not bdir:
        return
    card = cardlib.find_task(cardlib.load(bdir), tid)
    if card is None:
        return
    changed = False
    if status in RETIRE:
        cardlib.retire(card, bdir, "archive", status=status)
        changed = True
    elif status in STATUS_MAP:
        target = STATUS_MAP[status]
        if not re.match(r"%s\b" % target, (card.get("status") or "").strip()):
            cardlib.set_fields(card, status=target)
            changed = True
    owner = (ti.get("owner") or "").strip()
    if owner and not cardlib.clean(card.get("dept", "")) and card.get("status") not in RETIRE:
        cardlib.set_fields(card, dept=owner)
        changed = True
    if changed:
        cardlib.regen_digest(root, cfg)


def run(data):
    if hooklib is None or cardlib is None:
        return
    tool = data.get("tool_name", "")
    if tool not in ("TaskCreate", "TaskUpdate"):
        return
    root = hooklib.find_root(data.get("cwd") or os.getcwd())
    if not root:
        return
    if board is not None:
        root = board.main_checkout(root)  # the board lives in the MAIN checkout
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
    except Exception:
        return
    if not cfg.get("active"):
        return
    ti = data.get("tool_input", {}) or {}
    try:
        if tool == "TaskCreate":
            on_create(root, cfg, ti, data.get("tool_response"))
        else:
            on_update(root, cfg, ti)
    except Exception:
        pass


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    run(data)


if __name__ == "__main__":
    main()
