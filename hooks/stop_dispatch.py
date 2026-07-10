#!/usr/bin/env python3
"""Stop / SubagentStop dispatcher — one process for what used to be three.

hooks.json used to register stop_boss_board.py, stop_canon.py and stop_refute_tally.py
as separate commands, so every turn end in every session paid three interpreter
start-ups and read the transcript JSONL twice. This runs all three in-process: stdin
parsed once, the last assistant message extracted once, each hook's run() isolated by
its own try (a crash in one must not starve the others). Order: board/canon markers are
applied before the tally re-counts. Fail-open: any error → skip that piece, exit 0."""
import sys, os, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    try:
        return __import__(name)
    except Exception:
        return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    hooklib = _load("hooklib")
    text = hooklib.last_assistant_text(data.get("transcript_path", "")) if hooklib else None
    for name in ("stop_boss_board", "stop_canon", "stop_refute_tally"):
        mod = _load(name)
        if mod is None:
            continue
        try:
            mod.run(data, text)
        except Exception:
            pass


if __name__ == "__main__":
    main()
