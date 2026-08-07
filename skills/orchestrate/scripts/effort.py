#!/usr/bin/env python3
"""Per-seat effort — `orchestrate-effort <seat> <level>`.

A teammate does NOT get the `effort:` from its own brief. The spawn drops that field
and hands every teammate the LEAD's live session effort instead, so an org whose CEO
sits at `xhigh` runs its whole fleet at `xhigh` — including a haiku task desk paying
for maximum deliberation on mechanical writes. The only lever that reaches a single
seat is the `/effort` command typed into that seat's own pane, which is what this
script does: resolve the seat's pane from the team config, type the command, confirm
the dialog, and prove the pane said it took.

Two things make it more than a keystroke macro, and both are why it is a script and
not an instruction:

- **It repairs a side effect the CEO cannot see.** `/effort` in ANY pane rewrites the
  GLOBAL `~/.claude/settings.json` `effortLevel` — "saved as your default for new
  sessions". Left alone, the last seat you set silently becomes the default for every
  future session on this machine. The value is captured before typing and restored
  after the pane confirms, so setting a seat changes that seat and nothing else.
- **It refuses rather than guesses.** Typing into the wrong pane submits a command to
  someone else's session. The seat's GUID comes from the team roster, the pane must
  still be running claude, its title must still be that seat, and the pane must echo
  what was typed — any check failing stops before a Return is pressed.

Set effort AT SPAWN, before the seat has history. Effort is part of the rendered
prompt, so changing it mid-conversation invalidates the cached prefix and the whole
transcript is re-read on the next message — cheap on an empty seat, expensive on a
seat ten cards deep.
"""
import os, re, sys, json, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import board  # AppleScripts + the pane interlock, one implementation

LEVELS = ("low", "medium", "high", "xhigh", "max")
TEAMS = os.path.expanduser("~/.claude/teams")
SETTINGS = os.path.expanduser("~/.claude/settings.json")


def find_seat(seat, team=None):
    """(pane_guid, pinned_model, agent_type) for `seat`, or (None, None, None).

    Newest config wins. A handle is reused across sessions for months (`QA`, `Legal`),
    so every stale team dir on disk holds a dead pane with that exact name; picking the
    freshest is what keeps a lookup from resolving to a pane that closed in July."""
    best = None
    try:
        dirs = os.listdir(TEAMS)
    except Exception:
        return (None, None, None)
    for d in dirs:
        if team and d != team:
            continue
        p = os.path.join(TEAMS, d, "config.json")
        try:
            cfg = json.load(open(p, encoding="utf-8"))
            mtime = os.path.getmtime(p)
        except Exception:
            continue
        for m in cfg.get("members") or []:
            if m.get("name") == seat and m.get("tmuxPaneId"):
                if best is None or mtime > best[0]:
                    best = (mtime, m["tmuxPaneId"], m.get("model") or "",
                            m.get("agentType") or "")
    return (best[1], best[2], best[3]) if best else (None, None, None)


def live_panes():
    """The GUIDs of every iTerm pane with a FOREGROUND claude in it. Months of team
    configs sit on disk and every one of them still names its seats and their pane ids,
    so the roster alone would list a hundred dead desks as addressable."""
    if board._iterm_disabled():
        return None                            # unknowable, not empty — caller shows all
    out = board._osa(board.ITERM_ROSTER_APPLESCRIPT, timeout=6)
    if out is None:
        return None
    ttys = board._claude_ttys()
    live = set()
    for ln in (out or "").splitlines():
        bits = ln.split("\t")
        if len(bits) >= 2 and bits[1].strip() in ttys:
            live.add(bits[0].strip())
    return live


def live_seats():
    """Seats that still own a claude-running pane — what `orchestrate-effort` with no
    arguments prints, so a CEO never opens a config file to find out what it can
    address. Newest config wins per handle, for the same reason `find_seat` does."""
    seen, live = {}, live_panes()
    try:
        dirs = os.listdir(TEAMS)
    except Exception:
        return []
    for d in dirs:
        p = os.path.join(TEAMS, d, "config.json")
        try:
            cfg = json.load(open(p, encoding="utf-8"))
            mtime = os.path.getmtime(p)
        except Exception:
            continue
        for m in cfg.get("members") or []:
            name, guid = m.get("name"), m.get("tmuxPaneId")
            if not name or not guid or name == "team-lead":
                continue
            if live is not None and guid not in live:
                continue
            if name not in seen or mtime > seen[name][0]:
                seen[name] = (mtime, name, m.get("agentType") or "", m.get("model") or "", guid)
    return [(v[1], v[2], v[3], v[4]) for v in sorted(seen.values(), key=lambda v: -v[0])]


def read_global_effort():
    """The stored value, or None when the key has never been written. None is not the
    same as "high": restoring it means REMOVING the key, and writing "high" instead
    would silently pin a default the Boss never chose."""
    try:
        d = json.load(open(SETTINGS, encoding="utf-8"))
    except Exception:
        return None
    v = d.get("effortLevel")
    return v if isinstance(v, str) else None


def write_global_effort(value):
    """Put `effortLevel` back to `value` (or drop the key when value is None), editing
    the one line rather than re-serialising. The file is hand-maintained — a json.dump
    round-trip would reorder keys and strip formatting on a file nobody asked us to
    reformat."""
    try:
        raw = open(SETTINGS, encoding="utf-8").read()
    except Exception:
        return False
    pat = re.compile(r'^([ \t]*)"effortLevel"[ \t]*:[ \t]*"[^"]*"([ \t]*,?)[ \t]*$', re.M)
    if value is None:
        new = re.sub(r"\n\n+", "\n", pat.sub("", raw, count=1))
        try:
            json.loads(new)
        except Exception:
            # The key was the object's LAST entry, so dropping its line orphaned the
            # comma on the line above. Nothing else can be trailing here — the key was
            # last — so removing that comma is the whole repair.
            new = re.sub(r",(\s*\})", r"\1", new, count=1)
    elif pat.search(raw):
        new = pat.sub(lambda m: '%s"effortLevel": "%s"%s' % (m.group(1), value, m.group(2)),
                      raw, count=1)
    else:
        return False
    if new == raw:
        return True
    try:
        json.loads(new)                        # never leave the file unparseable
    except Exception:
        return False
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(new)
    os.replace(tmp, SETTINGS)
    return True


def _screen(guid):
    return board._osa(board.ITERM_READ_APPLESCRIPT, guid) or ""


def set_pane_effort(guid, seat, level, agent_type="", timeout=20.0):
    """Type `/effort <level>` into the pane and confirm it. Returns a status string.

    The sequence is type → Return → Return: Claude Code answers `/effort` with a
    confirmation dialog whose first option is already the level asked for, so the
    second Return accepts it. The pane's own printed line is the only acceptable
    proof — the dialog can be dismissed, the command can land in a busy queue, and
    a seat that never applied it looks identical from the outside."""
    if board._iterm_disabled():
        return "skip"
    # Retry the probe. Running at spawn time means competing with iTerm splitting a
    # pane and Claude Code booting in it, and a single osascript call that times out
    # under that load would silently skip the whole set — the failure nobody sees,
    # because this runs detached with nowhere to complain.
    probe = None
    for _ in range(3):
        probe = board._osa(board.ITERM_PROBE_APPLESCRIPT, guid)
        if probe is not None:
            break
        time.sleep(1.0)
    if probe is None:
        return "err"
    parts = (probe or "").split("\n")
    tty = parts[0].strip() if parts else ""
    title = board.pane_title(parts[1]) if len(parts) > 1 else ""
    if not tty:
        return "notfound"
    if tty not in board._claude_ttys():
        return "nosession"
    # The roster records a pane id, not a lease. A closed seat's pane can be reused by
    # an unrelated session that inherits the same id, and its title is the only thing
    # that still says who is actually sitting there. Accept the AGENT TYPE as well as
    # the handle: a fresh teammate's pane is titled with its type and only later carries
    # its handle, so matching the name alone refuses every seat at exactly the moment
    # this is supposed to run — spawn time.
    head = pane_head(title)
    want = {seat.lower()} | ({agent_type.lower()} if agent_type else set())
    # A bare `claude` title is a pane that has not identified itself yet, not a stranger.
    # Refusing on it turned a 4-second race into a permanent skip.
    if head and head not in want and head != "claude":
        return "wrongseat:" + title

    # Already there? Say so and type nothing. This is what lets the automatic set at
    # spawn coexist with a CEO that set the seat by hand a moment earlier: the late
    # arrival finds the level it wanted and leaves the deliberate choice standing.
    if board._squash("with %s effort" % level) in board._squash(_screen(guid)):
        return "already"

    cmd = "/effort " + level
    got = board._osa(board.ITERM_TYPE_APPLESCRIPT, guid, cmd)
    if got is None:
        return "err"
    body = board._squash(cmd)
    deadline = time.time() + timeout
    echoed = body in board._squash(_screen(guid))
    while not echoed and time.time() < deadline:
        time.sleep(0.2)
        echoed = body in board._squash(_screen(guid))
    if not echoed:
        return "typed"                         # in the box or not, do not press blind

    if not board._osa(board.ITERM_ENTER_APPLESCRIPT, guid):
        return "typed"
    want = board._squash("Set effort level to " + level)
    # One Return submits the command and raises the dialog; the second accepts the
    # pre-selected option. A pane that already printed the confirmation after the first
    # Return needs no second one, so check before pressing again rather than after.
    confirmed, pressed = False, False
    while time.time() < deadline:
        time.sleep(0.3)
        s = board._squash(_screen(guid))
        if want in s:
            confirmed = True
            break
        if not pressed and ("Changeeffortlevel" in s or "switchto" + level in s):
            board._osa(board.ITERM_ENTER_APPLESCRIPT, guid)
            pressed = True
    if not confirmed and not pressed:
        board._osa(board.ITERM_ENTER_APPLESCRIPT, guid)
        while time.time() < deadline:
            time.sleep(0.3)
            if want in board._squash(_screen(guid)):
                confirmed = True
                break
    return "ok" if confirmed else "unconfirmed"


def pane_head(title):
    """The identity a pane title claims, lowercased: strip a leading glyph, drop the
    parenthetical activity suffix, drop a stray quote the title can carry."""
    return re.sub(r"^[^\w]+", "", str(title or "")).split(" (")[0].strip().strip('"').lower()


def identified(parts, seat, agent_type=""):
    """True when the pane says it is this seat. A pane that has not titled itself yet —
    bare `claude`, or empty — is NOT-YET, which is a reason to wait rather than refuse."""
    head = pane_head(parts[1]) if len(parts) > 1 else ""
    want = {seat.lower()} | ({agent_type.lower()} if agent_type else set())
    return bool(head) and head in want


def wait_for_seat(seat, team=None, timeout=45.0):
    """Poll until `seat` has a pane id AND that pane answers, or give up.

    A spawn returns before its pane exists: the member lands in the config without a
    `tmuxPaneId` and the terminal takes a few seconds more. Anything firing at spawn
    time therefore has to wait, and the wait is why this runs detached instead of
    inline — nothing should hold the CEO's turn open for a settings write."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        guid, model, atype = find_seat(seat, team)
        # A pane id in the roster is not a usable pane, and a live tty is not a ready one.
        # A pane titles itself `claude` for the first seconds and only then takes the
        # seat's identity, so arriving in that window means the identity guard sees a
        # stranger and refuses a pane that is in fact ours. Wait for the pane to say who
        # it is; an unnamed pane is not-yet, not not-ours.
        if guid:
            probe = board._osa(board.ITERM_PROBE_APPLESCRIPT, guid) or ""
            parts = probe.split("\n")
            tty = parts[0].strip() if parts else ""
            if tty and tty in board._claude_ttys() and identified(parts, seat, atype):
                return guid, model, atype
        time.sleep(1.5)
    return (None, None, None)


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        sys.stderr.write(__doc__)
        return 0
    wait = "--wait" in argv
    argv = [a for a in argv if a != "--wait"]
    if not argv:
        seats = live_seats()
        if not seats:
            print("orchestrate-effort: no live seats (spawn a teammate first)")
            return 0
        print("effort is per-seat; set it AT SPAWN, before the seat has history:")
        for name, atype, model, _ in seats:
            print("  %-24s %-18s %s" % (name, atype, model))
        print("  usage: orchestrate-effort <seat> <%s>" % "|".join(LEVELS))
        return 0
    if len(argv) < 2:
        sys.stderr.write("usage: orchestrate-effort <seat> <%s>\n" % "|".join(LEVELS))
        return 1
    seat, level = argv[0], argv[1].lower()
    team = argv[2] if len(argv) > 2 else None
    if level not in LEVELS:
        sys.stderr.write("orchestrate-effort: level must be one of %s\n" % ", ".join(LEVELS))
        return 1

    guid, model, agent_type = wait_for_seat(seat, team) if wait else find_seat(seat, team)
    if not guid:
        sys.stderr.write("orchestrate-effort: no seat %r with a pane in any team config\n" % seat)
        return 1
    if model and "haiku" in model.lower():
        # Haiku has no effort ladder, so the command would be a no-op that still
        # rewrites the global default. Refusing is cheaper than repairing.
        print("%s runs haiku — no effort ladder; nothing to set" % seat)
        return 0

    before = read_global_effort()
    status = set_pane_effort(guid, seat, level, agent_type)
    if status == "already":
        print("%s is already %s" % (seat, level))
        return 0
    restored = True
    if status == "ok":
        # Restore only AFTER the pane confirms. The seat writes the global on its own
        # clock; restoring first would simply be overwritten by its write.
        if read_global_effort() != before:
            restored = write_global_effort(before)

    if status == "ok":
        was = "was %s" % before if before else "was unset"
        print("%s → %s (%s)" % (seat, level, was))
        if not restored:
            sys.stderr.write("orchestrate-effort: WARNING — global effortLevel is now %r, "
                             "not the %r it was; restore it by hand\n" % (level, before))
            return 1
        return 0

    why = {
        "skip": "iTerm is disabled (BOARD_SKIP_ITERM)",
        "err": "iTerm did not answer",
        "notfound": "the pane no longer exists — the seat is dead",
        "nosession": "the pane exists but nothing is running claude in it",
        "typed": "the command is in the pane's input box but it never echoed — "
                 "press Return there by hand",
        "unconfirmed": "the pane never printed 'Set effort level to %s' — it may be "
                       "mid-turn; retry when it is idle" % level,
    }.get(status.split(":")[0], status)
    if status.startswith("wrongseat"):
        why = "that pane now belongs to %s, not %s" % (status.split(":", 1)[1] or "?", seat)
    sys.stderr.write("orchestrate-effort: %s not set — %s\n" % (seat, why))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
