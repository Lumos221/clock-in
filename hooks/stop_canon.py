#!/usr/bin/env python3
"""Stop / SubagentStop hook — when a pane's turn ends, scan its last assistant message
for canonical-answer markers and apply them: `@CANON[<dept>] <topic> → <path> (affects: …)`
registers/re-points the current canonical file; `@CANON-ACK[<dept>] <topic>` clears a
re-check flag. The dept writes one marker line; this hook does the registry mechanics
(single-sourced in canon.py), so the CEO relay is out of the critical path. Marker-shaped
lines that don't parse land in .claude/marker-misses.log. Normally invoked via
stop_dispatch.py; runs standalone too. Fail-open: any error -> no-op. Acts only inside
an active .claude/orchestrate.json project."""
import sys, os, json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
try:
    import canon
    import hooklib
except Exception:
    canon = hooklib = None


def run(data, text=None):
    if canon is None or hooklib is None:
        return
    root = hooklib.find_root(data.get("cwd") or os.getcwd())
    if not root:
        return
    # Same worktree piercing as the board hook: a registration from a pane inside a
    # linked worktree must land in the MAIN checkout's docs/CANON.md, not a private
    # copy that vanishes when the worktree is reaped.
    root = canon.main_checkout(root)
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
    except Exception:
        return
    if not cfg.get("active"):
        return
    if text is None:
        text = hooklib.last_assistant_text(data.get("transcript_path", ""))
    if not text:
        return
    markers = canon.parse_canon_markers(text)
    hooklib.log_marker_misses(root, "canon", markers.get("misses"))
    for dept, topic, file, affects in markers["registers"]:
        try:
            canon.cmd_set(root, dept, topic, file, affects)
        except Exception:
            pass
    for dept, topic in markers["acks"]:
        try:
            canon.cmd_ack(root, topic, dept)
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
