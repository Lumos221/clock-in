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
import re, sys, os, json, hashlib, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
try:
    import board
    import hooklib
except Exception:
    board = hooklib = None


def _office_wants_nudge(cwd):
    """A branch office opts back INTO the unmarked-ask nudge with `board_nudge: true`
    in its `.claude/office.json`. Off by default there: the whole point of the nudge is
    that a prose-only ask dies in scrollback the Boss cannot reliably scroll back
    through, and inside a branch they are reading the conversation themselves."""
    d = os.path.abspath(cwd or "")
    for _ in range(12):
        p = os.path.join(d, ".claude", "office.json")
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return bool((json.load(f) or {}).get("board_nudge"))
            except Exception:
                return False
        parent = os.path.dirname(d)
        if parent == d:
            return False
        d = parent
    return False


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


NEEDS_RE = re.compile(r"^[-—#>*\s]*(?:🔴|⚪)?\s*(?:needs?\s+you|需要你|等你)\b", re.I)
# "Needs you: nothing." / "nothing right now." / 需要你：无 — a nil declaration, not
# an ask. Trailing qualifier words allowed; a clause continuing past a comma is not
# nil ("none of the options work, pick one" IS an ask).
NEEDS_NIL = re.compile(r"[:：]\s*(?:nothing|none|无|没有|—|-)\b[^,;，；]*$", re.I)


def _trailing_question(text):
    """True when the turn ends on an ask the board never saw: the final non-empty
    line reads as a question, OR one of the closing lines is a "Needs you"-style
    trailer with content (the CEO's reply-shape habit — field case 2026-07-19:
    "---Needs you: the same two optional items…" ended in a full stop, so the
    question-mark heuristic slept while the ask lived only in prose). A trailer
    declaring nothing needed ("Needs you: nothing") is not an ask."""
    return bool(_trailing_ask_text(text))


def _trailing_ask_text(text):
    """The trailing ask's OWN WORDS, or "". Returning the text rather than a bool is what
    lets the caller ask the next question: is this the thing the turn actually registered?"""
    lines = [l.strip().strip("*_` ") for l in (text or "").splitlines()
             if l.strip().strip("*_` ")]
    if not lines:
        return ""
    if lines[-1].endswith("?") or lines[-1].endswith("？"):
        return lines[-1]
    for s in lines[-3:]:
        if NEEDS_RE.match(s) and not NEEDS_NIL.search(s):
            return s
    return ""


_STOP = {"the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "it", "is", "are",
         "be", "should", "would", "do", "does", "you", "your", "i", "we", "that", "this",
         "with", "at", "as", "by", "not", "but", "if", "then", "than", "so", "one", "also",
         "only", "just", "still", "now", "new", "what", "which", "how", "can", "want"}


_CJK_STOP = set("的了是在和有我你不要吗呢个这那就都还也很与及对为以")


def _tokens(s):
    """Content tokens for a rough overlap test, in both languages this org writes in:
    ASCII words of 3+ characters, plus CJK characters minus function words.

    CJK is deliberately UNIGRAMS. Bigrams look more precise and are worse here: one
    inserted particle shifts every pair after it, so 「速查卡的版式要不要改成两面制」 and
    「速查卡版式改两面制」 — the same ask — scored 0.38 and read as unrelated."""
    s = (s or "").lower()
    out = {w for w in re.findall(r"[a-z0-9]{3,}", s) if w not in _STOP}
    out |= {c for c in re.findall(r"[一-鿿]", s) if c not in _CJK_STOP}
    return out


def _covered(question, markers):
    """True when something registered THIS TURN plausibly IS the trailing question.

    The gate here used to be "any marker at all", which immunised the whole turn: a turn
    that registered one ask and then asked a SECOND thing in prose passed silently, the
    board looked complete, and the second question died in the scroll — precisely the
    shape the nudge exists to prevent. Overlap on content words
    is the cheap discriminator: a marker restating the question carries its nouns, an
    unrelated one does not. A question with nothing distinctive in it ("ready?") scores
    as covered, because there is nothing to compare it against."""
    raised = list(markers.get("raises") or []) + list(markers.get("infos") or [])
    if not raised:
        return False         # registered nothing at all: the original nudge case, unchanged
    q = _tokens(question)
    if len(q) < 2:
        return True          # "anything?" — too little to compare; never second-guess a
                             # turn that DID register something on the strength of one word
    for _, _, t in raised:
        m = _tokens(t)
        if m and len(q & m) / len(q) >= 0.5:
            return True
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
            # they file as information (verdicts were
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
    # ---- Obsidian desk mirror (0.9.38): the ask register as generated notes in
    # docs/board/desk/ — refreshed every turn end AFTER captures/dones landed, so
    # the Bases Desk view tracks the panel. Fail-open, byte-stable when unchanged.
    try:
        board.desk_mirror(root)
    except Exception:
        pass
    # ---- supersede collision (any add path): a fresh ask targets the same task as
    # an older still-open ask — regardless of raiser handle or kind (0.9.36: one ask
    # registered twice, CLI add + marker re-end, wore different dept AND kind and
    # slipped the old same-dept+kind key) — nudge BEFORE anything supersedes (Boss's
    # call, 0.9.21: the raiser handles it correctly — a real @BOSS-DONE outcome, or
    # a deliberate keep-both). 0.9.22: the flag is read from the STORE, not the
    # capture — the field miss (a live project CEO-151/152) was a CLI `orchestrate-board
    # add`, which the marker-only collection never saw. This turn's @BOSS-DONE lines
    # ran above, so a collider closed in-turn never fires.
    collisions = _open_collisions(root)
    if collisions:
        fresh = [c for c in collisions
                 if not _collide_nudged(root, _collide_key(c))]
        if fresh:
            for c in fresh:
                _collide_mark(root, _collide_key(c))
            lines = "; ".join("%s targets the same task as the still-open %s"
                              % (new, ", ".join(olds)) for new, olds in fresh)
            return ("🛑 boss-board: ask collision — %s. Replaces the old one, or is the "
                    "same ask twice (a CLI add AND a marker) → re-end adding "
                    "`@BOSS-DONE[<old-id>]: <one-line outcome>`. Genuinely separate "
                    "decisions → end again unchanged, both stay open." % lines)

    # ---- unmarked trailing ask (lead session): prose is transport, the BOARD is the
    # register. Field case 2026-07-18: the CEO ended a work burst with "Still open for
    # you: … ?" — no marker, so the board never saw it and the question died in
    # scrollback while the panel showed nothing waiting. A work turn whose final line
    # is a question, with no raise/info marker → block the stop once with the fix.
    if not hooklib.is_lead(data.get("transcript_path") or ""):
        return  # teammate pane — dept ask discipline lives in its SOP (nudge is lead-only)
    # A 分公司 runs as its own session against a handful of desks, and the Boss works
    # inside it directly — so the register the nudge defends is the conversation they are
    # already reading, not a panel they have to be pointed at. Firing there interrupted a
    # turn to demand a marker for a question they had just been asked to them face (their
    # report, 2026-07-28). Same gate the other CEO-team sentinels use. `board_nudge:
    # true` in the office file opts a branch back in.
    if hooklib.local_office(data.get("cwd") or "") and not _office_wants_nudge(data.get("cwd") or ""):
        return
    trailing = _trailing_ask_text(text)
    if not trailing:
        return
    # NOT "did this turn raise anything" — "is THIS question the thing it raised". One
    # marker used to immunise a whole turn, so a second ask left in prose was never
    # caught (2026-07-27).
    if _covered(trailing, markers):
        return
    if not _turn_used_tools(data.get("transcript_path") or ""):
        return
    key = str(data.get("prompt_id") or hashlib.md5(text.encode("utf-8", "replace")).hexdigest())
    if not _nudge_once(root, key):
        return
    return ("🛑 boss-board: this turn ends on an ask to the Boss that the board never "
            "got — a prose-only ask dies in scrollback while the panel shows nothing "
            "waiting. Re-end the turn adding `@BOSS[<dept>#<task>]: <one-line ask> :: "
            "<detail>` (or `mcp__boss__message`). **Then point, do not repeat** — your "
            "reply says where it is. Rhetorical, or aimed at a teammate → end again "
            "unchanged and it passes.")


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
