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
machine-truncate CEO prose (a hook can't know which lines carry the judgement).

Same sentinel pattern over DECISIONS.md (field causes, refcheck 07-14): a tagged
[topic-key] ruling with no CANON row makes lookups grep-luck, and a recent entry
with no **Impl:** line is silent loss — implementation "queued" in prose that never
became a card, so the dead behaviour survives and re-teaches the dead design. And
tombstone TaskBoard cards (finished, hand-closed by striking the heading, no
task_id) get a DELETE prescription — the register-via-TaskCreate advice would
re-register shipped work, so a CEO rightly ignores it and the tombstones rot."""
import sys, json, os, re
from datetime import date

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
IMPL_RECENT_DAYS = 7    # only recent entries owe an **Impl:** — never spam the archive
ASK_MAX_CHARS = 280     # a decidable ask is 1–2 lines; the Boss reads a 2-line clamp


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


def decisions_flags(root, cfg):
    """Token-free discipline flags over DECISIONS.md (list of str; [] when clean/absent):
    tagged [topic-key] entries with no CANON row, and recent entries missing **Impl:**."""
    flags = []
    try:
        dec = open(os.path.join(root, cfg.get("decisions", "docs/DECISIONS.md")),
                   encoding="utf-8").read()
    except Exception:
        return flags
    try:
        canon = open(os.path.join(root, cfg.get("canon", "docs/CANON.md")),
                     encoding="utf-8").read()
    except Exception:
        canon = ""
    topics = {c.strip().strip("`").lower()
              for c in re.findall(r"(?m)^\|\s*([^|\n]+?)\s*\|", canon)}
    tagged, no_impl, today = [], [], date.today()
    for m in re.finditer(r"(?m)^##\s+([^\n]*)\n((?:(?!^##\s)[^\n]*\n?)*)", dec):
        head, body = m.group(1), m.group(2)
        km = re.search(r"\[([A-Za-z0-9][A-Za-z0-9_-]{2,})\]", head)
        if km:
            tagged.append(km.group(1))
        dm = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", head)
        if dm and "**Impl:**" not in body:
            try:
                age = (today - date(*map(int, dm.groups()))).days
            except ValueError:
                continue
            if 0 <= age <= IMPL_RECENT_DAYS:
                no_impl.append((km.group(1) if km else head[:32].strip()))
    unreg = [k for k in dict.fromkeys(tagged) if k.lower() not in topics]
    if unreg:
        flags.append(
            "⚠ %d tagged decision(s) have no CANON row (%s) — settled answers must be one "
            "lookup away, not grep luck. Register each: `@CANON[<dept>] <topic-key> → "
            "DECISIONS (affects: …)`, or `orchestrate-canon add`."
            % (len(unreg), ", ".join(unreg[:6]) + ("…" if len(unreg) > 6 else "")))
    if no_impl:
        flags.append(
            "⚠ %d recent DECISIONS entr%s no **Impl:** line (%s) — a behaviour-changing "
            "ruling names its card (`#<id>`), an explicit `parked: <why>`, or `none-needed`; "
            "implementation queued only in prose is silent loss (nothing tracks it, the dead "
            "behaviour re-teaches the dead design)."
            % (len(no_impl), "y carries" if len(no_impl) == 1 else "ies carry",
               ", ".join(no_impl[:4]) + ("…" if len(no_impl) > 4 else "")))
    return flags


def context_for(root, cfg, audience="lead", agent_name=None):
    """The injection text for an armed project (str), or None to stay silent.
    audience: "lead" = the CEO session (full text + discipline flags);
    "dept" = a teammate pane (slim: role line + redlines + SoT — the flags are CEO
    chores and would only distract/cost tokens in every dept spawn)."""
    if audience == "dept":
        parts = ["📋 CEO orchestration is active for this project. You are the teammate "
                 "%s — follow your agent brief; the CEO owns the task lifecycle."
                 % (agent_name or "",),
                 "Settled-question discipline: before stating what's allowed/designed/"
                 "settled, search the record — `orchestrate-canon get <topic>` + grep "
                 "DECISIONS.md — and answer from the log, not from principles."]
        redlines = cfg.get("redlines", [])
        if redlines:
            parts.append("Signed 红线 (need the Boss's two-key 准/驳 before editing):")
            for r in redlines:
                rp = r.get("path") if isinstance(r, dict) else r
                note = (" — %s" % r.get("note")) if isinstance(r, dict) and r.get("note") else ""
                parts.append("  - %s%s" % (rp, note))
        sot_rel = cfg.get("sot", "docs/SoT.md")
        try:
            text = open(os.path.join(root, sot_rel), encoding="utf-8").read()
            parts.append("\n— current source of truth (%s) —\n%s" % (sot_rel, text[:4000]))
        except Exception:
            pass
        return "\n".join(parts) + "\n"
    parts = ["📋 CEO orchestration mode is active for this project. You are the CEO — follow the orchestrate skill.",
             "Settled-question discipline: before stating what's allowed/designed/settled, "
             "search the record — `orchestrate-canon get <topic>` + grep DECISIONS.md — and "
             "answer from the log, not from principles."]
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
            idless = [t for t in tbv["tasks"] if not t["task_id"]]
            # A tombstone (finished card hand-closed by striking the heading) must NOT
            # get the register advice — re-registering shipped work is worse than the
            # rot, so the CEO learns to ignore the flag. Prescribe deletion instead.
            tomb = [t for t in idless
                    if board.TOMB_RE.search("%s %s" % (t["label"], t["name"]))]
            live = [t for t in idless if t not in tomb]
            if live:
                names = [(t["label"] or t["name"])[:24] for t in live]
                parts.append(
                    "⚠ %d Active card(s) carry no platform task_id (%s). CEO: register each "
                    "via TaskCreate — widget-born tasks stay hook-synced; hand-only cards rot. "
                    "(TaskCreate not loaded? It's deferred — ToolSearch "
                    "select:TaskCreate,TaskUpdate,TaskList,TaskGet first. Genuinely absent — "
                    "widget-gated session? Spawn the 书记处 Registrar (.claude/agents/Registrar.md, "
                    "haiku teammate) and route the task lifecycle through it — reference/task-widget.md.)"
                    % (len(live), ", ".join(names[:6]) + ("…" if len(names) > 6 else "")))
            if tomb:
                names = [(t["label"] or t["name"])[:24] for t in tomb]
                parts.append(
                    "⚠ %d finished tombstone card(s) still sit in Active (%s) — closed by "
                    "striking the heading, so no hook can ever retire them. CEO: Delete the "
                    "card(s) now (history already lives in BACKLOG / Recently shipped). Close "
                    "live cards via TaskUpdate→completed — never by strikethrough."
                    % (len(tomb), ", ".join(names[:6]) + ("…" if len(names) > 6 else "")))
        except Exception:
            pass
    if board is not None:
        try:
            fat = [(e["id"], len(e.get("text", ""))) for e in board.board_list(root)
                   if e.get("status") == "open" and len(e.get("text", "")) > ASK_MAX_CHARS]
            if fat:
                parts.append(
                    "⚠ %d open Boss-Board ask(s) are essays (%s) — the Boss reads a 2-line "
                    "clamp, and an essay isn't decidable. Re-raise each as question · options "
                    "· recommendation (1–2 lines; detail → a file/card the ask points at) + "
                    "`@BOSS-DONE[<old-id>]` in the same turn."
                    % (len(fat), ", ".join("%s: %d chars" % f for f in fat[:4])
                       + ("…" if len(fat) > 4 else "")))
        except Exception:
            pass
    try:
        parts.extend(decisions_flags(root, cfg))
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
    # Audience: teammate transcripts stamp agentName/agentSetting/teamName on every
    # line (field-verified 2026-07-15). Depts get the slim brief; the Registrar (a
    # mechanical proxy whose file says everything) gets nothing; the lead gets it all.
    audience, agent_name = "lead", None
    try:
        import stop_idle_nudge
        name, setting, team = stop_idle_nudge.identity(data.get("transcript_path") or "")
        if team and name and name != "team-lead":
            if (setting or name).startswith("Registrar"):
                return
            audience, agent_name = "dept", name
    except Exception:
        pass
    out = context_for(root, cfg, audience, agent_name)
    if out:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
