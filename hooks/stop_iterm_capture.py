#!/usr/bin/env python3
"""Stop piece (via stop_dispatch) — record the LEAD (Boss/CEO) session's iTerm2 pane id so
the Boss Board's Send types replies into THE BOSS'S pane.

Runs at turn end, NOT at session start: a freshly-spawned teammate's transcript isn't
stamped yet, so the start-time lead check mis-read a teammate as lead and let it overwrite
the Boss's target with its own pane. By turn end the
transcript IS stamped, so lead-vs-teammate is reliable, and the target locks onto the CEO
pane, refreshed every turn (so a restart never leaves it stale). Runs live from the working
tree (Stop is already registered — no restart). Lead only; fail-open; returns None (pure
side effect, never blocks the stop)."""
import os, sys, json

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


def run(data, text=None):
    if hooklib is None or board is None:
        return None
    if data.get("hook_event_name") not in ("Stop", None):
        return None
    sid = os.environ.get("ITERM_SESSION_ID")
    if not sid:
        return None                       # not iTerm2 — nothing to pin
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
    name = None
    try:
        import stop_idle_nudge
        name, setting, team = stop_idle_nudge.identity(data.get("transcript_path") or "")
        if not (team and name):
            name = None
    except Exception:
        pass

    # EVERY session registers itself, teammate or not. The registry is an index of what is
    # running, keyed by session_id and labelled with the last thing the Boss typed — it is what
    # lets the board name their sessions instead of guessing which pane is the right one.
    meta = {
        "cwd": data.get("cwd") or "",
        "session_id": data.get("session_id") or "",
        "transcript_path": data.get("transcript_path") or "",
        "iterm": sid,
        "agent": name or "",
    }
    board.register_session(root, meta)

    # The DEFAULT delivery target stays lead-only: a teammate pane must never take it.
    if name and name != "team-lead":
        return None
    board.capture_iterm_target(root, sid, meta)
    return None
