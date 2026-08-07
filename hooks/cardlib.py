#!/usr/bin/env python3
"""Per-card board store (0.9.28) — the truth moved out of the single TaskBoard.md
into one markdown note per card (docs/board/<id>-<slug>.md, flat YAML frontmatter +
free prose body), so two sessions (CEO + a 分公司 branch office) edit disjoint files
instead of racing one, Obsidian Bases can view the board as a database, and every
card carries its durable #NNN from birth. TaskBoard.md remains as a GENERATED digest
(its `## Active` section is machine-rewritten from the cards; everything else —
title, notes, the SHIPPED block update_shipped maintains — is preserved verbatim),
so every existing reader (board.parse_taskboard, capacity's card_dept, the Boss's
glance) keeps working unchanged. Writers go through here.

Frontmatter is a deliberate YAML subset: flat `key: value` scalars only, values
double-quoted on write when they need it, quotes stripped on read. Obsidian edits
properties in place and Bases keeps scalars scalar, so round-trips hold; unknown
keys a human (or Obsidian) adds are preserved verbatim on rewrite. task_id keeps
the legacy exactly-one-id contract: prose/multi-id values ("6 规格 · 7 build") are
matched by nobody and surgically touched by nobody.

Layout: <board>/ holds the active cards; <board>/done/ the completed (moved there
by the completion hook, gaining shipped+sha); <board>/archive/ the cancelled and
the migrated tombstones. Non-card files (mail/, *.base) are ignored by load().
Migration off a legacy board is LAZY — ensure_store() at any writer's entry: cards
split out via the same span-scanner the old surgery used, headings' durable #NNN
kept as the id, unnumbered cards minted the next free number, tombstones (struck
headings — parse_taskboard's TOMB_RE) retired straight to archive/. Built into a
tmp dir and os.rename'd in, so a racing hook sees either no store or a whole one.
No side effects at import; callers stay fail-open."""
import os, re, json
from datetime import datetime

FIELDS = ("dept", "task_id", "status", "since", "priority", "blocked_on", "what",
          "done-when", "artifacts")
# since: when the card ENTERED its current status. The panel's age chip used to come
# from the card FILE's mtime, which any touch resets — a hygiene sweep, a digest regen,
# a field edit — so it answered "when was this file last written", never "how long has
# this been sitting at the L2 gate". Stamped on the status transition instead, so the
# number means time-in-stage.
# priority: P0 urgent · P1 critical · P2 important · P3 nice-to-have · unset = normal
# (the vocabulary the dispatch doctrine hands the CEO — see PRIORITY_RE). Lexical sort
# works by construction — P0 < P1 < P2 < P3 < the — placeholder — so Bases and the panel
# sort it with no mapping table. Boss/CEO-owned; depts never touch it.
EMPTY = "—"
CARD_RE = re.compile(r"^(\d+)-.*\.md$")
TOMB_RE = re.compile(r"~~|\b(?:SHIPPED|RETIRED)\b|card closes")  # = board.TOMB_RE


def clean(v):
    """Field value → semantic value ('' for placeholders) — tb_clean's contract."""
    v = (v or "").strip().strip("`").strip()
    return "" if (not v or v.startswith("<") or v == EMPTY) else v


def board_dir(root, cfg):
    return os.path.join(root, (cfg or {}).get("board", "docs/board"))


# ---------------------------------------------------------------- card file I/O

def _quote(v):
    v = "" if v is None else str(v)
    if v == "" or re.search(r'[:#"\[\]{}\n]|^[\s\'>&*!|%@`-]|\s$|^\s', v):
        return '"%s"' % v.replace("\\", "\\\\").replace('"', '\\"')
    return v


def _unquote(v):
    v = (v or "").strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        body = v[1:-1]
        if v[0] == '"':
            body = body.replace('\\"', '"').replace("\\\\", "\\")
        return body
    return v


def parse_card(text):
    """(meta, extras, body) — meta: known keys (str values); extras: verbatim
    frontmatter lines for keys we don't own (Obsidian/human additions survive a
    rewrite); body: everything after the closing fence. None when no frontmatter."""
    if not (text or "").startswith("---"):
        return None
    close = text.find("\n---", 3)
    if close < 0:
        return None
    body_at = text.find("\n", close + 1)
    body = text[body_at + 1:] if body_at >= 0 else ""
    meta, extras = {}, []
    known = set(FIELDS) | {"id", "name", "shipped", "sha"}
    for line in text[text.index("\n") + 1:close + 1].splitlines():
        m = re.match(r"([A-Za-z][\w-]*):(.*)$", line)
        if m and m.group(1) in known:
            meta[m.group(1)] = _unquote(m.group(2))
        elif line.strip():
            extras.append(line)
    return meta, extras, body


def render_card(meta, extras=(), body=""):
    lines = ["---"]
    for k in ("id", "name") + FIELDS + ("shipped", "sha"):
        if k in meta:
            v = meta[k]
            lines.append("%s: %s" % (k, v if k == "id" else _quote(v)))
    lines.extend(extras)
    lines.append("---")
    out = "\n".join(lines) + "\n"
    return out + (body if body.startswith("\n") or not body else "\n" + body)


def _atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def load(bdir, sub=""):
    """Cards in <bdir>/<sub> (sorted by id): dicts of meta + _path/_extras/_body.
    Unparseable or non-card files are skipped, never guessed at."""
    d = os.path.join(bdir, sub) if sub else bdir
    out = []
    try:
        names = os.listdir(d)
    except OSError:
        return out
    for fn in names:
        if not CARD_RE.match(fn):
            continue
        path = os.path.join(d, fn)
        try:
            with open(path, encoding="utf-8") as fh:
                parsed = parse_card(fh.read())
        except OSError:
            continue
        if not parsed:
            continue
        meta, extras, body = parsed
        card = dict(meta)
        card["_path"], card["_extras"], card["_body"] = path, extras, body
        try:
            card["id"] = int(meta.get("id") or CARD_RE.match(fn).group(1))
        except ValueError:
            continue
        out.append(card)
    return sorted(out, key=lambda c: c["id"])


def save(card):
    meta = {k: v for k, v in card.items() if not k.startswith("_")}
    _atomic(card["_path"], render_card(meta, card.get("_extras", ()), card.get("_body", "")))


def now_stamp():
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def _stamp_transition(card, updates):
    """A status change re-stamps `since`. Every hook writes fields through here, so the
    machine paths are exact; a hand edit (Obsidian, a dept editing its own card) is
    healed at turn end by stamp_since."""
    if "status" in updates and "since" not in updates:
        if clean(updates.get("status")) != clean(card.get("status")):
            updates["since"] = now_stamp()
    return updates


def set_fields(card, **updates):
    card.update(_stamp_transition(card, updates))
    save(card)


def retire(card, bdir, sub, **updates):
    """Move a card to <bdir>/<sub>/ (done | archive) with field updates; collision
    gains a timestamp suffix, nothing is ever overwritten.

    **Retirement SURRENDERS the platform task_id**, and that is not tidiness. Those ids
    are small integers the platform restarts every session, so it hands out `115` again
    and again; a retired card that keeps one still answers to it forever. Months of
    those turn every id-keyed path ambiguous — `find_task` returns whichever holder it
    reached first, so a completion stamps the wrong card, the recycled-id detach clears
    the wrong card, and a review marker written for a long-dead card attaches to
    whatever wears its number today. Field state when this was found: ~100 duplicated
    ids in one project's store, 14 of them shared between a LIVE card and a retired one.
    The durable `#NNN` is the permanent identity (see `board.l2_verdict`); the platform
    id is already written into the BACKLOG row at completion, so nothing is lost by
    letting it go here."""
    updates.setdefault("task_id", EMPTY)
    card.update(_stamp_transition(card, updates))
    dest_dir = os.path.join(bdir, sub)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(card["_path"]))
    if os.path.exists(dest):
        base_, ext = os.path.splitext(dest)
        dest = "%s-%s%s" % (base_, datetime.now().strftime("%Y%m%d-%H%M%S"), ext)
    src = card["_path"]
    card["_path"] = dest
    save(card)
    try:
        os.remove(src)
    except OSError:
        pass


def slugify(name, cap=40):
    s = re.sub(r"[\s·—–]+", "-", (name or "").strip())
    s = re.sub(r'[\\/:*?"<>|#^\[\]]+', "", s)
    s = re.sub(r"-{2,}", "-", s).strip("-.")
    return s[:cap].rstrip("-.") or "card"


def claimed_ids(bdir):
    """Every durable id any card wears — active, done, archive. Done/archived cards
    keep their number forever; recycling one would fork the Boss's referent."""
    ids = set()
    for sub in ("", "done", "archive"):
        for c in load(bdir, sub):
            ids.add(c["id"])
    return ids


def new_card(bdir, name, want_id=None, body="", **fields):
    """Birth a card, minting the durable id: want_id when free, else the next free
    number. O_EXCL claims the filename, so two sessions minting concurrently can't
    silently share a number — the loser re-mints one up."""
    os.makedirs(bdir, exist_ok=True)
    taken = claimed_ids(bdir)
    cid = want_id if (want_id and want_id not in taken) else max(taken, default=0) + 1
    while True:
        path = os.path.join(bdir, "%d-%s.md" % (cid, slugify(name)))
        meta = {"id": cid, "name": name}
        for k in FIELDS:
            meta[k] = fields.get(k, "todo" if k == "status"
                                 else now_stamp() if k == "since" else EMPTY)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            taken.add(cid)
            cid = max(taken) + 1
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(render_card(meta, (), body))
        card = dict(meta)
        card["_path"], card["_extras"], card["_body"] = path, [], body
        return card


def find_task(cards, task_id):
    """The card whose task_id is EXACTLY this one id, else None (legacy contract:
    multi-id/prose values match nobody)."""
    for c in cards:
        if clean(c.get("task_id", "")) == str(task_id):
            return c
    return None


# ------------------------------------------------------------- hygiene sweeps

CANON_RE = re.compile(r"\b(todo|doing|review|blocked|done)\b", re.I)
# ship-speak and start-speak the sessions keep writing into status: despite
# doctrine — Bases groups each essay verbatim, parse_taskboard finds no keyword
# and misfiles the card under Todo
SYNONYMS = {"merged": "done", "complete": "done", "completed": "done",
            "shipped": "done", "closed": "done", "landed": "done",
            "pass": "done", "passed": "done",
            "active": "doing", "wip": "doing", "started": "doing",
            "in-progress": "doing", "in_progress": "doing",
            "parked": "todo", "pending": "todo", "queued": "todo",
            "waiting": "blocked"}
# P0 urgent · P1 critical · P2 important · P3 nice-to-have · unset = normal. The dispatch
# doctrine has said P0–P3 all along while this said P0–P2, so a CEO writing the level it
# was TOLD to write had it silently erased hours later by the sweep below — nine times on
# one board, including a card the Boss ruled P3 by name.
PRIORITY_RE = re.compile(r"P[0-3]$")

# A level with an explanation after it (`P0 (process-debt closure — …)`) is a correct
# level, not junk, and wiping the whole field DEMOTED it — that card lost a real P0. Keep
# the level, move the prose to the 状态注 note, because the field has to stay exactly
# `P<n>` for the panel's `^P\d$` sort and pill to see it at all.
PRIORITY_LEAD_RE = re.compile(r"^(P[0-3])\b")


def canonical_status(s):
    """The five-keyword canonical form of a status value, or None to leave it
    alone (empty/placeholder — unset is a state, not drift). First canonical
    keyword wins (parse_taskboard's own contract); else the first synonym token
    by order of appearance; else todo — prose naming no recognisable state is a
    parked wish, not progress."""
    s0 = clean(s)
    if not s0:
        return None
    m = CANON_RE.search(s0)
    if m:
        return m.group(1).lower()
    for tok in re.findall(r"[A-Za-z][\w-]*", s0):
        hit = SYNONYMS.get(tok.lower())
        if hit:
            return hit
    return "todo"


def canonicalise(bdir, stamp=None):
    """Mechanical field hygiene over the ACTIVE cards — the sweep doctrine alone
    keeps failing to be: status collapses to its canonical keyword, a priority that
    LEADS with a level keeps that level, and the original prose is preserved as a dated
    状态注 body line (the 迁移注 pattern). Idempotent — a canonical card is never
    rewritten. Returns human-readable trace lines ([] = clean).

    **This sweep translates; it does not guess.** `P0 (…because…)` is a card marked P0
    by someone who also wrote down why, so the level is kept and the prose moves to the
    note (the panel matches the field exactly, `^P\\d$`, and would not read a level with
    a tail). A value with no level in it at all is left untouched and REPORTED —
    `field_faults` — because clearing it was this sweep deciding, on no evidence, that
    the card was meant to be unprioritised."""
    stamp = stamp or datetime.now().strftime("%Y-%m-%d")
    traces = []
    for c in load(bdir):
        notes, updates = [], {}
        cur = (c.get("status") or "").strip()
        canon = canonical_status(cur)
        if canon and cur != canon:
            updates["status"] = canon
            notes.append('status was "%s"' % cur)
        pr = clean(c.get("priority", ""))
        lead = PRIORITY_LEAD_RE.match(pr) if pr else None
        if lead and not PRIORITY_RE.match(pr):
            updates["priority"] = lead.group(1)
            notes.append('priority was "%s"' % pr)
        # A value with NO level to read is left exactly where it is — see field_faults.
        if not updates:
            continue
        body = (c.get("_body") or "").rstrip("\n")
        c["_body"] = ((body + "\n\n") if body else "") + \
            "> 状态注 %s: %s\n" % (stamp, " · ".join(notes))
        set_fields(c, **updates)
        traces.append("#%d %s" % (c["id"], " · ".join(notes)))
    return traces


def field_faults(bdir):
    """[(id, field, value)] — values on live cards that no reader will act on and that
    this sweep has no basis to translate.

    **Reported, never repaired.** A sweep may TRANSLATE (`shipped` → `done`, `P0 (…)` →
    `P0`) because the intent survives the rewrite. `low` is not a translation problem: it
    has no level to recover, so clearing it was the sweep GUESSING the card was meant to
    be unprioritised — and the guess ran both ways, promoting what was written below
    normal and demoting a card whose level merely carried its reason. It also destroyed
    the only record of what someone had decided, hours later, in a different session, with
    the trace going to a log file nobody opens.

    Nothing forces the repair either: every reader already treats an unrecognised priority
    as unset (the panel sorts it last and draws no tag), so the card behaves identically
    whether the junk stays or goes. That is exactly why the value stays — it is visible
    evidence that someone meant something, and only they can say what."""
    out = []
    for c in load(bdir):
        if (c.get("status") or "").strip().lower() == "done":
            continue
        pr = clean(c.get("priority", ""))
        if pr and not PRIORITY_RE.match(pr) and not PRIORITY_LEAD_RE.match(pr):
            out.append((c["id"], "priority", pr))
    return out


def stamp_since(bdir, state_path, now=None):
    """Keep every card's `since` honest: the moment it ENTERED its current status.

    Three sources, in descending accuracy:
      1. the write path — `set_fields`/`retire` stamp the transition as it happens;
      2. this sweep — a status that differs from the one last seen for that card
         (`state_path`, a tiny id → status map) is a transition the hooks did not make:
         an Obsidian property edit, a dept editing its own card, a 分公司 session;
      3. backfill — a card with no `since` at all takes its FILE clock, which is the
         old approximate signal, kept only so a legacy card is not born reading `0m`.

    So the number starts approximate on cards that predate the field and becomes exact
    the first time each one actually moves. Idempotent, fail-open, returns traces."""
    now = now or now_stamp()
    try:
        seen = json.load(open(state_path, encoding="utf-8"))
    except Exception:
        seen = {}
    if not isinstance(seen, dict):
        seen = {}
    traces, dirty = [], False
    for card in load(bdir):
        cid = str(card.get("id"))
        st = clean(card.get("status")) or "todo"
        if seen.get(cid) != st:
            was, seen[cid], dirty = seen.get(cid), st, True
            if was is not None:          # a transition this sweep is the first to see
                set_fields(card, since=now)
                traces.append("#%s entered %s (%s)" % (cid, st, now))
                continue
        if not clean(card.get("since")):
            try:
                mt = datetime.fromtimestamp(os.path.getmtime(card["_path"]))
                stamp = mt.strftime("%Y-%m-%dT%H:%M")
            except OSError:
                stamp = now
            set_fields(card, since=stamp)
            traces.append("#%s since backfilled from the file clock" % cid)
    if dirty:
        try:
            os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
            _atomic(state_path, json.dumps(seen, indent=0, sort_keys=True))
        except Exception:
            pass                          # unrecorded → re-detected next turn, never lost
    return traces


def dedupe_ids(bdir, stamp=None):
    """Heal duplicate durable ids. Two sessions minting concurrently — or a hand-
    written card numbered from conversational memory — can both claim #NNN, and a
    duplicated number poisons every id-keyed path: task-sync's fill tier turns
    ambiguous (which then birthed ghost duplicates), gate keys and retirement pick
    a card at random. Keeper: a done/archive holder outranks an active one (its
    number is frozen in BACKLOG rows and shipped history — and retirement rewrote
    the file, so mtime lies about its age), then the eldest file (birth order;
    lexicographic tie-break); every other holder is renumbered to the next free id
    with a dated 编号注 body note. Returns trace lines ([] = clean)."""
    stamp = stamp or datetime.now().strftime("%Y-%m-%d")
    holders = {}
    for sub in ("", "done", "archive"):
        for c in load(bdir, sub):
            try:
                key = (1 if sub == "" else 0, os.path.getmtime(c["_path"]),
                       os.path.basename(c["_path"]))
            except OSError:
                key = (1 if sub == "" else 0, 0, os.path.basename(c["_path"]))
            holders.setdefault(c["id"], []).append((key, c))
    taken = set(holders)
    traces = []
    for cid in sorted(i for i, hs in holders.items() if len(hs) > 1):
        for _, c in sorted(holders[cid], key=lambda kv: kv[0])[1:]:
            new = max(taken) + 1
            taken.add(new)
            src = c["_path"]
            body = (c.get("_body") or "").rstrip("\n")
            c["_body"] = ((body + "\n\n") if body else "") + \
                "> 编号注 %s: 与 #%d 撞号（并发铸号），改编 #%d\n" % (stamp, cid, new)
            c["id"] = new
            c["_path"] = os.path.join(os.path.dirname(src),
                                      re.sub(r"^\d+", str(new), os.path.basename(src), count=1))
            save(c)
            try:
                os.remove(src)
            except OSError:
                pass
            traces.append("#%d worn twice — %s renumbered to #%d"
                          % (cid, os.path.basename(src), new))
    return traces


def frontmatter(text):
    """ALL scalar frontmatter keys of a note (mail, or anything note-shaped) —
    {} when there's no fence. Same YAML subset as cards; no rewrite support."""
    if not (text or "").startswith("---"):
        return {}
    close = text.find("\n---", 3)
    if close < 0:
        return {}
    out = {}
    for line in text[text.index("\n") + 1:close + 1].splitlines():
        m = re.match(r"([A-Za-z][\w-]*):(.*)$", line)
        if m:
            out[m.group(1)] = _unquote(m.group(2))
    return out


# ---------------------------------------------------------------- digest

DIGEST_NOTE = ("<!-- GENERATED SECTION — cards live in %s/ (one note per card); edit "
               "the card files, not this section. -->")


def render_active(cards, board_rel):
    lines = ["## Active", "", DIGEST_NOTE % board_rel, ""]
    for c in cards:
        lines.append("### #%d · %s" % (c["id"], c.get("name") or ""))
        for k in FIELDS:
            lines.append("- **%s:** %s" % (k, c.get(k) or EMPTY))
        lines.append("")
    return "\n".join(lines) + ("" if cards else "\n")


def regen_digest(root, cfg):
    """Rewrite the digest's `## Active` section from the card files; every other
    byte (title, notes, SHIPPED block) is preserved. Missing digest → minimal one."""
    bdir = board_dir(root, cfg)
    board_rel = os.path.relpath(bdir, root)
    tb = os.path.join(root, (cfg or {}).get("taskboard", "docs/TaskBoard.md"))
    active = render_active(load(bdir), board_rel)
    try:
        text = open(tb, encoding="utf-8").read()
    except OSError:
        text = None
    if text is None:
        out = ("# TaskBoard\n\n%s\n## Recently shipped\n<!-- SHIPPED:START -->\n"
               "<!-- SHIPPED:END -->\n" % (active + "\n"))
    else:
        m = re.search(r"(?m)^##\s+Active[^\n]*\n", text)
        if m:
            nxt = re.search(r"(?m)^##\s", text[m.end():])
            cut = m.end() + nxt.start() if nxt else len(text)
            out = text[:m.start()] + active + "\n" + text[cut:]
        else:
            out = text.rstrip("\n") + "\n\n" + active + "\n"
    os.makedirs(os.path.dirname(tb) or ".", exist_ok=True)
    _atomic(tb, out)


def digest_stale(root, cfg):
    """True when any card file is newer than the digest (an Obsidian/dept/branch
    edit landed since the last regen). Cheap mtime sweep, no parsing."""
    bdir = board_dir(root, cfg)
    tb = os.path.join(root, (cfg or {}).get("taskboard", "docs/TaskBoard.md"))
    try:
        ref = os.path.getmtime(tb)
    except OSError:
        return os.path.isdir(bdir)
    newest = 0
    try:
        for fn in os.listdir(bdir):
            if CARD_RE.match(fn):
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(bdir, fn)))
                except OSError:
                    pass
    except OSError:
        return False
    return newest > ref


# ---------------------------------------------------------------- lazy migration

def _legacy_cards(text):
    """Card blocks off a legacy single-file board's `## Active` section:
    (head, fields{}, body_lines). Same tolerant span-scan the old surgery used."""
    m = re.search(r"(?m)^##\s+Active[^\n]*\n(.*?)(?=^##\s|\Z)", text or "", re.S)
    if not m:
        return []
    out = []
    for block in re.split(r"(?m)^###\s+", m.group(1))[1:]:
        lines = block.splitlines()
        head = (lines or [""])[0].strip()
        fields, body = {}, []
        for ln in lines[1:]:
            fm = re.match(r"-\s*\*\*([\w-]+):\*\*\s*(.*)$", ln)
            if fm and fm.group(1) in FIELDS:
                fields[fm.group(1)] = fm.group(2).strip()
            elif ln.strip():
                body.append(ln)
        out.append((head, fields, body))
    return out


def ensure_store(root, cfg):
    """The per-card store's single entry point: a store holding any card FILE → its
    path; a legacy board with cards → migrate it now (built in a tmp dir, renamed —
    or moved file-by-file when the board dir already exists holding non-card files:
    a pre-staged Board.base, a folder Obsidian created — mere dir-existence must
    never block the migration; deterministic output makes a double-move benign);
    neither → ensure the empty dir. None only when migration failed. Returns
    (bdir, notice) — notice is a one-line human summary when migration ran."""
    bdir = board_dir(root, cfg)
    if load(bdir):
        return bdir, None
    tb = os.path.join(root, (cfg or {}).get("taskboard", "docs/TaskBoard.md"))
    try:
        text = open(tb, encoding="utf-8").read()
    except OSError:
        text = ""
    legacy = _legacy_cards(text)
    if not legacy:
        try:
            os.makedirs(bdir, exist_ok=True)
        except OSError:
            return None, None
        return bdir, None
    tmp = bdir + ".migrating-%d" % os.getpid()
    try:
        os.makedirs(tmp)
    except OSError:
        return None, None
    try:
        taken, moved, tombs = set(), 0, 0
        heads = []
        for head, fields, body in legacy:
            hm = re.match(r"[~\s]*#(\d+)\b", head)
            heads.append(int(hm.group(1)) if hm else None)
            if hm:
                taken.add(int(hm.group(1)))
        nxt = max(taken, default=0)
        for (head, fields, body), hid in zip(legacy, heads):
            name = (head.split("·", 1)[1] if "·" in head else head).strip().strip("~ ").strip()
            if hid is None:
                nxt += 1
                hid = nxt
            meta = {"id": hid, "name": name}
            for k in FIELDS:
                meta[k] = fields.get(k, EMPTY)
            tomb = bool(TOMB_RE.search(head)) and not clean(fields.get("status", ""))
            sub = os.path.join(tmp, "archive") if tomb else tmp
            os.makedirs(sub, exist_ok=True)
            fname = "%d-%s.md" % (hid, slugify(name))
            body_txt = ("\n".join(body) + "\n") if body else ""
            with open(os.path.join(sub, fname), "w", encoding="utf-8") as f:
                f.write(render_card(meta, (), body_txt))
            moved += 1
            tombs += 1 if tomb else 0
        if not os.path.isdir(bdir):
            os.rename(tmp, bdir)  # fast path: atomic whole-store appearance
        else:
            for base_dir, _, files in os.walk(tmp):
                rel = os.path.relpath(base_dir, tmp)
                dst_dir = bdir if rel == "." else os.path.join(bdir, rel)
                os.makedirs(dst_dir, exist_ok=True)
                for fn in files:
                    os.replace(os.path.join(base_dir, fn), os.path.join(dst_dir, fn))
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
    except OSError:
        try:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass
        return None, None
    notice = None
    if moved:
        regen_digest(root, cfg)
        notice = ("🔧 board migrated to the per-card store: %d card(s) → %s/"
                  % (moved, os.path.relpath(bdir, root))
                  + (" (%d tombstone(s) → archive/)" % tombs if tombs else "")
                  + " — TaskBoard.md is now a generated digest; edit the card files.")
    return bdir, notice
