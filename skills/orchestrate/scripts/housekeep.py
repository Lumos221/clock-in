#!/usr/bin/env python3
"""Housekeeping — `orchestrate-housekeep scan|run|prune [--days N]`.

Visual working artefacts (the Boss's marked screenshots in, dept-rendered mockups out)
are load-bearing while their card is open and clutter after the round ships. This
script retires them mechanically and SAFELY:

- **Archive, never delete.** `run` moves stale files to `<dir>/archive/YYYY-MM/`
  (subfolders preserved). Deletion exists only as the explicit `prune` subcommand,
  which trims old *archives* — a Boss-run act, never automatic.
- **Reference-safe by construction.** A file whose basename or project-relative path
  appears on an Active TaskBoard card, an open Boss-Board entry, `CANON.md` or the
  SoT is never touched, whatever its age. (The *Recently shipped* tail and BACKLOG
  don't protect — shipped work is exactly what should retire.)
- Also sweeps plugin residue: `.claude/idle-nudges/` state older than 7 days and an
  oversized `.claude/marker-misses.log` (rotated to `.1`).

Which dirs: `orchestrate.json` → `"housekeeping": [{"path": "docs/mockups", "days": 14}]`.
When the key is absent, the default is `docs/mockups` at 14 days IF that dir exists —
zero config for the common layout, nothing scanned otherwise.

Timing: `run` stamps `.claude/housekeep-stamp`; the session-start sentinel nudges when
candidates exist and the stamp is older than 7 days. Zero tokens when clean."""
import os, sys, json, re, shutil, time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    import board  # find root + worktree piercing conventions
except Exception:
    board = None

DEFAULT_DIRS = [{"path": "docs/mockups", "days": 14}]
RESIDUE_NUDGE_DAYS = 7
LOG_ROTATE_BYTES = 200_000
STAMP = ".claude/housekeep-stamp"


def find_root(start):
    d = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.exists(os.path.join(d, ".claude", "orchestrate.json")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def load_cfg(root):
    try:
        return json.load(open(os.path.join(root, ".claude", "orchestrate.json"),
                              encoding="utf-8"))
    except Exception:
        return {}


def hk_dirs(root, cfg):
    """Configured housekeeping dirs as [(abs_dir, rel_dir, days)]; default applies
    only when the conventional dir actually exists."""
    entries = cfg.get("housekeeping")
    if not isinstance(entries, list) or not entries:
        entries = DEFAULT_DIRS
        if not os.path.isdir(os.path.join(root, entries[0]["path"])):
            return []
    out = []
    for e in entries:
        if not isinstance(e, dict) or not e.get("path"):
            continue
        rel = str(e["path"]).strip("/")
        d = os.path.join(root, rel)
        if os.path.isdir(d):
            out.append((d, rel, int(e.get("days", 14))))
    return out


def live_references(root, cfg):
    """One text blob of everything that protects a file from archiving."""
    parts = []
    tb = os.path.join(root, cfg.get("taskboard", "docs/TaskBoard.md"))
    try:
        text = open(tb, encoding="utf-8").read()
        parts.append(re.split(r"(?mi)^##\s*Recently shipped", text)[0])
    except Exception:
        pass
    for rel in (cfg.get("sot", "docs/SoT.md"), cfg.get("canon", "docs/CANON.md")):
        try:
            parts.append(open(os.path.join(root, rel), encoding="utf-8").read())
        except Exception:
            pass
    try:
        store = json.load(open(os.path.join(root, ".claude", "boss-board.json"),
                               encoding="utf-8"))
        for e in store.get("entries", []):
            if isinstance(e, dict) and e.get("status") == "open":
                parts.append(str(e.get("text", "")))
    except Exception:
        pass
    return "\n".join(parts)


def candidates(root, cfg, now=None, dirs=None):
    """[(abs_path, rel_path, size)] of stale, unreferenced files across configured
    dirs (or an explicit `dirs` override — the `--path` ad-hoc case). archive/
    subtrees are skipped; referenced files are protected."""
    now = now or time.time()
    refs = live_references(root, cfg)
    out = []
    for d, rel, days in (dirs if dirs is not None else hk_dirs(root, cfg)):
        cutoff = now - days * 86400
        for dirpath, dirnames, filenames in os.walk(d):
            dirnames[:] = [x for x in dirnames if x != "archive"]
            for fn in filenames:
                if fn.startswith("."):
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    if os.path.getmtime(p) > cutoff:
                        continue
                    size = os.path.getsize(p)
                except Exception:
                    continue
                relp = os.path.relpath(p, root)
                if fn in refs or relp in refs:
                    continue
                out.append((p, relp, size))
    return out


def stale_quick_count(root, cfg, now=None):
    """(count, bytes) of age-stale files, WITHOUT the reference check — the cheap
    session-start approximation (the flag says candidates; `run` decides)."""
    now = now or time.time()
    n = b = 0
    for d, rel, days in hk_dirs(root, cfg):
        cutoff = now - days * 86400
        for dirpath, dirnames, filenames in os.walk(d):
            dirnames[:] = [x for x in dirnames if x != "archive"]
            for fn in filenames:
                if fn.startswith("."):
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    if os.path.getmtime(p) <= cutoff:
                        n += 1
                        b += os.path.getsize(p)
                except Exception:
                    continue
    return n, b


def stamp_age_days(root, now=None):
    now = now or time.time()
    try:
        return (now - os.path.getmtime(os.path.join(root, STAMP))) / 86400.0
    except Exception:
        return None  # never run


def archive(root, cfg, now=None, dirs=None):
    """Move every candidate into <dir>/archive/YYYY-MM/<subpath>; returns moved list.
    Also sweeps plugin residue and stamps the run."""
    now = now or time.time()
    month = datetime.fromtimestamp(now).strftime("%Y-%m")
    moved = []
    scan_dirs = dirs if dirs is not None else hk_dirs(root, cfg)
    dirs_map = {os.path.abspath(d): (d, rel) for d, rel, _ in scan_dirs}
    for p, relp, size in candidates(root, cfg, now, dirs=scan_dirs):
        base = next((d for d in dirs_map if os.path.abspath(p).startswith(d + os.sep)), None)
        if base is None:
            continue
        sub = os.path.relpath(p, base)
        dest = os.path.join(base, "archive", month, sub)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        stem, ext = os.path.splitext(dest)
        k = 1
        while os.path.exists(dest):
            dest = "%s-%d%s" % (stem, k, ext)
            k += 1
        shutil.move(p, dest)
        moved.append((relp, os.path.relpath(dest, root)))
    # plugin residue
    nd = os.path.join(root, ".claude", "idle-nudges")
    try:
        for fn in os.listdir(nd):
            p = os.path.join(nd, fn)
            if now - os.path.getmtime(p) > RESIDUE_NUDGE_DAYS * 86400:
                os.remove(p)
    except Exception:
        pass
    log = os.path.join(root, ".claude", "marker-misses.log")
    try:
        if os.path.getsize(log) > LOG_ROTATE_BYTES:
            os.replace(log, log + ".1")
    except Exception:
        pass
    sp = os.path.join(root, STAMP)
    os.makedirs(os.path.dirname(sp), exist_ok=True)
    with open(sp, "w", encoding="utf-8") as f:
        f.write(datetime.fromtimestamp(now).strftime("%Y-%m-%dT%H:%M:%S"))
    return moved


def prune(root, cfg, days, now=None, dirs=None):
    """DELETE archived files older than `days` under configured archive/ trees.
    Boss-run only — the launcher makes this an explicit subcommand, never automatic."""
    now = now or time.time()
    cutoff = now - days * 86400
    gone = []
    for d, rel, _ in (dirs if dirs is not None else hk_dirs(root, cfg)):
        a = os.path.join(d, "archive")
        for dirpath, _, filenames in os.walk(a):
            for fn in filenames:
                p = os.path.join(dirpath, fn)
                try:
                    if os.path.getmtime(p) <= cutoff:
                        os.remove(p)
                        gone.append(os.path.relpath(p, root))
                except Exception:
                    continue
    return gone


USAGE = "usage: orchestrate-housekeep [scan|run|prune] [--path <dir-in-project>] [--days <N>]\n"


def main(argv):
    args = list(argv)
    cmd = args.pop(0) if args and not args[0].startswith("--") else "scan"
    days = path = None
    while args:
        a = args.pop(0)
        if a == "--days" and args:
            try:
                days = int(args.pop(0))
            except ValueError:
                sys.stderr.write(USAGE)
                return 1
        elif a == "--path" and args:
            path = args.pop(0)
        else:
            sys.stderr.write(USAGE)
            return 1
    root = find_root(os.getcwd())
    if not root:
        sys.stderr.write("orchestrate-housekeep: no .claude/orchestrate.json above cwd\n")
        return 1
    if board is not None:
        try:
            root = board.main_checkout(root)
        except Exception:
            pass
    cfg = load_cfg(root)
    dirs = None
    if path:  # ad-hoc override — the Boss (or the model relaying the Boss) named a dir
        ap = path if os.path.isabs(path) else os.path.join(root, path)
        ap = os.path.abspath(ap)
        rel = os.path.relpath(ap, root)
        if rel.startswith(".."):
            sys.stderr.write("orchestrate-housekeep: --path must be inside the project\n")
            return 1
        if not os.path.isdir(ap):
            sys.stderr.write("orchestrate-housekeep: no such dir: %s\n" % rel)
            return 1
        dirs = [(ap, rel, days if (days is not None and cmd != "prune") else 14)]
    if cmd == "scan":
        cand = candidates(root, cfg, dirs=dirs)
        if not cand:
            print("housekeep: clean — nothing stale and unreferenced.")
            return 0
        mb = sum(s for _, _, s in cand) / 1e6
        print("housekeep: %d stale unreferenced file(s), %.1f MB — `orchestrate-housekeep run` archives them:"
              % (len(cand), mb))
        for _, relp, _ in cand[:40]:
            print("  " + relp)
        if len(cand) > 40:
            print("  … +%d more" % (len(cand) - 40))
        return 0
    if cmd == "run":
        moved = archive(root, cfg, dirs=dirs)
        print("housekeep: archived %d file(s)%s; residue swept; stamp updated."
              % (len(moved), (" → " + os.path.dirname(moved[0][1])) if moved else ""))
        return 0
    if cmd == "prune":
        if days is None:
            sys.stderr.write("prune deletes old archives — say how old: prune --days 60\n")
            return 1
        gone = prune(root, cfg, days, dirs=dirs)
        print("housekeep: pruned %d archived file(s) older than %d days." % (len(gone), days))
        return 0
    sys.stderr.write(USAGE)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
