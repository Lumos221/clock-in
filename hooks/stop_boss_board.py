#!/usr/bin/env python3
"""Stop / SubagentStop hook — when a pane's turn ends, scan its last assistant
message for Boss-Board markers and apply them: `@BOSS[<dept>]: <ask>` raises an
ask; `@BOSS-DONE[<dept>]` / `@BOSS-DONE[<id>]` resolves one. The model writes one
cheap line of intent; this hook does the board mechanics (single-sourced in
board.py). Lines that look like a marker but don't parse land in
.claude/marker-misses.log (the channel is otherwise fail-open end to end).
Normally invoked via stop_dispatch.py; runs standalone too. Fail-open: any
error -> no-op. Acts only inside an active .claude/orchestrate.json project.
Blocks a turn in exactly one case (once per prompt): a lead work turn trailing
an unanswered question to the Boss with no marker — the unmarked-ask nudge."""
import sys, os, json, hashlib, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
try:
    import board
    import hooklib
except Exception:
    board = hooklib = None


def _turn_used_tools(transcript_path):
    """True when the just-ended turn contains a tool_use block — the 'work turn'
    proxy. A pure conversational reply (锁需求 interrogation, live dialogue with the
    Boss) never trips the unmarked-ask nudge; a work burst that trails a question
    does. Scan the tail backwards: assistant entries belong to the turn until the
    real user prompt that started it (tool_result user entries are inside the turn)."""
    try:
        with open(transcript_path, encoding="utf-8") as f:
            lines = f.readlines()[-400:]
    except Exception:
        return False
    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        t = obj.get("type")
        msg = obj.get("message", {})
        content = msg.get("content") if isinstance(msg, dict) else None
        if t == "assistant":
            if isinstance(content, list) and any(
                    isinstance(b, dict) and b.get("type") == "tool_use" for b in content):
                return True
            continue
        if t == "user":
            if isinstance(content, list) and any(
                    isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                continue  # a tool result — still inside this turn
            return False  # the prompt that started the turn — scan ends
    return False


def _trailing_question(text):
    """True when the turn's final non-empty line reads as a question."""
    for line in reversed((text or "").splitlines()):
        s = line.strip().strip("*_` ")
        if not s:
            continue
        return s.endswith("?") or s.endswith("？")
    return False


def _nudge_once(root, key):
    """True the first time `key` is seen (and record it) — the nudge fires once per
    prompt; the re-ended turn passes whether or not the model added the marker."""
    p = os.path.join(root, ".claude", "ask-nudge-state")
    try:
        if open(p, encoding="utf-8").read().strip() == key:
            return False
    except Exception:
        pass
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(key)
    except Exception:
        pass
    return True


def _open_collisions(root):
    """[(new_id, [open_collider_ids])] for every OPEN entry whose recorded collides
    list still names open entries — the raiser hasn't handled the collision yet."""
    out = []
    try:
        by = {e["id"]: e for e in board.board_list(root)}
        for e in by.values():
            if e.get("status") != "open" or not e.get("collides"):
                continue
            olds = [o for o in e["collides"]
                    if (by.get(o) or {}).get("status") == "open"]
            if olds:
                out.append((e["id"], olds))
    except Exception:
        return []
    return sorted(out)


def _collide_key(c):
    return hashlib.md5(json.dumps(c).encode("utf-8")).hexdigest()


_COLLIDE_STATE = os.path.join(".claude", "collide-nudge-state")


def _collide_nudged(root, key):
    """Persistent multi-key cap (unlike the single-slot ask-nudge-state, which the
    trailing-ask nudge shares and would evict — an evicted cap re-nudges forever on
    an ignored collision)."""
    try:
        return key in json.load(open(os.path.join(root, _COLLIDE_STATE),
                                     encoding="utf-8"))
    except Exception:
        return False


def _collide_mark(root, key):
    p = os.path.join(root, _COLLIDE_STATE)
    try:
        keys = json.load(open(p, encoding="utf-8"))
    except Exception:
        keys = []
    if key not in keys:
        keys.append(key)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(keys[-50:], f)
    except Exception:
        pass


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
    # One batch id per capture: a single turn's marker lines are deliberate separate
    # decisions (one-decision-per-marker doctrine) — the supersede collision check
    # must only fire ACROSS turns, never within one.
    batch = uuid.uuid4().hex[:12]
    for dept, task, ask in markers["raises"]:
        try:
            # The Inspector's @BOSS channel carries verdicts/复盘 reads, never asks —
            # they file as information (Boss's call, 2026-07-18: verdicts were
            # crowding Needs-you). Unfiltered stands: the CEO still can't touch them.
            kind = "info" if dept.split("-")[0].lower() == "inspector" else "needs"
            board.board_add(root, dept, kind, ask, task=task, batch=batch)
        except Exception:
            pass
    for dept, task, fact in markers.get("infos", []):
        try:
            board.board_add(root, dept, "info", fact, task=task)
        except Exception:
            pass
    for token, outcome in markers["dones"]:
        try:
            if "-" in token and board.board_get(root, token):
                board.board_done(root, token, outcome)
            else:
                e, opens = board.board_resolve_dept(root, token, outcome)
                if not e and len(opens) > 1:
                    # An ambiguous @BOSS-DONE[<dept>] used to be swallowed silently — the
                    # dept believes it resolved while its asks stay open forever. Which ask
                    # the Boss actually answered is unknowable here, so surface the
                    # ambiguity on the board itself. board_notice keeps at most one open
                    # notice per dept and marks it so it never counts as an ask itself —
                    # plain board_add compounded ("2 asks open" begat "3 asks open").
                    board.board_notice(root, token,
                                       "@BOSS-DONE[%s] was ambiguous — %d asks open (%s); /board done <id> the answered one"
                                       % (token, len(opens), ", ".join(o["id"] for o in opens)))
        except Exception:
            pass
    # ---- supersede collision (any add path): a fresh ask targets the same task as
    # an older still-open ask from the same dept+kind — nudge BEFORE anything
    # supersedes (Boss's call, 0.9.21: the raiser handles it correctly — a real
    # @BOSS-DONE outcome, or a deliberate keep-both). 0.9.22: the flag is read from
    # the STORE, not the capture — the field miss (refcheck CEO-151/152) was a CLI
    # `orchestrate-board add`, which the marker-only collection never saw. This
    # turn's @BOSS-DONE lines ran above, so a collider closed in-turn never fires.
    collisions = _open_collisions(root)
    if collisions:
        fresh = [c for c in collisions
                 if not _collide_nudged(root, _collide_key(c))]
        if fresh:
            for c in fresh:
                _collide_mark(root, _collide_key(c))
            lines = "; ".join("%s targets the same task as the still-open %s"
                              % (new, ", ".join(olds)) for new, olds in fresh)
            return ("🛑 boss-board: ask collision — %s (same dept + kind). If the new ask "
                    "REPLACES the old, re-end this turn adding `@BOSS-DONE[<old-id>]: "
                    "<one-line outcome>` so the register closes with the real outcome. If "
                    "they are genuinely separate decisions, end the turn again unchanged — "
                    "both stay open. (Once per collision.)" % lines)

    # ---- unmarked trailing ask (lead session): prose is transport, the BOARD is the
    # register. Field case 2026-07-18: the CEO ended a work burst with "Still open for
    # you: … ?" — no marker, so the board never saw it and the question died in
    # scrollback while the panel showed nothing waiting. A work turn whose final line
    # is a question, with no raise/info marker → block the stop once with the fix.
    if markers["raises"] or markers.get("infos"):
        return
    try:
        import stop_idle_nudge
        name, _, team = stop_idle_nudge.identity(data.get("transcript_path") or "")
        if team and name and name != "team-lead":
            return  # teammate pane — dept ask discipline lives in its SOP (nudge is lead-only)
    except Exception:
        pass
    if not _trailing_question(text):
        return
    if not _turn_used_tools(data.get("transcript_path") or ""):
        return
    key = str(data.get("prompt_id") or hashlib.md5(text.encode("utf-8", "replace")).hexdigest())
    if not _nudge_once(root, key):
        return
    return ("🛑 boss-board: this work turn ends on an unanswered question to the Boss, but no "
            "board ask was raised — scrollback is transport, the BOARD is the register (the "
            "Boss may be away, and an unmarked trailing question dies in the scroll). Re-end "
            "the turn keeping your prose AND adding "
            "`@BOSS[<dept>#<task>]: <one-line ask> :: <detail>` — or, if the question was "
            "rhetorical or aimed at a teammate, simply end the turn again (this fires once).")


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    ret = run(data)
    if isinstance(ret, str) and ret:  # standalone parity with stop_dispatch's block path
        sys.stderr.write(ret)
        sys.exit(2)


if __name__ == "__main__":
    main()
