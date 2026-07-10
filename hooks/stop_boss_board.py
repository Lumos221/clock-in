#!/usr/bin/env python3
"""Stop / SubagentStop hook — when a pane's turn ends, scan its last assistant
message for Boss-Board markers and apply them: `@BOSS[<dept>]: <ask>` raises an
ask; `@BOSS-DONE[<dept>]` / `@BOSS-DONE[<id>]` resolves one. The model writes one
cheap line of intent; this hook does the board mechanics (single-sourced in
board.py). Lines that look like a marker but don't parse land in
.claude/marker-misses.log (the channel is otherwise fail-open end to end).
Normally invoked via stop_dispatch.py; runs standalone too. Fail-open: any
error -> no-op. Acts only inside an active .claude/orchestrate.json project.
Never blocks a turn (always exit 0)."""
import sys, os, json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
try:
    import board
    import hooklib
except Exception:
    board = hooklib = None


def run(data, text=None):
    if board is None or hooklib is None:
        return
    if os.environ.get("BOSS_BOARD_SKIP_SERVER"):
        board._SKIP_SERVER = True
    root = hooklib.find_root(data.get("cwd") or os.getcwd())
    if not root:
        return
    # A linked worktree carries its own checked-out orchestrate.json; without this its
    # asks land on a private board+server+tab the Boss never watches (board.py has why).
    root = board.main_checkout(root)
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
    markers = board.parse_markers(text)
    hooklib.log_marker_misses(root, "boss-board", markers.get("misses"))
    for dept, task, ask in markers["raises"]:
        try:
            board.board_add(root, dept, "needs", ask, task=task)
        except Exception:
            pass
    for token in markers["dones"]:
        try:
            if "-" in token and board.board_get(root, token):
                board.board_done(root, token)
            else:
                e, opens = board.board_resolve_dept(root, token)
                if not e and len(opens) > 1:
                    # An ambiguous @BOSS-DONE[<dept>] used to be swallowed silently — the
                    # dept believes it resolved while its asks stay open forever. Which ask
                    # the Boss actually answered is unknowable here, so surface the
                    # ambiguity on the board itself (board_add dedups re-raises).
                    board.board_add(root, token, "discuss",
                                    "@BOSS-DONE[%s] was ambiguous — %d asks open (%s); /board done <id> the answered one"
                                    % (token, len(opens), ", ".join(o["id"] for o in opens)))
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
