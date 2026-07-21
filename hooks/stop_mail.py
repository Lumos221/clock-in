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
import os, re, sys, json, hashlib
from datetime import datetime

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
STAMP_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})\D")
DATE_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})\D")


def backfill_time(mail_dir):
    """Mechanically fill a missing/empty `time:` on mailbox notes. The sender-
    written field (0.9.33) drifted within a day — live sessions post letters
    without it, and the CEO also names files without the HHMM stamp — so the Mail
    view's time column went patchy (Boss's 2026-07-21 screenshot). Truth order:
    filename stamp YYYYMMDD-HHMM → filename date + file-clock HH:MM → file clock
    alone. Only fenced notes are touched (dead letters stay the postmaster's
    nudge); a real value is never overwritten; idempotent. Returns filled count."""
    filled = 0
    try:
        names = sorted(os.listdir(mail_dir))
    except OSError:
        return 0
    for fn in names:
        if not fn.endswith(".md"):
            continue
        path = os.path.join(mail_dir, fn)
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            continue
        close = text.find("\n---", 3)
        if not text.startswith("---") or close < 0:
            continue
        head = text[:close]
        if re.search(r"(?m)^time:\s*\S", head):
            continue  # sender wrote a value — theirs wins
        m, d = STAMP_RE.match(fn), DATE_RE.match(fn)
        try:
            mt = datetime.fromtimestamp(os.path.getmtime(path))
        except OSError:
            mt = datetime.now()
        if m:
            val = "%s-%s-%s %s:%s" % m.groups()
        elif d:
            val = "%s-%s-%s %s" % (d.group(1), d.group(2), d.group(3), mt.strftime("%H:%M"))
        else:
            val = mt.strftime("%Y-%m-%d %H:%M")
        line = 'time: "%s"' % val
        if re.search(r"(?m)^time:", head):  # empty key → rewrite it in place
            out = re.sub(r"(?m)^time:.*$", line, head, count=1) + text[close:]
        else:
            nl = text.find("\n")
            out = text[:nl + 1] + line + "\n" + text[nl + 1:]
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(out)
            os.replace(tmp, path)
            filled += 1
        except OSError:
            pass
    return filled


def identity(local_root):
    """This checkout's office handle, or 'CEO' when unmarked."""
    try:
        d = json.load(open(os.path.join(local_root, ".claude", "office.json"),
                           encoding="utf-8"))
        return str(d.get("office") or "").strip() or "CEO"
    except Exception:
        return "CEO"


def sweep(mail_dir, office):
    """(mine, dead): unread notes addressed to this office, and DEAD LETTERS — .md
    files in the mailbox lacking `to:`/`status:` frontmatter. A dead letter is
    invisible to every addressee forever (field case, refcheck 2026-07-20: a
    commissioned dept report file-dropped as plain markdown sat with empty columns
    and no nudge), so the CEO office gets told instead of nobody."""
    me = office.strip().lower()
    mine, dead = [], []
    try:
        names = sorted(os.listdir(mail_dir))
    except OSError:
        return mine, dead
    for fn in names:
        if not fn.endswith(".md"):
            continue
        try:
            fm = cardlib.frontmatter(open(os.path.join(mail_dir, fn),
                                          encoding="utf-8").read())
        except OSError:
            continue
        to = (fm.get("to") or "").strip().lower()
        if not to or not (fm.get("status") or "").strip():
            dead.append(fn)
            continue
        if (fm.get("status") or "").strip().lower() != "unread":
            continue
        if to == me or (me == "ceo" and to in CEO_ALIASES):
            mine.append((fn, fm.get("from") or "?", fm.get("re") or ""))
    return mine, dead


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
    try:
        n = backfill_time(mail_dir)
        if n:
            hooklib.log_marker_misses(root, "mail-hygiene",
                                      ["time backfilled on %d letter(s)" % n])
    except Exception:
        pass
    office = identity(local_root)
    mine, dead = sweep(mail_dir, office)
    if office.strip().lower() != "ceo":
        dead = []  # the CEO office is the postmaster; branches see only their mail
    if not mine and not dead:
        return None
    sig = hashlib.md5(json.dumps([sorted(f for f, _, _ in mine),
                                  sorted(dead)]).encode("utf-8")).hexdigest()
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
    parts = []
    if mine:
        lst = " · ".join("%s (from %s%s)" % (f, s, " re %s" % r if r else "")
                         for f, s, r in mine[:4]) + ("…" if len(mine) > 4 else "")
        parts.append("%d unread for %s — %s. Read each (%s/), act or reply (a reply "
                     "is a NEW mail note: from/to/re/time/status: unread), then flip "
                     "its `status: read`."
                     % (len(mine), office, lst, os.path.relpath(mail_dir, root)))
    if dead:
        parts.append("%d DEAD letter(s) with no to:/status: frontmatter (%s) — "
                     "invisible to every addressee. Add the mail frontmatter, or move "
                     "the file out (the mailbox is for ADDRESSED inter-office notes; "
                     "dept reports go via SendMessage / the dept's own folder)."
                     % (len(dead), " · ".join(dead[:3]) + ("…" if len(dead) > 3 else "")))
    return "📮 mail: " + " ".join(parts) + " (One nudge per state — changes re-arm.)"


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
