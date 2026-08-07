#!/usr/bin/env python3
"""Seat-context sentinel (Stop, via stop_dispatch — LEAD session only): the CEO gets
the context gauge no one else can watch.

Field case (2026-07-29): teammates ground until PASSIVE auto-compact and the work
degrades — a bloated seat re-proposes its own abandoned approaches, and the compact
summary is lossy. The gauge was invisible to everyone who could act: a teammate
cannot see its own context %, the panes' statusline is only visible to the Boss (who
cannot watch four panes), and doctrine said "ask the Boss to /compact the pane" —
a rule with no mechanical backstop, whose violation announced itself only as the
auto-compact it existed to prevent.

So at each lead turn end, read every live teammate's transcript (the platform stamps
`agentName` from line 1 — hooklib.session_agent) and compute real usage from the last
assistant `usage` fields — the number /context reports, never the statusline estimate
(field-caught claiming 90% when /context said 51%). Two thresholds of the model's
window:

  warn (50%) — plan the boundary: finish the card in hand, don't queue the next one
               onto this seat; the next card gets a fresh `<Dept>-<NNN>`.
  high (70%) — rotate at the current card's boundary: checkpoint (commit WIP, write
               docs/handover-<Dept>.md — state · tried-and-abandoned · next step),
               retire the seat, spawn fresh for what remains.

One nudge per seat per threshold: state records each seat's current bucket and only
an INCREASE speaks. The record follows decreases silently, so a respawned seat (same
handle, fresh transcript) resets and earns its own future nudges. The Registrar is
exempt — mechanical proxy, nothing of quality to lose. Widget-less sessions and
分公司 offices are out of scope, same gates as stop_capacity. Fail-open everywhere."""
import os, json, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    import hooklib
except Exception:
    hooklib = None
try:
    import board  # main_checkout only
except Exception:
    board = None

WARN, HIGH = 0.50, 0.70
RANK = {None: 0, "": 0, "warn": 1, "high": 2}
STALE_S = 3600     # a candidate transcript may predate joinedAt by this much slack


def _members(team):
    """Live gauge-worthy members: named teammates minus the Registrar."""
    out = []
    for m in team.get("members", []):
        if not isinstance(m, dict):
            continue
        name = str(m.get("name", ""))
        if not name or name == "team-lead":
            continue
        if name.lower().startswith("registrar"):
            continue
        out.append(m)
    return out


def find_transcript(member, fallback_cwd, own_transcript):
    """The teammate's transcript path, else None. Teammate transcripts live in the
    platform's per-project dir and stamp `agentName` on every line; match on that,
    newest first, ignoring files older than the member's joinedAt (minus slack) and
    the lead's own transcript."""
    name = str(member.get("name", ""))
    tdir = hooklib.transcripts_dir(member.get("cwd") or fallback_cwd)
    try:
        joined = float(member.get("joinedAt") or 0) / 1000.0
    except Exception:
        joined = 0.0
    cands = []
    try:
        for fn in os.listdir(tdir):
            if not fn.endswith(".jsonl"):
                continue
            p = os.path.join(tdir, fn)
            if own_transcript and os.path.abspath(p) == os.path.abspath(own_transcript):
                continue
            try:
                mtime = os.path.getmtime(p)
            except Exception:
                continue
            if joined and mtime < joined - STALE_S:
                continue
            cands.append((mtime, p))
    except Exception:
        return None
    for _, p in sorted(cands, reverse=True):
        agent, _, _ = hooklib.session_agent(p)
        if agent == name:
            return p
    return None


def _fmt_tokens(n):
    return "%dk" % round(n / 1000.0)


def run(data, text):
    """Dispatcher contract: return the block reason (str) to nudge, else None."""
    if data.get("hook_event_name") != "Stop":
        return None
    if data.get("stop_hook_active"):
        return None
    if hooklib is None:
        return None
    if not hooklib.is_lead(data.get("transcript_path") or ""):
        return None
    root = hooklib.find_root(data.get("cwd") or "")
    if not root:
        return None
    if hooklib.local_office(data.get("cwd") or ""):
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
    team = hooklib.team_config(str(data.get("session_id") or ""),
                               data.get("cwd") or "")
    if not team:
        return None

    try:
        warn = float(cfg.get("seat_ctx_warn", WARN))
        high = float(cfg.get("seat_ctx_high", HIGH))
    except Exception:
        warn, high = WARN, HIGH
    windows = cfg.get("context_windows") if isinstance(cfg.get("context_windows"),
                                                       dict) else None

    state_path = os.path.join(root, ".claude", "seat-context-state")
    try:
        state = json.load(open(state_path, encoding="utf-8"))
        if not isinstance(state, dict):
            state = {}
    except Exception:
        state = {}

    members = _members(team)
    live_keys = set()
    crossings, new_state = [], {}
    for m in members:
        name = str(m.get("name", ""))
        key = str(m.get("agentId") or name)
        live_keys.add(key)
        path = find_transcript(m, data.get("cwd") or "",
                               data.get("transcript_path") or "")
        if not path:
            new_state[key] = state.get(key, "")
            continue
        tokens, model = hooklib.context_usage(path)
        if not tokens:
            new_state[key] = state.get(key, "")
            continue
        window = hooklib.model_window(model, windows)
        pct = tokens / float(window)
        bucket = "high" if pct >= high else "warn" if pct >= warn else ""
        new_state[key] = bucket
        if RANK.get(bucket, 0) > RANK.get(state.get(key), 0):
            crossings.append((name, bucket, pct, tokens, window))

    # a departed seat's record goes with it; same handle respawned starts clean
    if not crossings:
        if new_state != {k: v for k, v in state.items() if k in live_keys}:
            try:
                with open(state_path, "w", encoding="utf-8") as f:
                    json.dump(new_state, f)
            except Exception:
                pass
        return None

    parts = []
    for name, bucket, pct, tokens, window in sorted(
            crossings, key=lambda c: -RANK.get(c[1], 0)):
        gauge = "%s at %d%% (%s/%s ctx)" % (name, round(pct * 100),
                                            _fmt_tokens(tokens), _fmt_tokens(window))
        if bucket == "high":
            parts.append(
                gauge + " — rotate at the CURRENT card's boundary: have it checkpoint "
                "(commit WIP + write docs/handover-%s.md: state · tried-and-abandoned "
                "· next step), retire it, spawn a fresh '<Dept>-<NNN>' that reads the "
                "handover + card. Queue NOTHING new onto it" % name)
        else:
            parts.append(
                gauge + " — plan the boundary: let it finish the card in hand, but "
                "give the NEXT card a fresh seat instead of queueing onto this one")

    try:
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(new_state, f)
    except Exception:
        return None  # can't record → never risk a nudge loop
    return ("⏳ seat context: " + " · ".join(parts) +
            " (One nudge per seat per threshold; crossing the next one re-arms.)")


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    ret = run(data, None)
    if isinstance(ret, str) and ret:
        sys.stderr.write(ret)
        sys.exit(2)


if __name__ == "__main__":
    main()
