#!/usr/bin/env python3
"""Stop / SubagentStop dispatcher — one process for what used to be three.

hooks.json used to register stop_boss_board.py, stop_canon.py and stop_refute_tally.py
as separate commands, so every turn end in every session paid three interpreter
start-ups and read the transcript JSONL twice. This runs all three in-process: stdin
parsed once, the last assistant message extracted once, each hook's run() isolated by
its own try (a crash in one must not starve the others). Order: board/canon markers are
applied before the tally re-counts. Fail-open: any error → skip that piece, exit 0.

**What a piece says is an order, not a lesson** — fact, then the imperative, then a
prohibition only where the wrong fix is tempting. Rationale goes in the docstring; the
message is read once, in a live turn, by someone who has to act. `test_messages.py`
holds the length budget."""
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
    blocks = []
    for name in ("stop_iterm_capture", "stop_done_sweep", "stop_boss_board", "stop_canon",
                 "stop_refute_tally", "stop_idle_nudge", "stop_task_reconcile",
                 "stop_capacity", "stop_seat_context", "stop_stale_stage",
                 "stop_mail", "stop_dead_letters", "stop_branch_drift",
                 "stop_board_pointer", "stop_board_digest"):
        mod = _load(name)
        if mod is None:
            continue
        try:
            ret = mod.run(data, text)
        except Exception:
            continue
        # A module may return a block reason (str) — exit 2 feeds it back to the agent
        # (Stop: blocks the stop; TeammateIdle: keeps the teammate working). EVERY one is
        # delivered: this used to keep only the first, and each of these modules stamps
        # its one-nudge-per-state file BEFORE returning, so a message the dispatcher
        # dropped was a nudge spent and never re-armed. Unread mail sat unannounced
        # behind a capacity line that happened to run three places earlier (2026-08-04).
        if isinstance(ret, str) and ret and ret not in blocks:
            blocks.append(ret)
    if blocks:
        sys.stderr.write("\n\n".join(blocks))
        sys.exit(2)


if __name__ == "__main__":
    main()
