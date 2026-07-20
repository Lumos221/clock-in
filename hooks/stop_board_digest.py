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
    try:
        bdir = cardlib.board_dir(root, cfg)
        if os.path.isdir(bdir):
            # hygiene before freshness: heal duplicate ids, collapse essay status /
            # junk priority to canon (originals kept as dated body notes) — the
            # sweep's own writes then register as staleness and regen below
            traces = cardlib.dedupe_ids(bdir) + cardlib.canonicalise(bdir)
            if traces:
                hooklib.log_marker_misses(root, "board-hygiene", traces)
            if cardlib.digest_stale(root, cfg):
                cardlib.regen_digest(root, cfg)
    except Exception:
        pass
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    run(data, None)


if __name__ == "__main__":
    main()
