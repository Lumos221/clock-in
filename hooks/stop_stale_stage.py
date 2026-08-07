#!/usr/bin/env python3
"""Stop piece — surface cards STALLED IN A STAGE THAT NOBODY OWNS. Advisory: writes one
stderr nudge, never blocks (returns None always). Fail-open, lead-only, inert off an
active orchestrate project.

WHY (2026-07-25). The Boss asked "what happened to all these cards?" about 10 sitting in
审查. The answer was that they were three unrelated problems wearing one label, and every
one of them was INVISIBLE:
  · 3 had passed L2 two days earlier and were waiting on the CEO to merge,
  · 7 said `review` with no `.pass`/`.fail` on file at all — never submitted, so nobody
    was reviewing them and nobody was going to,
  · and 8 MORE carried a `.pass` while filed under `todo`, hidden in a pile of 45.
Then one stage earlier they spotted the same shape: cards reading 18h in 派工, which looks
like activity and is actually an untouched queue.

The common thread is not a stage, it is OWNERSHIP: a card whose stage clock keeps running
while no live seat is responsible for advancing it. 0.9.55 made the states legible on the
board; this makes them come and find their.

**Liveness is the whole point of the check** and it is why this cannot key on the card
alone. A card at 派工 for 18h with its dept pane ALIVE is a working queue and must stay
quiet; the same card with a dead pane is an orphan. Liveness = PRESENCE in the team
config's `members[]` (a clean shutdown removes the entry) — never `isActive`, which is a
busy-flag and reads false on a demonstrably responsive teammate.
"""
import os, re, json, glob
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
import sys
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
try:
    import hooklib
except Exception:
    hooklib = None
try:
    import cardlib
except Exception:
    cardlib = None
try:
    import board                        # only for main_checkout (worktree piercing)
except Exception:
    board = None

DEFAULT_HOURS = 24
CAP = 8                      # never wall-of-text their turn end
STATE = ".claude/stale-stage-state"
SUFFIX = re.compile(r"-\d+$")


def _live_handles(session_id, cwd=None):
    """Base handles with a member entry in this project's team config, or None when
    the roster can't be resolved at all.

    None ≠ empty set, and the difference is the whole sentinel: an empty set means
    "every seat is gone" and fires ③ on every assigned card. Keying the config on the
    CURRENT session id produced exactly that false alarm in the field (2026-07-26 —
    the roster lives under the id the team was born with), so resolution now goes
    through hooklib.team_key and an unresolvable roster stays SILENT."""
    cfg = hooklib.team_config(session_id, cwd) if hooklib else None
    if not cfg:
        return None
    out = set()
    for m in cfg.get("members") or []:
        n = str((m or {}).get("name") or "").strip()
        if n and n != "team-lead":
            out.add(SUFFIX.sub("", n).lower())
    return out


def _markers(root):
    """{id: (kind, mtime)} — the board's reader, verbatim, mtimes included.

    This carried its own copy twice over: its own key parser (blind to the
    `<dept>.<id>.<n>.pass` shape the field actually writes) AND no date test at all, while
    the board has date-checked since 0.9.61. The result was an alarm reporting 35 cards
    待合并 where the board confirmed 9 — the recycled-id collision the board had already
    fixed, replayed here."""
    if board is None:
        return {}
    try:
        return board._review_markers(root)
    except Exception:
        return {}


def _hours(since):
    try:
        t = datetime.strptime(str(since).strip()[:16].replace("T", " "), "%Y-%m-%d %H:%M")
    except Exception:
        return None
    d = (datetime.now() - t).total_seconds() / 3600.0
    return d if d > 0 else None


def findings(root, live, hours):
    """[(kind, #NNN, dept, hours, note)] — one row per card that nobody is advancing.

    `live` None = roster unresolvable. Liveness-dependent findings are then withheld
    entirely; only ① 待合并 and ② 未送审, which are true regardless of who is alive,
    still speak. Treating None as "nobody alive" is how a resolution bug turns into a
    wall of false 派工 alarms."""
    bdir = os.path.join(root, "docs", "board")
    marks = _markers(root)
    unknown = live is None
    out = []
    # cardlib.load, not a glob: a numbered .md in the board folder is not necessarily a
    # card. A plan of record and a schema proposal live there too, and with no frontmatter
    # they parsed as cards with no status and no clock — so a durable-id marker match went
    # unchecked and they sat in the alarm as "awaiting merge" permanently (4 of them on a
    # live board, 2026-07-27). cardlib already refuses to guess at a non-card; the alarm
    # was the only reader that did.
    for f in sorted(cardlib.load(bdir), key=lambda c: str(c.get("_path") or "")):
        m = re.match(r"(\d+)-", os.path.basename(str(f.get("_path") or "")))
        if not m:
            continue
        num = m.group(1)
        status = (f.get("status") or "").strip().lower()
        if status == "done":
            continue
        # `—` is cardlib's EMPTY placeholder, not a department. Truthiness alone read it
        # as one and flagged every unassigned card as a stalled queue (caught in dry-run).
        dept = cardlib.clean(f.get("dept") or "") or ""
        dept = "" if dept in ("—", "-", "–") else dept
        handle = SUFFIX.sub("", dept.split()[0]).lower() if dept else ""
        age = _hours(f.get("since") or "")
        # The board's rule, not a second reading of it: a marker older than the card's
        # stage clock is a verdict on an earlier leg, whichever id matched.
        l2 = board.l2_verdict(marks, num, f.get("task_id"), f.get("since"), root) if board else ""
        alive = (not unknown) and bool(handle) and handle in live

        # ① Through the gate, waiting on the CEO. Always their business, dept or not.
        if l2 == "pass":
            out.append(("待合并", num, dept or "—", age,
                        "L2 passed — verify the .pass, merge if not landed, complete the card"))
            continue
        # ② Claims review with no marker on file: never submitted, nobody reviewing.
        if status == "review" and not l2:
            out.append(("未送审", num, dept or "—", age,
                        "says review with no .pass/.fail on file — never submitted"
                        + ("" if alive or unknown else "; its seat is not alive")))
            continue
        # ③ Assigned or mid-work, clock running, and NO live seat to advance it.
        if not unknown and age is not None and age >= hours and dept and not alive:
            stage = "执行" if status == "doing" else "派工"
            out.append((stage, num, dept, age,
                        "no live %s seat — %s" % (dept, "abandoned mid-work" if status == "doing"
                                                  else "queued to a dept that never picked it up")))
    return out


def run(data, text=None):
    if hooklib is None or cardlib is None:
        return None
    # CEO-only output: a teammate finishing a turn is a Stop in ITS OWN session, so
    # the event excludes nobody — only the session identity does.
    if not hooklib.is_lead(data.get("transcript_path") or ""):
        return None
    root = hooklib.find_root(data.get("cwd") or "")
    if not root:
        return None
    # A 分公司 runs its OWN session in a worktree, and `root` has been pierced to the
    # main checkout — so this would judge the CEO's board against the BRANCH's roster and
    # task store. Its own lane is not the CEO team's queue.
    if hooklib.local_office(data.get("cwd") or ""):
        return None
    if board is not None:
        try:
            root = board.main_checkout(root)   # the board lives in the MAIN checkout
        except Exception:
            pass
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"),
                             encoding="utf-8"))
        if not cfg.get("active"):
            return None
    except Exception:
        return None
    hours = cfg.get("stale_stage_hours", DEFAULT_HOURS)
    try:
        hours = float(hours)
    except Exception:
        hours = DEFAULT_HOURS
    live = _live_handles(data.get("session_id"), data.get("cwd") or "")
    try:
        rows = findings(root, live, hours)
    except Exception:
        return None
    if not rows:
        _remember(root, "")
        return None
    sig = "|".join("%s%s" % (r[0], r[1]) for r in sorted(rows, key=lambda x: x[1]))
    if _remember(root, sig):
        return None                      # already said this; don't nag every turn
    shown = rows[:CAP]
    lines = ["\n⏳ STAGE STALL — %d card%s nobody is advancing:"
             % (len(rows), "" if len(rows) == 1 else "s")]
    for kind, num, dept, age, note in shown:
        clock = "%.0fh" % age if age is not None else "no clock"
        lines.append("   %-6s #%-5s %-14s %-9s %s" % (kind, num, dept[:14], clock, note))
    if len(rows) > CAP:
        lines.append("   … +%d more" % (len(rows) - CAP))
    lines.append("   待合并 = yours (merge + complete) · 未送审 = re-dispatch, it was never "
                 "submitted · 派工/执行 = its seat is gone, respawn or re-assign.")
    sys.stderr.write("\n".join(lines) + "\n")
    return None                          # advisory only — never blocks their turn


def _remember(root, sig):
    """True iff this exact finding set was already reported (once per change)."""
    p = os.path.join(root, STATE)
    try:
        prev = open(p, encoding="utf-8").read().strip()
    except OSError:
        prev = ""
    if prev == sig:
        return True
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write(sig)
    except OSError:
        pass
    return False
