#!/usr/bin/env python3
"""Shared helpers for this plugin's hooks — the logic every hook was duplicating
(project-root walk, transcript reading, marker-miss logging) lives once, here.
Importable from a hook (same dir) or a test (sys.path.insert). No side effects."""
import os, re, json
from datetime import datetime


def find_root(start):
    """Nearest ancestor holding .claude/orchestrate.json, else None."""
    d = os.path.abspath(start or os.getcwd())
    if os.path.isfile(d):
        d = os.path.dirname(d)
    while True:
        if os.path.exists(os.path.join(d, ".claude", "orchestrate.json")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


HEAD_LINES = 25   # the identity fields appear from line 1; cap the scan anyway


def session_agent(transcript_path):
    """(agentName, agentSetting, teamName) from the transcript head, else (None,)*3.

    A teammate's transcript stamps these on every line; the
    lead's carries none. This is the ONE reader. It used to live inside a Stop piece,
    which is exactly why the two sentinels that needed it never got it."""
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


def is_lead(transcript_path):
    """True when this session is the lead's own — or a standalone one such as a 分公司 —
    and False when it is a named teammate inside a team.

    **CEO-only output must gate on THIS, not on the event.** A teammate finishing a turn
    IS a Stop in its own session, so "only runs on Stop" excludes nobody. A field report
    (2026-07-27): a dept pane printed the stall report, a merge backlog and prompts to
    respawn agents — none of it the dept's business, and "a department can't merge to
    master" is a hard rule that only has to be obeyed once by a tired agent to break. Both
    sentinels already carried the 分公司 exclusion added on 26 July: that fix went to the
    case reported and never reached internal teammates.

    Unknown reads as LEAD, deliberately. The lead's transcript is precisely the one with
    no stamp, so treating "no stamp" as doubt would silence every sentinel for the one
    session that exists to receive them."""
    name, _, team = session_agent(transcript_path)
    return not (team and name and name != "team-lead")


def externals(cfg):
    """Lower-cased base handles of the 分公司 (branch-office) depts — orchestrate.json
    `external: ["Marketing"]`, additive beside `roster` (entries stay in roster too:
    the brief file is the branch session's identity). An external dept runs as its
    OWN session on its own account: never a teammate, never on the platform task
    lifecycle — its cards live purely on the durable #NNN."""
    out = set()
    for h in (cfg or {}).get("external") or []:
        h = re.sub(r"-\d+$", "", str(h)).strip().lower()
        if h:
            out.add(h)
    return out


def is_external(cfg, handle_or_dept):
    """True when a handle / card dept field names an external dept (base match —
    'Marketing-2' and a prose 'Marketing (branch)' both count)."""
    ext = externals(cfg)
    if not ext:
        return False
    s = str(handle_or_dept or "").strip().lower()
    base = re.sub(r"-\d+$", "", s)
    return base in ext or any(e in s for e in ext)


def last_assistant_text(transcript_path):
    """Text of the LAST assistant message in the transcript JSONL — and only that one.
    Walking further back would replay markers from an earlier, already-processed turn
    (e.g. re-raising a @BOSS ask the Boss already resolved), so a final message with
    no text blocks returns "" instead of falling through to an older message."""
    try:
        with open(transcript_path, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return ""
    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        msg = obj.get("message", obj)
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "assistant" and obj.get("type") != "assistant":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(b.get("text", "") for b in content
                             if isinstance(b, dict) and b.get("type") == "text")
        return ""
    return ""


# ---------------------------------------------------------------- TaskBoard surgery
# Shared by the task-sync hook (card birth + status mirror) and the completion hook
# (card retirement). Every mutator keys on a `**task_id:**` field that cleans to
# EXACTLY one id: real boards grow shared cards ("task_id:** 6 规格 · 7 build") and
# prose statuses — surgery on a card this code only half-understands would destroy
# the other tasks' record, so anything ambiguous is left alone (caller gets None).

def tb_clean(v):
    """Field value → semantic value: placeholders (`<...>`, `—`, backticks) → ''."""
    v = (v or "").strip().strip("`").strip()
    return "" if (not v or v.startswith("<") or v == "—") else v


def tb_card_spans(text):
    """[(start, end)] of every `### ` card block — heading line up to the next
    `##`/`###` heading or EOF. Line-scanner, not regex: card bodies are free prose."""
    spans, cur, pos = [], None, 0
    for ln in (text or "").splitlines(keepends=True):
        if ln.startswith("### ") or ln.startswith("## "):
            if cur is not None:
                spans.append((cur, pos))
                cur = None
            if ln.startswith("### "):
                cur = pos
        pos += len(ln)
    if cur is not None:
        spans.append((cur, len(text or "")))
    return spans


def tb_card_span(text, task_id):
    """Span of the card whose task_id field is exactly `task_id`, else None."""
    for a, b in tb_card_spans(text):
        m = re.search(r"\*\*task_id:\*\*\s*([^\n]*)", text[a:b])
        if m and tb_clean(m.group(1)) == str(task_id):
            return (a, b)
    return None


def tb_remove_card(text, task_id):
    """Text minus that card's whole block; None when no unambiguous match."""
    span = tb_card_span(text, task_id)
    if not span:
        return None
    a, b = span
    return text[:a] + text[b:]


def tb_set_field_at(text, span, field, value):
    """Set `- **field:** value` inside the card at `span`; a card missing the field
    line gains it right under the heading. Returns new text."""
    a, b = span
    block = text[a:b]
    new_block, n = re.subn(r"(\*\*%s:\*\*)[ \t]*[^\n]*" % re.escape(field),
                           lambda m: "%s %s" % (m.group(1), value), block, count=1)
    if not n:
        lines = block.splitlines(keepends=True)
        lines.insert(1, "- **%s:** %s\n" % (field, value))
        new_block = "".join(lines)
    return text[:a] + new_block + text[b:]


def tb_set_field(text, task_id, field, value):
    """Set a field on the exactly-matching card; None when no unambiguous match."""
    span = tb_card_span(text, task_id)
    if not span:
        return None
    return tb_set_field_at(text, span, field, value)


def tb_append_card(text, card_md):
    """Append a card at the END of the `## Active` section (before the next `##`
    heading); a board without one gains it at EOF. Returns new text."""
    card = card_md.rstrip() + "\n"
    m = re.search(r"(?m)^##\s+Active[^\n]*\n", text or "")
    if not m:
        base = (text or "").rstrip()
        return (base + "\n\n" if base else "") + "## Active\n\n" + card
    nxt = re.search(r"(?m)^##\s", text[m.end():])
    cut = m.end() + nxt.start() if nxt else len(text)
    before = text[:cut].rstrip("\n") + "\n\n"
    after = text[cut:]
    return before + card + ("\n" + after if after else "")


def tb_write(path, text):
    """Atomic replace — hooks race panes editing the board; no torn reads."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def cfg_root():
    """~/.claude, or CLAUDE_CONFIG_DIR when the user relocated it."""
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def local_office(cwd):
    """The office name from the nearest `.claude/office.json`, or '' for the CEO.

    A 分公司 (branch) runs as its OWN session in its own worktree and carries this file;
    the CEO's main checkout has none. It is the one identity signal that does not depend
    on a team config existing, which is why the CEO-team sentinels gate on it: firing
    "ASSIGN these cards or release the Frontend desk" into the Marketing branch is
    telling the wrong session to do the CEO's job."""
    d = os.path.abspath(cwd or "")
    for _ in range(12):
        try:
            with open(os.path.join(d, ".claude", "office.json"), encoding="utf-8") as f:
                return str((json.load(f) or {}).get("office") or "").strip()
        except Exception:
            pass
        if os.path.exists(os.path.join(d, ".claude", "orchestrate.json")):
            return ""                      # reached the project root with no office file
        parent = os.path.dirname(d)
        if parent == d:
            return ""
        d = parent
    return ""


def team_key(session_id, cwd=None):
    """8-hex key of the team/task store THE CALLING SESSION leads, or None.

    The platform files `~/.claude/{teams,tasks}/session-<8hex>` under whatever id the
    session carried when the store was created, and **that key does not track the
    running session_id**. Field case: a CEO's hook payload said
    `49310ed7` while the whole team roster and 79 live widget tasks sat under
    `e103ac6e`. Every hook that keyed on the current id went silently inert — the
    reconciler never reconciled, the stall sentinel read live depts as dead seats,
    and the session-start detacher saw an empty store and stripped `task_id` off
    every linked card.

    So resolve by the SESSION'S OWN WORKING DIRECTORY, not by id. The lead member's
    `cwd` inside a team config is a durable anchor that survives resume, compaction and
    re-keying. The id is tried first (cheap, and right for a fresh session); the cwd
    match answers when it isn't. Newest config wins when a project has led several teams.

    **The match is EXACT, and `cwd` must be the session's own directory — never a root
    that has been pierced to the main checkout.** These lookups are what make a hook
    lead-only, and the id-equality check they replaced was carrying that guarantee. A
    branch office and a dept worktree both live UNDER the project root, so anything
    looser than exact equality hands them the CEO's team and task store: 0.9.59 did that,
    and the capacity sentinel started ordering the Marketing branch to assign the CEO's
    cards."""
    sid = str(session_id or "")
    if sid:
        try:
            with open(os.path.join(cfg_root(), "teams", "session-%s" % sid[:8],
                                   "config.json"), encoding="utf-8") as f:
                if str(json.load(f).get("leadSessionId", "")) == sid:
                    return sid[:8]
        except Exception:
            pass
    if not cwd:
        return None
    try:
        want = os.path.realpath(cwd)
    except Exception:
        return None
    best = None
    try:
        names = os.listdir(os.path.join(cfg_root(), "teams"))
    except OSError:
        return None
    for name in names:
        if not name.startswith("session-"):
            continue
        p = os.path.join(cfg_root(), "teams", name, "config.json")
        try:
            with open(p, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            continue
        for m in cfg.get("members") or []:
            if str((m or {}).get("name") or "") != "team-lead":
                continue
            cwd = str((m or {}).get("cwd") or "")
            try:
                same = bool(cwd) and os.path.realpath(cwd) == want
            except Exception:
                same = False
            if same:
                try:
                    mt = os.path.getmtime(p)
                except OSError:
                    mt = 0
                if best is None or mt > best[0]:
                    best = (mt, name[len("session-"):])
            break
    return best[1] if best else None


def team_config(session_id, cwd=None):
    """The team config dict for the team this session LEADS, or None. See team_key."""
    key = team_key(session_id, cwd)
    if not key:
        return None
    try:
        with open(os.path.join(cfg_root(), "teams", "session-%s" % key,
                               "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def tasks_dir(session_id, cwd=None):
    """Path to the platform task store this session's widget writes, or None.

    Prefers the team-anchored key, falls back to the raw id so a solo lead with no
    teammates still resolves. A store holding no task JSON loses to one that does —
    an empty dir is exactly what a mis-keyed lookup looks like, and callers that
    mass-edit on absence (session_start's detacher) must never be handed one by
    mistake. Returns a path that may not exist; callers check."""
    cands = []
    key = team_key(session_id, cwd)
    if key:
        cands.append(key)
    sid = str(session_id or "")
    if sid and sid[:8] not in cands:
        cands.append(sid[:8])
    fallback = None
    for k in cands:
        p = os.path.join(cfg_root(), "tasks", "session-%s" % k)
        try:
            if any(n.endswith(".json") for n in os.listdir(p)):
                return p
        except OSError:
            continue
        if fallback is None:
            fallback = p
    return fallback


# ---------------------------------------------------------------- context gauge
# Read a session's real context usage from its transcript's LAST assistant `usage`
# — the number /context reports. NEVER estimate from statusline or byte counts:
# compact-sense's statusline claimed 90% when /context said 51% (2026-07-25).

CONTEXT_TAIL_BYTES = 262_144   # a turn's last assistant entry sits well inside 256KB
WINDOWS = (("claude-haiku", 200_000), ("claude-3", 200_000))
DEFAULT_WINDOW = 1_000_000     # every current non-haiku model (fable/opus/sonnet 5 gen)


def transcripts_dir(cwd):
    """The platform's per-project transcript directory for a working directory.
    Path munge is `/` and `.` → `-` (field-verified against ~/.claude/projects/)."""
    munged = re.sub(r"[/.]", "-", os.path.abspath(cwd or ""))
    return os.path.join(cfg_root(), "projects", munged)


def context_usage(transcript_path):
    """(context_tokens, model_id) from the last assistant entry carrying `usage`,
    else (None, ""). context = input + cache_read + cache_creation of the latest
    API call — output lands in the next call's input, so summing it would double-
    count. Reads only the file tail: a lead transcript can run to hundreds of MB."""
    try:
        with open(transcript_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - CONTEXT_TAIL_BYTES))
            tail = f.read().decode("utf-8", "ignore")
    except Exception:
        return None, ""
    for line in reversed(tail.splitlines()):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        msg = obj.get("message")
        if obj.get("type") != "assistant" or not isinstance(msg, dict):
            continue
        u = msg.get("usage")
        if not isinstance(u, dict):
            continue
        try:
            tokens = (int(u.get("input_tokens") or 0)
                      + int(u.get("cache_read_input_tokens") or 0)
                      + int(u.get("cache_creation_input_tokens") or 0))
        except Exception:
            continue
        if tokens > 0:
            return tokens, str(msg.get("model") or "")
    return None, ""


def model_window(model, overrides=None):
    """Context window (tokens) for a model id, longest-prefix match. `overrides`
    ({prefix: tokens}, e.g. orchestrate.json `context_windows`) wins over the
    built-ins. Unknown models read as 1M — the quiet failure mode (a 200k model
    misread as 1M warns late, which is today's behaviour; a 1M model misread as
    200k nags from 10%, which is noise they have to see)."""
    m = str(model or "").lower()
    for prefix, w in sorted((overrides or {}).items(), key=lambda kv: -len(kv[0])):
        try:
            if m.startswith(str(prefix).lower()):
                return int(w)
        except Exception:
            continue
    for prefix, w in WINDOWS:
        if m.startswith(prefix):
            return w
    return DEFAULT_WINDOW


def log_marker_misses(root, channel, misses):
    """Append marker-shaped lines that didn't parse to .claude/marker-misses.log.
    The marker channel is fail-open end to end, so without this a malformed
    @BOSS/@CANON line vanishes with no trace anywhere. Never raises."""
    if not misses:
        return
    try:
        path = os.path.join(root, ".claude", "marker-misses.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        with open(path, "a", encoding="utf-8") as f:
            for m in misses:
                f.write("%s [%s] %s\n" % (stamp, channel, m.strip()))
    except Exception:
        pass
