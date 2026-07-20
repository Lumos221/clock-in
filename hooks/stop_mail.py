#!/usr/bin/env python3
"""Stop piece (via stop_dispatch) — the 分公司 mail-lane nudge (0.9.29). The two
offices (CEO session · branch sessions) share no live channel: mail is markdown
notes in <board>/mail/ (frontmatter: from · to · re (#NNN) · status: unread|read ·
needs_boss — free prose body), and each office notices its mail MECHANICALLY at
turn end, because doctrine-only checking is exactly the pattern that failed three
times in the capacity-sentinel field history.

Identity: .claude/office.json at the LOCAL root (`{"office": "Marketing"}` —
worktree-local, written by the branch skill's setup) names this session's office;
absent → this is the CEO/main office. Mail is "mine" when `to:` base-matches the
identity (CEO aliases: ceo · boss · 总部 · hq). One nudge per unread-set signature
(acting or new mail re-arms; ignoring stays silent — the capacity pattern).
Fail-open everywhere; inert without an active orchestrate project or a mail dir."""
import os, sys, json, hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import hooklib, cardlib
except Exception:
    hooklib = cardlib = None
try:
    import board  # main_checkout only
except Exception:
    board = None

CEO_ALIASES = {"ceo", "boss", "总部", "hq", "main"}


def identity(local_root):
    """This checkout's office handle, or 'CEO' when unmarked."""
    try:
        d = json.load(open(os.path.join(local_root, ".claude", "office.json"),
                           encoding="utf-8"))
        return str(d.get("office") or "").strip() or "CEO"
    except Exception:
        return "CEO"


def unread_for(mail_dir, office):
    """[(filename, from, subject-ish)] of unread notes addressed to this office."""
    me = office.strip().lower()
    mine = []
    try:
        names = sorted(os.listdir(mail_dir))
    except OSError:
        return mine
    for fn in names:
        if not fn.endswith(".md"):
            continue
        try:
            fm = cardlib.frontmatter(open(os.path.join(mail_dir, fn),
                                          encoding="utf-8").read())
        except OSError:
            continue
        if (fm.get("status") or "").strip().lower() != "unread":
            continue
        to = (fm.get("to") or "").strip().lower()
        if not to:
            continue
        hit = to == me or (me == "ceo" and to in CEO_ALIASES)
        if hit:
            mine.append((fn, fm.get("from") or "?", fm.get("re") or ""))
    return mine


def run(data, text):
    if hooklib is None or cardlib is None:
        return None
    if data.get("hook_event_name") not in ("Stop", None):
        return None
    if data.get("stop_hook_active"):
        return None
    local_root = hooklib.find_root(data.get("cwd") or "")
    if not local_root:
        return None
    root = local_root
    if board is not None:
        try:
            root = board.main_checkout(local_root)  # mail lives in the MAIN checkout
        except Exception:
            pass
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"),
                             encoding="utf-8"))
        if not cfg.get("active"):
            return None
    except Exception:
        return None
    mail_dir = os.path.join(cardlib.board_dir(root, cfg), "mail")
    if not os.path.isdir(mail_dir):
        return None
    office = identity(local_root)
    mine = unread_for(mail_dir, office)
    if not mine:
        return None
    sig = hashlib.md5(json.dumps(sorted(f for f, _, _ in mine)).encode("utf-8")).hexdigest()
    state = os.path.join(local_root, ".claude", "mail-nudge-state")
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
    lst = " · ".join("%s (from %s%s)" % (f, s, " re %s" % r if r else "")
                     for f, s, r in mine[:4]) + ("…" if len(mine) > 4 else "")
    return ("📮 mail: %d unread for %s — %s. Read each (%s/), act or reply (a reply "
            "is a NEW mail note: from/to/re/status: unread), then flip its "
            "`status: read`. (One nudge per unread-set — new mail re-arms.)"
            % (len(mine), office, lst, os.path.relpath(mail_dir, root)))


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
