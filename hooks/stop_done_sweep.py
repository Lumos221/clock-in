#!/usr/bin/env python3
"""Stop piece (via stop_dispatch) — the TOOL-INDEPENDENT completion recorder.

`posttool_backlog_log` records a finished task only when it sees a platform
`TaskUpdate → completed`. The task widget is not always available (server-side gating
binds at session start; a resumed pane can lose it), so whole runs of completions were
never recorded: field state 2026-07-25 on a live project — 24 properly-retired cards, all 24
with a BACKLOG row, versus 91 cards left sitting at `status: done` on the Active board,
only 2 of which had a row. 89 finished tasks fell out of the written history.

This closes that hole by keying on the CARD instead of the tool: a card whose own
`status` says done IS a completion (the CEO writes that field by hand precisely when the
widget is absent), so at every turn end each one is recorded and retired through the same
shared writers the widget path uses — `log.py` for the BACKLOG row (one format, one
source), the digest's Recently-shipped block, then `cardlib.retire` into `board/done/`.
Both paths therefore converge on identical records; whichever fires first wins and the
other finds nothing to do.

Idempotent (a `#NNN` already carrying a BACKLOG row is skipped, so nothing double-logs),
capped per turn (a long-neglected board drains over several turns instead of stalling
one), lead-session only, fail-open, and side-effect only — it never returns a block
string, so recording history never interrupts the Boss's turn.

The date is the card file's own mtime, not today, so a backlog of old completions lands
under the days they actually finished. Retirement is a MOVE into `board/done/`, never a
delete. `note` records whether an L2 `.pass` was on file: this recorder states what is
true rather than silently upgrading an unreviewed card (the review gate still guards the
widget path; a card the CEO marked done by hand is already their call)."""
import os, re, sys, json, subprocess
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
try:
    import hooklib, cardlib
except Exception:
    hooklib = cardlib = None
try:
    import board
except Exception:
    board = None
try:
    import log as tasklog
except Exception:
    tasklog = None
try:
    import posttool_backlog_log as blog     # update_shipped + the SHIPPED markers
except Exception:
    blog = None

SWEEP_CAP = 25          # cards per turn — a neglected board drains over a few turns


def _has_row(backlog_text, nnn):
    """True if BACKLOG already carries a machine row for this durable #NNN."""
    return bool(re.search(r"#%s\b" % re.escape(str(nnn)), backlog_text))


def _pass_on_file(root, card):
    """The L2 review marker for this card, if any (task_id first, then #NNN)."""
    tid = cardlib.clean(card.get("task_id", "")) if cardlib else ""
    for key in ([tid] if tid.isdigit() else []) + [str(card.get("id"))]:
        p = os.path.join(root, "docs", "reviews", "%s.pass" % key)
        if os.path.exists(p):
            return os.path.basename(p)
    return ""


def sweep(root, cfg, cap=SWEEP_CAP):
    """Record + retire every `status: done` card that has no BACKLOG row yet.
    Returns a list of trace lines (empty when the board is already clean)."""
    if not (cardlib and tasklog):
        return []
    bdir = cardlib.board_dir(root, cfg)
    if not os.path.isdir(bdir):
        return []
    backlog = os.path.join(root, cfg.get("backlog", "docs/BACKLOG.md"))
    try:
        bltext = open(backlog, encoding="utf-8").read()
    except Exception:
        bltext = ""
    sha = ""
    try:
        sha = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        pass
    tb = os.path.join(root, cfg.get("taskboard", "docs/TaskBoard.md"))
    traces, n = [], 0
    for card in cardlib.load(bdir):
        if n >= cap:
            break
        if "done" not in cardlib.clean(card.get("status", "")).lower():
            continue
        nnn, name = card.get("id"), (card.get("name") or "")
        if nnn is None:
            continue
        if _has_row(bltext, nnn):
            continue                       # the widget path already recorded it
        tid = cardlib.clean(card.get("task_id", ""))
        dept = cardlib.clean(card.get("dept", ""))
        # the day it actually finished — the card file's last write
        try:
            day = datetime.fromtimestamp(os.path.getmtime(card["_path"])).strftime("%Y-%m-%d")
        except OSError:
            day = datetime.now().strftime("%Y-%m-%d")
        pf = _pass_on_file(root, card)
        d = {"task_id": tid or "—", "dept": dept or "—",
             "task": ("#%s %s" % (nnn, name)).strip(),
             "status": "done", "sha": sha,
             "note": "swept from card status" + ("" if pf else " · no L2 pass on file")}
        try:
            fresh = not os.path.exists(backlog) or os.path.getsize(backlog) == 0
            os.makedirs(os.path.dirname(backlog) or ".", exist_ok=True)
            with open(backlog, "a", encoding="utf-8") as f:
                if fresh:
                    f.write(tasklog.HEADER)
                f.write(tasklog.row(d, day))
            bltext += "#%s " % nnn         # in-run dedupe
        except Exception:
            continue                       # unrecorded → leave the card alone, retry next turn
        if blog is not None:
            try:
                # 6-field `date · #<card> · #<session id> · …` only when a session id
                # exists; without one the line takes the 5-field shape the widget path
                # already writes (posttool_backlog_log). The sweep IS the widget-less
                # path, so its rows almost never have a session id — emitting the field
                # anyway printed a literal `#—` on the Boss's ship tail.
                blog.update_shipped(tb, ("- %s · #%s · #%s · %s · %s · %s"
                                         % (day, nnn, tid, dept or "—", name or "—", sha or "—"))
                                    if tid else
                                    ("- %s · #%s · %s · %s · %s"
                                     % (day, nnn, dept or "—", name or "—", sha or "—")))
            except Exception:
                pass
        try:
            cardlib.retire(card, bdir, "done", status="done", shipped=day, sha=sha or "")
            n += 1
            traces.append("#%s recorded + retired (%s%s)" % (nnn, day, "" if pf else ", no L2 pass"))
        except Exception:
            pass
    if n:
        try:
            cardlib.regen_digest(root, cfg)
        except Exception:
            pass
    return traces


def run(data, text=None):
    if hooklib is None or cardlib is None or board is None:
        return None
    if data.get("hook_event_name") not in ("Stop", None):
        return None
    if data.get("stop_hook_active"):
        return None
    local_root = hooklib.find_root(data.get("cwd") or "")
    if not local_root:
        return None
    root = board.main_checkout(local_root)
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
        if not cfg.get("active"):
            return None
    except Exception:
        return None
    # Opt-in per project (`"done_sweep": true`). This recorder RETIRES cards and appends
    # to the durable log, and on a long-neglected board that is a large first sweep — a
    # project adopts it deliberately, after seeing what its own first pass would write,
    # never as a surprise on the turn the plugin updates.
    if not cfg.get("done_sweep"):
        return None
    # Lead only: a teammate pane must not retire the CEO's cards.
    try:
        import stop_idle_nudge
        name, setting, team = stop_idle_nudge.identity(data.get("transcript_path") or "")
        if team and name and name != "team-lead":
            return None
    except Exception:
        pass
    traces = sweep(root, cfg)
    if traces:
        try:
            hooklib.log_marker_misses(root, "done-sweep", traces)
        except Exception:
            pass
    return None                            # side effect only — never blocks the turn
