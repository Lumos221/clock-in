#!/usr/bin/env python3
"""PreToolUse hook (Agent) — two guards on teammate spawns. exit 2 = block (stderr
fed to the model); exit 0 = allow. Fail-open (any doubt → allow).

1) Spawn-collision: block spawning a teammate whose base handle already has a LIVE
   member in this session's team.
2) Brain-regime tier: in a Fable-CEO session, block a NAMED teammate spawn carrying
   no `model:` param — the roster's opus pin is parity-only; the brain regime spawns
   depts at an explicit tier (default sonnet; a Boss-designated tier, e.g. Marketing
   at Fable, passes just as well — only the SILENT omission is blocked). PreToolUse
   carries no model field (docs), so the session model comes from the transcript's
   last assistant `message.model` stamp (field-verified 2026-07-18).

Field case (refcheck, 2026-07-15): the CEO released an opus dept and respawned its
sonnet replacement in the same breath. A shutdown_request is a polite message a busy
teammate cannot process until its turn ends — the predecessor was 6 minutes into a
thinking turn — so the name was still held, the harness minted `Backend-Engine-2`,
and the released pane kept burning opus on a reassigned task. This guard fires at the
moment that mistake is made, BEFORE the duplicate exists.

Only teammate spawns are judged (an `Agent` call carrying `name:`); one-shots pass
untouched. Liveness comes from the team config's members[].isActive — internal,
undocumented state, hence read-only and fail-open on any schema surprise."""
import sys, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    import hooklib
except Exception:
    hooklib = None

SUFFIX = re.compile(r"-\d+$")


def base(handle):
    return SUFFIX.sub("", handle or "")


def team_config(session_id):
    """This session's team config dict, or None. Dir is keyed by the LEAD session's
    first 8 hex — a config found via OUR id whose leadSessionId matches proves this
    session is the lead (teammates and unrelated sessions never match)."""
    if not session_id:
        return None
    root = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    path = os.path.join(root, "teams", "session-%s" % session_id[:8], "config.json")
    try:
        cfg = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    if str(cfg.get("leadSessionId", "")) != str(session_id):
        return None
    return cfg


def live_collision(cfg, name):
    """The live member whose base handle collides with `name`, or None."""
    want = base(name).lower()
    if not want:
        return None
    for m in cfg.get("members", []):
        if not isinstance(m, dict):
            continue
        mname = m.get("name", "")
        if mname == "team-lead":
            continue
        if str(m.get("isActive")).lower() != "true":
            continue
        if base(mname).lower() == want or base(str(m.get("agentType", ""))).lower() == want:
            return mname
    return None


def session_model(transcript_path):
    """The transcript's most recent assistant `message.model` stamp, or "".
    Tail-read (last 64 KB) — transcripts grow to MBs and the stamp is on every
    assistant line; a truncated first line simply fails json and is skipped."""
    try:
        with open(transcript_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 65536))
            chunk = f.read().decode("utf-8", "replace")
    except Exception:
        return ""
    for line in reversed(chunk.splitlines()):
        try:
            d = json.loads(line)
        except Exception:
            continue
        m = (d.get("message") or {}).get("model")
        if m:
            return str(m)
    return ""


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
    if data.get("tool_name", "") != "Agent":
        return
    name = (data.get("tool_input", {}) or {}).get("name", "")
    if not name or name == "team-lead":
        return  # one-shot subagent — no collision possible
    if not active(hooklib.find_root(data.get("cwd") or os.getcwd())):
        return
    cfg = team_config(data.get("session_id"))
    if cfg is None:
        return
    hit = live_collision(cfg, name)
    if hit:
        sys.stderr.write(
            "⛔ spawn-collision: %s already has a LIVE teammate (%s) — likely mid-turn; "
            "a shutdown request is processed only when its turn ends. Wait for its "
            "termination, or re-task it via SendMessage instead. If the replacement "
            "truly cannot wait: spawn a suffixed name deliberately and treat the "
            "predecessor's output as void (release it on sight)." % (base(name), hit))
        sys.exit(2)
    if not (data.get("tool_input", {}) or {}).get("model"):
        if session_model(data.get("transcript_path") or "").startswith("claude-fable"):
            sys.stderr.write(
                "⛔ brain-regime tier guard: a Fable CEO spawns dept teammates with an "
                "EXPLICIT model — re-issue this spawn with model:\"sonnet\" (the brain-"
                "regime default; the roster's opus pin is parity-only), or the tier the "
                "Boss designated for this dept (e.g. model:\"fable\"). Any explicit tier "
                "passes; only the silent omission is blocked.")
            sys.exit(2)
    return


if __name__ == "__main__":
    main()
