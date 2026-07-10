#!/usr/bin/env python3
"""Shared helpers for this plugin's hooks — the logic every hook was duplicating
(project-root walk, transcript reading, marker-miss logging) lives once, here.
Importable from a hook (same dir) or a test (sys.path.insert). No side effects."""
import os, json
from datetime import datetime


def find_root(start):
    """Nearest ancestor holding .claude/orchestrate.json, else None."""
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
    """Text of the LAST assistant message in the transcript JSONL — and only that one.
    Walking further back would replay markers from an earlier, already-processed turn
    (e.g. re-raising a @BOSS ask the Boss already resolved), so a final message with
    no text blocks returns "" instead of falling through to an older message."""
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
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "assistant" and obj.get("type") != "assistant":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(b.get("text", "") for b in content
                             if isinstance(b, dict) and b.get("type") == "text")
        return ""
    return ""


def log_marker_misses(root, channel, misses):
    """Append marker-shaped lines that didn't parse to .claude/marker-misses.log.
    The marker channel is fail-open end to end, so without this a malformed
    @BOSS/@CANON line vanishes with no trace anywhere. Never raises."""
    if not misses:
        return
    try:
        path = os.path.join(root, ".claude", "marker-misses.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        with open(path, "a", encoding="utf-8") as f:
            for m in misses:
                f.write("%s [%s] %s\n" % (stamp, channel, m.strip()))
    except Exception:
        pass
