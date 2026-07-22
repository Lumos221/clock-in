#!/usr/bin/env python3
"""UserPromptSubmit hook — the Boss Board reply INBOX (the reverse channel's reliable
leg). When the Boss answers on the panel and hits Send, the board resolves the items
and stages a composed message in the store's outbox; the PRIMARY delivery is iTerm2
(board.iterm_send) writing that message straight into this pane. This hook is the
FALLBACK + truth: on any user prompt it injects still-undelivered outbox messages as
context and marks them delivered, so a denied Automation permission or a stale pane
never drops a reply.

Injection = plain stdout (a UserPromptSubmit hook's stdout is added to the prompt
context). Each message injects EXACTLY once: take_pending_outbox marks delivered in
the same locked pass, and the iTerm2 happy-path already marked its own record. Lead/CEO
session only (a teammate pane must not consume the Boss's outbox); fail-open; inert
without an active orchestrate project."""
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


def run(data):
    if hooklib is None or board is None:
        return None
    if data.get("hook_event_name") not in ("UserPromptSubmit", None):
        return None
    local_root = hooklib.find_root(data.get("cwd") or "")
    if not local_root:
        return None
    root = board.main_checkout(local_root)   # outbox lives in the MAIN checkout's store
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"),
                             encoding="utf-8"))
        if not cfg.get("active"):
            return None
    except Exception:
        return None
    # Teammate panes never own the Boss's outbox — only the lead/CEO session drains it.
    try:
        import stop_idle_nudge
        name, setting, team = stop_idle_nudge.identity(data.get("transcript_path") or "")
        if team and name and name != "team-lead":
            return None
    except Exception:
        pass
    pend = board._locked_mutate(root, board.take_pending_outbox)
    lines = [p["msg"] for p in (pend or []) if p.get("msg")]
    return "\n".join(lines) if lines else None


def main():
    if hooklib is None:
        return
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    try:
        out = run(data)
    except Exception:
        return
    if out:
        sys.stdout.write(out + "\n")


if __name__ == "__main__":
    main()
