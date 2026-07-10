#!/usr/bin/env python3
"""PreToolUse hook — accident guard: block genuinely IRREVERSIBLE shell ops as a
backstop. exit 2 = block (stderr is the reason fed to the model); exit 0 = allow.
Fail-open (any error → allow, never brick the tools).

This catches irreversible
damage. SOP is archive-over-remove, and teammates run auto-approved (no human prompt),
so this is their only backstop — but it should rarely fire.

Only acts when an active .claude/orchestrate.json marker exists (path-based lookup,
cwd-independent, so it covers teammates)."""
import sys, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    import hooklib
except Exception:
    hooklib = None

# All case-insensitive: shell flags come in both cases (`rm -Rf` — BSD rm treats -R
# like -r) and SQL is conventionally uppercase (`DROP TABLE`) — case-sensitive
# patterns silently missed both.
IRREVERSIBLE = [re.compile(p, re.IGNORECASE) for p in (
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\s+-[a-z]*f",
    r"\bgit\s+push\b.*\s(--force\S*|-f)\b",   # covers the short `-f` spelling too
    r"\bdrop\s+(database|table)\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r">\s*/dev/sd",
)]

# `rm -rf <one .next dir>` is whitelisted — the regenerable Next.js build cache
# (safe to delete; the standard dev-restart step). Boss-approved 2026-06-30.
NEXT_DIR = re.compile(r"(?:\./|[\w./@+-]+/)?\.next/?")


def rm_rf_targets(seg):
    """If this command segment invokes `rm` with both recursive and force in effect,
    return its target list (possibly empty); else None. Handles the flag spellings a
    single regex missed: combined vs separate (`-rf` / `-r -f`), long
    (`--recursive --force`) and uppercase (`-Rf`)."""
    toks = seg.split()
    if "rm" not in toks:
        return None
    flags, targets = set(), []
    rest = toks[toks.index("rm") + 1:]
    for i, t in enumerate(rest):
        if t == "--":
            targets.extend(rest[i + 1:])
            break
        if t in ("--recursive", "--force"):
            flags.add(t[2])          # 'r' / 'f'
        elif t.startswith("-") and not t.startswith("--") and len(t) > 1:
            flags.update(c.lower() for c in t[1:])
        elif not t.startswith("--"):
            targets.append(t)
    return targets if {"r", "f"} <= flags else None


def guard_verdict(cmd):
    """None = allow; else a short reason to block with."""
    for seg in re.split(r"[;&|]+|\n", cmd):
        targets = rm_rf_targets(seg)
        if targets is None:
            continue
        if len(targets) == 1 and NEXT_DIR.fullmatch(targets[0]):
            continue  # whitelisted: rm -rf of the regenerable .next build cache
        return "`%s` is an IRREVERSIBLE op (recursive force-remove)" % seg.strip()
    for pat in IRREVERSIBLE:
        if pat.search(cmd):
            return "`%s` is an IRREVERSIBLE op" % cmd
    return None


def active(root):
    if not root:
        return False
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
    except Exception:
        return False
    return bool(cfg.get("active"))


def main():
    if hooklib is None:
        return
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    if data.get("tool_name", "") != "Bash":
        return
    if not active(hooklib.find_root(data.get("cwd") or os.getcwd())):
        return
    cmd = (data.get("tool_input", {}) or {}).get("command", "")
    reason = guard_verdict(cmd)
    if reason:
        sys.stderr.write(
            "🛑 accident-guard: %s. SOP is archive-over-remove — archive instead, "
            "or get the Boss's explicit approval to run it." % reason)
        sys.exit(2)
    return  # allow


if __name__ == "__main__":
    main()
