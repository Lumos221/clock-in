#!/usr/bin/env python3
"""PostToolUse(Agent) — two jobs on every teammate spawn: SET the seat's effort level,
and record the live model it came up on.

Both live here rather than in a hook of their own, and that is load-bearing. A session
snapshots the plugin's hook REGISTRY at start but reads the FILE behind a registered
entry fresh at every invocation — so new behaviour in an existing hook reaches sessions
that are already running, and a new hook file reaches none of them until they restart.
Shipped separately, the effort work went half-live in the field: the guard that refuses
an undeclared spawn was an edit to a registered hook and took effect at once, while the
hook meant to carry out the declaration was a new file and never ran. Every seat came up
at the lead's level anyway, and the CEO had complied with an instruction that did
nothing. Adding to this file is what makes a fix land in a running org.

## 1 · Effort

A teammate is given no level by the platform: the spawn drops its brief's `effort:` and
hands the seat the LEAD's live level, so an omission is not a default, it is an accident
nobody can see. The CEO declares `effort=<level>` in the spawn's `description` (or
prompt) — a `PreToolUse` guard refuses the spawn without one — and this reads it back and
types it into that seat's own pane, which is the only lever that reaches one seat.

It rides the TEXT because `Agent` accepts an `effort` parameter, discards it, and never
shows it to a hook: `tool_input` carries only the tool's declared fields, so a parameter
would look right, do nothing, and tell nobody.

The setter runs DETACHED and waits: a spawn returns before its pane exists (the member
lands in the team config without a `tmuxPaneId`, and the terminal takes seconds more),
and nothing that waits may hold the CEO's turn open. Skipped for `haiku` seats — no
effort ladder, so the command would be a no-op that still rewrites the machine's global
default.

## 2 · Model

Record the LIVE model each department was spawned with, so the
Boss Board's Departments view shows the EFFECTIVE model, not the agent-file default.
Frontmatter `model:` is only the DEFAULT; the CEO overrides it per spawn in-session
(`Agent(..., model="opus")`), and that override — the real "what runs this dept" — lives
in the spawn's `tool_input.model` (absent = the dept runs its default). Keyed by the dept
handle (base of the teammate `name`); one-shot / reviewer / registrar spawns are skipped.
Writes {handle: {model, ts}} into the board store's `models` map, which load_roster reads.
Only the CEO (lead) spawns named teammates, so this is lead-only in practice. Fail-open;
inert off an active orchestrate project."""
import os, re, sys, json, subprocess

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

STANDING = {"auditor", "inspector", "registrar"}
SETTER = os.path.join(HERE, "..", "skills", "orchestrate", "scripts", "effort.py")
# `effort=high`, `effort: high`, `EFFORT = xhigh` — one shape to write, several to read,
# because a rule that only accepts one spelling is a rule the CEO fails on a typo. Kept
# identical to the guard's reader: a spawn the guard accepts must be one this can act on,
# or the CEO is told it declared something that then quietly never happens.
EFFORT_RE = re.compile(r"\beffort\s*[=:]\s*(low|medium|high|xhigh|max)\b", re.I)
NAME_RE = re.compile(r"(?:nickname|花名|alias)\s*[:=]\s*([A-Za-z0-9_\-\u4e00-\u9fff]+)")


def declared_effort(ti):
    """The level this spawn declares, or ''. `description` first — the short label field,
    so a level there is unambiguous."""
    for field in ("description", "prompt"):
        m = EFFORT_RE.search(str(ti.get(field) or ""))
        if m:
            return m.group(1).lower()
    return ""


def brief_model(root, handle):
    """The `model:` frontmatter pin for this handle, or ''. Project brief first, then the
    plugin's own agents/ dir, where the standing roles carry theirs."""
    for p in ([os.path.join(root, ".claude", "agents", "%s.md" % handle)] if root else []) + \
             [os.path.join(HERE, "..", "agents", "%s.md" % handle)]:
        try:
            head = open(p, encoding="utf-8").read(2048)
        except Exception:
            continue
        if not head.startswith("---") or head.count("---") < 2:
            continue
        m = re.search(r"(?m)^model:\s*(\S+)", head.split("---", 2)[1])
        if m:
            return m.group(1).strip()
    return ""


def set_seat_effort(root, name, ti):
    """Fire the detached setter for this seat, if the spawn declared a level."""
    level = declared_effort(ti)
    if not level:
        return                       # the guard already refused this spawn
    model = (str(ti.get("model") or "") or brief_model(root, base(name))).lower()
    if "haiku" in model:
        return
    try:
        subprocess.Popen([sys.executable, SETTER, name, level, "--wait"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        pass


def base(name):
    return re.sub(r"-\d+$", "", str(name or "")).strip()


def run(data):
    if hooklib is None or board is None:
        return
    if data.get("tool_name") != "Agent":
        return
    ti = data.get("tool_input") or {}
    name = ti.get("name") or ""
    if not name or name == "team-lead":
        return                       # one-shot subagent — not a standing dept
    root = hooklib.find_root(data.get("cwd") or "")
    if not root:
        return
    root = board.main_checkout(root)
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"),
                             encoding="utf-8"))
        if not cfg.get("active"):
            return
    except Exception:
        return

    # EFFORT SETTING IS SUSPENDED. `/effort` typed into a pane cannot apply until the
    # seat's current turn ENDS, and a dept's first turn IS its card — so the command sat
    # queued for 20 minutes while the seat worked at the inherited level, and the Boss
    # had to cancel it by hand to get their input box back. It never reached the work it
    # was declared for, and it interrupted the work that was happening. `set_seat_effort`
    # is kept below, unwired, until the routing that replaces it is settled.
    model = str(ti.get("model") or "").strip()
    handle = base(name)
    rtype = base(str(ti.get("subagent_type") or "").split(":")[-1]).lower()
    if not handle or rtype in STANDING or handle.lower() in STANDING:
        return                       # standing reviewers/registrar aren't departments
    # 花名/nickname = 显示名（CEO 在 spawn description 里写 `nickname=<花名>`，
    # 与 `effort=` 同款；分隔符 `:` 也兼容），
    # handle 不动
    nick = NAME_RE.search("%s %s" % (str(ti.get("description") or ""),
                                     str(ti.get("prompt") or "")))
    nick_name = nick.group(1) if nick else ""
    if not model and not nick_name:
        return                       # nothing to record — the dept runs its defaults

    def mut(store):
        if model:
            store.setdefault("models", {})[handle] = {"model": model, "ts": board._now()}
        if nick_name:
            store.setdefault("seats", {})[name] = {"nickname": nick_name, "ts": board._now()}
        return None

    try:
        board._locked_mutate(root, mut)
    except Exception:
        pass


def main():
    if hooklib is None:
        return
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    try:
        run(data)
    except Exception:
        return


if __name__ == "__main__":
    main()
