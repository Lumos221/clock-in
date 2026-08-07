#!/usr/bin/env python3
"""Stop piece — the board announces itself, so the terminal can stop carrying content.

WHY. The board was under-used, and the channel was not the reason: nothing told them an
item had landed. The panel opened only when a post happened to start the server, so they
stayed in the terminal, and because that is where they was, agents kept writing there. A
stream is the wrong place for anything that must be re-read: new output destroys scroll
position, so a decision that scrolled past is a decision missed.

So the terminal stops carrying the content and carries a POINTER instead: how many items
wait and how old the oldest is. That is the one thing a stream is good at. A desktop
banner covers the case where they are not watching the terminal at all.

ONE DELTA, TWO SURFACES. Both are computed here from the same reading, and the state
lives in the MAIN checkout so several sessions posting to one board cannot each announce
the same arrival. The banner fires only on ARRIVAL (a banner saying "still 2 waiting" is
nagging), while the line also speaks when the oldest item crosses an age bucket — that is
what stops a quiet board from silently ageing into a forgotten one.
"""
import os, sys, json, subprocess
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
try:
    import hooklib
except Exception:
    hooklib = None
try:
    import board
except Exception:
    board = None

STATE = ".claude/board-pointer-state"
AGE_BUCKET_HOURS = 6         # re-speak when the oldest waiting item ages past a bucket
NOTIFY_TIMEOUT = 3


def _hours(stamp):
    try:
        t = datetime.strptime(str(stamp).strip()[:16].replace("T", " "), "%Y-%m-%d %H:%M")
    except Exception:
        return None
    h = (datetime.now() - t).total_seconds() / 3600.0
    return h if h > 0 else 0.0


def waiting(root):
    """(needs, info) — open entries split by whether they actually want something of them.

    Notices are machine chatter about the queue rather than asks in it, and the Inspector's
    channel carries verdicts, not requests; both file as information on the desk already,
    so counting them as things that need their would inflate every count the Boss reads."""
    try:
        rows = [e for e in board.board_list(root) if e.get("status") == "open"]
    except Exception:
        return [], []
    needs, info = [], []
    for e in rows:
        is_info = (e.get("kind") == "info" or e.get("notice")
                   or str(e.get("dept") or "").lower().startswith("inspector"))
        (info if is_info else needs).append(e)
    return needs, info


def _oldest_hours(entries):
    ages = [h for h in (_hours(e.get("created")) for e in entries) if h is not None]
    return max(ages) if ages else None


def line(needs, info, oldest):
    n = len(needs)
    head = "📋 %d on your board" % n if n else "📋 board"
    if oldest is not None:
        head += ", oldest %s" % ("%.0fh" % oldest if oldest >= 1 else "just now")
    if info:
        head += " · %d info" % len(info)
    kinds = {}
    for e in needs:
        k = e.get("kind") or "ask"
        kinds[k] = kinds.get(k, 0) + 1
    if kinds:
        head += "  (" + " · ".join("%s %d" % (k, c) for k, c in sorted(kinds.items())) + ")"
    return head


def notify(title, body):
    """Retired. The board announces its own arrivals (0.9.84): on arrival rather than at
    turn end, under the board's icon, with the department as the title, the Boss's own ringtone,
    and a click that opens the panel. This hook's banner was a second announcement of the
    same event in a different format under Script Editor's icon — two banners for one item.

    The TERMINAL pointer this hook also writes is not retired: a stream is good at "N wait,
    oldest is 3h", which is the one thing the per-item banner cannot say."""
    return False


def run(data, text=None):
    if hooklib is None or board is None:
        return None
    # CEO-only output: a teammate finishing a turn is a Stop in ITS OWN session, so
    # the event excludes nobody — only the session identity does.
    if not hooklib.is_lead(data.get("transcript_path") or ""):
        return None
    root = hooklib.find_root(data.get("cwd") or "")
    if not root:
        return None
    try:
        root = board.main_checkout(root)
    except Exception:
        pass
    try:
        with open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8") as f:
            if not json.load(f).get("active"):
                return None
    except Exception:
        return None
    needs, info = waiting(root)
    if not needs:
        _remember(root, "")
        return None
    ids = sorted(str(e.get("id")) for e in needs)
    oldest = _oldest_hours(needs)
    bucket = int(oldest // AGE_BUCKET_HOURS) if oldest is not None else 0
    # The signature carries the id SET and the age bucket: a new arrival changes the set,
    # and a board nobody clears still re-speaks as its oldest item ages.
    sig = "%s|%d" % (",".join(ids), bucket)
    prev = _remember(root, sig)
    if prev == sig:
        return None
    fresh = [e for e in needs if str(e.get("id")) not in set((prev or "").split("|")[0].split(","))]
    if fresh:
        first = (fresh[0].get("text") or "").split(" :: ")[0]
        notify("%d on your board" % len(needs),
               first[:120] + ("" if len(fresh) == 1 else "  (+%d more)" % (len(fresh) - 1)))
    sys.stderr.write("\n" + line(needs, info, oldest) + "\n")
    return None                                  # advisory only, never blocks the turn


def _remember(root, sig):
    """The PREVIOUS signature, after storing the new one. Kept in the main checkout so
    two sessions on one board do not each announce the same arrival."""
    p = os.path.join(root, STATE)
    try:
        with open(p, encoding="utf-8") as f:
            prev = f.read().strip()
    except OSError:
        prev = ""
    if prev != sig:
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(sig)
        except OSError:
            pass
    return prev
