#!/usr/bin/env python3
"""Idle-nudge (Stop / TeammateIdle, via stop_dispatch) — mechanises the report half of
报告即停: a dept teammate about to go idle with unreported work gets ONE stderr reminder
to send its 4-line report. Zero tokens on every silent path; the only token-bearing path
is the nudge itself (one short feedback line + one extra teammate turn), which replaces
the costlier CEO notice→prompt→wait round-trip when a dept finishes silently.

Identity is read from the transcript head, NOT from hook metadata: teammate sessions
stamp every JSONL line with agentName / agentSetting / teamName (field-verified
2026-07-15 on a live team; the TeammateIdle input schema is undocumented and a request
to add teammate identity to it was closed "not planned"). The lead ("team-lead"), the
Registrar (mechanical proxy — its whole protocol IS SendMessage) and plain sessions
never match, so the hook is a no-op everywhere but dept panes of an armed project.

Nudge condition: work tool calls (Edit/Write/NotebookEdit/Bash/Agent) appear AFTER the
last SendMessage(to:"team-lead") — i.e. something changed that the CEO never heard
about. Suppressed while `.claude/boss-in-pane.json` marks this dept (the Boss is
iterating in the pane — orchestrate-pane start/end), when the turn ends on a pending
@BOSS[...] board ask (idling on the Boss is legitimate), and after one nudge per
report-epoch (the cap is keyed on the last-report offset: a teammate that ignores the
reminder is nudged once, not looped — the CEO's manual prompt stays the fallback).
Fail-open everywhere: any parse/IO doubt → no nudge (never risk a block loop)."""
import os, re, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
try:
    import hooklib
except Exception:
    hooklib = None
try:
    import board  # main_checkout only
except Exception:
    board = None

WORK_TOOLS = {"Edit", "Write", "NotebookEdit", "Bash", "Agent"}
HEAD_LINES = 25   # identity fields appear from line 1; cap the scan anyway
NUDGE = ('You are going idle with unreported work. If a work leg (or a Boss pane '
         'session) just ended, send your 4-line report now — SendMessage(to:"team-lead", '
         'summary:"…", message:"…") — plain text is invisible to the CEO. If you are '
         'blocked, report blocked instead. (One-time reminder.)')


def identity(transcript_path):
    """(agentName, agentSetting, teamName) from the transcript head, else (None,)*3."""
    try:
        with open(transcript_path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= HEAD_LINES:
                    break
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("agentName") or d.get("teamName"):
                    return d.get("agentName"), d.get("agentSetting"), d.get("teamName")
    except Exception:
        pass
    return None, None, None


def scan(transcript_path):
    """(last_report_line, last_work_line) — line indexes of the newest
    SendMessage(to:"team-lead") and the newest work tool_use; -1 when absent."""
    rep = work = -1
    try:
        with open(transcript_path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if '"tool_use"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("type") != "assistant":
                    continue
                content = (d.get("message") or {}).get("content") or []
                for b in content:
                    if not isinstance(b, dict) or b.get("type") != "tool_use":
                        continue
                    name = b.get("name", "")
                    if name == "SendMessage" and (b.get("input") or {}).get("to") == "team-lead":
                        rep = i
                    elif name in WORK_TOOLS:
                        work = i
    except Exception:
        return -1, -1
    return rep, work


def run(data, text):
    """Dispatcher contract: return the block reason (str) to nudge, else None."""
    if data.get("hook_event_name") not in ("Stop", "TeammateIdle"):
        return None  # SubagentStop = staff finishing mid-task; a nudge there is noise
    if data.get("stop_hook_active"):
        return None  # already continuing from a stop-hook block — never stack
    transcript = data.get("transcript_path") or ""
    name, setting, team = identity(transcript)
    if not team or not name or name == "team-lead":
        return None
    if (setting or name).startswith("Registrar"):
        return None
    if hooklib is None:
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
    try:  # boss-in-pane mute — match spawn name, its unsuffixed base, or the agent type
        pane = json.load(open(os.path.join(root, ".claude", "boss-in-pane.json"),
                              encoding="utf-8"))
        base = re.sub(r"-\d+$", "", name)
        if any(k in pane for k in {name, base, setting or ""} if k):
            return None
    except Exception:
        pass
    if "@BOSS[" in (text or ""):
        return None
    rep, work = scan(transcript)
    if work < 0 or work < rep:
        return None
    state_dir = os.path.join(root, ".claude", "idle-nudges")
    state_file = os.path.join(state_dir, "%s.json" % (data.get("session_id") or "unknown"))
    sig = str(rep)  # one nudge per report-epoch, however much work piles up after it
    try:
        if json.load(open(state_file, encoding="utf-8")).get("sig") == sig:
            return None
    except Exception:
        pass
    try:
        os.makedirs(state_dir, exist_ok=True)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump({"sig": sig, "dept": name}, f)
    except Exception:
        return None  # can't record the cap → don't risk repeat nudges
    return NUDGE
