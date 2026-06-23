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

IRREVERSIBLE = [
    r"\brm\s+-[a-z]*r[a-z]*f|\brm\s+-[a-z]*f[a-z]*r",   # rm -rf / -fr
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\s+-[a-z]*f",
    r"\bgit\s+push\b.*--force",
    r"\bdrop\s+(database|table)\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r">\s*/dev/sd",
]


def find_marker(start):
    """Walk up from a file or dir path to the nearest .claude/orchestrate.json."""
    if not start:
        return None
    d = os.path.abspath(start)
    if os.path.isfile(d):
        d = os.path.dirname(d)
    while True:
        m = os.path.join(d, ".claude", "orchestrate.json")
        if os.path.exists(m):
            return m
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def active(marker):
    if not marker:
        return False
    try:
        cfg = json.load(open(marker, encoding="utf-8"))
    except Exception:
        return False
    return bool(cfg.get("active"))


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    if data.get("tool_name", "") != "Bash":
        return
    if not active(find_marker(data.get("cwd") or os.getcwd())):
        return
    cmd = (data.get("tool_input", {}) or {}).get("command", "")
    for pat in IRREVERSIBLE:
        if re.search(pat, cmd):
            sys.stderr.write(
                "🛑 accident-guard: `%s` is an IRREVERSIBLE op. SOP is archive-over-remove — "
                "archive instead, or get the Boss's explicit approval to run it." % cmd)
            sys.exit(2)
    return  # allow


if __name__ == "__main__":
    main()
