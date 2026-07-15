#!/usr/bin/env python3
"""Boss-in-pane marker — `orchestrate-pane start|end|status|clear`.

One tiny state file, `.claude/boss-in-pane.json` (root .claude/, gitignored runtime
state like the boss-board store): {"<dept-handle>": "<ISO start time>"}. Written by
the CEO when it sends the Boss to a dept's pane, cleared when the Boss returns.

Three readers, all fail-open:
- the idle-nudge hook (stop_idle_nudge.py) — a marked dept is never nudged to report
  mid-conversation with the Boss;
- the CEO's own mute doctrine (SKILL §3) — pings from a marked dept are pure liveness;
- the (future) lingering-pane sentinel — a marked dept with no open task is not a corpse.

Resolves the project root like every hook: walk up from cwd to the orchestrate.json
marker, pierce a linked worktree to the main checkout (the marker must be shared, or a
dept-in-worktree pane would read a private, always-empty file)."""
import os, sys, json
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    import board  # main_checkout (worktree piercing)
except Exception:
    board = None


def find_root(start):
    d = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.exists(os.path.join(d, ".claude", "orchestrate.json")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def state_path(root):
    return os.path.join(root, ".claude", "boss-in-pane.json")


def load_state(root):
    try:
        s = json.load(open(state_path(root), encoding="utf-8"))
        return s if isinstance(s, dict) else {}
    except Exception:
        return {}


def save_state(root, state):
    p = state_path(root)
    if not state:
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
        return
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def main(argv):
    if len(argv) < 1 or argv[0] not in ("start", "end", "status", "clear"):
        sys.stderr.write("usage: orchestrate-pane start <dept> | end <dept> | status | clear\n")
        return 1
    root = find_root(os.getcwd())
    if not root:
        sys.stderr.write("orchestrate-pane: no .claude/orchestrate.json above cwd\n")
        return 1
    if board is not None:
        try:
            root = board.main_checkout(root)
        except Exception:
            pass
    cmd = argv[0]
    state = load_state(root)
    if cmd == "status":
        if not state:
            print("boss-in-pane: none")
        for dept, since in sorted(state.items()):
            print("boss-in-pane: %s (since %s)" % (dept, since))
        return 0
    if cmd == "clear":
        save_state(root, {})
        print("boss-in-pane: cleared")
        return 0
    if len(argv) < 2:
        sys.stderr.write("usage: orchestrate-pane %s <dept>\n" % cmd)
        return 1
    dept = argv[1]
    if cmd == "start":
        state[dept] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        save_state(root, state)
        print("boss-in-pane: %s muted (pings = liveness; idle-nudge suppressed)" % dept)
    else:  # end
        state.pop(dept, None)
        save_state(root, state)
        print("boss-in-pane: %s released — expect its report (the idle-nudge re-arms)" % dept)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
