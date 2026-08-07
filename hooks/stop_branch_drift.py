#!/usr/bin/env python3
"""Stop piece — a 分公司's own branch comes and tells it when it has drifted from the
main checkout. Advisory: one stderr nudge, never blocks (returns None always).
Fail-open, branch-office-only, inert off an active orchestrate project.

WHY (2026-07-26). The Boss asked what to do about the Marketing branch office living in
a worktree, "invocably facing the problem of disagreeing with main/master and having stale
files". The audit found the machinery was already sound — every shared-state hook pierces a
worktree to the main checkout via board.main_checkout (0.9.52) — and the damage was
entirely a matter of NOBODY BEING TOLD:
  · 77 commits unmerged since the last real merge two days earlier, so the signed
    correction to three date element names sat on the branch while master's blog copy
    still shipped the wrong ones,
  · 14 commits behind, so the branch's git-tracked copy of the card store / mail / review
    markers was a two-day-old snapshot of the org's shared state,
  · and one tracked file (the dept's OWN brief, carrying the growth target they ratified on
    07-22) modified but never committed for four days — the branch SOP tells the office to
    read its brief at the MAIN checkout, so the office had been reading a brief missing
    the very number it had written down.
Every one of those is invisible in a session that only ever looks at its own worktree. The
counts are one `git rev-list` away, so the fix is to say them out loud at 收工.

Branch-office-only on purpose. The 分公司 self-merges (branch SKILL step 7), so the office
holding the branch is the one who can act; firing this into the CEO's turn end would nag
the one session that cannot drain without the L2 pass. The cost is that a branch office
which never clocks in never hears it — the CEO's own stale-card sentinel is what covers
an office that has gone quiet.
"""
import os, sys, json, subprocess
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
try:
    import hooklib
except Exception:
    hooklib = None
try:
    import board                      # only for main_checkout (worktree piercing)
except Exception:
    board = None

DEFAULT_DRAIN_HOURS = 24
DEFAULT_BEHIND_COMMITS = 10
STATE = ".claude/branch-drift-state"
GIT_TIMEOUT = 5


def _git(cwd, *args, raw=False):
    """stdout of a git command, or '' on any failure (missing git, timeout, non-zero).

    `raw` keeps the output verbatim. Porcelain status encodes state in FIXED COLUMNS, and
    stripping the leading space of ` M path` shifts every path by one character (caught by
    test: the count was right and the clock silently never resolved)."""
    try:
        p = subprocess.run(("git", "-C", cwd) + args, capture_output=True, text=True,
                           timeout=GIT_TIMEOUT)
    except Exception:
        return ""
    if p.returncode != 0:
        return ""
    return p.stdout if raw else p.stdout.strip()


def _counts(wt, ref):
    """(behind, ahead) vs `ref`, or None when git can't answer.

    `A...B` left-counts commits in A only (= behind) and right-counts B only (= ahead);
    getting that pair backwards would report a drained branch as the worst offender."""
    out = _git(wt, "rev-list", "--left-right", "--count", "%s...HEAD" % ref)
    parts = out.split()
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def _oldest_unmerged_hours(wt, ref):
    """Age of the OLDEST commit the branch is holding, in hours (None if none/unknown).

    Age is the trigger, not count: three commits held for a week are worse than thirty
    held for an hour, and it was two days of holding that stranded their correction."""
    out = _git(wt, "log", "--format=%ct", "%s..HEAD" % ref)
    stamps = [s for s in out.splitlines() if s.strip().isdigit()]
    if not stamps:
        return None
    return max(0.0, (datetime.now().timestamp() - int(stamps[-1])) / 3600.0)


def uncommitted(wt):
    """(count, oldest_hours) over MODIFIED TRACKED files — untracked ones are excluded.

    A branch office's worktree legitimately carries untracked per-office state (the
    office.json marker, nudge state), so counting `??` would fire on every session
    forever. What matters is a tracked edit that exists nowhere but here."""
    # core.quotePath=false or git returns non-ASCII paths octal-escaped ("docs/\350\220..."),
    # which no getmtime can open — and this org's paths are overwhelmingly CJK.
    out = _git(wt, "-c", "core.quotePath=false", "status", "--porcelain", raw=True)
    paths, oldest = [], None
    for line in out.splitlines():
        if len(line) < 4 or line[:2] in ("??", "!!"):
            continue
        p = line[3:].strip()
        if " -> " in p:                       # rename: the destination is the live path
            p = p.split(" -> ", 1)[1].strip()
        if p.startswith('"') and p.endswith('"'):
            p = p[1:-1]
        paths.append(p)
        try:
            age = (datetime.now().timestamp() - os.path.getmtime(os.path.join(wt, p))) / 3600.0
        except OSError:
            continue                          # deleted file: counted, but it has no clock
        if oldest is None or age > oldest:
            oldest = age
    return len(paths), oldest


def findings(wt, ref, drain_hours, behind_commits):
    """[(kind, headline, advice)] — one row per way this branch has drifted."""
    pair = _counts(wt, ref)
    if pair is None:
        return []
    behind, ahead = pair
    rows = []
    held = _oldest_unmerged_hours(wt, ref) if ahead else None
    if ahead and held is not None and held >= drain_hours:
        rows.append(("未合并", "%d commit%s held, oldest %.0fh"
                     % (ahead, "" if ahead == 1 else "s", held),
                     "drain it: L2 .pass → merge into %s from the main checkout → ff back" % ref))
    if behind >= behind_commits:
        rows.append(("落后", "%d commits behind %s" % (behind, ref),
                     "sync first: git merge --ff-only %s — your tracked copy of the card "
                     "store, mail and review markers is that old" % ref))
    n, oldest = uncommitted(wt)
    if n and oldest is not None and oldest >= drain_hours:
        rows.append(("未提交", "%d tracked file%s uncommitted, oldest %.0fh"
                     % (n, "" if n == 1 else "s", oldest),
                     "commit or discard: an edit that lives only in this worktree is "
                     "invisible to the main office, brief write-backs included"))
    return rows


def run(data, text=None):
    if hooklib is None or board is None:
        return None
    cwd = data.get("cwd") or ""
    office = hooklib.local_office(cwd)
    if not office:
        return None                        # CEO / main office: no branch of its own
    # The office's own checkout root comes from git, not from the orchestrate.json walk:
    # find_root only stops inside the worktree when that file happens to be git-TRACKED
    # there, so a repo that keeps it untracked would resolve straight to main and this
    # sentinel would go quiet on exactly the setup it exists for.
    local = _git(cwd, "rev-parse", "--show-toplevel")
    if not local:
        return None
    try:
        main = board.main_checkout(local)
    except Exception:
        return None
    if os.path.realpath(main) == os.path.realpath(local):
        return None                        # not a linked worktree: nothing to drift from
    try:
        with open(os.path.join(main, ".claude", "orchestrate.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        if not cfg.get("active"):
            return None
    except Exception:
        return None
    th = cfg.get("thresholds") or {}
    drain_hours = _num(th.get("branch_drain_hours"), DEFAULT_DRAIN_HOURS)
    behind_commits = _num(th.get("branch_behind_commits"), DEFAULT_BEHIND_COMMITS)
    # Compare against whatever the MAIN checkout has checked out — this plugin ships to
    # repos on master and on main, and a detached main checkout has no name to compare to.
    ref = _git(main, "rev-parse", "--abbrev-ref", "HEAD")
    if not ref or ref == "HEAD":
        return None
    try:
        rows = findings(local, ref, drain_hours, behind_commits)
    except Exception:
        return None
    if not rows:
        _remember(local, "")
        return None
    # Hash the TRIGGER KINDS, not the counts: keyed on counts, every new commit would be a
    # fresh "state" and the nudge would fire every turn (0.9.60's lesson).
    sig = "|".join(sorted(r[0] for r in rows))
    if _remember(local, sig):
        return None
    branch = _git(local, "rev-parse", "--abbrev-ref", "HEAD") or office
    lines = ["\n🔀 BRANCH DRIFT — %s vs %s:" % (branch, ref)]
    for kind, headline, advice in rows:
        lines.append("   %-6s %-32s %s" % (kind, headline, advice))
    lines.append("   Shared state (cards · mail · docs/reviews · BACKLOG) is read and "
                 "written at the MAIN checkout; this branch only carries product work.")
    sys.stderr.write("\n".join(lines) + "\n")
    return None                            # advisory only — never blocks the turn


def _num(v, default):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _remember(local, sig):
    """True iff this exact trigger set was already reported (once per change).

    State lives in the WORKTREE, not the main checkout: it is this office's nudge, and
    two branch offices must not overwrite each other's memory (same reason stop_mail
    keeps its nudge state at the local root)."""
    p = os.path.join(local, STATE)
    try:
        with open(p, encoding="utf-8") as f:
            prev = f.read().strip()
    except OSError:
        prev = ""
    if prev == sig:
        return True
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(sig)
    except OSError:
        pass
    return False
