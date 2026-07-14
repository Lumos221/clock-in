#!/usr/bin/env python3
"""SessionStart hook — when CEO orchestration is active in this project, arm CEO mode:
inject the standing reminder, any signed 红线, and the SoT (source of truth — the
compass). Does nothing in a project without an active .claude/orchestrate.json marker.
Resolves the marker like every other hook — walk up from cwd, pierce a linked worktree
to the main checkout — so a session started in a subdirectory still arms (reads cwd
from stdin JSON; fail-open — any error → stay silent).

Loads SoT.md, NOT BACKLOG.md: SoT is the small "where we stand" compass designed to
load each session; BACKLOG is the append-only finished-task log, never auto-loaded.

Also the token-free bloat sentinel: file discipline (SoT ~15-line cap · cards are
pointers, not journals) is prose doctrine, and prose doctrine rots between one-off
housekeepings. This hook re-measures at EVERY session start and flags what's over —
zero tokens when clean, one line per violation until fixed. Detection only: never
machine-truncate CEO prose (a hook can't know which lines carry the judgement)."""
import sys, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
try:
    import hooklib
except Exception:
    hooklib = None
try:
    import board  # only for main_checkout (worktree piercing)
except Exception:
    board = None

SOT_MAX_LINES = 20      # doctrine says ~15; flag with a little slack
SOT_MAX_CHARS = 2000
CARD_MAX_CHARS = 1200   # a card is a pointer; past this it's become a journal


def sot_flag(text, sot_rel):
    """One-line over-cap flag for the SoT, or None when it's within cap."""
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) <= SOT_MAX_LINES and len(text) <= SOT_MAX_CHARS:
        return None
    return ("⚠ %s is %d lines / %d chars — over its ~15-line hard cap (it loads every "
            "session). Trim now: Now = 3 one-line slots; details/decisions → "
            "DECISIONS.md / CANON.md, never restated here." % (sot_rel, len(lines), len(text)))


def fat_cards_flag(tb_text):
    """One-line flag naming Active cards that outgrew a pointer, or None."""
    fat = []
    for a, b in hooklib.tb_card_spans(tb_text):
        if b - a > CARD_MAX_CHARS:
            head = tb_text[a:b].splitlines()[0][4:].strip()
            fat.append((head.split("·", 1)[0].strip() or head)[:24])
    if not fat:
        return None
    return ("⚠ %d TaskBoard card(s) exceed %d chars (%s) — a card is a pointer, not a "
            "journal. Keep status to ONE line; history → DECISIONS.md / 复盘 / the dept's "
            "report, then cut the card back."
            % (len(fat), CARD_MAX_CHARS, ", ".join(fat[:5]) + ("…" if len(fat) > 5 else "")))


def context_for(root, cfg):
    """The full injection text for an armed project (str), or None to stay silent."""
    parts = ["📋 CEO orchestration mode is active for this project. You are the CEO — follow the orchestrate skill."]
    redlines = cfg.get("redlines", [])
    if redlines:
        parts.append("Signed 红线 (need the Boss's two-key 准/驳 before editing):")
        for r in redlines:
            rp = r.get("path") if isinstance(r, dict) else r
            note = (" — %s" % r.get("note")) if isinstance(r, dict) and r.get("note") else ""
            parts.append("  - %s%s" % (rp, note))
    sot_rel = cfg.get("sot", "docs/SoT.md")
    sot = os.path.join(root, sot_rel)
    if os.path.exists(sot):
        try:
            text = open(sot, encoding="utf-8").read()
            parts.append("\n— current source of truth (%s) —\n%s" % (sot_rel, text[:4000]))
            flag = sot_flag(text, sot_rel)
            if flag:
                parts.append(flag)
        except Exception:
            pass
    tb = os.path.join(root, cfg.get("taskboard", "docs/TaskBoard.md"))
    if os.path.exists(tb):
        try:
            flag = fat_cards_flag(open(tb, encoding="utf-8").read())
            if flag:
                parts.append(flag)
        except Exception:
            pass
    if board is not None:
        try:
            tbv = board.load_taskboard(root)
            unreg = [(t["label"] or t["name"])[:24] for t in tbv["tasks"] if not t["task_id"]]
            if unreg:
                parts.append(
                    "⚠ %d Active card(s) carry no platform task_id (%s). CEO: register each "
                    "via TaskCreate — widget-born tasks stay hook-synced; hand-only cards rot. "
                    "(TaskCreate not loaded? It's deferred — ToolSearch "
                    "select:TaskCreate,TaskUpdate,TaskList,TaskGet first. Genuinely absent — "
                    "widget-gated session? Spawn the 书记处 Registrar (.claude/agents/Registrar.md, "
                    "haiku teammate) and route the task lifecycle through it — reference/task-widget.md.)"
                    % (len(unreg), ", ".join(unreg[:6]) + ("…" if len(unreg) > 6 else "")))
        except Exception:
            pass
    return "\n".join(parts) + "\n"


def main():
    if hooklib is None:
        return
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    root = hooklib.find_root(data.get("cwd") or os.getcwd())
    if not root:
        return  # no marker = as if not installed
    if board is not None:
        root = board.main_checkout(root)
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
    except Exception:
        return
    if not cfg.get("active"):
        return
    out = context_for(root, cfg)
    if out:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
