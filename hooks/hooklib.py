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
