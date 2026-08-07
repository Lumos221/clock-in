#!/usr/bin/env python3
"""Stop/SubagentStop piece (via stop_dispatch) — digest freshener for the per-card
board store (0.9.28). Card files are the truth; TaskBoard.md is a generated digest,
and the write-path hooks regen it on their own writes. What they can't see is a
card edited OUTSIDE the hook path — the Boss flipping a status in Obsidian (a Bases
property edit writes straight to the card's frontmatter), a dept updating its card
file mid-task, the 分公司 branch session working the same repo. This closes that
gap mechanically at every turn end: board hygiene first (0.9.34 — dedupe_ids heals
duplicate durable numbers from concurrent minting, canonicalise collapses essay
statuses / junk priorities to canon with the originals kept as body notes), then
one mtime sweep (no parsing), regen only when some card is newer than the digest.
Zero tokens, never blocks, fail-open; inert
outside an active orchestrate project or before the store exists (it never
triggers the migration itself — ensure_store owns that)."""
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import hooklib, cardlib
except Exception:
    hooklib = cardlib = None
try:
    import board  # main_checkout only
except Exception:
    board = None


def run(data, text):
    if hooklib is None or cardlib is None:
        return None
    root = hooklib.find_root(data.get("cwd") or "")
    if not root:
        return None
    if board is not None:
        try:
            root = board.main_checkout(root)
        except Exception:
            pass
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"),
                             encoding="utf-8"))
        if not cfg.get("active"):
            return None
    except Exception:
        return None
    faults = []
    try:
        bdir = cardlib.board_dir(root, cfg)
        if os.path.isdir(bdir):
            # hygiene before freshness: heal duplicate ids, collapse essay status,
            # recover a level from a priority that carries its reason (originals kept
            # as dated body notes) — the sweep's own writes then register as staleness
            # and regen below
            traces = (cardlib.dedupe_ids(bdir) + cardlib.canonicalise(bdir)
                      + cardlib.stamp_since(bdir, os.path.join(root, ".claude",
                                                               "since-state.json")))
            if traces:
                hooklib.log_marker_misses(root, "board-hygiene", traces)
            if cardlib.digest_stale(root, cfg):
                cardlib.regen_digest(root, cfg)
            faults = cardlib.field_faults(bdir)
    except Exception:
        pass
    return _fault_nudge(root, data, faults)


def _fault_nudge(root, data, faults):
    """The half the sweep must NOT do itself: a value with no reading is somebody's
    intent, and the only person who can say what it meant is the one who set it.

    It used to be cleared and filed to `.claude/marker-misses.log`, which nothing reads —
    so a level set at 23:52 was gone by 00:07 with no one told, in a session that had
    already ended. Said at the turn end instead, to the desk that owns the field, while
    whoever wrote it is still there. One nudge per state: a fault left standing is
    mentioned once, not every turn."""
    if not faults:
        _remember(root, "")
        return None
    if not hooklib.is_lead(data.get("transcript_path") or ""):
        return None                      # these fields are the CEO's to set
    if hooklib.local_office(data.get("cwd") or ""):
        return None
    sig = "|".join("%s:%s=%s" % f for f in sorted(faults))
    if _remember(root, sig):
        return None
    rows = "; ".join("#%s `%s: %s`" % (i, f, v) for i, f, v in faults[:6])
    more = "" if len(faults) <= 6 else " … +%d more" % (len(faults) - 6)
    return ("🏷️ CARD FIELD — no level reads from %s%s, so the card draws no tag and "
            "sorts as unset. Set one (P0 urgent · P1 critical · P2 important · P3 "
            "nice-to-have) or `—` for normal. Left as written until you do."
            % (rows, more))


def _remember(root, sig):
    """True iff this exact fault set was already reported."""
    p = os.path.join(root, ".claude", "board-fault-state")
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


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    run(data, None)


if __name__ == "__main__":
    main()
