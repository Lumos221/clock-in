#!/usr/bin/env python3
"""PostToolUse(Agent) — record the LIVE model each department was spawned with, so the
Boss Board's Departments view shows the EFFECTIVE model, not the agent-file default.
Frontmatter `model:` is only the DEFAULT; the CEO overrides it per spawn in-session
(`Agent(..., model="opus")`), and that override — the real "what runs this dept" — lives
in the spawn's `tool_input.model` (absent = the dept runs its default). Keyed by the dept
handle (base of the teammate `name`); one-shot / reviewer / registrar spawns are skipped.
Writes {handle: {model, ts}} into the board store's `models` map, which load_roster reads.
Only the CEO (lead) spawns named teammates, so this is lead-only in practice. Fail-open;
inert off an active orchestrate project."""
import os, re, sys, json

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
    model = str(ti.get("model") or "").strip()
    if not model:
        return                       # no override — the dept runs its frontmatter default
    handle = base(name)
    rtype = base(str(ti.get("subagent_type") or "").split(":")[-1]).lower()
    if not handle or rtype in STANDING or handle.lower() in STANDING:
        return                       # standing reviewers/registrar aren't departments
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

    def mut(store):
        store.setdefault("models", {})[handle] = {"model": model, "ts": board._now()}
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
