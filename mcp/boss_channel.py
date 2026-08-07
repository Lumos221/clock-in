#!/usr/bin/env python3
"""Boss channel — an MCP stdio server that makes the Boss Board a real destination.

WHY. Founder-facing items used to reach the board as `@BOSS[...]` markers parsed out of
assistant text at turn end: fire-and-forget, so a missed parse lost the item in silence
and nobody learned the message never arrived. A tool call is a different substrate. It
returns a receipt, so a rejected post is visible; its arguments can be VALIDATED, which
is the only way to keep a channel free of noise (prose cannot be checked, a schema can);
and it works from a subagent session without depending on that session's Stop dispatcher.

PROTOCOL. Newline-delimited JSON-RPC 2.0 on stdin/stdout. **stdout carries protocol
messages and nothing else** — a stray print corrupts the transport, so every diagnostic
goes to stderr. Requests without an `id` are notifications and MUST NOT be answered.

FAILURE POSTURE. The server always starts, even off a board project: a server that exits
at launch shows up as a broken plugin, while a server that starts and explains itself at
call time tells the caller exactly what is wrong. Every handler is wrapped; an exception
becomes an error result, never a crash.
"""
import os, sys, json, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "skills", "orchestrate", "scripts"))
sys.path.insert(0, os.path.join(ROOT, "hooks"))
try:
    import board
except Exception:                              # pragma: no cover - packaging accident
    board = None

PROTOCOL_DEFAULT = "2025-06-18"
ASK_MAX = 200
DETAIL_MAX = 1200
KINDS = {
    "decision": "the Boss must choose between options or rule on something",
    "blocker": "work has stopped and only the Boss can restart it",
    "signoff": "finished work needs the Boss's approval before it goes out",
    "info": "a durable fact worth re-reading later, needing nothing from the Boss",
}


def _version():
    try:
        with open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            return str(json.load(f).get("version") or "0")
    except Exception:
        return "0"


def project_root():
    """The MAIN checkout of the board project this session sits in, or None.

    The server inherits the session's cwd at launch, and a session may sit in a linked
    worktree whose checked-out copy of the store is a stale snapshot — so the same
    piercing every board hook uses applies here (board.project_root already does both
    the walk and the pierce)."""
    if board is None:
        return None
    try:
        return board.project_root(os.getcwd())
    except Exception:
        return None


def _active(root):
    try:
        with open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8") as f:
            return bool(json.load(f).get("active"))
    except Exception:
        return False


# ---------------------------------------------------------------- validation


def _clean_line(s):
    """One line, collapsed whitespace. A multi-line ask reads as a paragraph on a board
    built for scanning, so newlines are folded rather than rejected outright."""
    return re.sub(r"\s+", " ", str(s or "").strip())


def validate(args):
    """(fields, error) — error is a message that TEACHES the shape, never just 'invalid'."""
    dept = _clean_line(args.get("dept"))
    if not dept:
        return None, "dept is required: name the desk speaking, e.g. Frontend or CEO."
    kind = _clean_line(args.get("kind")).lower()
    if kind not in KINDS:
        return None, ("kind must be one of %s. %s" %
                      (" · ".join(sorted(KINDS)),
                       " ".join("%s = %s." % (k, v) for k, v in sorted(KINDS.items()))))
    ask = _clean_line(args.get("ask"))
    if not ask:
        return None, "ask is required: one line saying what you need, in the Boss's words not yours."
    if len(ask) > ASK_MAX:
        return None, ("ask is %d chars, the cap is %d. The ask is the line the Boss reads in a "
                      "list; move the context into `detail`." % (len(ask), ASK_MAX))
    detail = str(args.get("detail") or "").strip()
    if len(detail) > DETAIL_MAX:
        return None, ("detail is %d chars, the cap is %d. Anything longer belongs in a file "
                      "the post links to, not in the post." % (len(detail), DETAIL_MAX))
    if detail and _clean_line(detail) == ask:
        return None, "detail repeats the ask. Leave it out, or say what the Boss needs to decide with."
    card = _clean_line(args.get("card")).lstrip("#")
    return {"dept": dept, "kind": kind, "ask": ask, "detail": detail, "card": card}, None


# ---------------------------------------------------------------- board ops


def _open_entries(root):
    try:
        return [e for e in board.board_list(root) if e.get("status") == "open"]
    except Exception:
        return []


def do_message(args):
    root = project_root()
    if not root:
        return True, ("No board project here: this session's directory has no "
                      ".claude/orchestrate.json above it, so there is nowhere to post.")
    if not _active(root):
        return True, "This project's orchestrate.json is not active, so the board is closed."
    fields, err = validate(args)
    if err:
        return True, err
    text = fields["ask"] if not fields["detail"] else "%s :: %s" % (fields["ask"], fields["detail"])
    before = {e.get("id") for e in _open_entries(root)}
    try:
        entry = board.board_add(root, fields["dept"], fields["kind"], text,
                                task=fields["card"] or None)
    except Exception as exc:
        return True, "The board refused the post: %s" % exc
    eid = (entry or {}).get("id") or "?"
    opens = _open_entries(root)
    dup = eid in before
    lead = ("Already open as %s, nothing added" % eid) if dup else ("Posted %s" % eid)
    return False, ("%s (%s). %d open on the Boss's board now. It is read there; do not repeat "
                   "the content in your reply, point at it." % (lead, fields["kind"], len(opens)))


def do_resolve(args):
    root = project_root()
    if not root:
        return True, "No board project here."
    eid = _clean_line(args.get("id"))
    outcome = _clean_line(args.get("outcome"))
    if not outcome:
        return True, ("outcome is required: what was actually decided or done. Resolving "
                      "without an outcome loses the answer the board existed to keep.")
    if not eid:
        return True, "id is required: the entry to close, e.g. CEO-142."
    try:
        ok = board.board_done(root, eid, outcome)
    except Exception as exc:
        return True, "The board refused the resolve: %s" % exc
    if not ok:
        return True, "No open entry %s — check `list_open` for the live ids." % eid
    return False, "Resolved %s. %d still open." % (eid, len(_open_entries(root)))


def do_list_open(args):
    root = project_root()
    if not root:
        return True, "No board project here."
    rows = _open_entries(root)
    if not rows:
        return False, "Nothing open on the Boss's board."
    out = []
    for e in rows[:40]:
        out.append("%s [%s] %s — %s" % (e.get("id"), e.get("kind") or "ask",
                                        e.get("dept") or "?", (e.get("text") or "")[:160]))
    if len(rows) > 40:
        out.append("… +%d more" % (len(rows) - 40))
    return False, "\n".join(out)


TOOLS = [
    {
        "name": "message",
        "description": (
            "Put an item on the founder's board — the ONE place the Boss reads. Use it for "
            "anything the Boss must decide, sign off, unblock, or should be able to re-read "
            "later. The terminal is a stream the Boss cannot scroll reliably, so an item that "
            "exists only in your reply is an item they will miss. After posting, point at "
            "the board in your reply instead of repeating the content."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dept": {"type": "string", "description": "The desk speaking, e.g. Frontend, CEO."},
                "kind": {"type": "string", "enum": sorted(KINDS),
                         "description": " · ".join("%s: %s" % (k, v) for k, v in sorted(KINDS.items()))},
                "ask": {"type": "string",
                        "description": "One line, max %d chars: what you need from the Boss, "
                                       "phrased as the choice they face." % ASK_MAX},
                "detail": {"type": "string",
                           "description": "Optional, max %d chars: only what changes the Boss's "
                                          "answer. Link a file for anything longer." % DETAIL_MAX},
                "card": {"type": "string", "description": "Optional durable card number, e.g. 387."},
            },
            "required": ["dept", "kind", "ask"],
        },
    },
    {
        "name": "resolve",
        "description": ("Close a board item once it has an answer, recording WHAT was "
                        "decided. An item closed without an outcome loses the answer."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Entry id, e.g. CEO-142."},
                "outcome": {"type": "string", "description": "What was decided or done."},
            },
            "required": ["id", "outcome"],
        },
    },
    {
        "name": "list_open",
        "description": ("What is already open on the Boss's board. Check before posting so the "
                        "same ask does not arrive twice under two desks."),
        "inputSchema": {"type": "object", "properties": {}},
    },
]

HANDLERS = {"message": do_message, "resolve": do_resolve, "list_open": do_list_open}


# ---------------------------------------------------------------- transport


def handle(msg):
    """The response object, or None for a notification (which must never be answered)."""
    mid = msg.get("id")
    method = msg.get("method") or ""
    if mid is None:
        return None
    if method == "initialize":
        asked = str((msg.get("params") or {}).get("protocolVersion") or "")
        return _ok(mid, {
            "protocolVersion": asked if re.match(r"^\d{4}-\d{2}-\d{2}$", asked) else PROTOCOL_DEFAULT,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "boss", "version": _version()},
        })
    if method == "ping":
        return _ok(mid, {})
    if method == "tools/list":
        return _ok(mid, {"tools": TOOLS})
    if method == "tools/call":
        params = msg.get("params") or {}
        fn = HANDLERS.get(params.get("name") or "")
        if fn is None:
            return _ok(mid, _content("Unknown tool: %s" % params.get("name"), True))
        if board is None:
            return _ok(mid, _content("The board module failed to import; the plugin "
                                     "install looks incomplete.", True))
        try:
            is_err, text = fn(params.get("arguments") or {})
        except Exception as exc:                # a tool must never take the server down
            is_err, text = True, "Tool raised: %r" % (exc,)
        return _ok(mid, _content(text, is_err))
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": "Method not found: %s" % method}}


def _ok(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _content(text, is_error=False):
    return {"content": [{"type": "text", "text": text}], "isError": bool(is_error)}


def main():
    # Same escape hatch the board hooks use: a test must be able to post without the
    # panel daemon being started and a browser window opening behind it.
    if board is not None and os.environ.get("BOSS_BOARD_SKIP_SERVER"):
        board._SKIP_SERVER = True
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue                            # malformed frame: skip, never crash
        try:
            resp = handle(msg)
        except Exception as exc:
            sys.stderr.write("boss-channel: %r\n" % (exc,))
            continue
        if resp is None:
            continue
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
