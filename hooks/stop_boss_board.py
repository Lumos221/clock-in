#!/usr/bin/env python3
"""Stop / SubagentStop hook — when a pane's turn ends, scan its last assistant
message for Boss-Board markers and apply them: `@BOSS[<dept>]: <ask>` raises an
ask; `@BOSS-DONE[<dept>]` / `@BOSS-DONE[<id>]` resolves one. The model writes one
cheap line of intent; this hook does the board mechanics (single-sourced in
board.py). Fail-open: any error -> no-op. Acts only inside an active
.claude/orchestrate.json project. Never blocks a turn (always exit 0)."""
import sys, os, json

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "skills", "orchestrate", "scripts")
sys.path.insert(0, SCRIPTS)
try:
    import board
except Exception:
    board = None


def find_root(start):
    d = os.path.abspath(start or os.getcwd())
    if os.path.isfile(d):
        d = os.path.dirname(d)
    while True:
        if os.path.exists(os.path.join(d, ".claude", "orchestrate.json")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def last_assistant_text(transcript_path):
    """Defensive: scan JSONL from the end for the last assistant message; return
    its concatenated text. Tolerates content as a string or a list of blocks."""
    try:
        with open(transcript_path, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return ""
    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        msg = obj.get("message", obj)
        if msg.get("role") != "assistant" and obj.get("type") != "assistant":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            if parts:
                return "\n".join(parts)
    return ""


def main():
    if board is None:
        return
    if os.environ.get("BOSS_BOARD_SKIP_SERVER"):
        board._SKIP_SERVER = True
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    root = find_root(data.get("cwd") or os.getcwd())
    if not root:
        return
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
    except Exception:
        return
    if not cfg.get("active"):
        return
    text = last_assistant_text(data.get("transcript_path", ""))
    if not text:
        return
    markers = board.parse_markers(text)
    for dept, ask in markers["raises"]:
        try:
            board.board_add(root, dept, "needs", ask)
        except Exception:
            pass
    for token in markers["dones"]:
        try:
            if "-" in token and board.board_get(root, token):
                board.board_done(root, token)
            else:
                board.board_resolve_dept(root, token)
        except Exception:
            pass


if __name__ == "__main__":
    main()
