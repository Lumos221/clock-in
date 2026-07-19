#!/usr/bin/env python3
"""PostToolUse hook — TaskBoard.md follows the platform task list (the widget), not
the other way round. `TaskCreate` births the card with `task_id` pre-filled (no hand
registration to forget — the field-report staleness: cards without ids, ids without
cards); a hand-written card is FILLED, not duplicated — matched by exact name, by the
human card number its subject leads with (#NNN — the durable bridge onto
session-scoped platform ids), or by normalised name (0.9.20; the exact-only match
left `task_id: —` on real cards while appending hook-dup minimal ones, so completions
retired the wrong card — refcheck field report); `TaskUpdate` mirrors the coarse
lifecycle back onto the card (pending→todo ·
in_progress→doing · owner fills an empty dept) and retires the card on a
cancelled/deleted task (forward-proofing — the CLI's status enum is currently just
pending/in_progress/completed, verified in 2.1.206). Fine states (review/blocked) stay dept-written prose — the
widget doesn't know them, and this hook never overwrites what it only half
understands: all surgery keys on a `**task_id:**` field that cleans to EXACTLY one id
(shared multi-id cards are left alone, see hooklib). `completed` is NOT handled here —
posttool_backlog_log.py owns that transition (backlog row + shipped tail + card
retirement), so the two hooks can never write the board on the same event.

A recycled id (platform ids restart each session; a stale Active card may still hold
last session's `3`) detaches the old card — its task_id becomes `—`, a trace lands in
.claude/marker-misses.log — and the new card is appended. Fail-open: any error →
no-op. Acts only inside an active .claude/orchestrate.json project."""
import sys, os, re, json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
try:
    import hooklib
except Exception:
    hooklib = None
try:
    import board  # only for main_checkout (worktree piercing)
except Exception:
    board = None

STATUS_MAP = {"pending": "todo", "in_progress": "doing"}
RETIRE = {"deleted", "cancelled"}


def _norm(s):
    """Normalise a card name / CREATE subject for matching: strip a leading card
    number (#NNN), treat the heading separator as whitespace, collapse runs,
    casefold. '#130 · REDEEM — X' and '#130 REDEEM — X' become the same string."""
    s = re.sub(r"^#\d+\s*", "", (s or "").strip())
    return re.sub(r"\s+", " ", s.replace("·", " ")).strip().casefold()


def _card_number(head):
    """The human card number from a heading ('#130 · SUBJECT' → '130'), else None."""
    m = re.match(r"#(\d+)\b", head)
    return m.group(1) if m else None


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


def _tb_path(root, cfg):
    return os.path.join(root, cfg.get("taskboard", "docs/TaskBoard.md"))


def _read(path):
    try:
        return open(path, encoding="utf-8").read()
    except Exception:
        return ""


def _card_md(tid, subject, dept, what, blocked, label=None):
    """A fresh card. `label` (the heading slot) is the Boss-facing identity —
    coral pill, shipped-line lead, BACKLOG grep key. on_create promotes the
    subject's leading #NNN into it when no existing card claims that number
    (0.9.26; before this a hook-born `### #46 · #151 REDEEM…` wore the session id
    as its face and demoted the real number into the name); otherwise the
    platform id keeps the slot and the subject stays whole."""
    if label:
        name = re.sub(r"^#\d+\s*[·:—-]*\s*", "", subject).strip() or subject
    else:
        label, name = "#%s" % tid, subject
    return (
        "### %s · %s\n"
        "- **dept:** %s\n"
        "- **task_id:** %s\n"
        "- **status:** todo\n"
        "- **blocked_on:** %s\n"
        "- **what:** %s\n"
        "- **done-when:** <CEO fills — acceptance criterion from the dispatch spec>\n"
        "- **artifacts:** —\n" % (label, name, dept or "—", tid, blocked or "—", what)
    )


def on_create(root, cfg, ti, resp):
    tid = extract_id(resp)
    if not tid:
        return
    subject = (ti.get("subject") or ti.get("description") or "").strip().splitlines()
    subject = subject[0].strip() if subject else ""
    if not subject:
        subject = "task %s" % tid
    tb = _tb_path(root, cfg)
    text = _read(tb)

    span = hooklib.tb_card_span(text, tid)
    if span:
        head = text[span[0]:span[1]].splitlines()[0]
        # duplicate/replayed event — match normalised (the heading may carry the
        # subject's leading #NNN in the label slot, so byte-contains is too strict)
        if subject and (subject in head or (_norm(subject)
                        and _norm(subject) == _norm(re.sub(r"^#{1,6}\s*", "", head)))):
            return
        # stale card holding a recycled id: detach it so the gate keys stay honest
        text = hooklib.tb_set_field_at(text, span, "task_id", "—")
        hooklib.log_marker_misses(root, "task-sync", [
            "task_id %s recycled by TaskCreate '%s' — stale card detached" % (tid, subject)])

    # the CEO hand-wrote this card first, then registered it → fill, don't duplicate.
    # Match tiers: ① exact name/head equality (historic behaviour) ② the human card
    # number — a subject leading with #NNN fills the sole unregistered card headed
    # #NNN (the field norm: durable card numbers bridge to session-scoped platform
    # ids) ③ normalised equality (separator/space/case drift). ②③ require exactly
    # one candidate — ambiguity falls through to an append, never a guess.
    unregistered = []
    claimed_nums = set()
    for a, b in hooklib.tb_card_spans(text):
        block = text[a:b]
        head = block.splitlines()[0][4:].strip()
        n = _card_number(head)
        if n:
            claimed_nums.add(n)
        name = head.split("·", 1)[-1].strip() if "·" in head else head
        m = re.search(r"\*\*task_id:\*\*\s*([^\n]*)", block)
        registered = hooklib.tb_clean(m.group(1)) if m else ""
        if registered:
            continue
        if subject and (name == subject or head == subject):
            hooklib.tb_write(tb, hooklib.tb_set_field_at(text, (a, b), "task_id", tid))
            return
        unregistered.append(((a, b), head, name))
    sub_num = _card_number(subject)
    if sub_num:
        hits = [span for span, head, _ in unregistered if _card_number(head) == sub_num]
        if len(hits) == 1:
            hooklib.tb_write(tb, hooklib.tb_set_field_at(text, hits[0], "task_id", tid))
            return
    sub_norm = _norm(subject)
    if sub_norm:
        hits = [span for span, head, name in unregistered
                if sub_norm in (_norm(head), _norm(name))]
        if len(hits) == 1:
            hooklib.tb_write(tb, hooklib.tb_set_field_at(text, hits[0], "task_id", tid))
            return

    desc = (ti.get("description") or ti.get("activeForm") or subject).strip()
    what = desc.splitlines()[0].strip()
    if len(what) > 160:
        what = what[:159] + "…"
    blocked = ti.get("blockedBy") or ti.get("blocked_by") or []
    blocked = ", ".join("#%s" % b for b in blocked) if isinstance(blocked, list) else ""
    owner = (ti.get("owner") or "").strip()
    # promote the subject's #NNN into the heading slot only when NO existing card
    # claims that number — a second card wearing an already-claimed face would make
    # the durable id ambiguous (then the platform id keeps the slot, old shape)
    label = "#%s" % sub_num if (sub_num and sub_num not in claimed_nums) else None
    out = hooklib.tb_append_card(text, _card_md(tid, subject, owner, what, blocked,
                                                label=label))
    os.makedirs(os.path.dirname(tb) or ".", exist_ok=True)
    hooklib.tb_write(tb, out)


def on_update(root, cfg, ti):
    tid = str(ti.get("taskId") or "").strip()
    if not tid:
        return
    status = ti.get("status")
    if status == "completed":
        return  # posttool_backlog_log.py owns the completed transition
    tb = _tb_path(root, cfg)
    text = _read(tb)
    if not text:
        return
    changed = False
    if status in RETIRE:
        out = hooklib.tb_remove_card(text, tid)
        if out is not None:
            text, changed = out, True
    elif status in STATUS_MAP:
        span = hooklib.tb_card_span(text, tid)
        if span:
            target = STATUS_MAP[status]
            m = re.search(r"\*\*status:\*\*\s*([^\n]*)", text[span[0]:span[1]])
            current = (m.group(1).strip() if m else "")
            if not re.match(r"%s\b" % target, current):
                text = hooklib.tb_set_field_at(text, span, "status", target)
                changed = True
    owner = (ti.get("owner") or "").strip()
    if owner:
        span = hooklib.tb_card_span(text, tid)
        if span:
            m = re.search(r"\*\*dept:\*\*\s*([^\n]*)", text[span[0]:span[1]])
            if m is None or not hooklib.tb_clean(m.group(1)):
                text = hooklib.tb_set_field_at(text, span, "dept", owner)
                changed = True
    if changed:
        hooklib.tb_write(tb, text)


def run(data):
    if hooklib is None:
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
