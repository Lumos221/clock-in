#!/usr/bin/env python3
"""Stop / SubagentStop hook — when a pane's turn ends, scan its last assistant message
for canonical-answer markers and apply them: `@CANON[<dept>] <topic> → <path> (affects: …)`
registers/re-points the current canonical file; `@CANON-ACK[<dept>] <topic>` clears a
re-check flag. The dept writes one marker line; this hook does the registry mechanics
(single-sourced in canon.py), so the CEO relay is out of the critical path. Fail-open:
any error -> no-op. Acts only inside an active .claude/orchestrate.json project."""
import sys, os, json

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "skills", "orchestrate", "scripts")
sys.path.insert(0, SCRIPTS)
try:
    import canon
except Exception:
    canon = None


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
    if canon is None:
        return
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
    markers = canon.parse_canon_markers(text)
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


if __name__ == "__main__":
    main()
