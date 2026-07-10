#!/usr/bin/env python3
"""SessionStart hook — when CEO orchestration is active in this project, arm CEO mode:
inject the standing reminder, any signed 红线, and the SoT (source of truth — the
compass). Does nothing in a project without an active .claude/orchestrate.json marker.
Resolves the marker like every other hook — walk up from cwd, pierce a linked worktree
to the main checkout — so a session started in a subdirectory still arms (reads cwd
from stdin JSON; fail-open — any error → stay silent).

Loads SoT.md, NOT BACKLOG.md: SoT is the small "where we stand" compass designed to
load each session; BACKLOG is the append-only finished-task log, never auto-loaded."""
import sys, json, os

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


def main():
    if hooklib is None:
        return
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    root = hooklib.find_root(data.get("cwd") or os.getcwd())
    if not root:
        return  # no marker = as if not installed
    if board is not None:
        root = board.main_checkout(root)
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
    except Exception:
        return
    if not cfg.get("active"):
        return

    parts = ["📋 CEO orchestration mode is active for this project. You are the CEO — follow the orchestrate skill."]
    redlines = cfg.get("redlines", [])
    if redlines:
        parts.append("Signed 红线 (need the Boss's two-key 准/驳 before editing):")
        for r in redlines:
            rp = r.get("path") if isinstance(r, dict) else r
            note = (" — %s" % r.get("note")) if isinstance(r, dict) and r.get("note") else ""
            parts.append("  - %s%s" % (rp, note))
    sot_rel = cfg.get("sot", "docs/SoT.md")
    sot = os.path.join(root, sot_rel)
    if os.path.exists(sot):
        try:
            text = open(sot, encoding="utf-8").read()
            parts.append("\n— current source of truth (%s) —\n%s" % (sot_rel, text[:4000]))
        except Exception:
            pass
    sys.stdout.write("\n".join(parts) + "\n")


if __name__ == "__main__":
    main()
