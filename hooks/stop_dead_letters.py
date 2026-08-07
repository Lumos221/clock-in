#!/usr/bin/env python3
"""Dead-letter sentinel (Stop, lead-only, via stop_dispatch) — messages addressed to a
handle nobody staffs.

A teammate's mailbox is a file named for the EXACT handle: `<team>/inboxes/<name>.json`.
Address `Backend-IO` when the live seat is `Backend-IO-1049` and the message is written
to `Backend-IO.json`, where it sits forever. Nothing reads it, nothing expires it, and
NOTHING SAYS SO — the send returns a receipt, so the sender believes it landed.

Field state when this was written: **117 such messages** across one machine's teams, 52
of them in one live team, every one a `task_assignment` carrying a full card spec. Those
dispatches reached nobody and no one knew. The rule was already written down —
`reference/task-widget.md`: "ASSIGN to the exact live handle: a suffixed respawn
(`QA-2`) cannot claim `QA`'s card" — which is the point: a rule with nothing checking it
is a rule that gets followed until the day it doesn't, and then fails in silence.

Mechanical and exact, so it can afford to be loud: an inbox file whose name is not in the
team config's `members[]`, holding at least one message. No judgement, no heuristic, no
way to be wrong about it. What the CEO does about it IS judgement — re-send to the live
handle, or decide the message is stale — so this reports and never blocks the work.

Lead-only: the CEO is the one who can re-address. One nudge per state (the signature is
the set of orphaned handles and their counts), so a mailbox that stays orphaned is
mentioned once, not every turn. Fail-open everywhere."""
import os, re, sys, json, glob, hashlib, time

SUFFIX = re.compile(r"-\d+$")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    import hooklib
except Exception:
    hooklib = None


def dead_letters(session_id, cwd=None):
    """[(handle, count, age_days, misaddressed)] for inboxes nobody staffs.

    `misaddressed` = a live seat wears this handle plus a suffix, so the message was
    meant for someone who is right there and never got it. Sorted with those first.

    `members[]` is the roster the platform itself maintains, so a name absent from it is
    a name no seat answers to — including a seat that shut down cleanly after the message
    arrived. That case is still a dead letter: the message was never read."""
    if hooklib is None:
        return []
    cfg = hooklib.team_config(session_id, cwd)
    if not cfg:
        return []
    live = {str(m.get("name")) for m in (cfg.get("members") or []) if m.get("name")}
    if not live:
        return []                      # an empty roster proves nothing about addressing
    key = hooklib.team_key(session_id, cwd)
    if not key:
        return []
    # team_key returns the BARE 8-hex; the directory carries the `session-` prefix, the
    # same shape team_config resolves. Getting this wrong finds nothing and looks clean.
    box = os.path.join(hooklib.cfg_root(), "teams", "session-%s" % key, "inboxes")
    out = []
    for p in sorted(glob.glob(os.path.join(box, "*.json"))):
        who = os.path.basename(p)[:-5]
        if who in live:
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
            msgs = d if isinstance(d, list) else (d.get("messages") or [])
            n = len(msgs)
            if not n:
                continue
            age = (time.time() - os.path.getmtime(p)) / 86400.0
        except Exception:
            continue
        # Two very different letters land in the same pile, and only one is urgent.
        # `Frontend` while `Frontend-1096` is live = a mis-address happening NOW, and the
        # live seat is sitting there not getting its card. `Backend-IO-1025` long retired
        # = a message that arrived after its seat went; nothing to re-send it to.
        # Only a BARE handle is a mis-address. `Backend-IO` while `Backend-IO-1049` is
        # live means the sender dropped the suffix. `Backend-IO-1025` is not that — it is
        # a DIFFERENT seat that retired, and sharing a base with a live one says nothing.
        misaddressed = (not SUFFIX.search(who)
                        and any(SUFFIX.sub("", m) == who and m != who for m in live))
        out.append((who, n, age, misaddressed))
    return sorted(out, key=lambda r: (not r[3], -r[1]))


def run(data, text=None):
    """Dispatcher contract: return the nudge (str), else None."""
    if hooklib is None or data.get("hook_event_name") not in ("Stop", None):
        return None
    root = hooklib.find_root(data.get("cwd") or "")
    if not root:
        return None
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
        if not cfg.get("active"):
            return None
    except Exception:
        return None
    if not hooklib.is_lead(data.get("transcript_path") or ""):
        return None                    # only the CEO can re-address a dispatch
    if hooklib.local_office(data.get("cwd") or ""):
        return None                    # a 分公司 does not run the CEO's mailroom

    dead = dead_letters(data.get("session_id"), data.get("cwd") or "")
    if not dead:
        return None
    sig = hashlib.md5(json.dumps([[w, n] for w, n, _, _ in dead]).encode()).hexdigest()
    state = os.path.join(root, ".claude", "dead-letter-state")
    try:
        if open(state, encoding="utf-8").read().strip() == sig:
            return None                # already said, and nothing has changed since
    except Exception:
        pass
    try:
        os.makedirs(os.path.dirname(state), exist_ok=True)
        with open(state, "w", encoding="utf-8") as f:
            f.write(sig)
    except Exception:
        pass

    bad = [r for r in dead if r[3]]
    old = [r for r in dead if not r[3]]
    parts = []
    if bad:
        parts.append("**%d to a seat live under a suffix** — %s. Never received: re-send "
                     "to the exact handle, and ASSIGN to it too so the widget "
                     "notification lands."
                     % (sum(n for _, n, _, _ in bad),
                        "; ".join("`%s` → %d msg%s" % (w, n, "" if n == 1 else "s")
                                  for w, n, _, _ in bad[:6])))
    if old:
        parts.append("%d more sit in boxes of seats that have since gone (%s) — nothing "
                     "to re-send them to; read them before assuming you know what they "
                     "said."
                     % (sum(n for _, n, _, _ in old),
                        ", ".join("%s %dd" % (w, int(a)) for w, _, a, _ in old[:4])))
    return ("📮 DEAD LETTERS — a mailbox is named for the EXACT handle, so `Frontend` "
            "reaches nothing when the seat is `Frontend-1096`, and the send returns a "
            "receipt either way. " + " ".join(parts))
