#!/usr/bin/env python3
"""`orchestrate-sop` — print the operating contract for the seat that is asking.

A seat runs this at spawn. What it needs back depends on what kind of seat it is, and
it should not have to know or be told:

  ONE-SHOT (a subagent — staff, an expert, a dept dispatched for a single card)
      gets the core contract only. Queue-claiming, reporting to the lead, the pane
      protocol and the shutdown handshake describe a life it does not have; printing
      them costs it tokens on every single dispatch and invites it to act on rules
      that cannot apply.

  STANDING SEAT (a teammate — its own process, its own pane, addressable by name)
      gets the core contract plus the standing-seat addendum.

**Detected, never asked.** A teammate is its own `claude` process and carries
`--agent-name` in its argv; a subagent runs inside the lead's process, so walking up
from this script to the nearest `claude` ancestor answers the question outright. Making
the seat declare its own kind would put the one fact the machine knows for certain into
the hands of the reader most likely to get it wrong.

`--full` forces the addendum. A 分公司 runs as its own top-level session — no
`--agent-name`, so it reads as one-shot — and its own skill decides how much of the
standing contract still binds it.
"""
import os, re, sys, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "..", "reference")
CORE = os.path.join(REF, "department-sop.md")
ADDENDUM = os.path.join(REF, "department-sop-teammate.md")


def _ancestry(pid, depth=8):
    """argv of this process and its ancestors, nearest first."""
    out = []
    for _ in range(depth):
        try:
            r = subprocess.run(["ps", "-o", "ppid=,args=", "-p", str(pid)],
                               capture_output=True, text=True, timeout=4)
            line = (r.stdout or "").strip()
            if not line:
                break
            ppid, _, args = line.partition(" ")
            out.append(args.strip())
            pid = int(ppid)
        except Exception:
            break
        if pid <= 1:
            break
    return out


def is_teammate():
    """True when this seat is a standing teammate.

    Reads the nearest `claude` ancestor: a teammate is launched as its own process with
    `--agent-name`; a subagent runs inside the lead's, which has none. Fail-open to
    False — the core contract is correct for every seat, and the addendum is the part
    that misleads when it does not apply."""
    for args in _ancestry(os.getpid()):
        if re.search(r"(^|/)claude\b", args.split(" ")[0] or ""):
            return " --agent-name " in " %s " % args
    return False


def main(argv):
    full = "--full" in argv or is_teammate()
    parts = []
    for path in ([CORE, ADDENDUM] if full else [CORE]):
        try:
            parts.append(open(path, encoding="utf-8").read().rstrip("\n"))
        except Exception as exc:
            sys.stderr.write("orchestrate-sop: cannot read %s (%s)\n" % (path, exc))
            return 1
    sys.stdout.write("\n\n".join(parts) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
