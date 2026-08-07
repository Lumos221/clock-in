#!/usr/bin/env python3
"""Boss Board — a live "Needs-You" panel aggregating every pending ask for the
Boss across panes. Panes raise `@BOSS[<dept>]: <ask>` (a Stop hook captures it)
and resolve with `@BOSS-DONE[<dept>]`; the Boss raises via the `/board` command.
A singleton localhost server serves a self-polling page that always shows the
current open asks. Stdlib only; degrades, never hard-fails. See
docs/design/specs/2026-06-30-boss-board-design.md."""
import sys, os, re, json, time, html, hashlib, socket, tempfile, subprocess
from datetime import datetime, timedelta

STORE_REL = os.path.join(".claude", "boss-board.json")
IDLE_REAP_SECONDS = 600
POLL_MS = 1500


# ---------------------------------------------------------------- store layer
def normalize(text):
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def next_id(store, dept):
    n = 0
    for e in store["entries"]:
        if e.get("dept") == dept:
            try:
                n = max(n, int(str(e["id"]).rsplit("-", 1)[-1]))
            except Exception:
                pass
    return "%s-%d" % (dept, n + 1)


def find_open_dup(store, dept, text):
    key = normalize(text)
    for e in store["entries"]:
        if e["dept"] == dept and e["status"] == "open" and normalize(e["text"]) == key:
            return e
    return None


ASK_TASK_RE = re.compile(r"#(\d+)\b")


def ask_key(text, task=None):
    """The task an ask is ABOUT: the explicit task field, else the first #NNN its
    TITLE (text before '::') references, else None. The fallback matters in the
    field — asks raised without the #task linkage still lead their title with the
    card number (a live project CEO-143/144). No key → never auto-superseded."""
    if task:
        return str(task)
    m = ASK_TASK_RE.search((text or "").split("::", 1)[0])
    return m.group(1) if m else None


def raiser_pane():
    """The iTerm pane of whoever is calling — the CLI subprocess and the MCP server both
    inherit ITERM_SESSION_ID from the session that spawned them (verified across
    four live panes). So the board can know where every item CAME FROM, for free."""
    if _iterm_disabled():
        return ""
    sid = os.environ.get("ITERM_SESSION_ID") or ""
    return sid.split(":")[-1].strip()


def add_entry(store, dept, kind, text, now, task=None, batch=None, supersede=True,
              src=None):
    dup = find_open_dup(store, dept, text)
    if dup:
        return dup, False
    e = {"id": next_id(store, dept), "dept": dept, "text": (text or "").strip(),
         "kind": kind, "status": "open", "created": now, "updated": now}
    # WHERE IT CAME FROM. An answer belongs to the session that raised the question, and
    # that session is knowable at the moment the item is written — no inference, no picker,
    # no "which pane is the CEO". Everything before this tried to guess one destination for
    # the whole board; the board never needed one.
    if src is None:
        src = raiser_pane()
    if src:
        e["src"] = src
    if task:
        e["task"] = str(task)  # platform task_id — lets the panel show the ask's task card
    if batch:
        e["batch"] = batch  # same-turn marker batch — batch-mates never supersede each other
    # Supersede COLLISION detection: a NEW decision ask about the same task as an
    # older open one flags the new entry — the Stop hook turns the flag into a
    # ONE-TIME nudge so the raiser closes the old ask WITH a real outcome, or
    # deliberately keeps both (field failures cured: CEO-27/28, CEO-143/144 — a
    # revised re-raise leaving both open). CEO-in-the-loop BEFORE any supersede —
    # nothing here auto-resolves, because only the raiser knows which ask replaces which. 0.9.36 dropped the
    # same-dept+kind requirement: one ask registered through BOTH paths (CLI add +
    # marker re-end, field case Boss-13/CEO-166) wore a different raiser AND kind,
    # blinding the detector — the task key alone is the identity. Still never flags:
    # info (either side) · notices · same-batch (one turn's marker lines = deliberate
    # separate decisions) · keyless asks.
    if supersede and kind != "info":
        key = ask_key(text, task)
        if key:
            for old in store["entries"]:
                if old["status"] != "open" or old.get("notice") or old.get("kind") == "info":
                    continue
                if batch and old.get("batch") == batch:
                    continue
                if ask_key(old.get("text"), old.get("task")) == key:
                    e.setdefault("collides", []).append(old["id"])
    store["entries"].append(e)
    return e, True


def get_entry(store, eid):
    for e in store["entries"]:
        if e["id"] == eid:
            return e
    return None


# ---------------------------------------------------------------- Obsidian desk mirror

DESK_REL = os.path.join("docs", "board", "desk")
DESK_ANSWERED_KEEP = 8
# python twin of the panel's PATH_RE — file-path extraction for the files: column
DESK_FILE_RE = re.compile(
    r"(^|[^\w.\-/一-鿿])"
    r"((?:/?(?:[\w.\-一-鿿]+/)+[\w.\-一-鿿]+\.[A-Za-z0-9]{1,5})"
    r"|(?:/?(?:[\w.\-一-鿿]+/){2,})"          # a DIRECTORY, cited with its trailing slash
    r"|[\w一-鿿][\w.\-一-鿿]*\."
    r"(?:png|jpe?g|gif|webp|pdf|svg|md|txt|csv|json|log|html?|ya?ml|toml))")


def desk_files(text):
    out = []
    for m in DESK_FILE_RE.finditer(" " + (text or "")):
        p = m.group(2)
        if p not in out:
            out.append(p)
    return out


def is_info(e):
    """Information ≠ decisions: the entry asks nothing of the Boss, it only needs to be
    seen. ONE predicate, two runtimes — the panel's isInfo() is the JS twin; a change
    here that misses the twin splits the desk from the send."""
    return bool(e.get("kind") == "info" or e.get("notice")
                or (e.get("dept") or "").lower().startswith("inspector"))


def _desk_section(e):
    """The desk section an entry files under (panel parity); None = not mirrored.
    Numbered prefixes make Bases' lexical group sort match the panel's order."""
    info = is_info(e)
    if e.get("status") == "open":
        return "3 Information" if info else "1 Needs you"
    if e.get("status") == "parked":
        return "2 Parked"
    if e.get("status") == "resolved" and not e.get("notice"):
        return "4 Answered"
    return None


def desk_mirror(root):
    """Mirror the ask register into Obsidian notes — docs/board/desk/<id>.md, flat
    frontmatter (section · kind · dept · task · ask · files · updated) so a Bases
    view shows the Boss's desk (Needs you / Parked / Information / Answered) with
    file paths in their own column. GENERATED, machine-
    owned: status truth stays in the JSON store (resolve via @BOSS-DONE / CLI /
    the CEO) — notes rewrite wholesale (only when bytes change, so Obsidian stays
    quiet) and prune when their entry leaves the desk; the `mirror` key marks what
    may be pruned, foreign files are never touched. Answered keeps the newest
    DESK_ANSWERED_KEEP. Callers stay fail-open."""
    store = load_store(_store_path(root))
    entries = [e for e in store.get("entries", []) if _desk_section(e)]
    answered = sorted((e for e in entries if _desk_section(e) == "4 Answered"),
                      key=lambda e: e.get("updated") or "", reverse=True)
    drop = {e["id"] for e in answered[DESK_ANSWERED_KEEP:]}
    entries = [e for e in entries if e["id"] not in drop]
    ddir = os.path.join(root, DESK_REL)
    os.makedirs(ddir, exist_ok=True)
    keep = set()
    for e in entries:
        fn = "%s.md" % e["id"]
        keep.add(fn)
        title, _, detail = (e.get("text") or "").partition("::")
        title, detail = title.strip(), detail.strip()
        files = desk_files(e.get("text") or "")
        fm = [("mirror", "boss-board"), ("id", e["id"]),
              ("section", _desk_section(e)), ("kind", e.get("kind") or ""),
              ("dept", e.get("dept") or ""),
              ("task", ("#%s" % e["task"]) if e.get("task") else ""),
              ("ask", title[:120]),
              ("updated", e.get("updated") or e.get("created") or "")]
        lines = ["> 机器镜像（boss-board 生成）— 状态以 Boss Board 为准，此文件会被重写。", ""]
        if title:
            lines += ["**%s**" % title, ""]
        if detail:
            lines += [detail, ""]
        if e.get("status") == "resolved":
            # 答复 is the Boss's; 结案 is the raiser closing its own ask. Both can be present and
            # they are different people — the mirror named everything 答复 back when one
            # field held both, so a DONE note read as the Boss's decision.
            if e.get("sum"):
                lines += ["**答复:** %s" % e["sum"], ""]
            if e.get("outcome"):
                lines += ["**结案（提问方）:** %s" % e["outcome"], ""]
        if files:
            lines += ["Files:"] + ["- [%s](%s)" % (p, p) for p in files] + [""]
        # files = a YAML LIST of quoted wiki-links — Obsidian renders link-typed
        # list items clickable in the properties panel AND the Bases cell (a plain
        # scalar string rendered dead text — Boss's 2026-07-21 report). Always a
        # list, even empty: a key that flips scalar/list confuses the property type.
        files_yaml = ("files:\n" + "\n".join('  - "[[%s]]"' % p for p in files)
                      if files else "files: []")
        full = ("---\n"
                + "\n".join("%s: %s" % (k, json.dumps(v, ensure_ascii=False)) for k, v in fm)
                + "\n" + files_yaml
                + "\n---\n\n" + "\n".join(lines).rstrip("\n") + "\n")
        path = os.path.join(ddir, fn)
        try:
            cur = open(path, encoding="utf-8").read()
        except OSError:
            cur = None
        if cur != full:
            with open(path, "w", encoding="utf-8") as f:
                f.write(full)
    for fn in os.listdir(ddir):
        if not fn.endswith(".md") or fn in keep:
            continue
        try:
            with open(os.path.join(ddir, fn), encoding="utf-8") as f:
                head = f.read(200)
        except OSError:
            continue
        if 'mirror: "boss-board"' in head:
            try:
                os.remove(os.path.join(ddir, fn))
            except OSError:
                pass


def list_entries(store, dept=None):
    return [e for e in store["entries"] if dept is None or e["dept"] == dept]


def set_status(store, eid, status, now, sum=None, outcome=None):
    """Resolve/park/reopen an entry, and record WHO said what about it.

    `sum` is THE BOSS'S answer — the words they sent, which the board renders as theirs, over their
    name and their clock. `outcome` is the raiser's own closing note (`@BOSS-DONE`), which
    is a different person speaking about the same item. They shared one field, so a
    session that answered their and withdrew its own ask in the same turn replaced their
    reply with its one-line summary, still labelled "you". The words the Boss typed were
    gone from the board and the CEO's sentence was standing in their mouth.

    A DONE never overwrites an answer: the two live in their own fields and are rendered
    as two turns by two people."""
    e = get_entry(store, eid)
    if e:
        e["status"] = status
        e["updated"] = now
        if sum:
            e["sum"] = sum
        if outcome:
            e["outcome"] = outcome
    return e


# ---------------------------------------------------------------- interactive desk (reverse channel)
# The board is no longer read-only: the Boss answers on the panel, and Send flushes
# the staged answers into THIS session as ONE message. Resolution happens HERE, at
# send, server-side — so "forgot to run @BOSS-DONE" is structurally impossible: the
# answer's arrival IS the resolution. See docs/design/specs + reference/boss-board.md.
def set_read(store, eid, read, now):
    """Mechanical 'seen' flag on an entry (Information items need no decision, only a
    read tick). Pure display state — never touches status or the session."""
    e = get_entry(store, eid)
    if e:
        e["read"] = bool(read)
        e["updated"] = now
    return e


def basket_set(store, eid, kind, text, now):
    """Stage (or replace) the Boss's answer for one entry; empty text unstages it.
    kind 'reply' = a decision (resolves the item at send); 'ask' = a follow-up
    question (item stays open); 'msg' = a message to a whole conversation, keyed
    `free:<dept>`, which belongs to no entry and therefore resolves and reads nothing.
    One staged answer per entry — a re-stage overwrites.
    Persisted in the store so a page reload restores the tray."""
    b = [x for x in store.get("basket", []) if x.get("id") != eid]
    if (text or "").strip():
        b.append({"id": eid, "kind": (kind if kind in ("ask", "read", "msg") else "reply"),
                  "text": text.strip(), "ts": now})
    store["basket"] = b
    return b


def compose_basket(basket):
    """One SINGLE-LINE message carrying every staged action with its id (iTerm2 `write
    text` submits at each newline, so the whole basket lands as ONE prompt). Replies are
    flagged already-resolved (session never re-runs @BOSS-DONE); asks stay open.

    Archiving is NOT in here. Reading an update is their filing it away, not a message worth
    a session's turn — the board used to append `Read: CEO-1, CEO-2` and a "N marked read
    (acknowledged, no action)" note, which is a sentence that asks the reader to do exactly
    nothing. Only Reply and Ask send anything."""
    reps = [x for x in basket if x.get("kind") == "reply"]
    asks = [x for x in basket if x.get("kind") == "ask"]
    msgs = [x for x in basket if x.get("kind") == "msg"]

    def one(x):
        t = re.sub(r"\s+", " ", x.get("text", "")).strip()
        # A free message names no item, because it is about no item. Printing an id in
        # front of it told the reader it was a question about that card.
        if x.get("kind") == "msg":
            return t
        return "%s %s %s" % (x["id"], "asks:" if x.get("kind") == "ask" else "→", t)

    parts = [one(x) for x in reps + asks + msgs]
    # No preamble. The board used to prefix a count of what it was sending and an
    # instruction not to re-run the done-marker; that is bookkeeping about the message
    # rather than the message, and it arrived in front of every answer they wrote.
    return "[Boss Board] " + " · ".join(parts)


SENT_TAIL = 400        # their side of the conversation, newest kept


def board_send_mutate(store, now):
    """Flush the basket: resolve reply items (sum = the reply text), leave asks open, clear
    the basket. An ask ON an Information item also archives it — asking about an update IS
    reading it; leaving it unread demanded a manual tick plus a second Send just for the ack. Archiving alone never reaches here: it applies at the click and
    sends nothing.
    Returns {msg, items} — the composed one-line message the caller types into the
    Boss's input — or None when empty. No outbox: the message goes straight to the
    pane, so there is nothing to queue."""
    basket = [x for x in (store.get("basket") or []) if x.get("kind") != "read"]
    if not basket:
        store["basket"] = []
        return None
    # Group by WHERE EACH ITEM CAME FROM: two answers to two different sessions are two
    # messages, each going home. Items with no recorded origin (everything raised before
    # 0.9.84) fall into one "" group and use the board's default seat.
    groups = {}
    for x in basket:
        # `free:<dept>` is a message to a whole conversation and has no entry behind it,
        # so it routes by department the same way an item with no recorded pane does.
        if str(x["id"]).startswith("free:"):
            groups.setdefault("dept:%s#" % str(x["id"])[5:], []).append(x)
            continue
        e = get_entry(store, x["id"]) or {}
        # A teammate writes to the board from a process with no ITERM_SESSION_ID, so its
        # items record no pane at all. Falling back to "the board's default seat" sent the
        # answer to the CEO's input box — technically the default, and useless: the
        # department that asked has its own live session. Key those groups by DEPARTMENT so
        # the send path can look the teammate up instead of guessing.
        # Whoever wrote it gets the answer. `src` is the pane the WRITING process sat in,
        # so an item the lead relayed on a department's behalf answers to the LEAD — which
        # is right: it relayed the question, so it has to see the decision. A department
        # that wrote to the board itself is addressed by its own seat.
        key = e.get("src") or ("dept:%s#%s" % (e.get("dept") or "", e.get("task") or ""))
        groups.setdefault(key, []).append(x)
    # EVERYTHING they send is logged, because everything they send is part of the
    # conversation. Only a reply was ever kept (as the item's `sum`), so a question they
    # asked about an item, and a message they wrote to a department, went out to the
    # session and left no trace on the board at all — they wrote it, it vanished, and the
    # thread showed the reply above it and the answer below it with nothing in between.
    # Reply, ask and plain message are three ways of sending; all three must appear.
    log = store.setdefault("sent", [])
    for x in basket:
        rid = "" if str(x["id"]).startswith("free:") else x["id"]
        dept = (str(x["id"])[5:] if not rid
                else (get_entry(store, x["id"]) or {}).get("dept") or "")
        log.append({"id": rid, "dept": dept, "kind": x.get("kind") or "reply",
                    "text": x.get("text") or "", "at": now})
    store["sent"] = log[-SENT_TAIL:]
    for x in basket:
        if x.get("kind") == "reply":
            set_status(store, x["id"], "resolved", now, sum=x.get("text"))
        elif x.get("kind") == "ask":
            e = get_entry(store, x["id"])
            if e and is_info(e):    # asking about an update is reading it — folds with the send
                e["read"] = True
                e["updated"] = now
    rec = {"msg": compose_basket(basket), "items": [x["id"] for x in basket],
           "groups": [{"src": s, "msg": compose_basket(g), "items": [x["id"] for x in g]}
                      for s, g in groups.items()]}
    store["basket"] = []
    return rec


def set_direction(store, text, now):
    """The standing product-direction banner above the panel (e.g. a launch
    checklist). One slot, whole-text replace; empty text clears it."""
    if (text or "").strip():
        store["direction"] = {"text": text.strip(), "updated": now}
    else:
        store.pop("direction", None)
    return store.get("direction")


def open_for_dept(store, dept):
    return [e for e in store["entries"] if e["dept"] == dept and e["status"] == "open"]


def open_notices(store, dept):
    return [e for e in open_for_dept(store, dept) if e.get("notice")]


def resolve_by_dept(store, dept, now, outcome=None):
    # Ambiguity notices describe the queue — counting them as part of it made each
    # notice amplify the next ("2 asks open" begets "3 asks open" listing the first
    # notice) and left a dept-level DONE permanently ambiguous once one existed.
    #
    # INFO is excluded for the same reason and was not until 0.9.62. An info item asks
    # nothing of them: it is never what a DONE resolves, and it leaves the desk only when
    # they toggle it read. Counting it made `@BOSS-DONE[<dept>]` permanently ambiguous for
    # any dept holding one — on a live board the CEO had 7 open info items, the oldest
    # 5 days old, so every dept-level DONE raised a notice instead of resolving, and the
    # notice then inflated the desk count.
    opens = [e for e in open_for_dept(store, dept)
             if not e.get("notice") and e.get("kind") != "info"]
    if len(opens) == 1:
        set_status(store, opens[0]["id"], "resolved", now, outcome=outcome)
        for n in open_notices(store, dept):   # queue is unambiguous again — notice is moot
            n["status"] = "resolved"
            n["updated"] = now
        return opens[0], []
    return None, opens


def add_notice(store, dept, text, now):
    """One open ambiguity notice per dept: an unchanged re-raise keeps the existing
    card (same dedup contract as add_entry); a changed one supersedes it — the old
    count/id list is stale the moment the queue moves."""
    dup = find_open_dup(store, dept, text)
    if dup:
        return dup
    for n in open_notices(store, dept):
        n["status"] = "resolved"
        n["updated"] = now
    e, created = add_entry(store, dept, "discuss", text, now, supersede=False)
    if created:
        e["notice"] = True
    return e


def load_store(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("entries", [])
        return data
    except Exception:
        return {"entries": []}


def save_store(path, store):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


# ---------------------------------------------------------------- cross-process lock
LOCK_REL = STORE_REL + ".lock"
LOCK_WAIT_TIMEOUT = 2.0   # give up and proceed unlocked past this — a hook must never hang a turn
LOCK_STALE_AGE = 5.0      # a lock older than this is presumed abandoned by a crashed hook


class _StoreLock:
    """Cross-process mutex for the store's load-modify-save window. Two Stop hooks
    (stop_boss_board.py, stop_refute_tally.py) can both react to the same turn and both
    call board_add/board_done/etc — without this, whichever finishes saving last silently
    overwrites the other's just-written entry (lost update, no error, nothing in any log).
    Built from os.O_CREAT|O_EXCL (atomic create on POSIX and Windows) to stay stdlib-only.
    Fails open: on timeout or a lock we don't own, proceed without it rather than hang."""

    def __init__(self, root):
        self.path = os.path.join(root, LOCK_REL)
        self.fd = None

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        deadline = time.time() + LOCK_WAIT_TIMEOUT
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode())
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.path) > LOCK_STALE_AGE:
                        os.remove(self.path)  # reap a lock abandoned by a crashed hook
                        continue
                except OSError:
                    continue  # lock vanished between the check and the remove — retry
                if time.time() > deadline:
                    return self  # fail-open: proceed unlocked rather than hang the turn
                time.sleep(0.02)

    def __exit__(self, *exc_info):
        if self.fd is not None:
            os.close(self.fd)
            try:
                os.remove(self.path)
            except OSError:
                pass


def _locked_mutate(root, mutator):
    """Load the store, apply `mutator(store) -> result` under `_StoreLock`, save, return
    result. Every write path goes through this so no two hooks can race on the file."""
    p = _store_path(root)
    with _StoreLock(root):
        store = load_store(p)
        result = mutator(store)
        save_store(p, store)
    return result


# ---------------------------------------------------------------- markers
# `@BOSS[<dept>#<task_id>]: <ask>` — the optional #task links the ask to its TaskBoard
# card so the panel can show the task's context next to the ask. Bare `@BOSS[<dept>]:`
# stays valid (non-task asks, and every pre-0.7.0 dept brief).
# The task segment takes any run that is not a bracket, whitespace or `#`. It was
# ASCII-only, so a CJK task name — the normal way a 分公司 names its work — made the
# whole marker fail to parse. It then landed in marker-misses.log and nowhere else, so
# an ask the model had been NUDGED into registering still never reached the board
# (a task named in Chinese, logged twice, shown never).
RAISE_RE = re.compile(r"@BOSS\[([^\]\s#]+)(?:#([^\]\s#]+))?\]:\s*(.+)")
# `@BOSS-DONE[<dept>|<id>]: <one-line outcome>` — the optional outcome becomes the
# answered row's collapsed line on the panel (an essay ask folds to its result).
DONE_RE = re.compile(r"@BOSS-DONE\[([^\]\s]+)\](?::\s*(.+))?")
# `@BOSS-INFO[<dept>#<task_id>]: <fact>` — information for the Boss that needs NO
# decision (verdicts, 复盘 outcomes, FYI status). Lands in the panel's Information
# column, never in Needs-you (verdicts were crowding the
# decision queue).
INFO_RE = re.compile(r"@BOSS-INFO\[([^\]\s#]+)(?:#([^\]\s#]+))?\]:\s*(.+)")


def parse_markers(text):
    """raises = (dept, task_id-or-None, ask); dones = (dept-or-id, outcome-or-None);
    infos = (dept, task_id-or-None, fact). `misses` = lines that mention @BOSS but
    match no marker — the hook logs them (marker-misses.log) so a malformed marker
    doesn't vanish without a trace."""
    raises, dones, infos, misses = [], [], [], []
    for line in (text or "").splitlines():
        m = DONE_RE.search(line)
        if m:
            # tolerate a symmetric #task suffix on the token
            dones.append((m.group(1).split("#")[0], (m.group(2) or "").strip() or None))
            continue
        m = INFO_RE.search(line)
        if m:
            infos.append((m.group(1), m.group(2), m.group(3).strip()))
            continue
        m = RAISE_RE.search(line)
        if m:
            raises.append((m.group(1), m.group(2), m.group(3).strip()))
            continue
        if "@BOSS" in line:
            misses.append(line)
    return {"raises": raises, "dones": dones, "infos": infos, "misses": misses}


# ---------------------------------------------------------------- taskboard view
def _section(text, title):
    """Body of the `## <title>…` section (any suffix on the heading line), up to the
    next `## ` heading or EOF; "" if absent. Real boards order sections freely —
    a live project keeps *Recently shipped* ABOVE *Active* — so never split positionally."""
    m = re.search(r"(?m)^##\s+%s[^\n]*\n(.*?)(?=^##\s|\Z)" % re.escape(title), text, re.S | re.M)
    return m.group(1) if m else ""


STATUS_RE = re.compile(r"\b(todo|doing|review|blocked|done)\b", re.I)
# Hand-struck "tombstone" headings — a finished card closed by striking the heading
# instead of TaskUpdate→completed (field case: a live project 07-14; such cards have no
# status field and would garble the Todo column). SHOUTED closure words only: live
# card names legitimately contain lowercase "shipped"/"done-when".
TOMB_RE = re.compile(r"~~|\b(?:SHIPPED|RETIRED)\b|card closes")


def parse_taskboard(path):
    """Read TaskBoard.md into the panel's iteration view: the `## Active` section's
    cards (label · name · dept · task_id · status · blocked_on · what) + the
    Recently-shipped lines. Tolerant of field reality: sections in any order, prose
    status lines ("doing — L1 PASS 3rd round…", "✅ DONE + L2-passed" → first status
    keyword wins), placeholder values (`<...>`, `—`) → blank; missing file → empty."""
    try:
        text = open(path, encoding="utf-8").read()
    except Exception:
        return {"tasks": [], "shipped": []}

    def clean(v):
        v = (v or "").strip().strip("`").strip()
        return "" if (not v or v.startswith("<") or v == "—") else v

    tasks = []
    for block in re.split(r"(?m)^###\s+", _section(text, "Active"))[1:]:
        head = (block.splitlines() or [""])[0].strip()
        label, _, name = head.partition("·")

        def field(key):
            m = re.search(r"\*\*%s:\*\*\s*([^\n]+)" % key, block)
            return clean(m.group(1)) if m else ""

        sm = STATUS_RE.search(field("status"))
        status = sm.group(1).lower() if sm else ""
        if not status and TOMB_RE.search(head):
            status = "done"  # tombstone heading, no status field → file as done, not Todo
        tasks.append({"label": clean(label) or head, "name": clean(name) or clean(label),
                      "dept": field("dept"), "task_id": field("task_id"),
                      "status": status, "since": field("since"),
                      "priority": field("priority"), "kind": field("kind"),
                      "blocked_on": field("blocked_on"), "what": field("what"),
                      "done-when": field("done-when"), "artifacts": field("artifacts")})
    shipped = []
    m = re.search(r"<!-- SHIPPED:START -->(.*?)<!-- SHIPPED:END -->", text, re.S)
    seg = m.group(1) if m else _section(text, "Recently shipped")
    for line in seg.splitlines():
        if line.strip().startswith("- ") and not line.strip().startswith("- <"):
            shipped.append(line.strip()[2:])
    return {"tasks": tasks, "shipped": shipped}


# The panel polls every 1.5s and every poll rebuilt the whole payload from scratch —
# including 56 git subprocesses for the L2 verdicts, six seconds on their own. The page was
# not slow at one thing; it was recomputing everything, forever, and a paste queued behind
# it looked like a hung upload. These answers change when their SOURCES change.
_MEMO = {}


def _memo(name, stamp, build):
    """`build()`'s result, recomputed only when `stamp` moves. An unreadable stamp falls
    through to a 2s TTL, so a missing source degrades to slow rather than to stale."""
    if stamp is None:
        stamp = ("ttl", int(time.time() / 2))
    hit = _MEMO.get(name)
    if hit and hit[0] == stamp:
        return hit[1]
    val = build()
    _MEMO[name] = (stamp, val)
    return val


_DIRCAP = 4000


def _dirstamp(path):
    """A directory's own mtime moves only when an entry is created, renamed or removed —
    editing a file INSIDE it moves nothing at all. A lane cached on its folder's mtime
    therefore froze: three letters flipped `status: unread` to `read` in place and the
    board went on showing them unread for an hour, because nothing new had arrived to
    move the folder (2026-08-04, a screenshot). So the stamp is the ENTRIES: each
    name with its mtime and size, folded.

    Flat, one level, because every loader here reads its directory with `os.listdir` —
    the stamp covers exactly what the reader can see. A NESTED directory a loader opens
    (`<board>/done`) has to be named in the stamp itself; recursing instead cost 18ms on
    `docs/board` where one level costs 0.7ms. Past _DIRCAP entries the fold is abandoned
    for a 2s TTL: slow, never stale."""
    try:
        entries = list(os.scandir(path))
    except OSError:
        return 0
    if len(entries) > _DIRCAP:
        return ("ttl", int(time.time() / 2))
    fold = 0
    for e in entries:
        try:
            st = e.stat(follow_symlinks=False)
        except OSError:
            continue
        fold ^= hash((e.name, st.st_mtime_ns, st.st_size))
    return fold


def _mtimes(*paths):
    """A stamp from the paths a loader reads. A missing path counts as 0, so a file
    appearing or vanishing moves the stamp; a DIRECTORY is stamped by its entries
    (`_dirstamp`), never by its own mtime, which says nothing about an edit inside it."""
    out = []
    for p in paths:
        try:
            out.append(_dirstamp(p) if os.path.isdir(p) else os.path.getmtime(p))
        except Exception:
            out.append(0)
    return tuple(out)


def _git_head(root):
    try:
        return subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=4).stdout.strip()
    except Exception:
        return ""


def load_taskboard(root):
    """Cached on the board's own sources: the digest, the card directory, the retired
    cards, the review markers and git HEAD — everything an L2 verdict can turn on.
    `<board>/done` is named separately because `_dirstamp` is one level deep and
    `retired_tasks` reads that subdirectory."""
    def _sources():
        try:
            cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"),
                                 encoding="utf-8"))
        except Exception:
            cfg = {}
        bdir = os.path.join(root, cfg.get("board") or "docs/board")
        return _mtimes(os.path.join(root, cfg.get("taskboard", "docs/TaskBoard.md")),
                       bdir, os.path.join(bdir, "done"),
                       os.path.join(root, "docs", "reviews")) + (_git_head(root),)
    return _memo("taskboard:" + root, _sources(), lambda: _load_taskboard(root))


def _load_taskboard(root):
    rel = "docs/TaskBoard.md"
    ext = []
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"),
                             encoding="utf-8"))
        rel = cfg.get("taskboard", rel)
        ext = [str(h).strip().lower() for h in (cfg.get("external") or [])]
    except Exception:
        pass
    tb = parse_taskboard(os.path.join(root, rel))
    if ext:
        # 分公司 (branch-office) depts run outside this session's team — badge their
        # cards so the Boss reads the lane at a glance (0.9.29)
        for t in tb["tasks"]:
            d = (t.get("dept") or "").strip().lower()
            t["external"] = bool(d) and any(e in d for e in ext)
    # Done CARDS need a date so the Done column can split them today-vs-earlier exactly
    # like the shipped lines. The digest carries no date, so take the card
    # FILE's mtime — the last write is the completion write for a done card. Cards whose
    # file can't be found stay dateless and fall to "Earlier" (a lingering done card with
    # no traceable date is by definition not today's news).
    try:
        bdir = os.path.join(root, (cfg.get("board") or "docs/board"))
        stamps = {}
        for fn in os.listdir(bdir):
            m = re.match(r"(\d+)-", fn)
            if m and fn.endswith(".md"):
                try:
                    stamps[m.group(1)] = datetime.fromtimestamp(
                        os.path.getmtime(os.path.join(bdir, fn))).strftime("%Y-%m-%d")
                except OSError:
                    pass
        for t in tb["tasks"]:
            if t.get("status") == "done":
                num = re.sub(r"\D", "", t.get("label") or "")
                if num and num in stamps:
                    t["date"] = stamps[num]
    except Exception:
        pass
    # Retired cards used to vanish from the panel outright. The digest is regenerated
    # from the ACTIVE card directory, so the moment a finished card is moved to
    # <board>/done/ it leaves the digest and the pipeline shows nothing where it was —
    # it never lands in Done, it simply stops existing ("the
    # completed cards just disappeared instead of going to Done"). Read them back, newest
    # first and capped: Done is the tail of the pipeline, not the whole archive.
    try:
        tb["tasks"].extend(retired_tasks(os.path.join(bdir, "done"), ext))
    except Exception:
        pass
    _attach_l2(root, tb["tasks"])
    return tb


DONE_TAIL = 25


def _card_meta(path):
    """The card's frontmatter as a flat dict (last value wins on a repeated key).
    Multi-line values are not needed here — every field Done renders is single-line."""
    out = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return out
    if not text.startswith("---"):
        return out
    for line in text.split("---", 2)[1].splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip()
    return out


def retired_tasks(ddir, ext=(), cap=DONE_TAIL):
    """The most recently retired cards, as done tasks in the digest's own shape."""
    rows = []
    try:
        names = os.listdir(ddir)
    except OSError:
        return rows
    for fn in names:
        m = re.match(r"(\d+)-", fn)
        if not m or not fn.endswith(".md"):
            continue
        path = os.path.join(ddir, fn)
        meta = _card_meta(path)
        num = (meta.get("id") or m.group(1)).strip()
        stamp = (meta.get("shipped") or meta.get("since") or "").strip()
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = 0.0
        date = stamp[:10] if len(stamp) >= 10 else (
            datetime.fromtimestamp(mtime).strftime("%Y-%m-%d") if mtime else "")
        dept = (meta.get("dept") or "").strip()
        rows.append({
            "label": "#%s" % num, "name": meta.get("name") or fn[:-3],
            "dept": dept, "task_id": meta.get("task_id") or "",
            "status": "done", "since": meta.get("since") or "",
            "priority": meta.get("priority") or "", "kind": meta.get("kind") or "",
            "blocked_on": "",
            "what": meta.get("what") or "", "done-when": meta.get("done-when") or "",
            "artifacts": meta.get("artifacts") or "", "date": date, "retired": True,
            "external": bool(dept) and any(e in dept.lower() for e in (ext or [])),
            "_sort": (stamp or ""), "_mtime": mtime,
        })
    rows.sort(key=lambda r: (r["_sort"], r["_mtime"]), reverse=True)
    for r in rows:
        r.pop("_sort", None)
        r.pop("_mtime", None)
    return rows[:cap]


REVIEW_KEY_RE = re.compile(r"^x?(\d+)")


def review_key(fn):
    """The task/card id a review marker belongs to, or "" if the file is not a marker.

    Markers come in two shapes because the Auditor's own spec asked for two: `<id>.pass`
    on a pass, but `<dept>.<id>.<n>.fail` on a bounce. Writing both from one seat,
    reviewers settled on the dept-prefixed form for passes too, so the field is full of
    `Ops.409-checkout-price.1.pass` while every reader here assumed the bare form — real
    verdicts sat on disk invisible to the completion gate and to the board (four finished cards could not be ticked off, and the CEO rightly refused
    to forge the marker to clear them).

    The id is the FIRST dot-segment beginning with a number — first, because the trailing
    segment is the attempt count and would otherwise win. `x<NNN>` is an external card's
    key, where the `x` is a prefix and not part of the number. A marker with no numeric
    segment falls back to the old leading-token rule so nothing that worked before breaks.
    """
    if fn.endswith(".archived"):
        return ""              # a retired verdict must never count, at any call site
    base = fn
    for kind in (".pass", ".fail"):
        if base.endswith(kind):
            base = base[:-len(kind)]
            break
    else:
        return ""
    for seg in base.split("."):
        m = REVIEW_KEY_RE.match(seg.strip())
        if m:
            return m.group(1)
    return base.split(".", 1)[0].split("-", 1)[0].strip()


def _review_markers(root):
    """{id: 'pass'|'fail'} from docs/reviews/, keyed by the LEADING id of each marker.

    Field- on a live project: markers land as `208.pass`,
    `111-leg2-fe.pass`, `1.report-expert-prior.pass.archived` — so the id is the token
    before the first '.' with any '-suffix' trimmed, and `.archived` markers are retired
    and must not count. Doctrine says reviews key on the platform `task_id`, but ids die
    per session, so in practice the durable `#NNN` is what's on disk — match BOTH.
    A pass outranks a fail (rework passed on a later round). The mtime rides along
    because a marker's DATE is the only thing that can tell a real verdict from a
    recycled-id collision (see _attach_l2)."""
    out = {}
    rdir = os.path.join(root, "docs", "reviews")
    try:
        names = os.listdir(rdir)
    except OSError:
        return out
    for fn in names:
        if fn.endswith(".archived"):
            continue
        for kind in ("pass", "fail"):
            if not fn.endswith("." + kind):
                continue
            key = review_key(fn)
            if not key:
                continue
            try:
                ts = os.path.getmtime(os.path.join(rdir, fn))
            except OSError:
                ts = 0.0
            prev = out.get(key)
            if prev is None or (kind == "pass" and prev[0] != "pass") or \
                    (kind == prev[0] and ts > prev[1]):
                out[key] = (kind, ts, os.path.join(rdir, fn))
    return out


def _attach_l2(root, tasks):
    """Stamp each card with its L2 evidence — `l2` = 'pass' | 'fail' | '' — so the
    pipeline can tell three states apart that all render as "review" today:
      · `.pass` on file, not yet done → THROUGH the gate, waiting on the CEO to merge,
      · `.fail` on file             → bounced, the dept is reworking,
      · no marker at all            → says review but was never submitted (the common one:
        7 of 10 review cards on a live board, 2 days old, nobody reviewing them).
    Nothing else in the org reads these files, which is why a card could sit at the gate
    and still draw as 执行.

    A MARKER MUST BE NO OLDER THAN THE CARD'S STAGE CLOCK. Platform task ids restart
    every session, so `49.pass` written in July's session-A attaches to whatever card
    happens to hold task_id 49 in session-B — a card it has never seen. On a live board
    2026-07-26 that was **every single L2 chip on the board**: four cards wearing 已过审
    from markers 5 to 8 days older than the stage they were sitting in, which is exactly
    why a "passed" card still drew at 派工. Comparing the marker's mtime against `since`
    settles it, and it also retires the 0.9.55 ambiguity honestly: a marker predating the
    current stage cannot be a verdict on the current leg, whichever id matched.

    No stage clock to compare against → a durable #NNN is a permanent identity and is
    trusted; a task_id is not, and is refused rather than guessed."""
    marks = _review_markers(root)
    if not marks:
        for t in tasks:
            t.setdefault("l2", "")
        return
    for t in tasks:
        t["l2"] = l2_verdict(marks, re.sub(r"\D", "", t.get("label") or ""),
                             t.get("task_id"), t.get("since"), root)


def _git_out(root, args, stdin=None, timeout=15):
    try:
        p = subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True,
                           input=stdin, timeout=timeout)
    except Exception:
        return ""
    return p.stdout if p.returncode == 0 else ""


def marker_evidence(path):
    """{sha, patch-id, base} recorded inside a review marker, or {}.

    A verdict's subject is a CHANGE, not a moment. Keying validity on clocks made the
    board's own accuracy destructive: `since` re-stamps on every status edit, so recording
    what a card was blocked on invalidated the review written minutes earlier. A patch-id
    is stable across rebase and cherry-pick, so a marker that names one can prove the
    reviewed change is still the change on offer, whatever the clocks say."""
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(4096)
    except OSError:
        return out
    for line in head.splitlines():
        m = re.match(r"\s*(sha|patch-id|patch_id|base)\s*[:=]\s*([0-9a-fA-F]{7,64})\s*$", line)
        if m:
            out[m.group(1).replace("_", "-")] = m.group(2).lower()
    return out


_PID_CACHE = {}          # sha → patch-id: a commit's diff never changes, so it never expires
_SCAN_CACHE = {}         # (root, when) → (expiry, ids): the scan is ~1s, the panel polls


def patch_id_of(root, sha):
    """The stable patch-id of one commit, or "" — invariant across rebase and cherry-pick."""
    if not re.match(r"^[0-9a-f]{7,64}$", str(sha or "")):
        return ""
    key = (root, sha)
    if key in _PID_CACHE:
        return _PID_CACHE[key]
    diff = _git_out(root, ["diff", "%s^!" % sha])
    out = _git_out(root, ["patch-id", "--stable"], stdin=diff) if diff else ""
    _PID_CACHE[key] = out.split()[0].lower() if out.split() else ""
    return _PID_CACHE[key]


def _patch_ids_since(root, when, cap=300, ttl=60.0):
    """Every patch-id reachable from any ref since `when` — one git pipeline, not one call
    per commit, and memoised: it costs about a second on a real repo, `_attach_l2` runs it
    per card, and the panel polls every 1.5 seconds."""
    key = (root, when)
    hit = _SCAN_CACHE.get(key)
    now = time.time()
    if hit and hit[0] > now:
        return hit[1]
    log = _git_out(root, ["log", "--all", "-p", "--format=%H", "-%d" % cap]
                   + (["--since=%s" % when] if when else []), timeout=25)
    out = _git_out(root, ["patch-id", "--stable"], stdin=log, timeout=25) if log else ""
    ids = {l.split()[0].lower() for l in out.splitlines() if l.split()}
    _SCAN_CACHE[key] = (now + ttl, ids)
    return ids


def evidence_holds(root, ev, when=None):
    """True/False when a marker carries usable evidence, None when it carries none.

    None is not a failure — it means "this verdict predates the evidence format", and the
    caller falls back to the clock rule. Every marker written before today is in that
    state, so the fallback is the common path, not the exception."""
    pid = ev.get("patch-id")
    if not pid:
        return None
    sha = ev.get("sha")
    actual = patch_id_of(root, sha) if sha else ""
    if actual and actual == pid:
        return True                      # the reviewed commit is still there, unchanged
    if actual:
        # THE PAIR CONTRADICTS ITSELF: the sha resolves, and its patch-id is not the one
        # recorded beside it. That is not "the change is gone" — it is "this marker's
        # evidence proves nothing", and the two must not be answered the same way.
        #
        # The marker is written by the reviewer, a model transcribing forty hex characters
        # out of a command, so a slip here is silent and permanent. Read as absence it
        # refused a finished card FOREVER and told the office the marker was stale, which
        # sent it hunting a clock bug that did not exist (field: `sha: 016f2a00` recorded
        # against a patch-id belonging to nothing in the repository). Read as absence it
        # would also be claiming to know which of the two fields is the wrong one, and it
        # does not — the sha could be the mistyped half just as easily.
        #
        # So: no usable evidence, exactly like a marker written before this format existed.
        # The clock rule governs, which is what every pre-0.9.72 verdict already relies on.
        return None
    return pid in _patch_ids_since(root, when)   # rebased or cherry-picked: same change


def l2_verdict(marks, num, task_id, since, root=None):
    """'pass' | 'fail' | '' for ONE card — the single rule for reading review evidence.

    It lived inside `_attach_l2`, so the stall sentinel grew its own copy without the date
    test and reported 35 cards 待合并 where this rule confirms 9.
    Three readers of one rule, and the 0.9.61 date fix had reached only this one.

    A durable `#NNN` is a permanent identity and is trusted with no clock to check against;
    a platform `task_id` is not, because ids restart every session and an old marker
    otherwise attaches to whatever card holds that number now."""
    hit, durable = (marks.get(str(num)) if num else None), True
    tid = str(task_id or "").strip()
    if hit is None and tid.isdigit():
        hit, durable = marks.get(tid), False
    if hit is None:
        return ""
    kind, ts = hit[0], hit[1]
    # Evidence first: a marker that names the change it judged does not need a clock, and
    # the clock is the part that kept destroying real verdicts.
    #
    # ONLY FOR A DURABLE MATCH. Evidence answers "is the change this marker judged still on
    # the tree" — a question about FRESHNESS. On a `#NNN` match the identity is settled and
    # freshness is the only thing left in doubt, so evidence is the better answer. On a
    # task_id match the identity is itself a GUESS, and letting evidence override the clock
    # let it overrule the very test that validates the guess: a July marker whose commit is
    # (of course) still on master became a pass for whatever card wears that recycled id
    # today. Field, 2026-08-05: six cards at `todo`, never dispatched, no marker of their
    # own anywhere, all reported 待合并 — ids 117/120/121/129/16/29 against markers 5 days
    # to 7 weeks old whose evidence held perfectly. It also reached the completion gate,
    # where a colliding id would have waved an unreviewed card through.
    # So a guessed identity must satisfy the clock as well; evidence may only REFUSE.
    if root and len(hit) > 2:
        held = evidence_holds(root, marker_evidence(hit[2]),
                              datetime.fromtimestamp(ts - 86400).strftime("%Y-%m-%d"))
        if held is True and durable:
            return kind
        if held is False:
            return ""            # the reviewed change is gone: this judges nothing here
    entered = _stage_ts(since)
    if entered is None:
        return kind if durable else ""
    return kind if ts + RECYCLE_TOLERANCE >= entered else ""


# `since` is minute-precision, so a marker written seconds after the stage was stamped
# can read as microscopically older. The grace absorbs that without softening the real
# test — the collisions this rejects are days out, not minutes.
STAGE_GRACE = 300.0

# How far a marker may predate the card's stage clock and still be a verdict on this leg.
#
# The test rejects two things: a marker from a DIFFERENT card that held this platform id in
# an earlier session, and a pass from an earlier LEG of this card that has since been
# re-dispatched. Both are days out — the field cases were 5 to 8 days older than the stage.
#
# Five minutes was far too tight, because `since` re-stamps on every status change, so the
# clock is a moving target: a genuine verdict written minutes before the CEO recorded
# `blocked_on` read as stale, and **making the board more accurate destroyed a real review**
#. One day separates the two populations cleanly
# without softening the test that matters.
RECYCLE_TOLERANCE = 24 * 3600.0


def _stage_ts(since):
    """`since` → epoch seconds, or None when there is no usable stamp."""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(
                str(since or "").strip().strip('"')[:16 if "%H" in fmt else 10]
                .replace("T", " "), fmt).timestamp()
        except Exception:
            continue
    return None


def _agent_frontmatter(text):
    """Flat dict of a dept brief's leading `---` frontmatter (scalar values only), {}
    when absent. Tolerant of an inline `# comment` on a value (the 0.9.18 field bug)."""
    if not text.startswith("---"):
        return {}
    close = text.find("\n---", 3)
    if close < 0:
        return {}
    fm = {}
    for line in text[3:close].splitlines():
        m = re.match(r"([A-Za-z][\w-]*):\s*(.*)$", line)
        if m:
            v = re.sub(r"\s+#.*$", "", m.group(2)).strip().strip('"').strip("'")
            fm[m.group(1)] = v
    return fm


def load_roster(root):
    return _memo("load_roster:" + root, _mtimes(os.path.join(root, ".claude", "orchestrate.json"), os.path.join(root, ".claude", "agents")), lambda: _load_roster(root))


def _load_roster(root):
    """The department 花名册 for the Departments view. One entry per project dept — a
    `.claude/agents/<handle>.md` file, the design-native registry (same source as
    stop_refute_tally._known_handles; standing agents ship plugin-scope, so they never
    appear here) — carrying the MODEL it runs on (frontmatter `model:`, the truth for
    'what runs this pane'), its role/description, the 分公司 (external) flag, and its
    live card counts. Internal depts first, then 分公司; each alphabetical. [] when none."""
    adir = os.path.join(root, ".claude", "agents")
    try:
        files = sorted(f for f in os.listdir(adir) if f.endswith(".md"))
    except OSError:
        return []
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
    except Exception:
        cfg = {}
    ext = {str(h).strip().lower() for h in (cfg.get("external") or [])}
    try:
        models = load_store(_store_path(root)).get("models") or {}   # live spawn overrides
    except Exception:
        models = {}
    try:
        seats = load_store(_store_path(root)).get("seats") or {}     # 花名 display names
    except Exception:
        seats = {}
    tasks = load_taskboard(root)["tasks"]
    out = []
    for f in files:
        handle = f[:-3]
        try:
            fm = _agent_frontmatter(open(os.path.join(adir, f), encoding="utf-8").read())
        except OSError:
            fm = {}
        cards = [t for t in tasks if (t.get("dept") or "").strip().lower() == handle.lower()]
        default_model = fm.get("model", "")
        live = str((models.get(handle) or {}).get("model") or "")
        names = sorted(
            {str((rec or {}).get("nickname") or (rec or {}).get("name"))
             for sh, rec in seats.items()
             if re.sub(r"-\d+$", "", str(sh)).lower() == handle.lower()
             and ((rec or {}).get("nickname") or (rec or {}).get("name"))}
        )
        # Effective model = the CEO's in-session spawn override if any, else the
        # frontmatter default (which is NOT the truth once overridden — the Boss's call).
        out.append({"handle": handle, "model": live or default_model,
                    "default_model": default_model, "live": bool(live),
                    "role": fm.get("role") or fm.get("description") or "",
                    "external": handle.lower() in ext, "cards": len(cards),
                    "active": len([c for c in cards if c.get("status") in ("doing", "review", "blocked")]),
                    "statuses": [c.get("status") for c in cards],
                    "names": names})
    out.sort(key=lambda d: (d["external"], d["handle"].lower()))
    return out


_BASE_FOLDER_RE = re.compile(r'inFolder\("([^"]+)"\)')


def _base_columns(text):
    """The first table view's column order (its `order:` list) from a .base file."""
    m = re.search(r"(?m)^\s*order:\s*\n((?:[ \t]*-[ \t]*.+\n?)+)", text)
    if not m:
        return []
    return [re.sub(r"^[ \t]*-[ \t]*", "", l).strip()
            for l in m.group(1).splitlines() if l.strip().startswith("-")]


def load_finance(root):
    """The finance ledger for the Finance view — read straight from an Obsidian Base
    (markdown-native, no DB connection). orchestrate.json `finance` names a `docs/…/*.base`
    file; its table view gives the column order and its folder filter gives the rows
    (each note's frontmatter = one period). None when unconfigured or absent, so the tab
    stays hidden on projects without a finance base."""
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
    except Exception:
        return None
    rel = cfg.get("finance")
    if not rel:
        return None
    try:
        btext = open(os.path.join(root, rel), encoding="utf-8").read()
    except Exception:
        return None
    fm = _BASE_FOLDER_RE.search(btext)
    folder = fm.group(1) if fm else os.path.dirname(rel)
    cols = _base_columns(btext)
    rows = []
    try:
        for f in sorted(os.listdir(os.path.join(root, folder))):
            if not f.endswith(".md"):
                continue
            try:
                data = _agent_frontmatter(open(os.path.join(root, folder, f), encoding="utf-8").read())
            except OSError:
                continue
            if data:
                rows.append(data)
    except OSError:
        return None
    if not rows:
        return None
    if cols and all(cols[0] in r for r in rows):
        rows.sort(key=lambda r: r.get(cols[0], ""), reverse=True)   # newest period first
    if not cols:
        cols = list(rows[0].keys())
    return {"name": os.path.splitext(os.path.basename(rel))[0], "folder": folder,
            "columns": cols, "rows": rows}


def load_sot(root):
    """The Dashboard's compass — the SoT's `## Now` section (State · Blocked-on-their ·
    Money). It replaces the retired manual Direction band precisely because the SoT is
    CEO-curated, capped, and re-read every session (the discipline sentinel keeps it from
    going stale), so it never becomes the noise an unmaintained banner did. {now, as_of}
    or None."""
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
        text = open(os.path.join(root, cfg.get("sot", "docs/SoT.md")), encoding="utf-8").read()
    except Exception:
        return None
    m = re.search(r"(?m)^##\s+Now\b[^\n]*\n(.*?)(?=^##\s|\Z)", text, re.S)
    if not m or not m.group(1).strip():
        return None
    hm = re.search(r"(?m)^##\s+Now\b[^\n(]*\(([^)]+)\)", text)
    return {"now": m.group(1).strip(), "as_of": (hm.group(1).strip() if hm else "")}


def load_decisions(root, limit=14):
    return _memo("load_decisions:" + root, _mtimes(os.path.join(root, "docs", "DECISIONS.md"), os.path.join(root, "docs", "CANON.md")), lambda: _load_decisions(root, limit))


def _load_decisions(root, limit=14):
    """The org's decision memory for the Decisions view: recent DECISIONS.md rulings
    (`## <date> · [key] <title>`, newest first — the file is prepend-ordered) and the
    CANON.md topic index (`` `topic` → <pointer> (updated <date>) ``, the settled answer
    for each question). Returns {decisions, canon} or None when neither exists."""
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
    except Exception:
        cfg = {}
    out = {"decisions": [], "canon": [], "decisions_total": 0, "canon_total": 0,
           "recheck_total": 0}
    try:
        dec = open(os.path.join(root, cfg.get("decisions", "docs/DECISIONS.md")), encoding="utf-8").read()
        for m in re.finditer(r"(?m)^##\s+(\d{4}-\d{2}-\d{2})\b[ ·:\-]*(.+)$", dec):
            out["decisions_total"] += 1     # the file's count, not the slice's
            if len(out["decisions"]) >= limit:
                continue
            rest = m.group(2).strip()
            km = re.match(r"\[([^\]]+)\]\s*(.*)", rest)
            out["decisions"].append({"date": m.group(1), "key": km.group(1) if km else "",
                                     "title": (km.group(2).strip() if km else rest)})
    except Exception:
        pass
    # The REGISTRY table — read with canon.py's own parser, never a second one. The
    # panel used to run a bullet regex of its own, which matched nothing in the table
    # and everything in the `## ⚠ Needs re-check` list above it. So "Canon · settled
    # answers" was in fact listing the entries that were NOT settled, and its count was
    # the size of the re-check queue. Clearing that queue emptied the panel, which read
    # as the canon disappearing when it was the opposite.
    try:
        import canon as canonlib
        rows = canonlib.load_rows(os.path.join(root, cfg.get("canon", "docs/CANON.md")))
        out["canon_total"] = len(rows)
        out["recheck_total"] = sum(1 for r in rows if r.get("needs_recheck"))
        for r in rows[:80]:
            out["canon"].append({"topic": r["topic"], "file": r["file"], "dept": r["dept"],
                                 "updated": r["updated"],
                                 "recheck": ", ".join(r.get("needs_recheck") or [])})
    except Exception:
        pass
    return out if (out["decisions"] or out["canon"]) else None


def load_mail(root, limit=30):
    return _memo("load_mail:" + root, _mtimes(os.path.join(root, "docs", "board", "mail")), lambda: _load_mail(root, limit))


def _load_mail(root, limit=30):
    """Mail & Branches view: the 分公司 mail lane (docs/board/mail/*.md frontmatter:
    time·from·to·re·status, newest first — filenames lead with the YYYYMMDD-HHMM stamp)
    plus the branch offices (orchestrate.json `external` depts, badged with their letter
    + unread counts). The WHOLE lane is read (letters are small; the scan is bounded at
    400 files) and the newest `limit` are rendered: a branch's letter/unread counts and
    the lane badge speak for the lane, not for the slice — counting the slice told them a
    75-letter lane held 30. Returns {mail, branches, total} or None."""
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
    except Exception:
        cfg = {}
    mdir = os.path.join(root, cfg.get("board", "docs/board"), "mail")
    every = []
    try:
        for f in sorted(os.listdir(mdir), reverse=True)[:400]:
            if not f.endswith(".md"):
                continue
            try:
                fm = _agent_frontmatter(open(os.path.join(mdir, f), encoding="utf-8").read())
            except OSError:
                continue
            if not (fm.get("to") or fm.get("from")):
                continue  # dead letter (no headers) — the postmaster's problem, not a row
            every.append({"file": f, "from": fm.get("from", ""), "to": fm.get("to", ""),
                          "re": fm.get("re", ""), "time": fm.get("time", ""),
                          "status": fm.get("status", ""),
                          "dept": fm.get("dept", ""), "seat": fm.get("seat", "")})
    except OSError:
        pass
    branches = []
    for h in (cfg.get("external") or []):
        hl = str(h).lower()
        involved = [m for m in every if m["from"].lower() == hl or m["to"].lower() == hl]
        branches.append({"handle": str(h), "letters": len(involved),
                         "unread": len([m for m in involved if (m["status"] or "").lower() == "unread"]),
                         "last": involved[0]["time"] if involved else ""})
    return ({"mail": every[:limit], "branches": branches, "total": len(every)}
            if (every or branches) else None)


def _blank(v):
    """A log cell's placeholder (`—`, `-`) reads as absent, not as a value."""
    v = (v or "").strip()
    return "" if v in ("—", "-", "–") else v


def _backlog_rows(text):
    """The MACHINE history: `log.py`'s append-only table
    (`| date | id | dept | task | status | sha | note |`). Every completion since the
    task-log existed lands here — the hand-written `> **✅ DONE**` prose blocks below
    are the pre-table era and stopped being written. Reading only the prose (which is
    what the panel did) froze the Archive at the last hand-written entry while hundreds
    of real rows piled up underneath, so 0.9.46's whole point — completions reaching
    BACKLOG with or without the task widget — never showed on the board."""
    out = []
    for m in re.finditer(r"(?m)^\|\s*(\d{4}-\d{2}-\d{2})\s*\|(.*?)\|?\s*$", text):
        # `log.py` escapes a literal pipe inside a cell as `\|` — split on the unescaped ones.
        cells = [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", m.group(2))]
        cells += [""] * (6 - len(cells))
        title = _blank(cells[2])
        if not title:
            continue  # a row with no task names nothing — the card-less bookkeeping line
        out.append({"date": m.group(1), "task_id": _blank(cells[0]), "dept": _blank(cells[1]),
                    "title": title, "status": _blank(cells[3]) or "done",
                    "sha": _blank(cells[4]), "note": _blank(cells[5])})
    return out


def _backlog_prose(text):
    """The pre-table era: `> **✅ DONE — <title>** (<dept, sha, …, date>) — …`."""
    out = []
    for m in re.finditer(r"(?m)^>\s*\*\*✅\s*DONE\s*[—:-]\s*(.+?)\*\*\s*(?:\(([^)]*)\))?", text):
        meta = (m.group(2) or "").strip()
        dm = re.search(r"(\d{4}-\d{2}-\d{2})", meta)
        # the meta is `(<dept>, <sha>, …)` OR `(<topic-key>, <dept>, <sha>, …)` — the
        # dept is the first Capitalised token (Ops · Backend-IO); a lowercase-hyphen
        # topic-key or a hex sha never matches, so it is never mislabelled a dept.
        dept = next((p.strip() for p in meta.split(",")
                     if re.match(r"^[A-Z][A-Za-z][A-Za-z_-]*$", p.strip())), "")
        out.append({"title": m.group(1).strip(), "dept": dept, "task_id": "",
                    "date": (dm.group(1) if dm else ""), "status": "done",
                    "sha": "", "note": ""})
    return out


def _card_key(title):
    """The durable `#NNN` a history line is about — the identity a row is deduped on
    (the same task can hold a machine row AND a hand-written block from the old era)."""
    m = re.match(r"\s*#(\d+)\b", title or "")
    return m.group(1) if m else ""


def load_archive(root, limit=40):
    return _memo("load_archive:" + root, _mtimes(os.path.join(root, "docs", "BACKLOG.md"), os.path.join(root, "docs", "board")), lambda: _load_archive(root, limit))


def _load_archive(root, limit=40):
    """Archive view: finished-work history — the taskboard's Recently-shipped tail plus
    BACKLOG.md, newest first. BACKLOG carries two eras (machine table + legacy prose);
    both are read and merged, machine rows winning a `#NNN` collision because they carry
    the sha and the review note. `total` is the honest count behind the `limit` slice.
    Returns {shipped, backlog, total} or None."""
    shipped = load_taskboard(root).get("shipped", [])
    backlog = []
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
        text = open(os.path.join(root, cfg.get("backlog", "docs/BACKLOG.md")), encoding="utf-8").read()
        rows = _backlog_rows(text)
        seen = {_card_key(r["title"]) for r in rows if _card_key(r["title"])}
        rows += [p for p in _backlog_prose(text)
                 if not (_card_key(p["title"]) and _card_key(p["title"]) in seen)]
        # newest first; an undated legacy block sorts last rather than posing as today's.
        backlog = sorted(rows, key=lambda r: r.get("date") or "", reverse=True)
    except Exception:
        pass
    return ({"shipped": shipped, "backlog": backlog[:limit], "total": len(backlog)}
            if (shipped or backlog) else None)


# ---------------------------------------------------------------- project root
def main_checkout(d):
    """Linked git worktrees check out their own copy of .claude/orchestrate.json, so a
    pane running inside one would get a PRIVATE board — its own store, server, port and
    auto-opened tab — that the Boss never watches (asks vanish; the tab freezes when the
    worktree is reaped). A linked worktree's `.git` is a pointer FILE
    (`gitdir: <main>/.git/worktrees/<name>`), so resolve to the main checkout whenever
    that is itself a board project. Fail-open: on any doubt, keep `d`."""
    try:
        gitfile = os.path.join(d, ".git")
        if os.path.isfile(gitfile):
            with open(gitfile, encoding="utf-8") as f:
                target = f.read().strip()
            if target.startswith("gitdir:"):
                gitdir = target.split(":", 1)[1].strip().replace("\\", "/")
                m = re.match(r"(.*)/\.git/worktrees/[^/]+/?$", gitdir)
                if m and os.path.exists(os.path.join(m.group(1), ".claude", "orchestrate.json")):
                    return m.group(1)
    except Exception:
        pass
    return d


def project_root(start=None):
    d = os.path.abspath(start or os.getcwd())
    if os.path.isfile(d):
        d = os.path.dirname(d)
    cur = d
    while True:
        if os.path.exists(os.path.join(cur, ".claude", "orchestrate.json")):
            return main_checkout(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            return d  # no marker -> original dir
        cur = parent


# ---------------------------------------------------------------- runtime / server
_SKIP_SERVER = False  # set True in tests to avoid spawning a server / opening a browser


def proj_hash(root):
    return hashlib.sha1(os.path.abspath(root).encode()).hexdigest()[:10]


def runtime_dir(root):
    d = os.path.join(tempfile.gettempdir(), "clockin-board-" + proj_hash(root))
    os.makedirs(d, exist_ok=True)
    return d


def pidfile(root):
    return os.path.join(runtime_dir(root), "server.pid")


def portfile(root):
    return os.path.join(runtime_dir(root), "port")


def versionfile(root):
    return os.path.join(runtime_dir(root), "version")


def _plugin_version():
    """This script's plugin version (scripts/ is 3 dirs below the plugin root)."""
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "..", "..", ".claude-plugin", "plugin.json")
        return json.load(open(p, encoding="utf-8")).get("version", "")
    except Exception:
        return ""


def _build_stamp():
    """Plugin version + content hash of this file — the staleness key for daemon
    replacement and tab hot-reload. Hash-based so a CODE edit self-deploys exactly like
    a release: no bumping the version for every little change (the alternative was
    per-edit release churn)."""
    try:
        h = hashlib.sha1(open(os.path.abspath(__file__), "rb").read()).hexdigest()[:8]
    except Exception:
        h = "0"
    return "%s+%s" % (_plugin_version(), h)


BUILD = _build_stamp()


# A replaced server must not be replaced straight back. Bounds any residual ping-pong
# to one swap per window, whatever its cause.
BOARD_MIN_LIFE = 20.0


def _recorded_build(root):
    try:
        return open(versionfile(root), encoding="utf-8").read().strip()
    except Exception:
        return ""


def _build_parts(stamp):
    """(version tuple, code hash) from a build stamp like `0.9.77+b8674c33`."""
    ver, _, h = (stamp or "").strip().partition("+")
    return tuple(int(x) for x in re.findall(r"\d+", ver)), h


def _supersedes(mine, theirs):
    """True iff build `mine` should REPLACE a server running build `theirs`.

    Replacement has to be MONOTONIC or two installs fight forever. The plugin runs from
    a VERSIONED cache directory, so a long-running session pins an old copy while a
    newer one exists alongside it. Under the old rule — replace whenever the stamp is
    not mine — each read the other as stale and killed the other's server on every call.
    The port was dead between each kill and bind (the panel's tab showed a refused
    connection), and every call reported that it had started the server, which opened a
    fresh browser tab each time. Both symptoms, one cause.

    So: only a strictly NEWER build replaces; an older one reuses what is running. Same
    version with different code is an edited working copy and should self-deploy — that
    case is bounded by BOARD_MIN_LIFE rather than by ordering, since two edited copies
    of one version cannot be ranked."""
    mv, mh = _build_parts(mine)
    tv, th = _build_parts(theirs)
    if not tv:
        return True                 # unstamped or foreign: ours is the known quantity
    if mv != tv:
        return mv > tv
    return mh != th


def _spawn_build():
    """Build stamp of the code `ensure_server` is about to exec — read FRESH from disk,
    never the module-level `BUILD`.

    `BUILD` is captured at import. That is right for a running daemon (it IS the code it
    is executing) and WRONG for anyone SPAWNING one, because ensure_server execs the
    FILE: the child runs whatever is on disk now, not the parent's in-memory copy.

    Long-lived importers exist — the MCP board channel holds board.py in memory for days
    across every plugin update — so a parent's `BUILD` can name a build that no longer
    exists anywhere on disk. Field-caught 2026-07-29: the version record read
    `0.9.75+<hash>` while every copy on disk was `0.9.81+<other hash>`, i.e. the record
    described a fossil while the server it labelled was running current code.

    A record that lies about what is running is what revives the 0.9.78 bug from the
    other end. The lie always reads as OLD, so every newer install judges the live server
    stale and replaces it; each replacement leaves a window where no server is listening,
    and any ensure_server call landing in that window sees nothing running, reports
    `started`, and opens a fresh browser window. 0.9.78 stopped a REPLACEMENT from
    opening a tab; this stops a stale stamp from manufacturing endless replacements."""
    fresh = _build_stamp()
    return fresh if _build_parts(fresh)[0] else BUILD   # unreadable on disk → in-memory


def _server_age(root):
    try:
        return time.time() - os.path.getmtime(versionfile(root))
    except Exception:
        return 1e9


def derive_port(root):
    h = int(hashlib.sha1(("port:" + os.path.abspath(root)).encode()).hexdigest(), 16)
    return 49152 + (h % (65535 - 49152))


def port_free(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # SO_REUSEADDR so a just-killed server's TIME_WAIT socket doesn't read as busy —
    # without it a restart drifts off the derived port (+1) and orphans every open tab.
    # A LIVE listener still fails the bind, so "busy" stays truthful. The server side
    # already matches (ThreadingHTTPServer sets allow_reuse_address).
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def pick_port(root):
    port = derive_port(root)
    span = 65535 - 49152
    for _ in range(200):
        if port_free(port):
            return port
        port = 49152 + ((port - 49152 + 1) % span)
    return port


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def server_info(root):
    try:
        pid = int(open(pidfile(root)).read().strip())
        port = int(open(portfile(root)).read().strip())
    except Exception:
        return None
    if _pid_alive(pid) and not port_free(port):
        return port
    return None


def _port_holders(port):
    """PIDs listening on the port, via lsof — best-effort (absent/odd platform → [])."""
    try:
        out = subprocess.run(["lsof", "-ti", "tcp:%d" % port, "-sTCP:LISTEN"],
                             capture_output=True, text=True, timeout=3).stdout
        return [int(p) for p in out.split() if int(p) != os.getpid()]
    except Exception:
        return []


def _is_our_board(port, root):
    """True iff the port answers like a Boss-Board server FOR THIS ROOT — the guard
    that keeps zombie reclaim from shooting an innocent process that happens to
    squat the derived port."""
    import urllib.request
    try:
        raw = urllib.request.urlopen("http://127.0.0.1:%d/state.json" % port, timeout=1).read()
        d = json.loads(raw)
        return "entries" in d and d.get("project") == os.path.basename(os.path.abspath(root))
    except Exception:
        return False


def _reclaim_port(port, root):
    """Free the port from a superseded board server whose pidfile generation was
    lost. Field case: a 0.9.6 zombie held the derived port
    for two days — the pidfile pointed elsewhere, so every replacement missed it,
    drifted to +1, and the Boss's open tab (which polls the ZOMBIE) kept it alive
    while each real server, unpolled, idle-reaped itself. Kills only a process
    that answers as this root's board."""
    if port_free(port) or not _is_our_board(port, root):
        return
    for pid in _port_holders(port):
        try:
            os.kill(pid, 15)
        except Exception:
            pass
    for _ in range(40):
        if port_free(port):
            return
        time.sleep(0.05)


def _superseded(root, port):
    """True iff a NEWER install has taken over the record. The idle reaper alone cannot
    retire a stale server: an open tab keeps polling it (immortal) while the freshly
    spawned current one, unpolled, reaps itself — the system converges on serving old
    code. Monotonic like `_supersedes`, so an OLDER install writing the record could
    never make a newer server stand down. Missing record → False (standalone `serve`)."""
    try:
        rec = _recorded_build(root)
        if rec and rec != BUILD and _supersedes(rec, BUILD):
            return True
        if int(open(portfile(root)).read().strip()) != port:
            return True
    except Exception:
        pass
    return False


def ensure_server(root):
    """Return (port, started) — `started` True only when NO live server existed before
    this call, i.e. only when a browser window is actually needed.

    Replacing a live-but-stale server does NOT count as started: a tab is already
    pointing at that port, and the page reloads itself as soon as /state.json answers
    with a different version. Reporting `started` for every replacement is what opened a
    new tab on every update instead of refreshing the one already open.

    The check+spawn window runs under the store lock: two hooks reacting to the same Stop
    event could otherwise both see "no server" and spawn twice — the loser's pidfile then
    points at a dead process, which reads as "no server" and drifts the port next time."""
    replaced = False
    mine = _spawn_build()      # the code about to be exec'd, NOT this process's import
    with _StoreLock(root):
        port = server_info(root)
        if port and (not _supersedes(mine, _recorded_build(root))
                     or _server_age(root) < BOARD_MIN_LIFE):
            return port, False
        if port:
            replaced = True
            # Live but stale (spawned by a previous plugin version) — replace it so an
            # updated plugin never keeps serving the old panel. The page self-reloads
            # once the new server answers with a different version (see PAGE JS).
            try:
                os.kill(int(open(pidfile(root)).read().strip()), 15)
            except Exception:
                pass
            for _ in range(40):
                if port_free(port):
                    break
                time.sleep(0.05)
            _reclaim_port(port, root)          # pidfile pid missed the real holder
        # Reclaim the derived port from any unrecorded predecessor — otherwise the
        # respawn drifts to +1 and every open tab stays orphaned on the old server.
        _reclaim_port(derive_port(root), root)
        port = pick_port(root)
        with open(portfile(root), "w") as f:
            f.write(str(port))
        with open(versionfile(root), "w") as f:
            f.write(mine)          # describes the child, so the record can never lie
        proc = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "serve", "--root", root, "--port", str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, start_new_session=True)
        with open(pidfile(root), "w") as f:
            f.write(str(proc.pid))
    for _ in range(60):
        if not port_free(port):
            break
        time.sleep(0.05)
    return port, not replaced


def board_url(port):
    return "http://127.0.0.1:%d/" % port


def open_url(url):
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", url], check=False)
        elif sys.platform.startswith("win"):
            os.startfile(url)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", url], check=False)
    except Exception:
        pass


PAGE = r"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Boss Board · Needs you</title>
<style>
html { color-scheme: light; }
html.dark { color-scheme: dark; }
* { box-sizing: border-box; }
/* Anthropic theme: ivory page, warm paper surfaces, Claude-coral accent, serif masthead */
body { font: 14px/1.5 -apple-system, "SF Pro Text", Helvetica, "PingFang SC", Arial, sans-serif;
       max-width: 1060px; margin: 0 auto; padding: 26px 24px 48px; color: #1f1e1d;
       background: #f0eee6; }
/* One line, not two stacked. The band was spending a third of the page's height on the
   product's own name above the project's. */
header { padding-bottom: 9px; border-bottom: 1px solid #dcd8cb; margin-bottom: 0; }
.hdr-l { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.brand { font-size: .64rem; font-weight: 600; letter-spacing: .16em; text-transform: uppercase;
         color: #c15f3c; margin: 0; flex: none; }
.bdot { color: #c9c3b4; font-size: .8rem; flex: none; }
h1 { font-family: "Tiempos Text", ui-serif, Georgia, "Songti SC", serif;
     font-size: 1.22rem; font-weight: 600; letter-spacing: 0; margin: 0;
     overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.stamp { color: #87867f; font-size: .76rem; }
h2 { font-size: .74rem; text-transform: uppercase; letter-spacing: .06em; color: #87867f;
     margin: 1.9em 0 .55em; }
.count { display: inline-block; background: #e7e2d5; border-radius: 10px; padding: 0 8px;
         font-size: .7rem; color: #6b6a62; vertical-align: 2px;
         font-family: ui-monospace, "SF Mono", Menlo, monospace; }
[data-k]:focus-visible { outline: 2px solid #c15f3c; outline-offset: 1px; }
/* GitHub-issues-style rows: dot = state, click/Enter to expand */
.row { display: flex; gap: 9px; padding: 8px 4px; border-top: 1px solid #edeae0;
       cursor: pointer; font-size: .82rem; line-height: 1.45; }
.row:first-child { border-top: none; }
.row:hover { background: rgba(193,95,60,.05); }
/* The BASE carries a colour so an unlisted kind can never render an invisible dot.
   Enumerating kinds was the old rule and it silently failed: `ask`, `decide` and
   `sign` are all live in the store, none had a class, and every one of them drew a
   blank where its state marker should be. A default cannot rot the way a list does. */
.dot2 { width: 9px; height: 9px; border-radius: 50%%; margin-top: .45em; flex: none;
        background: #b3ac9b; }
.k-needs, .k-decide, .k-ask { background: #be4b32; }
.k-discuss { background: #6e8ca8; }
.k-info { background: #5b7fa6; }
.k-sign { background: #a8763f; }
/* Refined kinds from the MCP channel. Warm = the Boss must act, cool = they need not. */
.k-decision { background: #be4b32; }
.k-blocker { background: #8f3a26; }
.k-signoff { background: #a8763f; }
.rc { flex: 1; min-width: 0; }
/* Mail columns — tick · sender · subject · date. Only the desk feed (.mrow) takes the
   grid; the task rows (.drow) keep the flex row, since their third slot is a dept chip,
   not a subject. align-items:start so a two-line expansion does not drag the sender and
   the date down with it. */

/* ---- Conversation frame (ported from the approved mockup, 2026-08-03) --------------
   .ib is a FIXED region whose height JS measures; the rail and the thread each scroll
   inside it and the composer never leaves the bottom. The page itself does not scroll. */
.ib.frame { display: grid; grid-template-columns: 232px minmax(0,1fr); }
.rail.convo { overflow-y: auto; min-height: 0; padding-bottom: 12px; }
.rg.live { color: #a2542f; }
.dclear2 { padding: 8px 14px; font-size: .74rem; color: #87867f; }
.convcol { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
.threadwrap { flex: 1; display: flex; flex-direction: column; min-height: 0; position: relative; }
.list.thread { flex: 1; overflow-y: auto; min-height: 0; padding: 14px 18px 20px;
               scroll-behavior: smooth; }
.av { width: 30px; height: 30px; border-radius: 8px; display: grid; place-items: center;
      font: 650 .6rem/1 -apple-system, "SF Pro Text", Helvetica, sans-serif; color: #fff;
      flex: none; letter-spacing: .02em; }
.av.sm { width: 25px; height: 25px; border-radius: 7px; font-size: .55rem; }
.cmid { min-width: 0; }
.cname { font-size: .78rem; font-weight: 600; overflow: hidden; text-overflow: ellipsis;
         white-space: nowrap; }
.crow.quiet .cname { font-weight: 500; color: #6b6a62; }
.crow.quiet .av { opacity: .7; }
.cprev { font-size: .69rem; color: #87867f; overflow: hidden; text-overflow: ellipsis;
         white-space: nowrap; }
.cmeta { display: flex; flex-direction: column; align-items: flex-end; gap: 3px; }
.ctime { font: .61rem/1 ui-monospace, "SF Mono", Menlo, monospace; color: #a8a49a; }
.badge { min-width: 17px; height: 17px; padding: 0 5px; border-radius: 9px; background: #be4b32;
         color: #fff; font: 650 .62rem/17px -apple-system, sans-serif; text-align: center; }
.badge.q { background: #e2ddcf; color: #87867f; }
.more { margin: 5px 12px 0; padding: 6px 0; background: none; border: 0;
        border-top: 1px solid var(--rulesoft, #edeae0);
        font: 600 .69rem/1 -apple-system, sans-serif; color: #a2542f; cursor: pointer;
        text-align: left; width: calc(100%% - 24px); }
.more:hover { text-decoration: underline; }
.chd { display: flex; align-items: center; gap: 9px; padding: 11px 18px;
       border-bottom: 1px solid #edeae0; flex: none; }
.chd .who { font-size: .88rem; font-weight: 650; }
.readnote { font-size: .65rem; color: #87867f; }
.tbody { display: flex; flex-direction: column; gap: 15px; }
/* the sticky pointer to an unanswered ask that has scrolled out of view */
.jump { position: absolute; left: 50%%; transform: translateX(-50%%); z-index: 4;
        display: flex; align-items: center; gap: 8px; max-width: min(540px, 84%%);
        background: #be4b32; color: #fff; border: 0; border-radius: 16px; padding: 7px 14px;
        cursor: pointer; font: 600 .71rem/1.3 -apple-system, sans-serif;
        box-shadow: 0 3px 12px rgba(0,0,0,.17); opacity: 0; pointer-events: none;
        transition: opacity .16s; }
.jump.on { opacity: 1; pointer-events: auto; }
.jump.up { top: 12px; } .jump.down { bottom: 12px; }
.jump .jt { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; opacity: .92; }
.jump .jid { font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: .94em; }
.daymark { align-self: center; font: .62rem/1 ui-monospace, "SF Mono", Menlo, monospace;
           color: #87867f; background: #f0ede3; padding: 5px 11px; border-radius: 10px; }
.msg { display: flex; flex-direction: column; gap: 6px; max-width: 82%%; scroll-margin: 16px; }
/* Read is a state, not a dimmer. Greying the text made a filed message harder to read
   than an unread one; a tick says the same thing and costs nothing. */
/* The read mark sits OUTSIDE the bubble, beside it, level with its bottom edge — the row
   is a flex line so the tick is a sibling of the bubble rather than anything inside it. */
.bubrow { display: flex; align-items: flex-end; gap: 8px; }
.bubrow > .bub { flex: 1; min-width: 0; }
.rdtick { flex: none; display: inline-flex; align-items: center; color: #5f7d55;
          padding-bottom: 9px; }
.rdtick svg { display: block; }
.msg .mhead { font: .63rem/1 ui-monospace, "SF Mono", Menlo, monospace; color: #87867f;
              display: flex; gap: 8px; align-items: baseline; }
.msg .mhead b { color: #6b6a62; font-weight: 600; }
.msg .clock { font-variant-numeric: tabular-nums; }
.flag { font: 650 .6rem/1 -apple-system, sans-serif; text-transform: uppercase;
        letter-spacing: .08em; padding: 3px 6px; border-radius: 5px; }
.via { font-size: .62rem; color: #a8a49a; }
.flag.need { background: #f5e4da; color: #be4b32; }
.flag.done { background: #e8eee0; color: #5f7d55; }
.bub { background: #fff; border: 1px solid #e6e1d4; border-radius: 12px; padding: 12px 15px;
       font-size: .82rem; line-height: 1.6; transition: box-shadow .3s; }
.msg.need .bub { border-left: 3px solid #be4b32; }
.msg.answered .bub { border-left: 3px solid #5f7d55; }
.msg.flash .bub { box-shadow: 0 0 0 3px #f5e4da, 0 0 0 4px #c15f3c; }
.msg .ttl { font-weight: 650; display: block; margin-bottom: 4px; }
/* the Boss's answer, quoting the ask it settled */
.msg.out { align-self: flex-end; align-items: flex-end; max-width: 66%%; }
.msg.out .bub, .msg .msg.out .bub { background: #ece6d6; border-color: transparent; border-left: 0; }
.msg.out .mhead { justify-content: flex-end; }
/* the raiser closing its OWN ask — a note about the item, not a turn in the conversation,
   so it sits quiet and full-width rather than taking either side */
.msg.note { max-width: 100%%; }
.msg.note .bub { background: transparent; border: 0; border-top: 1px dashed #e2dccd;
                 border-radius: 0; padding: 8px 0 2px; color: #87867f; font-size: .76rem; }
.quo { display: block; width: 100%%; text-align: left; background: none; border: 0;
       border-left: 3px solid #d6cdb6; padding: 2px 0 2px 9px; margin: 0 0 7px; cursor: pointer;
       font: inherit; }
.quo .qid { font: 600 .67rem/1.4 ui-monospace, "SF Mono", Menlo, monospace; color: #a2542f;
            display: block; }
.quo .qt { font-size: .74rem; color: #6b6a62; opacity: .85; display: -webkit-box;
           -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
.acts { display: flex; gap: 6px; flex-wrap: wrap; }
.chip { font: 600 .67rem/1 -apple-system, sans-serif; padding: 5px 11px; border-radius: 14px;
        border: 1px solid #d9d4c6; background: #fff; color: #6b6a62; cursor: pointer; }
.chip:hover { border-color: #c15f3c; color: #a2542f; }
.chip.p { border-color: #c15f3c; color: #a2542f; background: #f5e4da; }
.chip.on { border-color: #c15f3c; background: #f0ddd2; color: #a2542f; }
.chip.quiet { color: #9c9a92; border-color: #e5e0d2; }
/* one composer, pinned to the bottom of the thread */
.composer { flex: none; padding: 10px 18px 14px; display: none; }
.composer.on { display: block; }
.cwrap { border: 1px solid #e2dccd; border-radius: 12px; background: #fff; overflow: hidden;
         transition: border-color .13s, box-shadow .13s; }
.cwrap:focus-within { border-color: #c15f3c; box-shadow: 0 0 0 3px #f5e4da; }
.cctx { display: flex; align-items: center; gap: 9px; padding: 8px 13px; font-size: .7rem;
        color: #87867f; background: #f6f2e8; border-bottom: 1px solid #eee9dc; }
.cctx.bound { background: #f5e4da; color: #a2542f; }
.cto { font-weight: 650; font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: .95em; }
.cqt { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; opacity: .8; }
.cx { margin-left: auto; background: none; border: 0; color: inherit; cursor: pointer;
      font-size: .9rem; opacity: .6; padding: 0 2px; line-height: 1; flex: none; }
.cx:hover { opacity: 1; }
.composer .cwrap #ctext { width: 100%%; display: block; border: 0; border-radius: 0;
         background: none; box-shadow: none; outline: none; resize: none;
         padding: 12px 14px 6px; font: .84rem/1.6 -apple-system, "SF Pro Text", Helvetica,
         "PingFang SC", sans-serif; color: #1f1e1d; min-height: 56px; max-height: 190px;
         overflow-y: auto; }
.composer .cwrap #ctext:focus { outline: none; border: 0; box-shadow: none; }
.composer .cwrap #ctext::placeholder { color: #8b897f; }
.crow2 { display: flex; align-items: center; gap: 10px; padding: 4px 11px 9px 14px; }
.chint { font: .67rem/1 ui-monospace, "SF Mono", Menlo, monospace; color: #87867f;
         overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* the shortcut lives ON the button it fires — a separate hint says the same thing twice */
/* One group, pushed right as a unit. Two separate auto margins — one on the hint, one
   inherited by .sendbtn from the tray — split the free space and parked Stage in the
   middle of the row instead of against Send. */
.cbtns2 { margin-left: auto; display: inline-flex; align-items: center; gap: 8px; flex: none; }
.cbtns2 .sendbtn { margin-left: 0; }
.stagebtn { display: inline-flex; align-items: center; gap: 7px; flex: none;
  font: 600 .76rem -apple-system, "SF Pro Text", Helvetica, sans-serif; cursor: pointer;
  border: 1px solid #d9d4c6; background: #faf9f5; color: #4b4a45; border-radius: 8px;
  padding: 8px 13px; }
.stagebtn:hover { border-color: #c15f3c; color: #a2542f; }
.stagebtn kbd { font: .88em/1 ui-monospace, "SF Mono", Menlo, monospace; color: #a8a49a;
  background: none; border: 0; padding: 0; }
.sendbtn { display: inline-flex; align-items: center; gap: 8px; flex: none; }
.sendbtn kbd { font: .9em/1 ui-monospace, "SF Mono", Menlo, monospace;
               background: rgba(255,255,255,.22); border-radius: 4px; padding: 3px 5px; }
html.dark .bub { background: #262422; border-color: #3d3a34; }
html.dark .msg.out .bub { background: #34302a; }
html.dark .msg.note .bub { background: transparent; border-top-color: #3a3730; color: #96938a; }
html.dark .chd, html.dark .cctx { border-color: #3a3730; }
html.dark .cctx { background: #2b2825; }
html.dark .cctx.bound { background: #3a271e; color: #e6a184; }
html.dark .cwrap { background: #232120; border-color: #45423c; }
html.dark .composer .cwrap #ctext { color: #e5e1d6; }
html.dark .stagebtn { background: #232120; border-color: #45423c; color: #b8b5ac; }
html.dark .stagebtn:hover { border-color: #d97757; color: #e09b78; }
html.dark .stagebtn kbd { color: #6f6c64; }
html.dark .chip { background: #232120; border-color: #45423c; color: #b8b5ac; }
html.dark .chip.p, html.dark .chip.on { background: #3a271e; border-color: #d97757; color: #e6a184; }
html.dark .badge.q { background: #38352f; color: #a09789; }
html.dark .daymark { background: #2b2825; color: #8f8b80; }
html.dark .flag.need { background: #3a271e; color: #e0674a; }
html.dark .flag.done { background: #293024; color: #8fae82; }
html.dark .cprev, html.dark .ctime, html.dark .readnote { color: #8f8b80; }

/* ---- Conversations: the rail is who is talking, the pane is their thread ---- */
.av { width: 30px; height: 30px; border-radius: 8px; display: grid; place-items: center;
      font: 650 .62rem/1 -apple-system, "SF Pro Text", Helvetica, sans-serif; color: #fff;
      flex: none; letter-spacing: .02em; }
.av.big { width: 26px; height: 26px; border-radius: 7px; font-size: .58rem; }
.rail.convo .crow { display: grid; grid-template-columns: 30px minmax(0,1fr) auto; gap: 9px;
      align-items: center; padding: 8px 10px; cursor: pointer;
      border-left: 2px solid transparent; border-radius: 0; }
.rail.convo .crow:hover { background: rgba(193,95,60,.06); }
.rail.convo .crow.on { background: rgba(193,95,60,.11); border-left-color: #c15f3c; }
.cmid { min-width: 0; }
.cname { font-size: .78rem; font-weight: 600; overflow: hidden; text-overflow: ellipsis;
         white-space: nowrap; }
.cprev { font-size: .69rem; color: #87867f; overflow: hidden; text-overflow: ellipsis;
         white-space: nowrap; }
.cmeta { display: flex; flex-direction: column; align-items: flex-end; gap: 3px; }
.ctime { font: .62rem/1 ui-monospace, "SF Mono", Menlo, monospace; color: #a8a49a; }
.badge { min-width: 17px; height: 17px; padding: 0 5px; border-radius: 9px; background: #be4b32;
         color: #fff; font: 650 .62rem/17px -apple-system, sans-serif; text-align: center; }
.badge.mute { background: #e2ddcf; color: #87867f; }
.thead { display: flex; align-items: center; gap: 9px; padding: 2px 2px 10px;
         border-bottom: 1px solid #edeae0; margin-bottom: 12px; }
.thead .who { font-size: .88rem; font-weight: 650; }
.troute { margin-left: auto; font: .66rem/1 ui-monospace, "SF Mono", Menlo, monospace;
          color: #87867f; }
.tbody { display: flex; flex-direction: column; gap: 13px; }
.msg { display: flex; flex-direction: column; gap: 5px; max-width: 78%%; }
/* Read is a state, not a dimmer. Greying the text made a filed message harder to read
   than an unread one; a tick says the same thing and costs nothing. */
/* The read mark sits OUTSIDE the bubble, beside it, level with its bottom edge — the row
   is a flex line so the tick is a sibling of the bubble rather than anything inside it. */
.bubrow { display: flex; align-items: flex-end; gap: 8px; }
.bubrow > .bub { flex: 1; min-width: 0; }
.rdtick { flex: none; display: inline-flex; align-items: center; color: #5f7d55;
          padding-bottom: 9px; }
.rdtick svg { display: block; }
.msg .mhead { font: .64rem/1 ui-monospace, "SF Mono", Menlo, monospace; color: #87867f;
              display: flex; gap: 6px; align-items: baseline; }
.msg .mhead b { color: #6b6a62; font-weight: 600; }
.needsflag { color: #be4b32; font-weight: 600; }
.mage { margin-left: auto; }
.bub { background: #fff; border: 1px solid #e6e1d4; border-radius: 11px; padding: 10px 13px;
       font-size: .82rem; line-height: 1.5; }
.msg.needs > .bub { border-left: 3px solid #be4b32; }
.msg .ttl { font-weight: 600; display: block; margin-bottom: 3px; }
/* The Boss's own answer, sitting under the ask it settled — the thread says what was decided
   without opening anything. */
.msg .msg.mine { align-self: flex-end; align-items: flex-end; max-width: 100%%; margin-top: 3px; }
.msg .msg.mine .bub { background: #ece6d6; border-color: transparent; }
.acts { display: flex; gap: 6px; }
.chip { font: 600 .66rem/1 -apple-system, "SF Pro Text", Helvetica, sans-serif; padding: 5px 10px;
        border-radius: 14px; border: 1px solid #d9d4c6; background: #fff; color: #6b6a62;
        cursor: pointer; }
.chip:hover { border-color: #c15f3c; color: #a2542f; }
.chip.p { border-color: #c15f3c; color: #a2542f; background: #f4e3d9; }
.chip.on { border-color: #c15f3c; background: #f0ddd2; color: #a2542f; }
.list.thread .rcompose { margin-top: 6px; }
html.dark .bub { background: #262422; border-color: #3d3a34; }
html.dark .msg .msg.mine .bub { background: #34302a; }
html.dark .thead { border-bottom-color: #3a3730; }
html.dark .chip { background: #232120; border-color: #45423c; color: #b8b5ac; }
html.dark .chip.p { background: #3a271e; border-color: #d97757; color: #e6a184; }
html.dark .chip.on { background: #3a271e; border-color: #d97757; color: #e6a184; }
html.dark .badge.mute { background: #38352f; color: #a09789; }
html.dark .cprev, html.dark .ctime, html.dark .troute { color: #8f8b80; }
html.dark .msg .mhead b { color: #c2c0b6; }
.row.mrow { display: grid; grid-template-columns: 16px 112px minmax(0,1fr) 46px;
            align-items: start; column-gap: 10px; }
.rsel { display: flex; align-items: center; justify-content: center; height: 1.55em; }
.rsel input { cursor: pointer; margin: 0; }
/* The locator: the item id, monospaced so CEO-498 and CEO-4 line up under each other. */
.rid { font-size: .7rem; color: #87867f; overflow: hidden; text-overflow: ellipsis;
       white-space: nowrap; line-height: 1.55;
       font-family: ui-monospace, "SF Mono", Menlo, monospace; }
/* Still live = bold locator. Archived rows and resolved History carry no .nw, so the
   weight alone says what is still waiting. */
.row.mrow.nw .rid { font-weight: 600; color: #6b6a62; }
/* Subject in ink, the rest of the ask trailing in grey on the SAME line. One line
   collapsed: the point of columns is that the eye runs DOWN them. */
.rtp { color: #8f8d84; }
.row.mrow:not(.x) .rt { display: block; white-space: nowrap; overflow: hidden;
                        text-overflow: ellipsis; }
.row.mrow:not(.x) .rt .rtt { font-weight: 500; }
/* brk() breaks the title before every ①-⑳ marker, which is right in an expanded essay and
   fatal in a one-line column — a <br> beats nowrap. Suppress the break, keep the markup. */
.row.mrow:not(.x) .rt br { display: none; }
/* The one item on their desk is the exception: it gets two lines, because it is the row
   they are meant to read rather than scan past. */
.list .row.mrow.hot:not(.x) .rt { display: -webkit-box; -webkit-box-orient: vertical;
                                  -webkit-line-clamp: 2; white-space: normal; }
.row.mrow.x .rtp { display: none; }   /* expanded, the body is rendered in full below */
.rt { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
/* expanded essays need air: looser leading + a gap before the meta line */
.row.x .rt { -webkit-line-clamp: unset; line-height: 1.55; }
.row.x .rm { margin-top: 6px; }
.rm { font-size: .68rem; color: #87867f; margin-top: 2px; }
.rm b { color: #6b6a62; font-weight: 600;
        font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: .95em; }
.rx { display: none; }
.row.x .rx { display: block; margin-top: 2px; }
/* fmt(): structured essay rows — sentence lines, ①-⑳ hanging indents, · list rows */
.fmt > div { margin: .26em 0; }
.fmt > div:first-child { margin-top: .05em; }
.fli { padding-left: 1.25em; text-indent: -1.25em; }
.fdot { padding-left: 1em; position: relative; }
.fdot .fm { position: absolute; left: .12em; color: #c15f3c; font-weight: 600; }
/* expanded kanban card: the clamp swaps for the fielded card (labelled compartments) */
.t .tx { display: none; }
.t.x .tx { display: block; }
.t.x > .sub { display: none; }
.t .tx .dr { margin: 3px 0 1px; }
/* dept chip — deterministic pastel per handle via --dh; unassigned = quiet grey */
.dchip { display: inline-block; font-size: .64rem; font-weight: 600; padding: 1px 7px;
         border-radius: 9px; background: hsl(var(--dh,40),30%%,88%%); color: hsl(var(--dh,40),45%%,30%%); }
.dchip.d0 { background: #eae6d9; color: #8a887f; font-weight: 500; }
/* compartment label — tiny uppercase over a hairline, the fielded-card chrome */
.tl { font-size: .6rem; font-weight: 600; letter-spacing: .14em; text-transform: uppercase;
      color: #a8a49a; margin: .55em 0 .12em; padding-top: .45em; border-top: 1px solid #edeadd; }
.rage { flex: none; font-size: .7rem; color: #87867f; margin-top: .25em;
        font-family: ui-monospace, "SF Mono", Menlo, monospace; }
/* In the mail grid the date is a COLUMN: right-aligned so the digits stack, and on the
   subject's own baseline rather than nudged down by the flex row's margin. */
.row.mrow .rage { text-align: right; margin-top: 0; line-height: 1.45; }
.parked .row { opacity: .6; }
.parked .dot2 { background: #cbc6b9; }
/* Information: fresh verdicts/FYIs stay visible (they're why the column exists);
   resolved history dims and folds behind the History sub-header — collapsed by
   default, fold class on the static h4 so it survives the per-poll re-render. */
.info #hist .row { opacity: .72; }
.info #hist .dot2 { background: #6b9e5f; }
h4.hist { font-size: .68rem; margin: .55em 0 .15em; display: flex; align-items: center;
          gap: 6px; color: #87867f; cursor: pointer; text-transform: uppercase;
          letter-spacing: .06em; }
h4.hist::after { content: '▸'; margin-left: auto; font-size: .82em; }
h4.hist.x::after { content: '▾'; }
h4.hist:not(.x) + div { display: none; }
/* Structured asks: the detail body lives in the expansion; extracted file paths
   get their own quiet row under a hairline so the Boss never hunts inside prose. */
.rx .files { margin-top: 6px; padding-top: 5px; border-top: 1px solid #e9e5d8; font-size: .74rem; }
/* SoT compass — the Dashboard's maintained "where we stand" band (SoT `## Now`),
   replacing the retired manual Direction band. Boxed as a quiet card: it reads as
   live status, not a masthead motto (which is exactly why the old banner went stale). */
.sotband { margin: 2px 0 6px; padding: 14px 16px; border: 1px solid #dfdacc; border-radius: 14px;
  background: #faf9f5; box-shadow: 0 1px 2px rgba(31,30,29,.05); }
.skick { display: flex; align-items: center; gap: 8px; font-size: .64rem; font-weight: 600;
  letter-spacing: .12em; text-transform: uppercase; color: #c15f3c; margin-bottom: 8px; }
.sage { margin-left: auto; letter-spacing: 0; text-transform: none; font-weight: 400; color: #a8a49a; }
.srow { font-size: .82rem; line-height: 1.5; margin: 3px 0; color: #4b4a45; }
/* Collapsed to one line unless clicked (0.9.73) — see sotBand(). */
.sotband { cursor: pointer; }
.sotband:not(.x) { padding: 8px 14px; }
.sotband:not(.x) .skick { margin-bottom: 0; }
.sotband:not(.x) .sfull, .sotband:not(.x) .sage { display: none; }
.sotband.x .sgist { display: none; }
.sgist { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  letter-spacing: 0; text-transform: none; font-weight: 400; color: #6b6a62; font-size: 1.18em; }
.skick::after { content: '▸'; margin-left: 8px; color: #a8a49a; font-size: 1.1em; }
.sotband.x .skick::after { content: '▾'; }
html.dark .sgist { color: #b8b5ac; }
html.dark .skick::after { color: #6f6c64; }
.srow b { color: #1f1e1d; font-weight: 600; }
/* An answered row with a one-line outcome folds to it; the original ask sits
   behind the click, quoted under a hairline. */
.rx .orig { margin: 4px 0 2px; padding-left: 8px; border-left: 2px solid #e2ddd0;
            color: #6b6a62; }
.colempty { text-align: center; padding: 12px 6px 16px; }
.glyph { color: #b6b2a4; margin: .45em 0 .05em; }
html.dark .glyph { color: #6f6d66; }
.chip { display: inline-block; font-size: .72rem; border: 1px solid #d9d4c6; border-radius: 10px;
        padding: 1px 8px; margin: .35em .3em 0 0; color: #6b6a62; }
/* id pills — .pj = the durable project #NNN (coral), .pt = the session task_id (neutral) */
.pill { display: inline-block; font: 600 .68rem ui-monospace, "SF Mono", Menlo, monospace;
        border-radius: 8px; padding: 1px 7px; margin-right: 5px; vertical-align: 1px;
        font-variant-numeric: tabular-nums; }
.pill.pj { background: #f0ddd2; color: #a2542f; }
.pill.pt { background: #eae6d9; color: #6b6a62; }
.pill.px { background: #d9e4ea; color: #3d6a80; }  /* 分公司 branch-office lane */
/* P0 urgent · P1 critical · P2 important · P3 nice-to-have. The words are the whole
   definition — which level a card gets is a judgment, and the judgment is the CEO's. */
/* P0 is the only one that reads as a BADGE — filled, light text — because it is the only
   level that means drop what you are doing. P1–P3 are tints of the same ramp, so the eye
   sorts them without reading them. P0 against P1 as two neighbouring tints (#e0a394 vs
   #e8b4a0) was a distinction only a colour picker could make. */
.pill.pr-0 { background: #a8321a; color: #fff1ec; }
.pill.pr-1 { background: #e8b4a0; color: #7c2d12; }
.pill.pr-2 { background: #f0ddb8; color: #7c5a12; }
.pill.pr-3 { background: #dfe4ea; color: #4d5d70; }
/* A bug is not a priority — a card can be both, so it wears its own tag. */
.pill.bug { background: #efdcd6; color: #8c3a2a; font-weight: 650; }
.chip b { font-variant-numeric: tabular-nums; }
code { font: .85em ui-monospace, "SF Mono", Menlo, monospace;
       background: #eae6d9; border-radius: 4px; padding: 0 4px; }
/* file-path links (served by /file) — quiet accent, long paths wrap anywhere */
a { color: #a2542f; text-decoration: underline; text-decoration-color: rgba(193,95,60,.4);
    text-underline-offset: 2px; overflow-wrap: anywhere; }
a:hover { text-decoration-color: #c15f3c; }
b { font-weight: 600; }
.t .nm, .t .sub { display: -webkit-box; -webkit-box-orient: vertical; overflow: hidden; }
.t .nm { -webkit-line-clamp: 2; }
.t .sub { -webkit-line-clamp: 3; }
.t.x .nm, .t.x .sub { -webkit-line-clamp: unset; }
.t { cursor: pointer; }
.parked .card { opacity: .5; border-left-color: #c7c7cc; }
.empty { color: #98968c; font-style: italic; margin: .3em 0; }
.board { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; align-items: start; }
@media (max-width: 760px) { .board { grid-template-columns: 1fr; } }
.col { border: 1px solid #dfdacc; border-radius: 14px; padding: 12px 14px;
       background: #faf9f5; box-shadow: 0 1px 2px rgba(31,30,29,.05); }
.col.c-todo { background: #ebefe1; }
.col.c-prog { background: #f4ecda; }
.col.c-done { background: #eee9f0; }
.col h3 { font-size: .82rem; margin: .1em 0 .4em; display: flex; align-items: center; gap: 7px; }
.dot { width: 9px; height: 9px; border-radius: 50%%; display: inline-block; border: 2px solid; }
.t { border: 1px solid #e2ddd0; border-radius: 6px; padding: 6px 9px; margin: .35em 0; background: #fffefb; }
.t.s-blocked { background: #f8ece5; }
.t.s-review { background: #f1edf6; }
.tid, .t .tid { font-family: ui-monospace, "SF Mono", Menlo, monospace; }
.t .tid { font-size: .72rem; font-weight: 600; color: #6b6a62; font-variant-numeric: tabular-nums; }
.t .nm { font-size: .84rem; }
.t .sub { font-size: .7rem; color: #87867f; }
.badge { font-size: .66rem; border-radius: 8px; padding: 1px 7px; margin-left: 4px; }
.badge.blocked { background: #f6e0d7; color: #a6452c; }
.badge.review { background: #ebe4f4; color: #7a67a8; }
.done-line { font-size: .76rem; color: #87867f; margin: .35em 0; padding: 6px 9px;
             border: 1px solid #e2ddd0; border-radius: 6px; background: #fffefb;
             cursor: pointer; }
/* clamp on an inner box, not the padded card — clamping the padded element lets a
   sliver of the cropped 3rd line bleed into the bottom padding */
.done-line .dl { display: -webkit-box; -webkit-box-orient: vertical;
                 -webkit-line-clamp: 2; overflow: hidden; }
.done-line.x .dl { -webkit-line-clamp: unset; }
/* Claude dark: warm charcoal, paper surfaces, coral holds the accent. Applied via the
   .dark class — set from the system preference, or pinned with ?theme=light|dark. */
html.dark body { color: #e9e6dd; background: #16150f; }
html.dark header { border-bottom-color: #38352f; }
html.dark .brand { color: #d97757; }
html.dark .col, html.dark .t, html.dark .done-line { border-color: #38352f; box-shadow: none; }
html.dark .done-line, html.dark .col { background: #232120; }
html.dark .row { border-top-color: #322f2a; }
html.dark .row:hover { background: rgba(217,119,87,.07); }
html.dark .dot2 { background: #55524a; }
html.dark .k-needs, html.dark .k-decide, html.dark .k-ask { background: #e08262; }
html.dark .k-sign { background: #cfa06a; }
html.dark .k-discuss { background: #8fa9c4; }
html.dark .k-info { background: #7f9cc0; }
html.dark .k-decision { background: #e08262; }
html.dark .k-blocker { background: #c96a4a; }
html.dark .k-signoff { background: #cfa06a; }
html.dark .parked .dot2 { background: #5c5b57; }
html.dark .info #hist .dot2 { background: #7fae72; }
html.dark h4.hist { color: #8f8b80; }
html.dark .rx .files { border-top-color: #322f2a; }
html.dark .sotband { background: #232120; border-color: #38352f; box-shadow: none; }
html.dark .skick { color: #d97757; }
html.dark .srow { color: #d8d5cc; } html.dark .srow b { color: #e9e6dd; }
html.dark .rx .orig { border-left-color: #45423c; color: #b8b5ac; }
html.dark .col.c-todo { background: #2c312a; }
html.dark .col.c-prog { background: #363023; }
html.dark .col.c-done { background: #322e37; }
html.dark .t { background: #383734; }
html.dark .t.s-blocked { background: #45302a; }
html.dark .t.s-review { background: #3b3444; }
html.dark .stamp, html.dark h2, html.dark .rm, html.dark .rage,
html.dark .t .sub, html.dark .done-line, html.dark .empty { color: #8f8b80; }
html.dark .rm b, html.dark .t .tid { color: #c2c0b6; }
html.dark .seats { border-color: #3d3a34; }
html.dark .seathd { background: #2e2b26; color: #8f8b80; }
html.dark .seat { border-top-color: #3a3730; }
html.dark .seatn { color: #ded9cd; }
html.dark .seatc, html.dark .seatt { color: #8f8b80; }
html.dark .seatk { background: #38352f; color: #b8b5ac; }
html.dark .seatk.s-ceo { background: #452f24; color: #e09b78; }
html.dark .seatk.s-branch { background: #2a3540; color: #86b6cf; }
html.dark .more { border-top-color: #37332d; }
html.dark .rid { color: #8f8b80; }
html.dark .row.mrow.nw .rid { color: #c2c0b6; }
html.dark .rtp { color: #8a877e; }
html.dark .count { background: #38352f; color: #b8b5ac; }
html.dark .chip { border-color: #45423c; color: #b8b5ac; }
html.dark .pill.pj { background: #453026; color: #e09b78; }
html.dark .pill.pt { background: #3a3935; color: #b8b5ac; }
html.dark .pill.px { background: #263c48; color: #86b6cf; }
html.dark .pill.pr-0 { background: #c03d20; color: #fff1ec; }
html.dark .pill.pr-1 { background: #4a2318; color: #f0a284; }
html.dark .pill.pr-2 { background: #453a1c; color: #dcc27a; }
html.dark .pill.pr-3 { background: #2a3540; color: #9fb4c9; }
html.dark .pill.bug { background: #43261f; color: #e8a08c; }
html.dark .fdot .fm { color: #e09b78; }
html.dark .dchip { background: hsl(var(--dh,40),20%%,27%%); color: hsl(var(--dh,40),35%%,76%%); }
html.dark .dchip.d0 { background: #3a3935; color: #8f8d85; }
html.dark .tl { color: #6f6c64; border-top-color: #322f2a; }
html.dark code { background: #38352f; }
html.dark a { color: #e08262; text-decoration-color: rgba(224,130,98,.4); }
html.dark a:hover { text-decoration-color: #e08262; }
html.dark .badge.blocked { background: #4a2a20; color: #e08262; }
html.dark .badge.review { background: #3a3050; color: #c4b3e8; }
html.dark [data-k]:focus-visible { outline-color: #d97757; }
/* ---- interactive desk: reply/ask affordances, outbox tray, composer, toast ---- */
.rowbtns { display: flex; gap: 6px; margin-top: 6px; }
.bbtn { font: 600 .66rem -apple-system, "SF Pro Text", Helvetica, sans-serif; border: 1px solid #d9d4c6;
        background: #faf9f5; color: #6b6a62; border-radius: 7px; padding: 2px 10px; cursor: pointer; }
.bbtn:hover { border-color: #c15f3c; color: #a2542f; }
.bbtn.staged { border-color: #c15f3c; background: #f0ddd2; color: #a2542f; }
/* Archive is filing, not an answer — it must not compete with Reply/Ask for the eye. */
.bbtn.quiet { color: #9c9a92; border-color: #e5e0d2; }
.bbtn.quiet:hover { color: #6b6a62; border-color: #cfc9b8; }
.l2 { font-size: 11px; padding: 1px 7px; border-radius: 999px; margin-left: 5px; letter-spacing: .02em; }
.l2p { background: #dce9d7; color: #4b7a3d; } .l2f { background: #f0ddb8; color: #8a6a1e; }
.l2n { background: #e8e4dc; color: #7d7566; }
html.dark .l2p { background: #2c3a26; color: #9cc78a; } html.dark .l2f { background: #453a1c; color: #dcc27a; }
html.dark .l2n { background: #33302b; color: #a09789; }
.row.rd { opacity: .5; }
.row.rd:hover { opacity: .85; }
body.haspanel { padding-bottom: 108px; }   /* clear the fixed bottom bar */
#tray { position: fixed; left: 0; right: 0; bottom: 0; z-index: 20; display: none;
        background: #faf9f5; border-top: 1px solid #dcd8cb; box-shadow: 0 -2px 12px rgba(31,30,29,.07);
        padding: 11px 24px 14px; }
#tray.on { display: block; }
.trayhd { display: flex; align-items: center; gap: 10px; max-width: 1060px; margin: 0 auto; }
#traycount { font-size: .74rem; color: #87867f; }
/* Where Send will land, named before they click. The old tray said "Send to session" and
   left their to find out which session afterwards. */
#traytarget { font-size: .7rem; color: #87867f; flex: 1; min-width: 0; overflow: hidden;
              text-overflow: ellipsis; white-space: nowrap; }
#traytarget b { color: #6b6a62; font-weight: 600; }
#traytarget.bad { color: #be4b32; }
#traytarget.bad b { color: #be4b32; }
.seatpick { margin-left: 8px; color: #c15f3c; cursor: pointer; text-decoration: underline;
            text-underline-offset: 2px; }
/* The seat picker: every live claude pane, labelled main / 分公司 / other. */
.seats { display: none; max-width: 1060px; margin: 8px auto 0; border: 1px solid #e2ded1;
         border-radius: 8px; overflow: hidden; }
.seats.on { display: block; }
.seathd { font-size: .66rem; text-transform: uppercase; letter-spacing: .08em;
          color: #87867f; padding: 7px 10px; background: #f4f1e8; }
.seat { display: grid; grid-template-columns: 58px minmax(0,1fr) minmax(0,1.1fr) 92px;
        gap: 10px; align-items: center; padding: 7px 10px; font-size: .74rem;
        cursor: pointer; border-top: 1px solid #edeae0; }
.seat:hover { background: rgba(193,95,60,.06); }
.seat.on { background: rgba(193,95,60,.11); }
.seatk { font-size: .62rem; font-weight: 600; text-align: center; padding: 1px 0;
         border-radius: 9px; background: #eae6d9; color: #8a887f; }
.seatk.s-ceo { background: #e8ddd2; color: #9a5c3c; }
.seatk.s-branch { background: #dfe4ea; color: #5a6b80; }
.seatk.s-dept { background: #e6e2d4; color: #7a7768; }
.seatn { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #40403a; }
.seata { font-size: .62rem; color: #87867f; }
.seatc, .seatt { overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
                 color: #87867f; font-family: ui-monospace, "SF Mono", Menlo, monospace;
                 font-size: .68rem; }
.traylist { max-width: 1060px; margin: 8px auto 0; display: flex; flex-wrap: wrap; gap: 6px; }
.tchip { display: inline-flex; align-items: center; gap: 6px; font-size: .74rem; max-width: 360px;
         background: #f0eee6; border: 1px solid #e2ddd0; border-radius: 9px; padding: 2px 5px 2px 9px; }
.tchip .tk { font: 600 .64rem ui-monospace, "SF Mono", Menlo, monospace; color: #a2542f; flex: none; }
.tchip.ask .tk { color: #3d6a80; }
.tchip .tt { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #4b4a45; }
.tchip .tx2 { cursor: pointer; color: #a8a49a; padding: 0 3px; flex: none; }
.tchip .tx2:hover { color: #be4b32; }
.sendbtn { margin-left: auto; font: 600 .82rem -apple-system, sans-serif; border: none; cursor: pointer;
           background: #c15f3c; color: #fff; border-radius: 8px; padding: 7px 18px; }
.sendbtn:hover { background: #a2542f; }
/* ---- the reply box, INLINE in the row it answers (0.9.76) ------------------------
   It used to be a bar fixed to the foot of the window: a chat composer, which is the
   right shape for one conversation and the wrong shape for replying to one item in a
   list. Being anchored to the WINDOW rather than to the thing being answered, it sat
   on top of the row it belonged to (hence a quote line, to re-show what it covered),
   it needed the page's bottom padding measured to it, and under zoom it stranded
   itself away from its own subject. In the row it is ordinary: it opens underneath the
   ask, pushes the list down, scrolls with the page, and cannot be separated from the
   question because the question is the line above it. */
.rcompose { margin: 9px 0 3px; cursor: default; }
.rcompose #ctext { width: 100%%; min-height: 46px; max-height: 260px; resize: vertical;
         font: inherit; font-size: .86rem; color: inherit; padding: 9px 11px;
         border: 1px solid #d9d4c6; border-radius: 8px; background: #faf9f5; display: block;
         overflow-y: auto; }
.rcompose #ctext:focus { outline: 2px solid #c15f3c; outline-offset: 1px; border-color: #c15f3c; }
.cbtns { display: flex; gap: 8px; margin-top: 9px; align-items: center; }
.cbtns button { font: 600 .8rem -apple-system, sans-serif; border: 1px solid #d9d4c6; background: #faf9f5;
                color: #4b4a45; border-radius: 8px; padding: 6px 16px; cursor: pointer; }
.cbtns .primary { background: #c15f3c; color: #fff; border-color: #c15f3c; }
.cbtns .primary:hover { background: #a2542f; }
.cbtns button:disabled { opacity: .45; cursor: default; }
.cnote { font-size: .7rem; color: #a8a49a; margin-top: 7px; }
html.dark .cnote { color: #6f6c64; }
.ckeys { margin-left: auto; font-size: .7rem; color: #a8a49a; white-space: nowrap; }
.ckeys kbd { font: inherit; color: #6b6a62; background: #f0eee6; border: 1px solid #e2ddd0;
             border-radius: 4px; padding: 0 4px; margin: 0 1px; }
html.dark .ckeys kbd { color: #b8b5ac; background: #2c2a25; border-color: #45423c; }
@media (max-width: 620px) { .ckeys { display: none; } }
html.dark .ckeys { color: #6f6c64; }
#toast { position: fixed; bottom: 18px; left: 50%%; transform: translateX(-50%%); z-index: 40;
         max-width: 82vw; text-align: center; background: #1f1e1d; color: #f0eee6; font-size: .78rem;
         padding: 9px 16px; border-radius: 9px; opacity: 0; transition: opacity .22s; pointer-events: none; }
#toast.on { opacity: .96; }
html.dark .bbtn { background: #232120; border-color: #45423c; color: #b8b5ac; }
html.dark .bbtn:hover { border-color: #d97757; color: #e09b78; }
html.dark .bbtn.staged { background: #453026; border-color: #d97757; color: #e09b78; }
html.dark #tray { background: #232120; border-top-color: #38352f; }
html.dark #traycount { color: #8f8b80; }
html.dark .tchip { background: #383734; border-color: #45423c; }
html.dark .tchip .tt { color: #d8d5cc; }
html.dark #ctext { background: #232120; border-color: #45423c; }
html.dark .cbtns button { background: #232120; border-color: #45423c; color: #d8d5cc; }
html.dark .cbtns .primary { background: #c15f3c; border-color: #c15f3c; color: #fff; }
html.dark #toast { background: #0d0d0c; color: #e9e6dd; }
/* ---- dashboard: tab bar ---- */
nav.tabs { display: flex; gap: 2px; margin: 4px 0 20px; border-bottom: 1px solid #dcd8cb; }
nav.tabs button { font: 600 .82rem -apple-system, "SF Pro Text", Helvetica, sans-serif; background: none;
  border: none; cursor: pointer; padding: 8px 15px; color: #87867f; border-bottom: 2px solid transparent;
  margin-bottom: -1px; }
nav.tabs button:hover { color: #1f1e1d; }
nav.tabs button.on { color: #a2542f; border-bottom-color: #c15f3c; }
section.tabpane { display: none; }
section.tabpane.on { display: block; }
html.dark nav.tabs { border-bottom-color: #38352f; }
html.dark nav.tabs button { color: #8f8b80; }
html.dark nav.tabs button:hover { color: #e9e6dd; }
html.dark nav.tabs button.on { color: #e09b78; border-bottom-color: #d97757; }
/* ---- Dashboard: the desk as an INBOX (0.9.73) -------------------------------------
   Three columns and a four-tile monitor became one list beside a rail of counts.
   The grid gave the emptiest column a third of the width while the fullest one set
   the page height, so the ordinary state — nothing to answer against a full feed of
   notices — drew two screens of blank canvas next to a narrow ribbon of text, and the
   one thing that needed a decision was the SMALLEST object on the page. One list cannot
   have an empty column; the rail puts every count that used to cost a tab switch on the
   same screen; and the tiles are gone because four numbers, three of them usually zero,
   were the first thing on the page. The rail's Work group is a PARTITION of the header's
   in-flight number (doing + review + 待合并 + blocked), so the two can never disagree —
   the tile and the header used to answer the same question with different numbers. */
.ib { display: grid; grid-template-columns: 190px 1fr; margin: 16px 0 0;
  border: 1px solid #dfdacc; border-radius: 13px; overflow: hidden; background: #faf9f5; }
@media (max-width: 700px) { .ib { grid-template-columns: 1fr; }
  .rail { display: flex; flex-wrap: wrap; border-right: none; border-bottom: 1px solid #e5e0d2; } }
.rail { background: #f4f2ea; border-right: 1px solid #e5e0d2; padding: 10px 0 16px; }
.rg { font-size: .6rem; text-transform: uppercase; letter-spacing: .13em; color: #a8a49a;
  padding: 13px 14px 5px; width: 100%%; }
.rg:first-child { padding-top: 3px; }
.rf { display: flex; align-items: center; gap: 8px; padding: 5px 14px; font-size: .8rem;
  color: #4b4a45; cursor: pointer; border-left: 2px solid transparent; }
.rf:hover { background: rgba(193,95,60,.06); }
.rf.on { background: #f6ece6; border-left-color: #c15f3c; color: #1f1e1d; font-weight: 600; }
.rf .rd2 { width: 7px; height: 7px; border-radius: 50%%; flex: none; background: #cbc6b9; }
.rf.hot .rd2 { background: #c15f3c; }
.rf .n { margin-left: auto; font: .72rem ui-monospace, "SF Mono", Menlo, monospace;
  color: #87867f; font-variant-numeric: tabular-nums; }
.rf.on .n { color: #a2542f; }
/* A grid item defaults to min-width:auto, so a 1fr column refuses to shrink below its
   content and every row runs out under the container's clipped edge. */
.list { min-width: 0; min-height: 360px; }
.dsplit { padding: 5px 15px; font-size: .6rem; letter-spacing: .13em; text-transform: uppercase;
  color: #a8a49a; background: #f4f2ea; border-top: 1px solid #e5e0d2; border-bottom: 1px solid #e5e0d2; }
.dclear { display: flex; align-items: center; gap: 9px; padding: 10px 15px; font-size: .84rem;
  color: #5c7f52; background: #f2f6ef; }
.dclear .m { margin-left: auto; color: #8aa082; font-size: .76rem; }
.dmore { padding: 8px 15px; font-size: .72rem; color: #87867f; border-top: 1px solid #edeae0; }
/* Rows in the list: ONE line collapsed, meta and controls behind the click. An FYI
   showed three redundant fields (widget id, a dept that is the same 12 times in 14,
   a kind already carried by the dot) on every row — that repetition was the density. */
.list .row { padding: 7px 15px; border-top: 1px solid #edeae0; }
.list .row:first-child { border-top: none; }
.list .row .rt { -webkit-line-clamp: 1; }
.list .row:not(.x) .rm { display: none; }
.list .row:not(.x) .rowbtns { visibility: hidden; margin-top: 0; height: 0; overflow: hidden; }
.list .row:not(.x):hover .rowbtns { visibility: visible; height: auto; margin-top: 5px; }
.list .row.x .rt { -webkit-line-clamp: unset; }
/* A live ask keeps its verb visible and its title at heading size: it is the one row
   they are meant to ACT on, and the old board gave it the same weight as an FYI. */
.list .row.hot { background: #fbf1eb; padding: 12px 15px 12px 12px; border-left: 3px solid #c15f3c; }
.list .row.hot .rt { -webkit-line-clamp: 2; font-size: .96rem; font-weight: 500; line-height: 1.4; }
.list .row.hot .rowbtns { visibility: visible; height: auto; margin-top: 7px; }
.list .row.hot .dot2 { width: 8px; height: 8px; }
.drow .tid { font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: .92em; color: #6b6a62; }
.k-task { background: #b3ac9b; }
html.dark .ib { background: #1c1b16; border-color: #38352f; }
html.dark .rail { background: #191813; border-right-color: #2c2a25; }
html.dark .rg { color: #6f6c64; }
html.dark .rf { color: #b8b5ac; }
html.dark .rf:hover { background: #201f19; }
html.dark .rf.on { background: #221c18; border-left-color: #d97757; color: #f3f0e7; }
html.dark .rf .rd2 { background: #4a4741; }
html.dark .rf.hot .rd2 { background: #e08262; }
html.dark .rf .n { color: #8f8b80; } html.dark .rf.on .n { color: #e09b78; }
html.dark .dsplit { color: #6f6c64; background: #191813; border-color: #2c2a25; }
html.dark .dclear { color: #86a67c; background: #1b201a; }
html.dark .dclear .m { color: #6f7a6b; }
html.dark .list .row { border-top-color: #262420; }
html.dark .list .row.hot { background: #241d18; border-left-color: #d97757; }
html.dark .dmore { color: #8f8b80; border-top-color: #262420; }
html.dark .drow .tid { color: #b8b5ac; }
html.dark .k-task { background: #55524a; }
/* ---- Departments 花名册: one card per dept, showing the model it runs on ---- */
.depts { display: grid; grid-template-columns: repeat(auto-fill, minmax(238px, 1fr)); gap: 12px; }
.dept { border: 1px solid #dfdacc; border-radius: 14px; padding: 13px 15px; background: #faf9f5;
  transition: border-color .15s, transform .1s, box-shadow .15s; }
.dept:hover { border-color: #c15f3c; transform: translateY(-2px); box-shadow: 0 6px 20px rgba(31,30,29,.09); }
html.dark .dept:hover { border-color: #d97757; box-shadow: 0 6px 22px rgba(0,0,0,.45); }
.dept { box-shadow: 0 1px 2px rgba(31,30,29,.05); }
.depts { --gap: 12px; }
.dhd { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; }
.drole { font-size: .74rem; color: #6b6a62; margin: 7px 0 2px; line-height: 1.45;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
.dstats { font-size: .7rem; color: #87867f; margin-top: 8px; display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
.mpill { margin-left: auto; font: 600 .64rem ui-monospace, "SF Mono", Menlo, monospace; padding: 2px 8px;
  border-radius: 8px; letter-spacing: .02em; }
.m-opus { background: #e7d7f0; color: #6d3d94; } .m-sonnet { background: #d9e4ea; color: #3d6a80; }
.m-haiku { background: #dce9d7; color: #4b7a3d; } .m-fable { background: #f0ddb8; color: #8a6a1e; }
.m-other { background: #eae6d9; color: #6b6a62; } .m-none { background: #ece9df; color: #a8a49a; font-weight: 500; }
.stpill { font-size: .64rem; padding: 1px 7px; border-radius: 7px; background: #ece8dc; color: #6b6a62; }
.stpill.st-doing { background: #f4ecda; color: #8a6420; } .stpill.st-review { background: #ece4f4; color: #6f56a0; }
.stpill.st-blocked { background: #f6e0d7; color: #a6452c; } .stpill.st-todo { background: #e7eadf; color: #5f7a50; }
html.dark .dept { background: #232120; border-color: #38352f; box-shadow: none; }
html.dark .drole { color: #b8b5ac; } html.dark .dstats { color: #8f8b80; }
html.dark .m-opus { background: #3a2c47; color: #c9a9e0; } html.dark .m-sonnet { background: #263c48; color: #86b6cf; }
html.dark .m-haiku { background: #2c3a26; color: #9cc78a; } html.dark .m-fable { background: #453a1c; color: #dcc27a; }
html.dark .m-other { background: #3a3935; color: #b8b5ac; } html.dark .m-none { background: #333230; color: #6f6c64; }
html.dark .stpill { background: #3a3935; color: #b8b5ac; }
html.dark .stpill.st-doing { background: #363023; color: #dcc27a; } html.dark .stpill.st-review { background: #322c40; color: #c4b3e8; }
html.dark .stpill.st-blocked { background: #45302a; color: #e08262; } html.dark .stpill.st-todo { background: #2c312a; color: #9cbf8a; }
.mlive { margin-left: 5px; font-size: .8em; font-weight: 700; opacity: .7; text-transform: uppercase; letter-spacing: .04em; }
.msrc { font-size: .64rem; color: #a8a49a; margin-top: 6px; font-family: ui-monospace, "SF Mono", Menlo, monospace; }
html.dark .msrc { color: #6f6c64; }
/* ---- Finance: the Obsidian-Base ledger rendered as a table ---- */
.fmeta { font-size: .72rem; color: #87867f; margin-bottom: 12px; }
.ftable { overflow-x: auto; border: 1px solid #dfdacc; border-radius: 14px; background: #faf9f5;
  box-shadow: 0 1px 2px rgba(31,30,29,.05); }
.ftable table { border-collapse: collapse; width: 100%%; font-size: .82rem; }
.ftable th { text-align: left; font-size: .63rem; text-transform: uppercase; letter-spacing: .07em;
  color: #87867f; font-weight: 600; padding: 10px 14px; border-bottom: 1px solid #e2ddd0; white-space: nowrap; }
.ftable td { padding: 9px 14px; border-bottom: 1px solid #edeae0; white-space: nowrap; }
.ftable tr:last-child td { border-bottom: none; }
.ftable td.num { text-align: right; font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-variant-numeric: tabular-nums; }
.ftable .e { color: #c7c3b6; }
html.dark .ftable { background: #232120; border-color: #38352f; box-shadow: none; }
html.dark .ftable th { color: #8f8b80; border-bottom-color: #38352f; }
html.dark .ftable td { border-bottom-color: #322f2a; }
html.dark .fmeta { color: #8f8b80; }
/* ---- Decisions / Canon: recent rulings + the settled-answer index ---- */
/* minmax(0,1fr) not 1fr: a long unbroken topic-key gave the left column a huge
   min-content, squishing it to a sliver and char-wrapping the key (Boss 2026-07-22). */
.dcol2 { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 22px; align-items: start; }
@media (max-width: 720px) { .dcol2 { grid-template-columns: 1fr; } }
.dsub { font-size: .74rem; text-transform: uppercase; letter-spacing: .06em; color: #87867f;
  margin: 0 0 .7em; font-weight: 600; }
.panel { border: 1px solid #dfdacc; border-radius: 14px; background: #faf9f5; padding: 6px 15px 12px;
  box-shadow: 0 1px 2px rgba(31,30,29,.05); }
html.dark .panel { background: #232120; border-color: #38352f; box-shadow: none; }
.panel .dsub { margin-top: 12px; }
.dec { border-top: 1px solid #edeae0; padding: 9px 2px; }
.dec:first-of-type { border-top: none; }
.dech { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }
.decdate { font: 600 .68rem ui-monospace, "SF Mono", Menlo, monospace; color: #87867f; font-variant-numeric: tabular-nums; }
.deckey { font: 600 .63rem ui-monospace, "SF Mono", Menlo, monospace; background: #f0ddd2; color: #a2542f;
  border-radius: 7px; padding: 1px 7px; min-width: 0; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; max-width: 100%%; }
.dectitle { font-size: .8rem; line-height: 1.45; color: #4b4a45;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
/* The topic key is the INDEX — it is what they scan the canon by, so it holds a column
   of its own and wraps; only the prose pointer gives up width. (It used to shrink first
   and ellipse, which cut exactly the identifying half: `citely-cn…`, `pp-d…`.) */
/* A registry row is a QUESTION and the file that answers it. The topic used to be a
   short kebab key and wore monospace; it is a full sentence now, so it leads the row in
   the body font and the pointer drops to a quiet monospace tail. */
.cx { display: flex; flex-wrap: wrap; gap: 5px 10px; align-items: baseline;
  padding: 7px 2px; border-top: 1px solid #edeae0; font-size: .75rem; }
.cx:first-of-type { border-top: none; }
.ctopic { flex: 1 1 20em; min-width: 0; font-size: .82rem; font-weight: 500; color: #1f1e1d; }
.cptr { color: #87867f; min-width: 0; overflow-wrap: anywhere;
  font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: .7rem; }
.cupd { color: #a8a49a; white-space: nowrap; font-variant-numeric: tabular-nums; margin-left: auto; }
.crecheck, .cwarnc { background: #f6e4db; color: #a2542f; border-radius: 7px; padding: 0 6px;
  font-size: .66rem; white-space: nowrap; font-weight: 600; }
.cx.cwarn .ctopic { color: #a2542f; }
html.dark .ctopic { color: #e9e6dd; }
html.dark .cptr { color: #8f8b80; }
html.dark .crecheck, html.dark .cwarnc { background: #45302a; color: #e09b78; }
html.dark .cx.cwarn .ctopic { color: #e09b78; }
html.dark .dsub { color: #8f8b80; }
html.dark .dec { border-top-color: #322f2a; }
html.dark .decdate { color: #8f8b80; }
html.dark .deckey { background: #453026; color: #e09b78; }
html.dark .dectitle { color: #d8d5cc; }
html.dark .ctable { background: #232120; border-color: #38352f; }
html.dark .ctable td { border-bottom-color: #322f2a; }
html.dark .ctopic, html.dark .cptr { color: #b8b5ac; }
html.dark .cupd { color: #6f6c64; }
/* ---- Mail & Branches · Archive ---- */
.brwrap { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 6px; }
.brn { display: inline-flex; align-items: center; gap: 6px; border: 1px solid #dfdacc; border-radius: 999px;
  padding: 5px 10px; background: #faf9f5; font-size: .74rem; }
.brmeta { color: #87867f; }
.mstat { color: #be4b32; text-align: center; width: 1.4em; }
.marrow { color: #a8a49a; text-align: center; }
.mfrom, .mto { font-weight: 600; white-space: nowrap; }
/* The subject is the ONLY elastic cell: it takes the leftover width and ellipses there.
   Without this it set the table's width, the lane overflowed its box, and the time
   column (0.9.33) sat off-screen behind a horizontal scroll — invisible on the panel. */
.mre { color: #6b6a62; width: 100%%; max-width: 0; overflow: hidden; text-overflow: ellipsis; }
.mtime { color: #a8a49a; white-space: nowrap; font-variant-numeric: tabular-nums;
  text-align: right; }
.ftable tr.unread td { background: rgba(190,75,50,.05); }
.shl { font-size: .8rem; padding: 6px 2px; border-top: 1px solid #edeae0; color: #4b4a45; }
.shl:first-child { border-top: none; }
.blg { border-top: 1px solid #edeae0; padding: 9px 2px; }
.blg:first-of-type { border-top: none; }
.blh { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }
/* ---- Tasks: pipeline cards (edict's dashboard, adapted to our gates) -------------
   A column told them a card's status; it never told them where the card sits in the ORG's
   flow, which is the thing the Boss actually asks about. Every card now wears the pipeline
   itself — 未派 · 派工 · 执行 · 审查 · 完成 — so a card parked at the L2 gate for four
   days is visible from across the room. No emoji, and nothing wears red: red is
   auspicious in the almanac tradition the palette borrows from, so a stalled card is amber. */
/* The controls sit on the section-title line, right-aligned — Notion puts a view's
   controls level with its name, not on a row of their own. */
.thead { display: flex; align-items: baseline; justify-content: space-between;
  gap: 16px; margin: 0 0 10px; }
.thead h2 { margin: 0; }
.filters { display: flex; gap: 8px; align-items: center; }
/* View controls in Notion's convention, not a flat strip: seven lanes and four sorts
   spread across the header made every option shout on every visit. The header states
   the CHOICE — lane + count, sort — and a quiet popover holds the alternatives. */
.fwrap { position: relative; }
.fsel { font: inherit; font-size: .74rem; color: #57554e; background: transparent;
  border: 1px solid transparent; border-radius: 8px; padding: 4px 10px; cursor: pointer;
  display: inline-flex; align-items: center; gap: 6px; }
.fsel:hover { background: rgba(0,0,0,.05); }
.fsel b { font-weight: 600; color: #a2542f; }
.chev { font-size: .58rem; color: #a09a8c; }
.fnum { font-size: .68rem; color: #a09a8c; font-variant-numeric: tabular-nums; }
.flab { font-size: .62rem; letter-spacing: .1em; text-transform: uppercase; color: #a09a8c; }
.fmenu { display: none; position: absolute; top: 30px; right: 0; min-width: 196px;
  background: #faf9f5; border: 1px solid #dcd8cb; border-radius: 10px; padding: 5px;
  box-shadow: 0 10px 30px rgba(31,30,29,.14); z-index: 40; }
.fmenu.open { display: block; }
.fopt { display: flex; align-items: center; gap: 10px; padding: 6px 10px;
  border-radius: 7px; font-size: .76rem; color: #57554e; cursor: pointer; }
.fopt .fl { flex: 1 1 auto; }
.fopt:hover { background: rgba(193,95,60,.07); }
.fopt.on { color: #a2542f; font-weight: 600; }
/* Multi-select lanes wear a checkbox, Notion's filter idiom; aggregates stay plain. */
.cb { width: 13px; height: 13px; border: 1px solid #c9c4b4; border-radius: 4px;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: .6rem; color: transparent; flex: none; }
.fopt.on .cb { background: #c15f3c; border-color: #c15f3c; color: #fff; }
.fdiv { border-top: 1px solid #e7e3d6; margin: 5px 4px; }
html.dark .fsel { color: #b9b5aa; }
html.dark .fsel:hover { background: rgba(255,255,255,.06); }
html.dark .fsel b { color: #e09b78; }
html.dark .flab { color: #6f6a60; }
html.dark .fmenu { background: #232120; border-color: #38352f;
  box-shadow: 0 10px 30px rgba(0,0,0,.5); }
html.dark .fopt { color: #b9b5aa; }
html.dark .fopt:hover { background: rgba(217,119,87,.1); }
html.dark .fopt.on { color: #e09b78; }
html.dark .cb { border-color: #4a463d; }
html.dark .fopt.on .cb { background: #d97757; border-color: #d97757; }
html.dark .fdiv { border-top-color: #38352f; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; }
.pcard { background: #faf9f5; border: 1px solid #dfdacc; border-radius: 14px; padding: 14px 15px;
  cursor: pointer; box-shadow: 0 1px 2px rgba(31,30,29,.05);
  transition: border-color .15s, transform .1s, box-shadow .15s; }
.pcard:hover { border-color: #c15f3c; transform: translateY(-2px); box-shadow: 0 6px 20px rgba(31,30,29,.09); }
.pcard.s-blocked { border-left: 3px solid #c08b2d; }
html.dark .pcard { background: #232120; border-color: #38352f; box-shadow: none; }
html.dark .pcard:hover { border-color: #d97757; box-shadow: 0 6px 22px rgba(0,0,0,.45); }
html.dark .pcard.s-blocked { border-left-color: #dcc27a; }
/* the strip itself */
.pipe { display: flex; align-items: flex-start; margin-bottom: 11px; }
.pn { display: flex; flex-direction: column; align-items: center; gap: 3px; flex: 0 0 auto; }
.pd { width: 9px; height: 9px; border-radius: 50%%; border: 1.5px solid #cbc6b9; background: transparent; }
.pn.done .pd { background: #6b9e5f; border-color: #6b9e5f; }
.pn.active .pd { background: #c15f3c; border-color: #c15f3c; width: 11px; height: 11px;
  box-shadow: 0 0 0 3px rgba(193,95,60,.16); }
.pn-l { font-size: .58rem; color: #87867f; white-space: nowrap; }
.pn.done .pn-l { color: #5f8b55; }
.pn.active .pn-l { color: #a2542f; font-weight: 700; }
.pn.pending .pd, .pn.pending .pn-l { opacity: .42; }
.pseg { flex: 1 1 0; height: 1.5px; background: #e2ddd0; margin-top: 4px; }
.pseg.done { background: #6b9e5f; }
html.dark .pd { border-color: #4a4740; }
html.dark .pn-l { color: #8f8b80; }
html.dark .pn.done .pd { background: #7fae72; border-color: #7fae72; }
html.dark .pn.done .pn-l { color: #7fae72; }
html.dark .pn.active .pd { background: #d97757; border-color: #d97757; box-shadow: 0 0 0 3px rgba(217,119,87,.2); }
html.dark .pn.active .pn-l { color: #e09b78; }
html.dark .pseg { background: #38352f; }
html.dark .pseg.done { background: #7fae72; }
/* card body */
.pids { display: flex; align-items: baseline; gap: 6px; }
.pctitle { font-size: .9rem; font-weight: 600; line-height: 1.4; margin: 4px 0 8px;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
.ptags { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
.pfoot { display: flex; align-items: center; justify-content: space-between; gap: 8px;
  margin-top: 9px; padding-top: 8px; border-top: 1px solid #edeae0; }
html.dark .pfoot { border-top-color: #322f2a; }
.age { font-size: .63rem; color: #87867f; font-variant-numeric: tabular-nums; }
.age.stale { color: #a67c2e; }
html.dark .age { color: #8f8b80; }
html.dark .age.stale { color: #dcc27a; }
.arts { font-size: .63rem; color: #87867f; }
html.dark .arts { color: #8f8b80; }
/* detail modal — the fielded card, opened rather than expanded in place */
.mbg { position: fixed; inset: 0; background: rgba(31,30,29,.55); z-index: 60; display: none; overflow-y: auto; }
html.dark .mbg { background: rgba(0,0,0,.62); }
.mbg.open { display: flex; align-items: flex-start; justify-content: center; padding: 44px 16px; }
.pmodal { background: #faf9f5; border: 1px solid #dfdacc; border-radius: 16px; width: 100%%;
  max-width: 720px; padding: 24px 26px; position: relative; box-shadow: 0 24px 60px rgba(31,30,29,.18); }
html.dark .pmodal { background: #232120; border-color: #38352f; box-shadow: 0 24px 60px rgba(0,0,0,.55); }
.mclose { position: absolute; top: 12px; right: 12px; width: 28px; height: 28px; display: flex;
  align-items: center; justify-content: center; border-radius: 8px; cursor: pointer; color: #87867f;
  border: none; background: none; font-size: 1.1rem; }
.mclose:hover { background: #eee9dd; color: #1f1e1d; }
html.dark .mclose:hover { background: #2b2926; color: #e9e6dd; }
.mtitle { font-size: 1.18rem; font-weight: 700; line-height: 1.32; margin: 4px 0 15px; }
.mpipe { padding: 15px 18px; background: #f2f0e9; border-radius: 12px; margin-bottom: 16px; }
html.dark .mpipe { background: #2b2926; }
/* the Dashboard's WHICH band — same column furniture as the desk, lighter rows */
.grow { display: flex; gap: 8px; align-items: baseline; padding: 6px 2px; border-top: 1px solid #edeae0; }
.grow:first-of-type { border-top: none; }
.grow .dchip { flex: none; white-space: nowrap; }
.gtx { min-width: 0; }
.gname { font-size: .78rem; color: #4b4a45; overflow-wrap: anywhere; }
.gsub { font-size: .7rem; color: #a8a49a; margin-top: 2px; }
html.dark .grow { border-top-color: #322f2a; }
html.dark .gname { color: #d8d5cc; }
html.dark .gsub { color: #6f6c64; }
.blsha { font: .66rem ui-monospace, "SF Mono", Menlo, monospace; color: #a8a49a; }
.blnote { font-size: .7rem; color: #a8a49a; margin-top: 2px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.blmore { font-size: .72rem; color: #a8a49a; padding: 10px 2px 0; border-top: 1px solid #edeae0; }
html.dark .blsha, html.dark .blnote, html.dark .blmore { color: #6f6c64; }
html.dark .blmore { border-top-color: #322f2a; }
html.dark .brn { background: #232120; border-color: #38352f; }
html.dark .brmeta, html.dark .mtime { color: #8f8b80; }
html.dark .mre { color: #b8b5ac; }
html.dark .shl { border-top-color: #322f2a; color: #d8d5cc; }
html.dark .blg { border-top-color: #322f2a; }
html.dark .ftable tr.unread td { background: rgba(224,130,98,.08); }
/* ---- masthead + top nav (the mockup they picked): the name and the org's live numbers
   on one line, the seven panes as tabs under it, each carrying its own count. The left
   rail is gone — with the tabs on top the content column runs the full width, which is
   what the card grid wanted. ---- */
body { max-width: 1400px; }
.hdr { display: flex; align-items: flex-end; justify-content: space-between; gap: 14px;
  flex-wrap: wrap; padding-bottom: 13px; border-bottom: 1px solid #dcd8cb; }
.hdr h1 { font-size: 1.5rem; line-height: 1.1; margin: 2px 0 0; }
.hdr-r { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; }
.hchip { font-size: .68rem; padding: 3px 10px; border: 1px solid #dcd8cb; border-radius: 999px;
  background: #faf9f5; color: #87867f; white-space: nowrap; }
.hchip b { color: #1f1e1d; font-weight: 600; }
.hchip.attn { border-color: #c15f3c; color: #a2542f; }
.hchip.attn b { color: #a2542f; }
html.dark .hdr { border-bottom-color: #38352f; }
html.dark .hchip { background: #232120; border-color: #38352f; color: #8f8b80; }
html.dark .hchip b { color: #e9e6dd; }
html.dark .hchip.attn { border-color: #d97757; color: #e09b78; }
html.dark .hchip.attn b { color: #e09b78; }
/* The mockup's tabs: an underline on the active one, counts in mono beside the label, and
   no pill. The strip still scrolls when it is too narrow, but its scrollbar is hidden —
   a permanent grey thumb parked next to Finance was chrome that meant nothing. */
nav.tabs { display: flex; gap: 3px; margin: 13px 0 18px; border-bottom: 1px solid #dcd8cb;
  overflow-x: auto; scrollbar-width: none; }
nav.tabs::-webkit-scrollbar { display: none; }
nav.tabs button { font: 600 .8rem -apple-system, "SF Pro Text", Helvetica, sans-serif;
  padding: 9px 13px; cursor: pointer; color: #87867f; background: none; white-space: nowrap;
  border: 0; border-bottom: 2px solid transparent; margin-bottom: -1px; }
nav.tabs button:hover { color: #1f1e1d; }
nav.tabs button.on { color: #1f1e1d; border-bottom-color: #c15f3c; }
.tbadge { font: .65rem ui-monospace, "SF Mono", Menlo, monospace; padding: 0; background: none;
  color: #87867f; margin-left: 5px; font-variant-numeric: tabular-nums; }
nav.tabs button.on .tbadge { background: none; color: #87867f; }
html.dark nav.tabs { border-bottom-color: #38352f; }
html.dark nav.tabs button { color: #8f8b80; }
html.dark nav.tabs button:hover { color: #e9e6dd; }
html.dark nav.tabs button.on { color: #e9e6dd; border-bottom-color: #d97757; }
html.dark .tbadge, html.dark nav.tabs button.on .tbadge { background: none; color: #8f8b80; }
.main > section > h2:first-child { margin-top: .15em; }
#sndtog { background: none; border: 0; cursor: pointer; font-size: .95rem; padding: 0 2px;
          line-height: 1; opacity: .85; }
#sndtog:hover { opacity: 1; }
#themetog { width: 26px; height: 24px; border: 1px solid #dcd8cb; background: #faf9f5;
  color: #87867f; border-radius: 999px; cursor: pointer; line-height: 1; }
#themetog:hover { border-color: #c15f3c; color: #a2542f; }
html.dark #themetog { background: #232120; border-color: #38352f; color: #8f8b80; }
html.dark #themetog:hover { border-color: #d97757; color: #e09b78; }
</style>
<script>
// Dark-FIRST: the board is a monitor that sits open all
// day, so it defaults dark and they flip it by hand, rather than following whatever the
// OS decided. Order of authority: ?theme= (pins a screenshot) > their saved choice > dark.
(function(){
  const q = new URLSearchParams(location.search).get('theme');
  let pref = q;
  if(!pref){ try{ pref = localStorage.getItem('board-theme'); }catch(e){} }
  document.documentElement.classList.toggle('dark', (pref || 'dark') !== 'light');
})();
function toggleTheme(){
  const dark = !document.documentElement.classList.contains('dark');
  document.documentElement.classList.toggle('dark', dark);
  try{ localStorage.setItem('board-theme', dark ? 'dark' : 'light'); }catch(e){}
}
</script>
</head><body>
<div class='shell'>
<header class='hdr'>
  <div class='hdr-l'><span class='brand'>Boss Board</span><span class='bdot'>·</span><h1 id='proj'>—</h1></div>
  <div class='hdr-r'>
    <span class='hchip' id='hdesk'>—</span>
    <span class='hchip' id='hflight'>—</span>
    <span class='hchip' id='stamp'>—</span>
    <button id='sndtog' onclick='toggleSound()' title='Arrival sound' aria-label='Arrival sound'>🔔</button>
    <button id='themetog' onclick='toggleTheme()' title='Light / dark' aria-label='Light / dark'>◐</button>
  </div>
</header>
<nav class='tabs'>
  <button data-tab='dash' class='on' onclick='showTab("dash")'>Dashboard</button>
  <button data-tab='tasks' onclick='showTab("tasks")'>Tasks<span class='tbadge' id='b-tasks'></span></button>
  <button data-tab='depts' onclick='showTab("depts")'>Departments<span class='tbadge' id='b-depts'></span></button>
  <button data-tab='decisions' onclick='showTab("decisions")'>Decisions<span class='tbadge' id='b-decisions'></span></button>
  <button data-tab='mail' onclick='showTab("mail")' style='display:none'>Mail &amp; Branches<span class='tbadge' id='b-mail'></span></button>
  <button data-tab='archive' onclick='showTab("archive")'>Archive<span class='tbadge' id='b-archive'></span></button>
  <button data-tab='finance' onclick='showTab("finance")' style='display:none'>Finance</button>
</nav>
<main class='main'>
<section class='tabpane on' id='tab-dash'>
  <div id='sot'></div>
  <div class='ib' id='ib'>
    <div class='rail' id='rail'></div>
    <div class='convcol'>
      <div class='threadwrap'>
        <button class='jump up' id='jumpup' onclick='jumpMark(this)'></button>
        <button class='jump down' id='jumpdn' onclick='jumpMark(this)'></button>
        <div class='list' id='desklist'></div>
      </div>
      <div class='composer' id='composer'></div>
    </div>
  </div>
</section>
<section class='tabpane' id='tab-tasks'>
  <div class='thead'><h2>Current iteration</h2>
  <div class='filters' id='filters'></div></div>
  <div class='grid' id='grid'></div>
</section>
<section class='tabpane' id='tab-depts'>
  <h2>花名册 · Departments</h2>
  <div class='depts' id='depts'></div>
</section>
<section class='tabpane' id='tab-decisions'>
  <h2>Decisions · 决策与定案</h2>
  <div class='dcol2' id='decisions'></div>
</section>
<section class='tabpane' id='tab-mail'>
  <h2>Mail &amp; Branches · 分公司</h2>
  <div id='mail'></div>
</section>
<section class='tabpane' id='tab-archive'>
  <h2>Archive · 归档</h2>
  <div id='archive'></div>
</section>
<section class='tabpane' id='tab-finance'>
  <h2>Finance · 财务台账</h2>
  <div id='finance'></div>
</section>
</main>
</div>
<div id='toast'></div>
<div id='tray'>
  <div class='trayhd'><span id='traycount'></span><span id='traytarget'></span><button class='sendbtn' id='traysend' onclick='sendBasket()'>Send to session</button></div>
  <div class='seats' id='seats'></div>
  <div class='traylist' id='traylist'></div>
</div>
<div class='mbg' id='taskmbg' onclick='if(event.target===this)closeTask()'><div class='pmodal' id='taskmodal'></div></div>
<script>
const POLL = %d;
const VER = %s;  // page generation — a version change from the server hot-reloads the tab
// Escape EVERY field: dept/kind/task text come from markers/files any pane can write —
// unescaped they'd be an HTML injection straight into the Boss's panel.
function esc(s){return (s||"").replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
// Minimal markdown AFTER escaping (order matters — esc first keeps the XSS guarantee):
// **bold**, `code` and ~~strike~~ (hand-struck tombstone headings) are what markers/
// cards actually use. Leftover unpaired markers — panes use "** " as a bullet — are
// stripped rather than shown literally.
// Project-relative file paths (asks constantly carry mockup/review paths) become
// links onto the daemon's /file endpoint, so the Boss clicks instead of hunting in
// Finder. Two shapes: dir/…/name.any-ext, and a BARE filename with a known artifact
// extension — CEOs write "docs/mockups/a.png + b.png" and the sibling must be just
// as clickable (the server resolves bare names by basename search). A preceding char
// outside the path charset (or start) anchors both, so URL innards (host/a.png)
// never match; trailing punctuation stays outside via the \b. stopPropagation keeps
// a link click from toggling the row/card it sits in.
const PATH_RE = /(^|[^\w.\-\/一-鿿])((?:\/?(?:[\w.\-一-鿿]+\/)+[\w.\-一-鿿]+\.[A-Za-z0-9]{1,5})|(?:\/?(?:[\w.\-一-鿿]+\/){2,})|[\w一-鿿][\w.\-一-鿿]*\.(?:png|jpe?g|gif|webp|pdf|svg|md|txt|csv|json|log|html?|ya?ml|toml))/g;
// The path charset admits no HTML-escapable characters, so `p` is safe raw in
// href (encoded), label AND the inline onclick string.
// Two click behaviours: types the browser renders
// natively (images/PDF — mockups, marked shots) open in the tab as before;
// everything it would dump as plain text (.md, logs, csv …) opens in the OS
// default app via /open — the CLI-click behaviour. The /file href stays on
// both, so right-click / middle-click still gives the raw view.
const VIEW_RE = /\.(png|jpe?g|gif|webp|pdf)$/i;
function openLocal(ev, p){
  ev.stopPropagation(); ev.preventDefault();
  fetch('/open?p='+encodeURIComponent(p), {headers:{'X-Board':'1'}}).catch(()=>{});
}
function flink(p){
  if (VIEW_RE.test(p))
    return `<a href="/file?p=${encodeURIComponent(p)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">${p}</a>`;
  return `<a href="/file?p=${encodeURIComponent(p)}" title="opens in default app · right-click for raw" onclick="openLocal(event,'${p}')">${p}</a>`;
}
function paths(h){ return h.replace(PATH_RE, (m,pre,p)=>pre+flink(p)); }
// Every file path an ask mentions, deduped in order — rendered as the expansion's
// own files row so the Boss clicks a list, never hunts inside prose.
function filesOf(t){
  const out = [];
  (' '+(t||'')).replace(PATH_RE, (m,pre,p)=>{ if(!out.includes(p)) out.push(p); return m; });
  return out;
}
// Structured ask: `<title> :: <body>` — title is the one-line decision (the row's
// collapsed face), body is the detail behind the click. Legacy asks (no `::`)
// keep the whole text as face, exactly the old behaviour.
function splitAsk(t){
  const i = (t||'').indexOf('::');
  return i < 0 ? [t||'', ''] : [(t.slice(0,i)).trim(), t.slice(i+2).trim()];
}
function md(s){
  return paths(esc(s).replace(/^\*\*\s+/,'')                 // "** " used as a bullet, not bold
               .replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>')
               .replace(/~~([^~]+)~~/g,'<s>$1</s>')
               .replace(/`([^`]+)`/g,'<code>$1</code>')
               .replace(/\*\*|~~/g,''));
}
// Expanded cards must survive the poll re-render (each tick used to rebuild the DOM
// and instantly re-collapse whatever the Boss had just clicked open).
const EXP = new Set();
// #x in the URL = expand-all mode (open every card/row pre-expanded — a reading
// pass over the whole board without a click per card; clicking still collapses).
const XALL = location.hash === '#x';
function tog(el){
  if (getSelection().toString()) return;   // selecting text is not a toggle
  const k = el.dataset.k;
  el.classList.toggle('x');
  if (el.classList.contains('x')) { EXP.add(k); EXP.delete('!'+k); }
  else { EXP.delete(k); EXP.add('!'+k); }   // '!' = collapsed-by-hand, sticky under #x
}
function xc(k){ if (XALL && !EXP.has('!'+k)) EXP.add(k); return EXP.has(k) ? ' x' : ''; }
document.addEventListener('keydown', e=>{
  if(e.key==='Enter' && e.target && e.target.dataset && e.target.dataset.k){ tog(e.target); e.preventDefault(); }
});
function age(ts){
  if(!ts) return '';
  const d = (Date.now() - new Date(ts).getTime())/1000;
  if(!isFinite(d) || d < 0) return '';
  if(d < 90) return 'now';
  if(d < 5400) return Math.round(d/60)+'m';
  if(d < 129600) return Math.round(d/3600)+'h';
  return Math.round(d/86400)+'d';
}
// Every time on this page is an AGE derived at render — and a render only happens when
// the data changes. So on a quiet board every age froze at the last change while the
// masthead clock kept ticking: the page read live and told stale time — the one number
// visibly moving was the one with nothing behind it. One pass per poll
// re-derives them IN PLACE: it rewrites text nodes only, so nothing they expanded or is
// typing into is touched. The timestamp travels on the element (`data-ts`, plus optional
// `data-pre`/`data-post` for a framed line); stage chips carry `data-since` because they
// are minute-precision time-in-stage, formatted by their own rule.
function retick(){
  document.querySelectorAll('[data-ts]').forEach(el=>{
    const v = age(el.dataset.ts);
    if(!v) return;
    const t = (el.dataset.pre||'') + v + (el.dataset.post||'');
    if(el.textContent !== t) el.textContent = t;
  });
  document.querySelectorAll('[data-since]').forEach(el=>{
    const d = stageDur(el.dataset.since);
    if(!d) return;
    const t = d.txt + (el.dataset.where ? ' ' + el.dataset.where : '');
    if(el.textContent !== t) el.textContent = t;
    // Only the card chip wears the stale colour (`.age.stale`); a lane row shows the
    // same duration with no styling of its own, and must not collect a dead class.
    if(el.classList.contains('age')) el.classList.toggle('stale', d.m/1440 >= 3);
  });
}
// Empty-state glyphs: monoline SVG in the theme's muted ink (currentColor) — not emoji.
const ICONS = {
  clear: `<svg width="42" height="42" viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="24" cy="24" r="15"/><path d="M17.5 24.5l4.5 4.5 9-10"/></svg>`,
  crab: `<svg width="50" height="44" viewBox="0 0 52 46" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="26" cy="29" rx="11" ry="8"/><path d="M21 22L19 16"/><circle cx="18.6" cy="13.6" r="1.8"/><path d="M31 22l2-6"/><circle cx="33.4" cy="13.6" r="1.8"/><path d="M15 26c-5-1-8-5-7-10"/><path d="M8 16l-3-2.5M8 16l3.5-2"/><path d="M37 26c5-1 8-5 7-10"/><path d="M44 16l3-2.5M44 16l-3.5-2"/><path d="M16 33.5l-6 2.5M18.5 36.5l-5 4M33.5 36.5l5 4M36 33.5l6 2.5"/></svg>`,
  inbox: `<svg width="42" height="42" viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.9 10.2 4 24v12a4 4 0 0 0 4 4h32a4 4 0 0 0 4-4V24l-6.9-13.8A4 4 0 0 0 33.5 8h-19a4 4 0 0 0-3.6 2.2z"/><polyline points="4 24 16 24 20 30 28 30 32 24 44 24"/></svg>`,
};
// Long texts enumerate with circled digits (① hand test… ② the batch…) — break
// each onto its own line so the wall scans as a list. The lookahead keeps inline
// REFERENCES ("chain ①②③④ COMPLETE") intact: only a digit that starts a clause
// (preceded by space, not followed by another digit) breaks. nl=true also honours
// literal newlines (expanded ask bodies / quoted originals — the direction band
// gets pre-line from CSS); collapsed titles stay flowing, so no nl there.
function brk(t, nl){
  const h = md(t).replace(/\s([①-⑳])(?![①-⑳])/g,'<br>$1');
  return nl ? h.replace(/\n/g,'<br>') : h;
}
// fmt(): the essay formatter — asks must read as organized, structured and
// ADHD-friendly. CEO asks are single-line essays glued with · and sentence
// runs, so literal-newline support alone never broke them. Mechanical typography
// rebuilds the structure the prose hides: sentences end lines (。？！； always;
// . ! ? only before a fresh capital/「/digit so paths and decimals hold), ①-⑳
// clauses become hanging-indent rows, ` · ` runs become dotted list rows.
// Titles never come here — collapsed faces stay clamped flow.
function fmt(t){
  const parts = [];
  (t||'').split('\n').forEach(seg=>{
    seg.split(/\s(?=[①-⑳](?![①-⑳]))/).forEach(s2=>{
      s2.split(/(?<=[。？！；])(?![」』）\)])\s*|(?<=[^.\d][.!?])\s+(?=[A-Z0-9「『#①-⑳])/).forEach(s3=>{
        s3 = (s3||'').trim(); if(!s3) return;
        if(/^[①-⑳]/.test(s3)) parts.push({c:'fli', t:s3});
        else if(s3.includes(' · '))
          s3.split(' · ').forEach(it=>{ it=it.trim(); if(it) parts.push({c:'fdot', t:it}); });
        else parts.push({c:'fln', t:s3});
      });
    });
  });
  if(!parts.length) return '';
  return `<div class='fmt'>` + parts.map(p=>
    `<div class='${p.c}'>${p.c==='fdot'?`<span class='fm'>·</span>`:''}${md(p.t)}</div>`).join('') + `</div>`;
}
function sotBand(sot){
  // The SoT `## Now` bullets (State · Blocked-on-their · Money) — each a maintained
  // status line; the leading "**Label:**" bolds via md(), circled digits break to rows.
  // A bullet marker is a dash or star FOLLOWED BY SPACE. Without that guard a line
  // that opens in bold ("**State:** …", no bullet) lost its first asterisk to the
  // strip and rendered as a literal `*State:`.
  const rows = sot.now.split('\n').map(l=>l.replace(/^\s*[-*]\s+/,'').trim()).filter(Boolean);
  // COLLAPSED by default (0.9.73). It is doctrine they wrote and rarely changes, and at
  // full height it pushed the first thing they could act on below the fold every visit.
  // One line, clickable; the fold state persists through `xc`/`tog` like any other row.
  // First clause of each bullet. Sentence enders only — splitting on a colon too would
  // cut "重心:功能优先" down to "重心", throwing away the half that carries the meaning.
  const gist = rows.map(l=>l.replace(/[*`]/g,'').split(/[。.](?:\s|$)|——/)[0].trim())
                   .filter(Boolean).join(' · ');
  return `<div class='sotband${xc('sot')}' data-k='sot' tabindex='0' onclick='tog(this)'>
    <div class='skick'>Source of truth<span class='sgist'>${esc(gist)}</span>
      <span class='sage'>${esc(sot.as_of||'')}</span></div>
    <div class='sfull'>${rows.map(l=>`<div class='srow'>${brk(l)}</div>`).join('')}</div></div>`;
}
// Information ≠ decisions: info-kind entries never sit in Needs-you — they get the
// third column, fresh ones visible, history folded. Legacy Inspector entries (posted
// as needs/discuss by pre-0.9.18 stores) route by DEPT so live boards migrate on
// render, no store surgery.
// `notice` belongs here and was missing until 0.9.62. An ambiguity notice is a card the
// system generates to DESCRIBE their queue, so counting it as part of the queue makes each
// notice inflate the next — the exact amplification resolve_by_dept documents and guards
// against. Python's desk mirror had the rule; this side did not, so the masthead read one
// higher than the Obsidian panel for the same register.
function isInfo(e){ return e.kind==='info' || !!e.notice || /^inspector/i.test(e.dept||''); }
function chip(t){
  // Hook-born cards have label "#<id>" and ·-less headings parse label===name —
  // show each fact once (same guards as tCard).
  const id = t.task_id && t.label !== '#'+t.task_id ? ` · #`+esc(t.task_id) : '';
  const nm = t.name && t.name !== t.label ? ` · `+md(t.name) : '';
  return `<span class="chip"><b>${md(t.label)}${id}</b>${nm} · ${esc(t.status||'?')}</span>`;
}
function askRow(e, T, ts, cls){
  // Context for the decision: the explicitly linked task first; else the dept's
  // in-flight cards (its ask is almost always about one of them).
  let linked = (e.task && T.byId[e.task]) ? [T.byId[e.task]]
    : T.list.filter(t=>t.dept===e.dept && ['doing','review','blocked'].includes(t.status)).slice(0,2);
  const a = age(ts || e.created);
  // A resolved ask with a recorded outcome wears the outcome as its face; the ask
  // it answered is quoted behind the click. Reopening shows the full ask again.
  // A structured ask (`title :: body`) wears the title; the body waits in the
  // expansion, above the task chips, with its file paths extracted to a files row.
  // Their answer is the face when there is one; a card closed by its own raiser with no
  // reply from them wears that note instead, rather than falling back to the ask itself.
  const sum = e.status==='resolved' && (e.sum || e.outcome);
  const [title, body] = splitAsk(e.text);
  const rt = brk(sum ? sum : (title || e.text));
  const files = filesOf(e.text);
  // The id·dept·kind meta line is a quiet FOOTER in both states: collapsed it sits
  // under the clamped title; expanded it must not wedge between title and body
  // (Boss's 2026-07-21 report — mid-card it read as a divider), so .rx comes first.
  const writing = cTarget && cTarget.id === e.id;
  const rd = !!e.read;                       // archived — dims, then folds to History
  // A MESSAGE LIST, not a mailbox. Four columns:
  //   col 1  state dot — what kind of message it is
  //   col 2  the item id (CEO-498), because that is what they need to locate and cite it.
  //          The dept alone was "CEO" over and over, which located nothing; the id carries
  //          the dept as its prefix anyway, so this column says strictly more.
  //   col 3  the message: title in ink, the rest trailing in grey on the SAME line
  //   col 4  age, right-aligned, monospaced so the column lines up
  // The tick stays a TICK, in column one, where they can hit it without opening the row.
  // Only what it MEANS changed: it archives on their side at the click and tells the session
  // nothing. It used to stage a 已读回执 that rode out with the next Send.
  const prev = sum ? e.text : body;
  const nw = e.status === 'open' && !rd ? ' nw' : '';   // still live = bold locator
  const tick = isInfo(e)
    ? `<label class="rsel" title="archive — filed on your side, nothing is sent" onclick="event.stopPropagation()"><input type="checkbox" ${rd?'checked':''} onchange="archive('${esc(e.id)}',this.checked)"></label>`
    : `<span class="rsel"><span class="dot2 k-${esc(e.kind)}"></span></span>`;
  return `<div class="row mrow${nw}${writing?' x':xc(e.id)}${rd?' rd':''}${cls?' '+cls:''}" data-k="${esc(e.id)}" tabindex="0" onclick="tog(this)">
    ${tick}
    <span class="rid" title="${esc(e.dept)} · ${esc(e.kind)}">${esc(e.id)}</span>
    <div class="rc">
      <div class="rt"><span class="rtt">${rt}</span>${prev?`<span class="rtp"> — ${brk(prev).replace(/<br\s*\/?>/g,' · ')}</span>`:''}</div>
      <div class="rx">${!sum && body?`<div class='body'>${fmt(body)}</div>`:''}${sum?`<div class='orig'>${fmt(e.text)}</div>`:''}${linked.map(chip).join('')}${files.length?`<div class='files'>${files.map(flink).join(' · ')}</div>`:''}</div>
      <div class="rm">${esc(e.dept)} · ${esc(e.kind)}${e.task?` · task #${esc(e.task)}`:''}</div>
      ${rowCtl(e)}${composeBox(e)}
    </div>
    <span class="rage" data-ts="${esc(ts || e.created || '')}">${a}</span></div>`;
}
// Deterministic per-dept hue (edict's per-ministry colour coding, Anthropic-muted):
// the handle hashes to a hue, CSS derives the pastel pair per theme from --dh.
function hue(s){ let h = 0; for (const c of s) h = (h*31 + c.codePointAt(0)) %% 360; return h; }
let NICKS = {};   // spawn-recorded seat 花名 (store `seats`), set each tick
function dchip(t, short){
  // A card store writes an em-dash placeholder for "no dept" as readily as it writes
  // nothing at all. Only the empty string was treated as unassigned, so a placeholder
  // rendered as a coloured chip naming a department called "—".
  const d = (t.dept||'').trim().replace(/^[—–\-]+$/, '');
  if(!d) return `<span class="dchip d0">未派</span>`;
  // A dept cell often carries its scope in prose ("Backend-Engine (grounding: …) →
  // Frontend (web fix)"). On a card FACE that blob outweighs the title, so the face
  // wears the handle and the tooltip keeps every word; the modal shows it in full.
  // The handle's trailing number is the seat's CARD, not the department: the face wears
  // the DEPARTMENT (one hue per dept, however many seats), and the number keys the
  // seat's CEO-given 花名 out of the spawn record — by the handle on the card, or by
  // dept plus this card's own number.
  const head = dhead(d), base = head.replace(/-\d+$/, '');
  const num = String(t.label||'').replace(/\D/g, '');
  const rec = NICKS[head] || (num && NICKS[`${base}-${num}`]) || null;
  const nick = rec && rec.nickname ? ` · ${rec.nickname}` : '';
  const txt = (short ? base : d) + nick;
  return `<span class="dchip" style="--dh:${hue(base)}" title="${esc(d)}">${esc(txt)}</span>${t.external?` <span class='pill px'>分</span>`:''}`;
}
// A labelled compartment (fielded card, the edict lesson): tiny uppercase label
// over the formatted content; absent fields render nothing at all.
function sect(label, v){ return v ? `<div class="tl">${label}</div>${fmt(v)}` : ''; }
// The masthead's three chips: what is waiting on THE BOSS'S, what the org has in flight, and
// how fresh the page is. `flight` is null on a no-change poll — the chip holds its value
// rather than flickering to a placeholder every 1.5s.
function setHeader(needs, flight){
  const d = document.getElementById('hdesk');
  d.innerHTML = `<b>${needs}</b> on your desk`;
  d.classList.toggle('attn', needs > 0);
  if(flight !== null) document.getElementById('hflight').innerHTML = `<b>${flight}</b> in flight`;
  // The stamp printed the wall clock on EVERY poll, so it said "updated <now>" forty
  // times a minute on a board where nothing had moved since breakfast — a freshness claim
  // it could not back, and the only clock on the page that was allowed to lie. It now
  // names the moment the CONTENT last changed. The poll that proves the page is still
  // live sits on the tooltip, and a server that has actually died still says so by
  // dimming the page and replacing this line outright.
  const st = document.getElementById('stamp');
  st.textContent = 'last change ' + (lastChange ? lastChange.toLocaleTimeString() : '—');
  st.title = 'board content last changed at this time · last checked '
           + new Date().toLocaleTimeString();
}
function badge(id, n){ const e = document.getElementById(id); if(e) e.textContent = n || ''; }
// ---- Tasks: the org's pipeline drawn on every card ------------------------------
// The three columns said WHAT STATE a card was in. The strip says where it sits in the
// flow the org actually runs — and because 审查 is the L2 gate, a card stuck there for
// days is now the loudest thing on the page. Chinese on the node, English in the title
// attribute. No emoji anywhere (edict's own nodes are emoji; ours are dots).
const PIPE = ['未派','派工','执行','审查','完成'];
const PIPE_EN = ['unassigned','dispatched','in progress','L2 review','done'];
const TORDER = {doing:0, review:1, blocked:2, todo:3, done:4};
const TFILTERS = [['active','In flight'],['doing','Doing'],['review','In review'],
                  ['todo','Todo'],['blocked','Blocked'],['done','Done'],['all','Everything']];
let TASKS = [], TSHOWN = [], TFILTER = 'active', TDEEP = false, TSORT = 'urgent';
// 排序, the Boss's ask 2026-07-26: "urgent first, then newest first" is the DEFAULT. The other
// two answer the questions the board could not answer before: what is newest, and what
// has been sitting longest. Priority is lexical (P0 < P1 < P2 < unset) — unset sorts
// last rather than pretending to be P0.
const TSORTS = [['urgent','\u7d27\u6025\u4f18\u5148'], ['newest','\u6700\u65b0'],
                ['stale','\u505c\u6ede\u6700\u4e45'], ['stage','\u6309\u9636\u6bb5']];
const tPrio = t => /^P\d$/.test(t.priority||'') ? t.priority : 'P9';
const PRIONAME = {P0:'urgent', P1:'critical', P2:'important', P3:'nice-to-have'};
function prioPill(t){
  const p = /^P[0-3]$/.test(t.priority||'') ? t.priority : '';
  // The tag is the LEVEL. `P0 urgent` spent three quarters of its width restating what
  // P0 already means to anyone reading this board, on every row, next to an id pill and
  // a dept chip. The word is guidance for whoever SETS the level — it lives on the hover
  // and in the rule, not in the tag.
  return p ? `<span class='pill pr-${p[1]}' title='${PRIONAME[p]}'>${p}</span>` : '';
}
const isBug = t => /^bug$/i.test((t.kind||'').trim());
function bugPill(t){ return isBug(t) ? `<span class='pill bug'>bug</span>` : ''; }
// The durable #NNN is minted in order, so a bigger number IS a newer card — and unlike
// a timestamp it never moves when a card changes stage.
const tNo = t => { const m = /^#(\d+)$/.exec(t.label||''); return m ? +m[1] : -1; };
const tSince = t => { const v = t.since ? new Date(String(t.since).replace(' ','T')).getTime() : 0;
                      return v > 0 ? v : Infinity; };   // no clock → never "the stalest"
function tsorted(list){
  const a = list.slice();
  if(TSORT==='newest')      a.sort((x,y)=> tNo(y)-tNo(x));
  else if(TSORT==='stale')  a.sort((x,y)=> tSince(x)-tSince(y) || tNo(y)-tNo(x));
  else if(TSORT==='stage')  a.sort((x,y)=> (TORDER[x.status]??3)-(TORDER[y.status]??3)
                                        || tPrio(x).localeCompare(tPrio(y)));
  else                      a.sort((x,y)=> tPrio(x).localeCompare(tPrio(y)) || tNo(y)-tNo(x));
  return a;
}
// A card with no dept has not been given to anyone yet: that is 未派, the Boss's own word,
// and it is a different thing from "dispatched but not started".
function stageIdx(t){
  if(t.status==='done') return 4;
  // L2 EVIDENCE OUTRANKS THE STATUS FIELD (0.9.55). `review` is hand-written by the dept
  // and nothing verified it, so a card could sit at the gate drawing as 执行. A .pass or
  // .fail on disk is proof the card reached 审查 whatever its status says.
  // 0.9.61: a .pass now MOVES the card. It used to only chip, because a pass on a
  // todo/doing card was ambiguous — awaiting merge, or a stale marker from an earlier
  // leg. The marker is date-checked against the stage clock server-side now, so a
  // surviving pass is a verdict on THIS leg: 审查 is cleared and only the CEO's
  // merge+complete is owed. Leaving it at 派工 while the age chip already read 待合并
  // made one card contradict itself on the board.
  if(t.l2==='pass') return 4;
  if(t.l2==='fail' || t.status==='review') return 3;
  if(t.status==='doing') return 2;
  return t.dept ? 1 : 0;
}
// Three states hide inside "review" and they need different actions from them:
// .pass = through the gate, waiting on the CEO to MERGE · .fail = bounced, dept reworking
// · nothing = claims review but was never submitted, so nobody is reviewing it.
function l2chip(t){
  if(t.l2==='pass') return "<span class='l2 l2p' title='L2 passed — waiting on the CEO to verify and merge'>\u5df2\u8fc7\u5ba1</span>";
  if(t.l2==='fail') return "<span class='l2 l2f' title='L2 bounced — the dept is reworking'>\u5c01\u9a73</span>";
  if(t.status==='review') return "<span class='l2 l2n' title='status says review but no .pass/.fail on file — never submitted'>\u672a\u9001\u5ba1</span>";
  return '';
}
function pipeStrip(t){
  const k = stageIdx(t);
  // 完成 is REACHED only when the card is done. A passed card sits at k=4 with 完成 drawn
  // as the ACTIVE (owed) step, so 待合并 reads as "everything cleared, the merge is next"
  // rather than as finished work.
  const reached = t.status === 'done';
  let h = "<div class='pipe'>";
  PIPE.forEach((s,i)=>{
    if(i) h += `<div class='pseg ${i<=k?'done':''}'></div>`;
    const st = i<k ? 'done' : (i===k ? (reached ? 'done' : 'active') : 'pending');
    h += `<div class='pn ${st}' title='${PIPE_EN[i]}'><div class='pd'></div><div class='pn-l'>${s}</div></div>`;
  });
  return h + "</div>";
}
// `since` is stamped when a card ENTERS a stage (cardlib), so this is time-in-stage,
// not time-since-last-touched. No stamp yet → the chip says nothing rather than guess.
// The duration half stands alone, so the per-poll reticker can re-derive a chip already
// on the page from its own `data-since`, without holding the card it was drawn from.
function stageDur(since){
  if(!since) return null;
  const ms = Date.now() - new Date(String(since).replace(' ','T')).getTime();
  if(!(ms > 0)) return null;
  const m = Math.floor(ms/60000);
  return {m, txt: m<60 ? m+'m' : m<1440 ? Math.round(m/60)+'h' : Math.round(m/1440)+'d'};
}
function stageAge(t){
  const d = stageDur(t.since);
  if(!d) return null;
  // A passed card isn't "in 审查" any more — it is waiting on the CEO. Say so.
  const where = (t.l2==='pass' && t.status!=='done') ? '\u5f85\u5408\u5e76'
                                                    : 'in ' + PIPE[stageIdx(t)];
  return {txt: d.txt + ' ' + where, days: d.m/1440, where};
}
function pCard(t, i){
  const st = t.status || 'todo';
  const age = stageAge(t), stale = age && age.days >= 3;
  // Two id kinds, and the colours already mean something on this board: CORAL is the
  // durable project #NNN that outlives every session; NEUTRAL is the task-widget id.
  // A card with no neutral pill was never registered with the task tools.
  const lab = /^#\d+$/.test(t.label||'') ? `<span class='pill pj'>${esc(t.label)}</span>` : md(t.label||'');
  const tid = /^\d+$/.test(t.task_id||'') && t.label !== '#'+t.task_id
    ? `<span class='pill pt' title='registered with the task widget · session task ${esc(t.task_id)}'>#${esc(t.task_id)}</span>` : '';
  // P2 and P3 sorted but drew nothing, so 22 of one project's cards wore a tag the board
  // never showed. Every defined level renders now, and a bug wears its own tag beside it.
  const pp = prioPill(t) + bugPill(t);
  const arts = (t.artifacts||'').split(' · ').filter(Boolean).length;
  return `<div class='pcard s-${esc(st)}' tabindex='0' onclick='openTask(${i})'
      onkeydown='if(event.key==="Enter")openTask(${i})'>
    ${pipeStrip(t)}
    <div class='pids'>${pp}${lab}${tid}</div>
    <div class='pctitle'>${esc(t.name && t.name !== t.label ? t.name : (t.label||''))}</div>
    <div class='ptags'>${dchip(t, true)}<span class='stpill st-${esc(st)}'>${esc(st)}</span>${l2chip(t)}</div>
    <div class='pfoot'><span class='age ${stale?'stale':''}'${age?` data-since="${esc(String(t.since))}" data-where="${esc(age.where)}"`:''}>${age?age.txt:''}</span>
      <span class='arts'>${arts?arts+' artifact'+(arts>1?'s':''):''}</span></div>
  </div>`;
}
// ONE definition of in flight, for all three places that count it: the masthead chip, the
// Tasks tab badge and the In-flight filter. They each carried their own copy, and 0.9.61
// taught only the filter that a passed card is still in flight — so the chip and the badge
// would have read one low the moment a card cleared L2. A passed card IS in flight
// whatever its status field says: the last step is the CEO's merge.
function inFlight(t){
  return (t.l2==='pass' && t.status!=='done')
      || ['doing','review','blocked'].includes(t.status);
}
function tfMatch(k, t){
  return k==='all' ? true
       : k==='active' ? inFlight(t)
       : (t.status||'todo') === k;
}
// Which popover is open lives in state, not in the DOM: drawTasks rebuilds the header
// on every lane toggle, and a menu that must survive its own rebuild (multi-select
// keeps it open between ticks of the checkboxes) cannot keep that fact in a class.
let FMOPEN = null;
function fmenu(id){ FMOPEN = FMOPEN===id ? null : id; drawTasks(); }
document.addEventListener('click', e=>{
  if(FMOPEN && e.target && e.target.closest && !e.target.closest('.fwrap')){
    FMOPEN = null; drawTasks();
  }
});
// The lane filter is Notion's: the two aggregates (In flight \u00b7 Everything) pick alone
// and close the menu; the five value lanes are checkboxes that UNION, and the menu
// stays open while they tick them. An emptied set falls back to the In-flight default.
const TAGGS = ['active','all'];
function tfAgg(k){ TFILTER = k; FMOPEN = null; drawTasks(); }
function tfToggle(k){
  if(!(TFILTER instanceof Set)) TFILTER = new Set();
  TFILTER.has(k) ? TFILTER.delete(k) : TFILTER.add(k);
  if(!TFILTER.size) TFILTER = 'active';
  drawTasks();
}
function tfSel(t){
  return (TFILTER instanceof Set) ? [...TFILTER].some(k=>tfMatch(k,t)) : tfMatch(TFILTER, t);
}
function drawTasks(){
  TSHOWN = tsorted(TASKS.filter(tfSel));
  const tcount = k => TASKS.filter(t=>tfMatch(k,t)).length;
  const sort = TSORTS.find(([k])=>k===TSORT) || TSORTS[0];
  const name = k => (TFILTERS.find(([x])=>x===k)||['',k])[1];
  const sel = TFILTER instanceof Set ? [...TFILTER] : null;
  // The face states the choice the way Notion's filter chip does: an aggregate by
  // name, a selection by its first two lanes + how many more.
  const face = sel ? name(sel[0]) + (sel[1] ? `, ${name(sel[1])}` : '')
                     + (sel.length>2 ? ` +${sel.length-2}` : '')
                   : name(TFILTER);
  const laneRow = (k,l) =>
    `<div class='fopt ${(sel?sel.includes(k):false)?'on':''}' tabindex='0'
       onclick='event.stopPropagation();tfToggle("${k}")'
       ><span class='cb'>\u2713</span><span class='fl'>${l}</span><span class='fnum'>${tcount(k)}</span></div>`;
  const aggRow = (k,l) =>
    `<div class='fopt ${(!sel && TFILTER===k)?'on':''}' tabindex='0'
       onclick='event.stopPropagation();tfAgg("${k}")'
       ><span class='fl'>${l}</span><span class='fnum'>${tcount(k)}</span></div>`;
  const sortRow = ([k,l]) =>
    `<div class='fopt ${k===TSORT?'on':''}' tabindex='0'
       onclick='event.stopPropagation();TSORT="${k}";FMOPEN=null;drawTasks()'
       ><span class='fl'>${l}</span></div>`;
  document.getElementById('filters').innerHTML =
    `<span class='fwrap'><button class='fsel' onclick='event.stopPropagation();fmenu("fmenu")'>${face}
       <b>${TASKS.filter(tfSel).length}</b><span class='chev'>\u25be</span></button>
       <div class='fmenu${FMOPEN==="fmenu"?" open":""}' id='fmenu'>
         ${TFILTERS.filter(([k])=>TAGGS.includes(k)).map(([k,l])=>aggRow(k,l)).join('')}
         <div class='fdiv'></div>
         ${TFILTERS.filter(([k])=>!TAGGS.includes(k)).map(([k,l])=>laneRow(k,l)).join('')}</div></span>
     <span class='fwrap'><button class='fsel' onclick='event.stopPropagation();fmenu("smenu")'><span class='flab'>\u6392\u5e8f</span>
       ${sort[1]}<span class='chev'>\u25be</span></button>
       <div class='fmenu${FMOPEN==="smenu"?" open":""}' id='smenu'>${TSORTS.map(sortRow).join('')}</div></span>`;
  document.getElementById('grid').innerHTML = TSHOWN.length
    ? TSHOWN.map(pCard).join('')
    : `<div class='colempty' style='grid-column:1/-1'><div class='glyph'>${ICONS.clear}</div><p class='empty'>Nothing in this lane.</p></div>`;
  // `?task=<id>` opens one card straight away, so a card is linkable (and the modal is
  // reachable by a headless screenshot). Fires once; a poll must not reopen what they closed.
  if(!TDEEP){
    TDEEP = true;
    const want = new URLSearchParams(location.search).get('task');
    if(want){
      const key = want.startsWith('#') ? want : '#'+want;
      const i = TSHOWN.findIndex(t=>t.label===key);
      if(i >= 0) openTask(i);
    }
  }
}
// The fielded card opens instead of expanding in place: at 30+ cards an in-place
// expansion pushed everything below it down the page and lost their scroll position.
function openTask(i){
  const t = TSHOWN[i];
  if(!t) return;
  document.getElementById('taskmodal').innerHTML = `<button class='mclose' onclick='closeTask()' aria-label='Close'>×</button>
    <div class='pids'>${/^#\d+$/.test(t.label||'') ? `<span class='pill pj'>${esc(t.label)}</span>` : ''}${/^\d+$/.test(t.task_id||'') && t.label !== '#'+t.task_id ? `<span class='pill pt' title='registered with the task widget'>#${esc(t.task_id)}</span>` : ''}${prioPill(t)}${bugPill(t)}</div>
    <div class='mtitle'>${esc(t.name && t.name !== t.label ? t.name : (t.label||''))}</div>
    <div class='mpipe'>${pipeStrip(t)}</div>
    <div class='ptags' style='margin-bottom:14px'>${dchip(t)}<span class='stpill st-${esc(t.status||'todo')}'>${esc(t.status||'todo')}</span>${l2chip(t)}<span class='age'>${(stageAge(t)||{txt:''}).txt}</span></div>
    ${sect('What', t.what)}${sect('Done when', t['done-when'])}${sect('Blocked on', t.blocked_on)}${sect('Artifacts', t.artifacts)}`;
  document.getElementById('taskmbg').classList.add('open');
}
function closeTask(){ document.getElementById('taskmbg').classList.remove('open'); }
// Escape closes ONE thing, innermost first: a half-written answer must not be dismissed
// by the same key press that closes a card modal sitting behind it.
addEventListener('keydown', e=>{
  if(e.key !== 'Escape') return;
  if(cTarget){ closeCompose(); return; }
  closeTask();
});
addEventListener('resize', layoutPanels);
// ---- Dashboard desk: one list beside a rail of counts (0.9.73) -------------------
// DFILTER names the rail row in view; DESKDATA holds the last slice the poll built,
// so a rail click redraws at once instead of waiting up to a poll for the next frame.
const DESK_TAIL = 30;
let DFILTER = 'convo', DESKDATA = null;
const DEMPTY = {
  convo:   ['inbox', 'Pick a conversation on the left.'],
  desk:    ['clear', 'Nothing waiting on you.'],
  unread:  ['inbox', 'Verdicts and FYIs land here.'],
  parked:  ['crab',  'Nothing parked — the crab keeps the seat warm.'],
  history: ['clear', 'Nothing answered yet.'],
  doing:   ['clear', 'Nobody is mid-task.'],
  review:  ['clear', 'Nothing at the review gate.'],
  merge:   ['clear', 'Nothing passed and waiting on a merge.'],
  blocked: ['clear', 'Nothing blocked.'],
  todo:    ['clear', 'The backlog is empty.'],
  shipped: ['clear', 'Nothing shipped today yet.'],
};
function setDesk(k){
  DFILTER = k;
  try{ localStorage.setItem('board-desk', k); }catch(e){}
  drawDesk();
}
function railRow(k, label, n, hot){
  return `<div class='rf${DFILTER===k?' on':''}${hot&&n?' hot':''}' tabindex='0'
    onclick='setDesk("${k}")' onkeydown='if(event.key==="Enter")setDesk("${k}")'
    ><span class='rd2'></span>${label}<span class='n'>${n}</span></div>`;
}
// A work row names a card; clicking it opens that card. The Tasks pane may be filtered
// past it, so widen the filter first — a click that silently does nothing reads as broken.
function openTaskLabel(label){
  showTab('tasks');
  if(!TSHOWN.some(t=>t.label===label)){ TFILTER='all'; drawTasks(); }
  const i = TSHOWN.findIndex(t=>t.label===label);
  if(i>=0) openTask(i);
}
function deskTask(t){
  // Age only. stageAge() appends WHERE the card sits, which is worth saying on a card
  // in a mixed grid and is pure repetition in a lane that filters on exactly that
  // stage — every row would end with the name of the lane it is already in.
  const ag = (stageAge(t) || {txt:''}).txt.split(' ')[0];
  return `<div class='row drow' tabindex='0' onclick='openTaskLabel("${esc(t.label)}")'>
    <span class='dot2 k-${t.status==='blocked'?'needs':'task'}'></span>
    <div class='rc'><div class='rt'>${t.label?`<span class='tid'>${esc(t.label)}</span> `:''}${esc(t.name||'')}</div></div>
    ${dchip(t, true)}<span class='rage'${ag?` data-since="${esc(String(t.since))}"`:''}>${esc(ag)}</span></div>`;
}
// The Work lanes. A PARTITION of inFlight: disjoint, and summing to the header's
// number exactly — the retired tile said 11 while the header said 16 about the same
// question on the same screen. 待合并 is a card that passed L2 and is still unmerged;
// it is filed `todo` on the board, so Todo must exclude it or one card sits in two lanes.
// One named function, so the rail, the header and the tests cannot drift apart.
function deskLanes(tasks, psort){
  const srt = psort || (a=>a);
  const inMerge = t => t.l2==='pass' && !['done','doing','review','blocked'].includes(t.status);
  return {
    doing:   srt(tasks.filter(t=>t.status==='doing')),
    review:  srt(tasks.filter(t=>t.status==='review')),
    merge:   srt(tasks.filter(inMerge)),
    blocked: srt(tasks.filter(t=>t.status==='blocked')),
    todo:    srt(tasks.filter(t=>(t.status||'todo')==='todo' && !inMerge(t))),
  };
}
// Carries the timestamp rather than a frozen phrase, so the reticker keeps it honest on a
// board where nothing else is moving — which is exactly the board this line appears on.
function lastAnsweredLine(ts){
  const a = ts ? age(ts) : '';
  return a ? `<span class='m' data-ts="${esc(ts)}" data-pre="last answered " data-post=" ago">last answered ${a} ago</span>`
           : `<span class='m'></span>`;
}
function deskEmpty(k){
  const [g, msg] = DEMPTY[k] || ['clear', 'Nothing here.'];
  return `<div class='colempty'><div class='glyph'>${ICONS[g]}</div><p class='empty'>${msg}</p></div>`;
}
// ---- Conversations (layout A) ---------------------------------------------------------
// One conversation per DEPARTMENT. The rail is who is talking; the pane is that dept's
// thread; the composer sits at the bottom and never moves. Ported from the approved mockup
// (2026-08-03) — the rules below are theirs, each one paid for by a round of review.
let CONVO = null, convoJump = true, showAllQuiet = false, SEEN = null;
// Their side of the conversation: every reply, question and message they have sent, newest
// last. Read fresh from the server each poll — the board is the record, not this page.
let SENT = [];
try{ CONVO = localStorage.getItem('board-convo'); }catch(e){}
const AVCLR = ['#a2542f','#5a7fa0','#6f8a5c','#8a6aa0','#a08a4a','#7a6f64','#3f6b6b','#8f5a5a'];
function avatar(dept, sm){
  let h = 0; for(const ch of dept) h = (h*31 + ch.charCodeAt(0)) & 0xffff;
  const ini = dept.replace(/[^A-Za-z0-9一-鿿]/g,'').slice(0,3).toUpperCase() || '?';
  return `<span class="av${sm?' sm':''}" style="background:${AVCLR[h %% AVCLR.length]}">${esc(ini)}</span>`;
}
const plainTxt = h => String(h||'').replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim();
const clockOf = ts => { const d=new Date(ts); return isNaN(d) ? '' :
  String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0'); };
function dayLabel(ts){
  const d=new Date(ts); if(isNaN(d)) return '';
  const k=new Date(d); k.setHours(0,0,0,0);
  const t=new Date(); t.setHours(0,0,0,0);
  const diff=Math.round((t-k)/86400000);
  if(diff===0) return 'Today';
  if(diff===1) return 'Yesterday';
  return d.toLocaleDateString([], {day:'numeric', month:'short'});
}
const tsOf = e => e.updated || e.created || '';
const isLive = e => e.status === 'open';
const isPending = e => isLive(e) && !isInfo(e);
const isUnread = e => isLive(e) && isInfo(e) && !e.read;

// A conversation's order is its newest message, the rule every chat client uses.
function convos(D){
  const by = new Map();
  (D.all||[]).forEach(e=>{
    const k = e.dept || '—';
    let c = by.get(k);
    if(!c){ c = {dept:k, items:[], needs:0, unread:0, last:null}; by.set(k, c); }
    c.items.push(e);
    if(isPending(e)) c.needs++;
    if(isUnread(e)) c.unread++;
    if(!c.last || tsOf(e) > tsOf(c.last)) c.last = e;
  });
  const cs = [...by.values()];
  cs.forEach(c=>c.items.sort((x,y)=>(x.created||'').localeCompare(y.created||'')));
  cs.sort((x,y)=> (y.needs>0)-(x.needs>0) || tsOf(y.last||{}).localeCompare(tsOf(x.last||{})));
  return cs;
}
function convoRow(c, quiet){
  const face = c.last ? (splitAsk(c.last.text)[0] || c.last.text) : '';
  const badge = c.needs ? `<span class='badge'>${c.needs}</span>`
              : c.unread ? `<span class='badge q'>${c.unread}</span>` : '';
  return `<div class="crow${c.dept===CONVO?' on':''}${quiet?' quiet':''}" tabindex="0" role="button"
    onclick="openConvo('${esc(c.dept)}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openConvo('${esc(c.dept)}')}">
    ${avatar(c.dept)}
    <div class='cmid'><div class='cname'>${esc(c.dept)}</div>
    <div class='cprev'>${esc(plainTxt(face).slice(0,60))}</div></div>
    <div class='cmeta'><span class='ctime' data-ts="${esc(c.last?tsOf(c.last):'')}">${c.last?age(tsOf(c.last)):''}</span>${badge}</div></div>`;
}
// Needs you and Information are separate lists, and a conversation with nothing unread is
// not on the second one: reading IS filing, so a quiet dept is only shown when they ask.
function convoRail(D){
  const cs = convos(D);
  if(!cs.length) return `<div class='rg'>No conversations yet</div>`;
  if(!CONVO || !cs.some(c=>c.dept===CONVO)) CONVO = cs[0].dept;
  const needs = cs.filter(c=>c.needs);
  const info  = cs.filter(c=>!c.needs);
  const live  = info.filter(c=>c.unread>0 || c.dept===CONVO);
  const quiet = info.filter(c=>!(c.unread>0 || c.dept===CONVO));
  const shown = showAllQuiet ? live.concat(quiet) : live;
  return `<div class='rg live'>Needs you · ${needs.reduce((n,c)=>n+c.needs,0)}</div>`
    + (needs.length ? needs.map(c=>convoRow(c)).join('') : `<div class='dclear2'>✓ Nothing waiting on you</div>`)
    + `<div class='rg'>Information · ${live.reduce((n,c)=>n+c.unread,0)} unread</div>`
    + (shown.length ? shown.map(c=>convoRow(c, !c.unread)).join('') : `<div class='dclear2'>✓ Nothing unread</div>`)
    + (quiet.length ? `<button class='more' onclick='showAllQuiet=!showAllQuiet;lastRaw="";drawDesk()'>${showAllQuiet?'Hide the '+quiet.length+' read':'Show all · '+quiet.length+' read →'}</button>` : '')
    + `<div class='rg'>Work</div>`
    + railRow('doing','Doing',D.work.doing.length)
    + railRow('review','In review',D.work.review.length)
    + railRow('merge','待合并',D.work.merge.length)
    + railRow('blocked','Blocked',D.work.blocked.length,true)
    + railRow('todo','Todo',D.work.todo.length)
    + railRow('shipped','Shipped today',D.shipped.length);
}
// Opening a conversation reads what is ON THE PAGE at that moment — never what lands
// afterwards. An arrival must not file a message they have not looked at.
function openConvo(dept){
  CONVO = dept; DFILTER = 'convo'; convoJump = true; cTarget = null;
  try{ localStorage.setItem('board-convo', dept); localStorage.setItem('board-desk','convo'); }catch(e){}
  const c = convos(DESKDATA||{all:[]}).find(x=>x.dept===dept);
  if(c) c.items.filter(isUnread).forEach(e=>post('/read',{id:e.id,read:true}).catch(()=>{}));
  lastRaw=''; drawDesk();
}
function convoThread(D){
  const c = convos(D).find(x=>x.dept===CONVO);
  if(!c) return `<div class='dclear'>Pick a conversation on the left</div>`;
  const rows = c.items.slice(-THREAD_TAIL);
  const hid  = c.items.length - rows.length;
  // The Boss's own messages to this conversation that belong to no item — a question typed into
  // the box with nothing bound. They have their own place in the thread, by their clock.
  const loose = (SENT||[]).filter(s=>!s.id && s.dept===c.dept
                                      && (!rows.length || s.at >= (rows[0].created||'')));
  const stream = rows.map(e=>({at: e.created || tsOf(e), e}))
    .concat(loose.map(s=>({at: s.at, s})))
    .sort((x,y)=>String(x.at).localeCompare(String(y.at)));
  let out = '', day = '';
  stream.forEach(n=>{
    const L = dayLabel(n.at);
    if(L && L !== day){ day = L; out += `<span class='daymark'>${esc(L)}</span>`; }
    out += n.e ? msgRow(n.e, D.T) : mineRow(n.s);
  });
  return `<div class='chd'>${avatar(c.dept,1)}<span class='who'>${esc(c.dept)}</span>
      <span class='readnote'>read on open · nothing sent</span>
      <span class='troute' id='convoroute'></span></div>
    <div class='tbody' id='tbody'>${hid>0?`<div class='dmore'>showing the last ${THREAD_TAIL} of ${c.items.length}</div>`:''}${out}</div>`;
}
const THREAD_TAIL = 40;
// One message. Reply exists only on an ask — an update can be questioned or filed, but it
// has nothing in it to resolve. Their answer rides underneath as the Boss's own bubble, quoting the
// ask it settled, the way WeChat and Telegram do it.
function msgRow(e, T){
  const [title, body] = splitAsk(e.text);
  const need = isPending(e);
  const answered = e.status === 'resolved' && !isInfo(e);
  const files = filesOf(e.text);
  const linked = (e.task && T.byId[e.task]) ? [T.byId[e.task]] : [];
  const writing = cTarget && cTarget.id === e.id;
  const acts = isLive(e)
    ? (isInfo(e)
        ? `<button class="chip${(staged(e)||{}).kind==='ask'?' on':''}" onclick="openCompose('${esc(e.id)}','ask')">Ask</button>
           <button class='chip quiet' onclick="archive('${esc(e.id)}',true)">Archive</button>`
        : `<button class="chip p${(staged(e)||{}).kind==='reply'?' on':''}" onclick="openCompose('${esc(e.id)}','reply')">Reply</button>
           <button class="chip${(staged(e)||{}).kind==='ask'?' on':''}" onclick="openCompose('${esc(e.id)}','ask')">Ask</button>
           <button class='chip quiet' title='read it and answer nothing — no message is sent' onclick="ignoreItem('${esc(e.id)}')">Ignore</button>`)
    : '';
  const flag = need ? `<span class='flag need'>needs you</span>`
             : answered ? `<span class='flag done'>answered</span>` : '';
  // A filed update wears a tick, not a dimmer.
  const tick = e.read ? `<span class='rdtick' title='archived'><svg width="11" height="11" viewBox="0 0 12 12"
      fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
      ><path d="M1.5 6.5 4.5 9.5 10.5 2.5"/></svg></span>` : '';
  const incoming = `<div class="msg${need?' need':''}${answered?' answered':''}${e.read?' rd':''}${writing?' x':''}"
      id="msg-${esc(e.id)}" data-k="${esc(e.id)}">
    <div class='mhead'><b>${esc(e.id)}</b>${flag}${wroteIt(e)}<span class='clock'>${clockOf(e.created || tsOf(e))}</span></div>
    <div class='bubrow'><div class='bub'>${title?`<span class='ttl'>${brk(title)}</span>`:''}${fmt(body || (title?'':e.text))}
      ${linked.map(chip).join('')}${files.length?`<div class='files'>${files.map(flink).join(' · ')}</div>`:''}</div>${tick}</div>
    ${acts?`<div class='acts'>${acts}</div>`:''}</div>`;
  // Their answer is its OWN row in the thread — nested inside the ask it could only reach the
  // right edge of an 82%%-wide parent, so it rendered on the left.
  // Everything they sent ABOUT this item, in the order they sent it: their decision, and every
  // question the Boss asked on it. Only the decision used to be drawn (from `e.sum`), so an ask
  // they wrote left the board silent between the item and its answer.
  const mine = (SENT||[]).filter(s=>s.id === e.id);
  const said = mine.length
    ? mine.map(s=>outBub(e, title, s.text, s.at)).join('')
    : (answered && e.sum ? outBub(e, title, e.sum, e.updated) : '');
  const reply = said;
  // `@BOSS-DONE` — the session that raised the ask closing its own item. That is not their
  // answer and it may never wear their name: both used to be written to `e.sum`, so a
  // session that replied to them and withdrew its ask in the same turn left its one-line
  // summary standing where their words had been, over "you" and their clock.
  const closed = e.outcome ? `<div class='msg note'>
    <div class='mhead'><b>${esc(e.dept || '')}</b> closed this<span class='clock'>${clockOf(e.updated)}</span></div>
    <div class='bub'>${fmt(e.outcome)}</div></div>` : '';
  return incoming + reply + closed;
}
// One thing they said, on the right. Quoting the item when it answers one; standing on its
// own when it does not, because a message the Boss typed with nothing bound answers nothing.
function outBub(e, title, text, at){
  const quo = e ? `<button class='quo' onclick="jumpToId('${esc(e.id)}')"><span class='qid'>↩ ${esc(e.id)}</span>
      <span class='qt'>${esc(plainTxt(title||e.text)).slice(0,110)}</span></button>` : '';
  return `<div class='msg out'>
    <div class='mhead'>you<span class='clock' data-ts='${esc(at||'')}'>${clockOf(at)}</span></div>
    <div class='bub'>${quo}${fmt(text)}</div></div>`;
}
function mineRow(s){ return outBub(null, '', s.text, s.at); }
function jumpToId(id){
  const el = document.getElementById('msg-'+id); if(!el) return;
  el.scrollIntoView({block:'center'});
  el.classList.add('flash'); setTimeout(()=>el.classList.remove('flash'), 1100);
}
// Ignore = read it, answer nothing, tell nobody. It leaves the desk the way an archived
// update does; `park` remains the CLI verb for a backlog hold, which is a different act.
function ignoreItem(id){
  BASKET.delete(id); basketSave();
  post('/basket',{id,kind:'read',text:''}).catch(()=>{});
  post('/ignore',{id}).then(()=>{ lastRaw=''; renderTray();
    toast('Ignored — off your desk, nothing sent. It is in History.'); })
   .catch(()=>toast('Could not ignore that item.'));
}
// The sticky pointer to an unanswered ask that has scrolled out of view — the unread-jump
// every chat client has.
function marker(){
  const box = document.getElementById('desklist');
  const up = document.getElementById('jumpup'), dn = document.getElementById('jumpdn');
  if(!box || !up || !dn) return;
  up.classList.remove('on'); dn.classList.remove('on');
  if(DFILTER !== 'convo') return;
  const els = [...box.querySelectorAll('.msg.need')];
  if(!els.length) return;
  const r = box.getBoundingClientRect();
  const above = els.filter(el=>el.getBoundingClientRect().bottom < r.top + 8);
  const below = els.filter(el=>el.getBoundingClientRect().top > r.bottom - 8);
  const paint = (btn, list, dir) => {
    const el = list[dir==='up' ? list.length-1 : 0];
    const id = el.dataset.k;
    const e = (DESKDATA.all||[]).find(x=>x.id===id) || {};
    btn.dataset.k = id;
    btn.innerHTML = `<span>${dir==='up'?'↑':'↓'}</span><span class='jid'>${esc(id)}</span>
      <span class='jt'>${esc(plainTxt(splitAsk(e.text)[0]||e.text).slice(0,64))}</span>
      ${list.length>1?`<span>+${list.length-1}</span>`:''}`;
    btn.classList.add('on');
  };
  if(above.length) paint(up, above, 'up');
  if(below.length) paint(dn, below, 'down');
}
function jumpMark(btn){ jumpToId(btn.dataset.k); }
// Where the answer will ACTUALLY land. An item the lead relayed answers to the LEAD, so
// naming the button after the department it is signed by promised the wrong destination.
function sendTo(){
  const e = cTarget ? (DESKDATA.all||[]).find(x=>x.id===cTarget.id) : null;
  if(e && e.src){
    const p = (PANES||[]).find(x=>x.guid === e.src);
    if(p && (p.agent || p.seat === 'ceo')) return p.agent || 'CEO';
  }
  return CONVO || 'session';
}
// An item signed by a department may still have been RELAYED by the lead, and the answer
// follows whoever wrote it. Say so on the row, or a relayed item reads as a direct one and
// the reply seems to go to the wrong place.
function wroteIt(e){
  const via = (PANES||[]).find(p=>p.guid === e.src);
  const who = via && (via.agent || (via.seat === 'ceo' ? 'CEO' : ''));
  if(!who || who === e.dept) return '';
  return `<span class='via' title='written to the board from this session — your answer goes back to it'>via ${esc(who)}</span>`;
}
// ---- arrival sound --------------------------------------------------------------------
// A needs-you rings low and twice so it is recognisable from across the room; an update is
// one soft high note. Browsers block audio until the page has been clicked, so the first
// arrival after a cold load can be silent — that is the platform, not the switch.
let SND = true, _ac = null, KNOWN = null;
try{ SND = localStorage.getItem('board-sound') !== 'off'; }catch(e){}
function _tone(f, at, dur, vol, type){
  const o = _ac.createOscillator(), g = _ac.createGain(), t = _ac.currentTime + at;
  o.type = type || 'sine'; o.frequency.value = f;
  g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(vol, t + .014);
  g.gain.exponentialRampToValueAtTime(.0001, t + dur);
  o.connect(g).connect(_ac.destination); o.start(t); o.stop(t + dur + .02);
}
function ring(kind){
  // Silent by design. The SERVER plays the arrival sound — theirs, from
  // ~/.claude/clock-in-sounds — so it rings whether or not this tab is open, and rings
  // once. A chime here beside it would double every arrival they are looking at.
  if(true) return;
  if(!SND) return;
  try{
    _ac = _ac || new (window.AudioContext || window.webkitAudioContext)();
    if(_ac.state === 'suspended') _ac.resume();
    if(kind === 'needs'){ _tone(392,0,.42,.16,'triangle'); _tone(311.1,.16,.5,.15,'triangle'); }
    else { _tone(1046.5,0,.3,.085); _tone(1396.9,.055,.26,.055); }
  }catch(e){}
}
function toggleSound(){
  SND = !SND;
  try{ localStorage.setItem('board-sound', SND ? 'on' : 'off'); }catch(e){}
  const b = document.getElementById('sndtog');
  if(b){ b.textContent = SND ? '🔔' : '🔕'; b.title = SND ? 'Arrival sound on' : 'Arrival sound off'; }
  if(SND) ring('info');
}
// Ring for what ARRIVED, never for what was already there. The first poll only seeds the
// set — a page reload must not replay the backlog.
function ringArrivals(entries){
  const open = (entries||[]).filter(e=>e.status==='open');
  if(KNOWN === null){ KNOWN = new Set(open.map(e=>e.id)); return; }
  let needs = 0, info = 0;
  open.forEach(e=>{ if(KNOWN.has(e.id)) return; KNOWN.add(e.id); isInfo(e) ? info++ : needs++; });
  if(needs) ring('needs'); else if(info) ring('info');
}
// A pasted screenshot is written into the project and the message carries its path — the
// one form of an image a session on the other end can actually open.
async function pasteImage(ev){
  const items = [...((ev.clipboardData||{}).items || [])].filter(i=>i.type.startsWith('image/'));
  if(!items.length) return;                       // plain text pastes are untouched
  ev.preventDefault();
  const ta = ev.target;
  for(const it of items){
    const file = it.getAsFile(); if(!file) continue;
    try{
      const q = '?name=' + encodeURIComponent((cTarget?cTarget.id:CONVO)||'paste');
      const j = await (await fetch('/paste'+q, {method:'POST',
        headers:{'X-Board':'1','Content-Type':file.type||'image/png'}, body:file})).json();
      const at = ta.selectionStart, txt = ta.value;
      const ins = (at && txt[at-1] && txt[at-1] !== ' ' ? ' ' : '') + j.path + ' ';
      ta.value = txt.slice(0,at) + ins + txt.slice(ta.selectionEnd);
      ta.setSelectionRange(at+ins.length, at+ins.length);
      autoGrow(ta); saveDraft();
      toast(`Image saved — ${j.path}`);
    }catch(e){ toast('Could not save that image.'); }
  }
}
// A message typed with nothing bound is addressed to the CONVERSATION and to no item in
// it. It used to ride on the thread's newest live card as an "ask" about that card, so a
// plain question arrived as "CEO-553 asks: …" against something unrelated, and read it.
function freeSend(){
  const ta = document.getElementById('ctext');
  const text = ta ? ta.value.trim() : '';
  if(!text) return;
  if(!CONVO){ toast('Open a conversation first — a message needs someone to go to.'); return; }
  const id = 'free:' + CONVO;
  BASKET.set(id, {kind:'msg', text}); basketSave();
  post('/basket',{id,kind:'msg',text}).catch(()=>{});
  ta.value=''; lastRaw=''; sendBasket();
}

// ---- the persistent composer ----------------------------------------------------------
// One box, always at the bottom of the thread. Reply/Ask on a message BINDS it; the strip
// above the box names what it answers, and the ⌘↩ lives on the Send button rather than in
// a second line of chrome saying the same thing.
let composerKey = null, freeDraft = '', composerSig = null, imeOn = false;
function drawComposer(force){
  const box = document.getElementById('composer');
  if(!box) return;
  if(DFILTER !== 'convo'){ box.innerHTML=''; box.classList.remove('on'); composerSig=null; return; }
  box.classList.add('on');
  // NEVER rebuild mid-composition. An IME holds uncommitted keystrokes in the element
  // itself, so replacing the element mid-word throws the composition away and leaves the
  // raw pinyin behind — 「很」 became `hen`. renderTray() runs on every poll and called
  // this unconditionally, so the box was being destroyed and rebuilt every 1.5 seconds
  // while the Boss typed into it.
  if(imeOn && !force) return;
  const t = TARGET, n = BASKET.size;
  const bound = cTarget ? (DESKDATA.all||[]).find(e=>e.id===cTarget.id) : null;
  const ta = document.getElementById('ctext');
  // The box carries the draft for THIS binding. Reading the live element unconditionally
  // is what left a sent answer sitting in the box afterwards: staging cleared the draft
  // and unbound the target, then the redraw copied the text back out of the old element.
  const key = cTarget ? cTarget.id : '\u0000free';
  const keep = (composerKey === key && ta) ? ta.value
             : cTarget ? (DRAFTS.get(cTarget.id) ?? (BASKET.get(cTarget.id)||{}).text ?? '')
             : freeDraft;
  composerKey = key;
  const focused = ta && document.activeElement === ta;
  // `n+1` assumed the composer always holds one more answer. With an empty box it promised
  // to send one that does not exist: "2 answers staged" under "Send all 3". Declared HERE,
  // after `ta` — reading it earlier was a temporal dead zone error that blanked the page.
  const typed = (ta && ta.value.trim()) || (cTarget && (DRAFTS.get(cTarget.id) || '').trim());
  const pending = n + (typed ? 1 : 0);
  const ctx = cTarget
    ? `<div class='cctx bound'>${cTarget.kind==='ask'?'Asking about':'Replying to'}
        <span class='cto'>${esc(cTarget.id)}</span>
        <span class='cqt'>${esc(plainTxt(splitAsk((bound||{}).text||'')[0] || (bound||{}).text || '').slice(0,80))}</span>
        <button class='cx' onclick='closeCompose()' title='unbind'>✕</button></div>`
    : `<div class='cctx'>Message <span class='cto'>${esc(CONVO||'')}</span></div>`;
  const hint = cTarget
    ? (cTarget.kind==='reply' ? 'resolves '+esc(cTarget.id)+' on the board' : esc(cTarget.id)+' stays open')
    : (t && t.ok ? 'goes back to the session that raised it'
                 : (t && t.why ? esc(t.why) : 'no session pinned — Send will copy instead'));
  const ph = cTarget && cTarget.kind==='ask' ? 'Your question…'
           : cTarget ? 'Your decision…' : 'Message '+esc(CONVO||'')+'…';
  const sendLabel = `Send${pending>1?' all '+pending:''} to ${esc(sendTo())}<kbd>⌘↩</kbd>`;
  const sig = composerSignature();
  // THE BOX the Boss IS TYPING INTO IS NEVER REBUILT. Everything around it may change — who it
  // is bound to, the hint, the Send label — and each of those is patched onto its own node
  // while the textarea stays exactly where it is, keeping its value, its caret, its
  // selection and any half-finished IME composition. The old code rewrote the whole box
  // and then tried to put their back: the text was restored, but the caret snapped to the
  // end and a mid-word composition was already gone. Restoring their is not the same thing
  // as not interrupting them, and that difference was the entire complaint (2026-08-04).
  const wrap = box.querySelector('.cwrap');
  if(wrap && ta && !force){
    if(sig !== composerSig){
      const cur = wrap.querySelector('.cctx');
      if(cur && cur.outerHTML !== ctx) cur.outerHTML = ctx;
      const hn = wrap.querySelector('.chint');
      if(hn && hn.innerHTML !== hint) hn.innerHTML = hint;
      const sb = wrap.querySelector('#sendbtn');
      if(sb && sb.innerHTML !== sendLabel) sb.innerHTML = sendLabel;
      if(ta.placeholder !== ph) ta.placeholder = ph;
      const forId = cTarget ? cTarget.id : '';
      if(ta.dataset.for !== forId) ta.dataset.for = forId;
      composerSig = sig;
    }
    // Only a real change of text is written into the element: assigning an identical
    // value still drops the caret to the end in every browser that matters.
    if(ta.value !== keep){ ta.value = keep; autoGrow(ta); }
    return;
  }
  if(sig === composerSig && !force) return;    // nothing about it changed — leave it alone
  composerSig = sig;
  box.innerHTML = `<div class='cwrap'>${ctx}
    <textarea id='ctext' rows='2' data-for='${esc(cTarget?cTarget.id:'')}'
      placeholder='${ph}'
      oninput='autoGrow(this);saveDraft()' onpaste='pasteImage(event)'
      oncompositionstart='imeOn=true' oncompositionend='imeOn=false'
      onkeydown='if((event.metaKey||event.ctrlKey)&&event.key==="Enter"){event.preventDefault();commitCompose(!event.shiftKey);}'>${esc(keep)}</textarea>
    <div class='crow2'><span class='chint'>${hint}</span>
      <span class='cbtns2'>
        <button class='stagebtn' onclick='commitCompose(false)' title='hold it in the tray and keep answering'>Stage<kbd>⇧⌘↩</kbd></button>
        <button class='sendbtn' id='sendbtn' onclick='commitCompose(true)'>${sendLabel}</button>
      </span>
    </div></div>`;
  const t2 = document.getElementById('ctext');
  if(t2){ autoGrow(t2); if(focused){ t2.focus(); t2.setSelectionRange(t2.value.length,t2.value.length); } }
}
// Everything the composer's markup depends on. Identical signature => identical DOM.
// NOT the target's title. That is the destination pane's iTerm session name, and a working
// Claude Code pane keeps its spinner in it — `⠂ ⠐ ⠄ ⠆` — so it changed several times a
// second for as long as the session they was writing to was busy. It appears nowhere in the
// composer's markup (`sendTo()` reads PANES, not the title), so it was pure noise, and it
// defeated the one guard standing between their keyboard and a rebuild on EVERY poll.
function composerSignature(){
  const t = TARGET || {};
  return [DFILTER, CONVO, cTarget && cTarget.id, cTarget && cTarget.kind,
          BASKET.size, t.ok, t.why].join('\u0000');
}
// The thread column is a FIXED region: the rail and the thread each scroll inside it and the
// composer never leaves the bottom. Measured rather than guessed — a hard-coded offset goes
// wrong the moment the SoT band wraps to two lines.
function sizeFrame(){
  const ib = document.getElementById('ib');
  if(!ib) return;
  const top = ib.getBoundingClientRect().top + window.scrollY;
  ib.style.height = Math.max(600, window.innerHeight - top - 22) + 'px';
}
window.addEventListener('resize', sizeFrame);
function deskList(D){
  if(DFILTER === 'convo') return convoThread(D);
  const T = D.T;
  if(DFILTER === 'desk'){
    // By design: with nothing waiting the desk SHRINKS to a line rather than padding
    // itself out with status. An empty board should get smaller, not look busy.
    const head = D.needs.length
      ? D.needs.map(e=>askRow(e, T, null, 'hot')).join('')
      : `<div class='dclear'>✓ Nothing waiting on you${lastAnsweredLine(D.lastAnsweredTs)}</div>`;
    return head + `<div class='dsplit'>Updates · ${D.info.length} unread</div>`
      + (D.info.length ? D.info.map(e=>askRow(e, T)).join('') : deskEmpty('unread'));
  }
  if(DFILTER === 'unread')  return D.info.length   ? D.info.map(e=>askRow(e,T)).join('')   : deskEmpty('unread');
  if(DFILTER === 'parked')  return D.parked.length ? D.parked.map(e=>askRow(e,T)).join('') : deskEmpty('parked');
  if(DFILTER === 'history') return D.hist.length
    ? D.hist.slice(0, DESK_TAIL).map(e=>askRow(e,T,e.updated)).join('')
      + (D.hist.length > DESK_TAIL
         ? `<div class='dmore'>showing the latest ${DESK_TAIL} of ${D.hist.length}</div>` : '')
    : deskEmpty('history');
  if(DFILTER === 'shipped') return D.shipped.length ? D.shipped.map(D.shipLine).join('') : deskEmpty('shipped');
  const rows = (D.work||{})[DFILTER] || [];
  return rows.length ? rows.map(deskTask).join('') : deskEmpty(DFILTER);
}
function drawDesk(){
  const D = DESKDATA; if(!D) return;
  // The compose box lives inside a row, so any redraw destroys the element they are typing
  // into. Capture the text and the caret first, restore them after.
  const ta0 = document.getElementById('ctext');
  const sel = ta0 ? [ta0.selectionStart, ta0.selectionEnd, document.activeElement === ta0] : null;
  if(ta0) saveDraft();
  // The conversation rail REPLACED the desk rail. Work and Shipped
  // stay as a footer group: they navigate to other views rather than holding desk items,
  // so deleting them would have cost them the shortcuts without buying any clarity.
  document.getElementById('rail').innerHTML = convoRail(D);
  document.getElementById('rail').classList.toggle('convo', true);
  sizeFrame();
  const list = document.getElementById('desklist');
  list.classList.toggle('thread', DFILTER === 'convo');
  // Where they was BEFORE the rewrite: parked on the newest message (stay pinned there,
  // the way a chat client does) or somewhere back up the thread (put their back exactly).
  // Both reads must happen while the old list is still in the box — after innerHTML the
  // box has been rebuilt and its scroll is 0. They were USED below and never captured,
  // so drawDesk threw a ReferenceError on every data-changing poll in the conversation
  // view, and everything after the throw was skipped: the caret and focus restore, the
  // unread pointer, and — because drawDesk is called from inside tick's try — the tab
  // counts for Tasks, Departments, Decisions, Mail and Archive, which then read whatever
  // they had said the last time the board was opened (2026-08-04).
  const keepTop = list.scrollTop;
  const atEnd = list.scrollHeight - list.scrollTop - list.clientHeight < 40;
  list.innerHTML = deskList(D);
  // The thread is oldest-at-top like a chat, and #desklist is its OWN scroll region, so
  // landing on the newest message is a scrollTop on that box. Never window.scrollTo: this
  // page does not scroll the window (elements sat at y=-12705 while window.scrollY read 0).
  // Only on an explicit open — a poll redraw must never yank their out of what they are reading.
  drawComposer();
  if(DFILTER === 'convo'){
    if(convoJump || atEnd){
      convoJump = false;
      // INSTANTLY. `.list.thread` sets `scroll-behavior: smooth`, so assigning scrollTop
      // animated the jump — opening a conversation crawled the whole thread from the
      // oldest message to the newest, which is exactly the scrolling the jump exists to
      // save them (2026-08-05). An explicit behavior beats the stylesheet. Re-applied on
      // the next frame because the thread is still growing when this runs: images, the
      // day marks and the composer all settle after the write, and a bottom measured
      // before they land leaves their short of it.
      const bottom = () => list.scrollTo({top: list.scrollHeight, behavior: 'auto'});
      bottom(); requestAnimationFrame(bottom);
      // What still moves the floor after those two frames is a late-loading image:
      // each one that finishes grows the thread under the jump, parking their mid-thread
      // — and every retry warmed the image cache, which is why repeated clicks crept
      // closer to the bottom. Re-pin on every load while they are still near the floor;
      // never after they have scrolled up to read.
      list.querySelectorAll('img').forEach(im=>{ if(!im.complete)
        im.addEventListener('load', ()=>{
          if(list.scrollHeight - list.scrollTop - list.clientHeight < 160) bottom();
        }, {once:true}); });
    }
    else if(keepTop != null) list.scrollTop = keepTop;
    requestAnimationFrame(marker);
  }
  const ta = document.getElementById('ctext');
  if(ta){
    const k = document.getElementById('ckeys');
    if(k) k.innerHTML = KEYHINT;
    autoGrow(ta);
    if(sel && sel[2]){ ta.focus(); ta.setSelectionRange(sel[0], sel[1]); }
  }
}
// `?desk=<row>` opens the Dashboard straight onto one rail row, the same way `?tab=`
// and `?task=` work. A URL row is a VISIT: it never overwrites the row they left open.
try{
  const _d = new URLSearchParams(location.search).get('desk');
  if(_d && DEMPTY[_d]) DFILTER = _d;
  else { const _s = localStorage.getItem('board-desk'); if(_s && DEMPTY[_s]) DFILTER = _s; }
}catch(e){}
let fails = 0, lastRaw = '', lastChange = null;
// ---- interactive desk: reply/ask basket + outbox tray + composer ----
// The tray and composer are FIXED bars outside #asks, so a background board update
// (a dept posting mid-reply) re-renders the columns without ever wiping an answer in
// progress. BASKET is the client mirror of the store's staged basket (server-persisted
// so a reload restores it). Nothing sends until "Send to session" flushes it as ONE
// message; replies resolve their item on the board at that moment (never re-run here).
const BASKET = new Map();   // id -> {kind:'reply'|'ask', text}
// Staged answers survive a reload, a server restart and a failed POST, because they are
// written to this browser the moment they are staged. The server copy is a convenience;
// THIS is the record. Losing a page of typed answers to a restart happened once and must
// not be possible twice.
const BKEY = 'board-basket';
function basketSave(){
  try{ localStorage.setItem(BKEY, JSON.stringify([...BASKET.entries()])); }catch(e){}
}
function basketLoad(){
  try{
    const raw = localStorage.getItem(BKEY);
    if(raw) JSON.parse(raw).forEach(([id,v])=>BASKET.set(id,v));
  }catch(e){}
}
basketLoad();
let basketInit = false, cTarget = null, TARGET = null, PANES = [], sending = false;
function syncBasket(server){
  // MERGE, never replace. The old rule cleared the local basket and adopted the server's,
  // so a restarted server — whose store had not yet caught the last POST — emptied a page
  // of typed answers. Anything staged here wins; the server can only ADD what this browser
  // has not seen.
  (server||[]).forEach(x=>{ if(!BASKET.has(x.id)) BASKET.set(x.id,{kind:x.kind,text:x.text}); });
  basketInit = true;
  basketSave();
}
function staged(e){ return BASKET.get(e.id); }
function rowCtl(e){
  if (e.status!=='open') return '';          // Reply/Ask only on live asks
  const s = staged(e);
  const rep = isInfo(e) ? '' :               // info needs no decision — Ask only
    `<button class="bbtn${s&&s.kind!=='ask'?' staged':''}" onclick="event.stopPropagation();openCompose('${esc(e.id)}','reply')">${s&&s.kind!=='ask'?'✎ Reply staged':'Reply'}</button>`;
  const ask =
    `<button class="bbtn${s&&s.kind==='ask'?' staged':''}" onclick="event.stopPropagation();openCompose('${esc(e.id)}','ask')">${s&&s.kind==='ask'?'✎ Question staged':'Ask'}</button>`;
  // An update needs no decision, only Ask. Archiving is the row's own tick in column one —
  // never a button buried behind a click on the entry.
  return `<div class="rowbtns">${rep}${ask}</div>`;
}
// The tick archives on their side: it applies at the click, folds the row to History, and
// tells nobody. It used to stage into the basket and ride out with the next Send as
// "N marked read (acknowledged, no action)" — a 已读回执 asking the reader to do nothing.
// Untick brings it back out of History, so it needs no confirm.
function archive(id, on){
  const yes = on !== false;
  BASKET.delete(id); basketSave();
  post('/basket',{id,kind:'read',text:''}).catch(()=>{});   // clear any legacy staged ack
  post('/read',{id,read:yes}).catch(()=>{});
  lastRaw=''; renderTray();
}
// Typing that was never staged. Cancel used to destroy it, and so did a mis-click on
// another row's Reply — the one thing a compose box must never do to a written answer.
const DRAFTS = new Map();
// ...and neither may a reload. DRAFTS lived only in memory, so the automatic reload a
// plugin update triggers took the sentence they was in the middle of. Staged answers have
// survived a restart since the day a page of them was lost; the unfinished one is worth
// the same three lines. Written on every keystroke, alongside the staged basket.
const DKEY = 'board-drafts';
function draftsSave(){
  try{ localStorage.setItem(DKEY, JSON.stringify({d:[...DRAFTS.entries()], f:freeDraft})); }
  catch(e){}
}
function draftsLoad(){
  try{
    const v = JSON.parse(localStorage.getItem(DKEY) || 'null');
    if(!v) return;
    (v.d||[]).forEach(([id,t])=>{ if(!DRAFTS.has(id)) DRAFTS.set(id,t); });
    if(!freeDraft) freeDraft = v.f || '';
  }catch(e){}
}
draftsLoad();
// ⌘↵ stages (the safe half), ⇧⌘↵ stages and delivers the batch. Name the modifier the
// reader's own keyboard has, rather than showing a Mac glyph to someone holding Ctrl.
// Computed AT the declaration: a later initialiser left every earlier reference in the
// temporal dead zone, which threw at load and took the rest of the script with it.
const KEYHINT = (function(){
  const mac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || '');
  const mod = mac ? '⌘' : 'Ctrl+', ent = mac ? '↩' : 'Enter', shift = mac ? '⇧' : 'Shift+';
  return `<kbd>${mod}${ent}</kbd> stage · <kbd>${shift}${mod}${ent}</kbd> send · <kbd>esc</kbd> close`;
})();
// The box itself, rendered INSIDE the row it answers (see the .rcompose note in the CSS).
// Listeners are inline attributes because the element is rebuilt with its row.
function composeBox(e){
  if(!cTarget || cTarget.id !== e.id) return '';
  const ask = cTarget.kind === 'ask';
  const staged = BASKET.get(e.id);
  const val = DRAFTS.get(e.id) ?? (staged ? staged.text : '');
  // A send flushes the WHOLE basket, not just this row, so name the real number.
  const n = BASKET.size + (BASKET.has(e.id) ? 0 : 1);
  return `<div class='rcompose' onclick='event.stopPropagation()'>
    <textarea id='ctext' rows='2' data-for='${esc(e.id)}'
      placeholder='${ask ? 'Your question…' : 'Your decision…'}'
      oninput='autoGrow(this)'
      onkeydown='if((event.metaKey||event.ctrlKey)&&event.key==="Enter"){event.preventDefault();stageCompose(event.shiftKey);}'
      >${esc(val)}</textarea>
    <div class='cbtns'><button class='primary' onclick='stageCompose()'>Stage</button
      ><button id='csend' onclick='stageCompose(true)'>${n>1 ? 'Stage &amp; send all '+n : 'Stage &amp; send'}</button
      ><button onclick='closeCompose()'>Cancel</button><span class='ckeys' id='ckeys'></span></div>
    <div class='cnote'>${ask ? (isInfo(e) ? 'Goes to the session; this update folds to History when sent.'
                                          : 'Goes to the session; this item stays open.')
                             : 'Resolves this item and goes to the session.'}</div>
  </div>`;
}
function openCompose(id, kind){
  if(cTarget && cTarget.id !== id) saveDraft();   // switching targets must not eat the old draft
  cTarget = {id, kind};
  drawDesk(); drawComposer(true); renderTray();
  const ta = document.getElementById('ctext');
  if(ta){
    ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length);
    ta.scrollIntoView({block:'nearest'});
  }
}
// Keyed on the row the box was RENDERED for, never on the current target. Reading
// cTarget instead meant that switching asks filed the visible text under the NEW id
// before the redraw replaced it — the first ask's answer appearing inside the second.
function saveDraft(){
  const ta = document.getElementById('ctext');
  const id = ta && ta.dataset ? ta.dataset.for : null;
  if(!id){ if(ta) freeDraft = ta.value; return; }
  const t = ta.value, st = BASKET.get(id);
  // Kept whenever it differs from what is staged — including an in-flight EDIT of a
  // staged answer, which a "not in the basket" test would have thrown away.
  if(t.trim() && (!st || st.text !== t.trim())) DRAFTS.set(id, t);
  else DRAFTS.delete(id);
  draftsSave();
}
function closeCompose(){ saveDraft(); cTarget=null; drawDesk(); renderTray(); }
// One-line answers were getting a box four lines tall; long ones needed a drag to read.
function autoGrow(ta){
  ta.style.height = 'auto';
  ta.style.height = Math.min(Math.max(ta.scrollHeight + 2, 46), 260) + 'px';
}
// Only the staged tray is fixed now. Its height still has to be reserved, or it covers
// the last rows of the list.
function layoutPanels(){
  const t = document.getElementById('tray');
  const on = t.classList.contains('on');
  document.body.classList.toggle('haspanel', on);
  document.body.style.paddingBottom = on ? (t.offsetHeight + 18) + 'px' : '';
}
// Every write gets a deadline. Without one a request that never resolves hangs the await
// that owns the UI state, and the page has no way to recover — the button and the tray sit
// on "Sending…" until a reload.
function postT(path, body, ms){
  const ac = new AbortController();
  const t = setTimeout(()=>ac.abort(), ms || 30000);
  return post(path, body, ac.signal).finally(()=>clearTimeout(t));
}
function post(path, body, signal){
  return fetch(path,{method:'POST',headers:{'X-Board':'1','Content-Type':'application/json'},
                     body:JSON.stringify(body||{}), signal});
}
// Stage holds an answer in the tray so several can go out together; Send flushes the whole
// tray including this one. Both run the same path, so a staged answer and a sent one are
// the same object and cannot drift.
function commitCompose(send){
  const ta = document.getElementById('ctext');
  const text = ta ? ta.value.trim() : '';
  let id = cTarget && cTarget.id, kind = cTarget && cTarget.kind;
  if(!id){
    // Nothing bound: this is a MESSAGE to the department, about nothing. It used to be
    // hung on the conversation's newest live item as an "ask" about that item, so a plain
    // question went out reading "CEO-553 asks: <their words>" against a card from the night
    // before that had nothing to do with it — and it marked that card read on the way past
    //. A message with no subject is not an ask; it is addressed
    // to the conversation and nothing else.
    if(!CONVO){ toast('Open a conversation first — a message needs someone to go to.'); return; }
    id = 'free:' + CONVO; kind = 'msg';
  }
  if(!text && !BASKET.has(id)){ if(send) sendBasket(); return; }
  if(text) BASKET.set(id,{kind,text}); else BASKET.delete(id);
  basketSave();                                  // before anything can fail
  DRAFTS.delete(id);
  post(`/basket`,{id,kind,text}).catch(()=>{});
  // Staging also reaches the clipboard: whatever else breaks, the words survive.
  if(!send && text){
    const all = [...BASKET.values()].map(v=>v.text).join('\n');
    try{ navigator.clipboard && navigator.clipboard.writeText(all); }catch(e){ legacyCopy(all); }
  }
  // Empty the box for real: unbind, drop the free draft, and forget which binding the
  // live element belonged to so the redraw cannot copy the text back out of it.
  cTarget = null; freeDraft = ''; composerKey = null; composerSig = null; lastRaw = '';
  imeOn = false;
  draftsSave();   // the box is empty for real — a reload must not bring the words back
  if(ta) ta.value = '';
  // Claim the send BEFORE the redraw, so the tray never renders a button for a message
  // already on its way — but never let a redraw strand the claim.
  if(send) sending = true;
  try{
    drawDesk(); drawComposer(true); renderTray();
  }catch(err){
    console.error('[board] redraw failed during commit', err);
    toast('The page had trouble redrawing — sending anyway.');
  }finally{
    if(send) sending = false;
  }
  if(send) sendBasket();
  else toast(`Staged ${id}. Send when you have answered the rest.`);
}
function stageCompose(send){ commitCompose(send); }   // the row-level box still calls this
function unstage(id){ BASKET.delete(id); basketSave(); post(`/basket`,{id,text:''}).catch(()=>{}); lastRaw=''; renderTray(); }
// Name the pane Send will type into, before they click. A red line here means the click
// will only reach the clipboard, and says why — which beats finding out from a toast after
// the basket has already been flushed.
function renderTarget(){
  // The thread header carries the same route, so the conversation always says where its
  // composer lands without their opening the tray.
  const hdr = document.getElementById('convoroute');
  if(hdr){
    const t = TARGET;
    hdr.textContent = t && t.ok ? `→ ${t.title || 'your session'}${t.tty ? ' · ' + t.tty : ''}`
                    : 'each answer goes back to the session that raised it';
  }
  const el = document.getElementById('traytarget');
  if(!el) return;
  const t = TARGET;
  if(!t){ el.textContent=''; el.classList.remove('bad'); return; }
  // "change" opens the seat picker. The auto-claim gets it right in the ordinary case and
  // cannot be right in every case — several sessions live in one tree (CEO, the Marketing
  // 分公司, whatever else is open) and only they know which one is the CEO.
  const pick = PANES.length>1 ? ` <a class="seatpick" onclick="event.stopPropagation();toggleSeats()">change</a>` : '';
  if(t.ok){
    el.classList.remove('bad');
    el.innerHTML = `→ <b>${esc(t.title || 'your session')}</b>${t.tty?' · '+esc(t.tty):''}${t.pinned?' · pinned':''}${pick}`;
  } else {
    el.classList.add('bad');
    el.innerHTML = `→ no pane · <b>${esc(t.why || 'unreachable')}</b> · Send will copy instead${pick}`;
  }
  renderSeats();
}
let SEATSOPEN = false;
function toggleSeats(){ SEATSOPEN = !SEATSOPEN; renderSeats(); }
function renderSeats(){
  const box = document.getElementById('seats');
  if(!box) return;
  if(!SEATSOPEN || !PANES.length){ box.classList.remove('on'); box.innerHTML=''; return; }
  box.classList.add('on');
  // The seat label is what the Boss recognises: the pane's own Claude Code title, then the cwd
  // that says whether it is the main checkout or a 分公司 worktree.
  const tag = {ceo:'CEO', dept:'dept', branch:'分公司', other:'other'};
  box.innerHTML = `<div class='seathd'>Send types into which session?</div>` + PANES.map(p=>
    `<div class="seat${p.current?' on':''}" onclick="pinSeat('${esc(p.guid)}')">
       <span class="seatk s-${esc(p.seat)}">${esc(tag[p.seat]||p.seat)}</span>
       <span class="seatn">${esc(p.label || p.title || '(untitled pane)')}${p.agent?` <span class="seata">${esc(p.agent)}</span>`:''}</span>
       <span class="seatc">${esc(p.cwd||'')}</span>
       <span class="seatt">${esc(p.tty||'')}</span>
     </div>`).join('');
}
async function pinSeat(guid){
  try{
    const j = await (await post('/pin',{guid})).json();
    TARGET = j; SEATSOPEN = false; renderTarget();
    toast(`Send now types into ${j.title || 'that session'}.`);
  }catch(e){ toast('Could not pin that session.'); }
}
function renderTray(){
  renderTarget();
  drawComposer();
  const tb = document.getElementById('traysend');
  if(tb){ tb.disabled = sending; tb.textContent = sending ? 'Sending…' : 'Send to session'; }
  const tray = document.getElementById('tray');
  const items = [...BASKET.entries()];
  if(!items.length){
    tray.classList.remove('on'); document.getElementById('traylist').innerHTML='';
  } else {
    document.getElementById('traycount').textContent = sending
      ? 'Sending ' + items.length + '…'
      : items.length+(items.length===1?' answer staged':' answers staged');
    // A free message is keyed `free:<dept>` because it belongs to no item; the chip says
    // where it is going rather than printing that key at them.
    document.getElementById('traylist').innerHTML = items.map(([id,v])=>
      `<span class="tchip${v.kind==='ask'?' ask':''}"><span class="tk">${v.kind==='msg'?'→ '+esc(id.slice(5)):esc(id)}${v.kind==='ask'?' ?':''}</span><span class="tt" title="${esc(v.text)}">${esc(v.text)}</span><span class="tx2" title="unstage" onclick="unstage('${esc(id)}')">✕</span></span>`).join('');
    tray.classList.add('on');   // stays up WHILE composing — it used to vanish behind it
  }
  layoutPanels();
}
function toast(msg){
  const t=document.getElementById('toast'); t.textContent=msg; t.classList.add('on');
  clearTimeout(t._t); t._t=setTimeout(()=>t.classList.remove('on'),3800);
}
function legacyCopy(text){
  try{
    const ta=document.createElement('textarea'); ta.value=text;
    ta.style.position='fixed'; ta.style.opacity='0'; document.body.appendChild(ta);
    ta.select(); const ok=document.execCommand('copy'); document.body.removeChild(ta); return ok;
  }catch(e){ return false; }
}
async function sendBasket(){
  if(!BASKET.size || sending) return;
  sending = true;
  const btn = document.getElementById('sendbtn');
  if(btn){ btn.disabled = true; btn.dataset.was = btn.innerHTML; btn.textContent = 'Sending…'; }
  let j;
  // The try used to wrap the whole of the post-send handling, so ANY error after the
  // request — a toast, a re-render, a copy — reported "Send failed" for a message the
  // session had already received. Only the request itself can fail a send.
  try{
    j = await (await postT(`/send`, {}, 45000)).json();
  }catch(e){
    sending = false;
    const b0 = document.getElementById('sendbtn');
    if(b0){ b0.disabled = false; if(b0.dataset.was) b0.innerHTML = b0.dataset.was; }
    renderTray();                       // the tray must leave "Sending…" too
    toast(e && e.name === 'AbortError'
      ? 'Send timed out — the board did not answer. Your answers are still staged, and on your clipboard.'
      : 'Send failed — your answers are still staged, and on your clipboard.');
    return;
  }
  try{
    BASKET.clear(); basketSave(); basketInit=true; lastRaw=''; closeCompose(); renderTray();
    const n=j.n||0, msg=j.msg||'', legs=j.legs||[];
    // Copy FIRST, always — delivered or not. The basket is flushed by the time this runs,
    // so the clipboard is the only remaining copy of what they wrote.
    let copiedAll=false;
    try{ if(msg && navigator.clipboard){ await navigator.clipboard.writeText(msg); copiedAll=true; } }catch(e){}
    if(!copiedAll && msg) copiedAll = legacyCopy(msg);
    const named = legs.filter(l=>l.to).map(l=>l.to).join(' · ');
    const who = named ? ` → ${named}` : '';
    if(!msg){ toast('Nothing staged.'); return; }
    // Each answer went home to the session that raised it. Nothing left to do.
    if(j.delivery==='ok'){ toast(`Sent ${n} answer(s) back to ${legs.length>1?legs.length+' sessions':'its session'}${who}.${copiedAll?' Also on your clipboard.':''}`); return; }
    if(j.delivery==='partial'){
      const bad = legs.filter(l=>l.delivery!=='ok');
      // The undelivered halves replace the whole-message copy: those are the ones they have
      // to place by hand.
      let copied=false;
      try{ if(navigator.clipboard){ await navigator.clipboard.writeText(bad.map(l=>l.msg).join('\n')); copied=true; } }catch(e){}
      toast(`${legs.length-bad.length} of ${legs.length} delivered; ${bad.length} could not be reached${copied?' — the undelivered ones are on your clipboard':''}.`);
      return;
    }
    // Landed in the input box but the echo could not be confirmed, so Return was NOT
    // pressed. The text is already there — they finish it, and nothing was typed blind.
    if(j.delivery==='typed'){ toast(`Typed ${n} answer(s) into your session${who} — press Enter to send (the echo could not be confirmed, so it was not submitted for you).`); return; }
    // Everything else means we would not touch the pane at all — clipboard fallback.
    const amb = legs.filter(l=>l.delivery==='ambiguous').map(l=>l.why).filter(Boolean);
    if(amb.length){
      toast(`Not delivered — ${amb[0]}. ${copiedAll?'It is on your clipboard — paste it into the right seat.':'Copy failed too.'}`);
      return;
    }
    const why = j.delivery==='nosession' ? 'the pinned pane is no longer running claude'
              : j.delivery==='notfound'  ? 'the pinned pane is gone'
              : j.delivery==='wrongseat' ? 'the pane it auto-claimed is not your CEO session — hit “change” and pick it'
              : j.delivery==='skip'      ? 'no pane is pinned yet'
              : 'iTerm2 could not be reached';
    toast(copiedAll
      ? `Not delivered — ${why}. ${n} answer(s) on your clipboard; paste (⌘V) into your session + Enter.`
      : `Resolved on the board — ${why}, and the copy failed too.`);
  }catch(e){
    // The message went. Anything broken here is display only, and must not claim otherwise.
    toast('Sent. (The page had trouble redrawing — reload if it looks stale.)');
  }finally{
    sending = false;
    const b = document.getElementById('sendbtn');
    if(b){ b.disabled = false; if(b.dataset.was) b.innerHTML = b.dataset.was; }
    renderTray();                       // clear "Sending…" now, not at the next poll
  }
}
// Dashboard tabs (Dashboard glance · Tasks kanban home). Persisted in localStorage;
// #x expand-all still works independently of the active tab.
function showTab(name, pin){
  document.querySelectorAll('nav.tabs button').forEach(b=>b.classList.toggle('on', b.dataset.tab===name));
  document.querySelectorAll('section.tabpane').forEach(s=>s.classList.toggle('on', s.id==='tab-'+name));
  if(pin !== false) try{ localStorage.setItem('board-tab', name); }catch(e){}
}
// `?tab=<id>` opens straight onto one view (a linkable tab, and the only way a headless
// screenshot can reach a pane behind a click). A URL tab is a VISIT, not a preference —
// it never overwrites the tab they left the board on.
try{
  const _q = new URLSearchParams(location.search).get('tab');
  if(_q && document.getElementById('tab-'+_q)) showTab(_q, false);
  else { const _t=localStorage.getItem('board-tab'); if(_t && document.getElementById('tab-'+_t)) showTab(_t); }
}catch(e){}
// Departments 花名册: the model each dept runs on is its badge (edict's officials board,
// re-pointed from token cost to model). Tier → colour; unset shows plainly.
function modelPill(m, live){
  if(!m) return `<span class="mpill m-none" title="no model set in the agent file">model unset</span>`;
  const k = /opus/i.test(m)?'opus':/sonnet/i.test(m)?'sonnet':/haiku/i.test(m)?'haiku':/fable/i.test(m)?'fable':'other';
  const tip = live ? 'live: this dept was spawned with this model this session'
                   : 'default from the agent file — the CEO can override it at spawn';
  return `<span class="mpill m-${k}" title="${tip}">${esc(m)}${live?`<span class="mlive">live</span>`:''}</span>`;
}
function deptCard(d){
  const st = {}; (d.statuses||[]).forEach(s=>{ if(s) st[s]=(st[s]||0)+1; });
  const chips = ['doing','review','blocked','todo','done'].filter(s=>st[s])
    .map(s=>`<span class="stpill st-${s}">${st[s]} ${s}</span>`).join(' ');
  const handle = `<span class="dchip" style="--dh:${hue(d.handle)}">${esc(d.handle)}</span>`;
  const nicks = (d.names||[]).map(n=>`<span class='dchip' style='--dh:${hue(n)}'>${esc(n)}</span>`).join(' ');
  // Honest about source: 'default' is the frontmatter fallback; 'running' is the live
  // spawn override the CEO chose this session (the real answer to "what runs this dept").
  // Only the live override is worth a line: the pill already says which model, and its
  // tooltip already says frontmatter-default. Printing "no live override this session"
  // under every idle dept put the same sentence on the page ten times.
  const src = (d.model && d.live)
    ? `running ${esc(d.model)}${d.default_model&&d.default_model!==d.model?` · default ${esc(d.default_model)}`:''}` : '';
  return `<div class="dept">
    <div class="dhd">${handle}${nicks?` ${nicks}`:''}${d.external?`<span class='pill px'>分</span>`:''}${modelPill(d.model, d.live)}</div>
    ${d.role?`<div class="drole">${md(d.role)}</div>`:''}
    <div class="dstats">${d.cards?`${d.active} active · ${d.cards} card(s)`:'idle'}${chips?' · '+chips:''}</div>
    ${src?`<div class="msrc">${src}</div>`:''}
  </div>`;
}
// Finance 财务台账: the configured Obsidian Base's ledger, one period per row. Columns
// come from the .base view order; numeric cells right-align in tabular figures.
function financeView(f){
  if(!f || !f.rows || !f.rows.length)
    return `<p class='empty'>No finance base configured — set <code>finance</code> in orchestrate.json to a <code>.base</code> file.</p>`;
  const cols = (f.columns && f.columns.length) ? f.columns : Object.keys(f.rows[0]);
  const head = cols.map(c=>`<th>${esc(c)}</th>`).join('');
  const body = f.rows.map(r=>`<tr>${cols.map(c=>{
    const v = (r[c]==null?'':String(r[c]));
    const num = v!=='' && !isNaN(v.replace(/,/g,''));
    return `<td class="${num?'num':''}">${v===''?`<span class='e'>—</span>`:esc(v)}</td>`;
  }).join('')}</tr>`).join('');
  return `<div class='fmeta'>${esc(f.name)} · ${f.rows.length} period(s) · <code>${esc(f.folder)}</code></div>
    <div class='ftable'><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}
// Decisions/Canon: the org's decision memory — recent dated rulings (title clamped;
// full why lives in DECISIONS.md) beside the CANON settled-answer index (topic → pointer).
function decisionsView(dd){
  if(!dd) return `<p class='empty'>No decision log yet (DECISIONS.md / CANON.md).</p>`;
  const decs = (dd.decisions||[]).map(x=>
    `<div class='dec'><div class='dech'><span class='decdate'>${esc(x.date)}</span>${x.key?`<span class='deckey'>${esc(x.key)}</span>`:''}</div><div class='dectitle'>${md(x.title)}</div></div>`).join('') || `<p class='empty'>—</p>`;
  // Canon as compact flex rows, NOT a table: a stretched grid cell was distributing
  // the table's row heights into huge blank cells (Boss 2026-07-22). A registry row is
  // a QUESTION and the file that answers it; needs-re-check is a flag ON the row, never
  // the panel's whole content — reading the re-check list as the canon is what made an
  // emptied queue look like a vanished registry.
  const canon = (dd.canon||[]).map(x=>
    `<div class='cx${x.recheck?' cwarn':''}'><span class='ctopic' title='${esc(x.topic)}'>${esc(x.topic)}</span>${x.dept?`<span class='dchip' style='--dh:${hue(dhead(x.dept))}'>${esc(dhead(x.dept))}</span>`:''}<span class='cptr' title='${esc(x.file)}'>${esc(x.file)}</span>${x.recheck?`<span class='crecheck' title='needs re-check: ${esc(x.recheck)}'>⚠ 待复核</span>`:''}${x.updated?`<span class='cupd'>${esc(x.updated)}</span>`:''}</div>`).join('') || `<p class='empty'>—</p>`;
  const dshown = (dd.decisions||[]).length, dtotal = dd.decisions_total || dshown;
  const cshown = (dd.canon||[]).length, ctotal = dd.canon_total || cshown;
  const rech = dd.recheck_total || 0;
  return `<div class='panel'><h3 class='dsub'>Recent rulings <span class='count'>${dtotal}</span></h3>${decs}
      ${dtotal>dshown?`<div class='blmore'>showing the latest ${dshown} · the log is docs/DECISIONS.md</div>`:''}</div>
    <div class='panel'><h3 class='dsub'>Canon · settled answers <span class='count'>${ctotal}</span>${
        rech?`<span class='count cwarnc'>${rech} 待复核</span>`:''}</h3>${canon}
      ${ctotal>cshown?`<div class='blmore'>showing ${cshown} · the index is docs/CANON.md</div>`:''}</div>`;
}
// A dept cell often carries its scope in prose ("Backend-Engine (sonnet seat,
// diagnosis-first)"). A scanned line wears the handle; the tooltip keeps every word.
function dhead(d){ const h = String(d||'').split(' (')[0].split(' · ')[0].trim();
  return h.length > 22 ? h.slice(0,21)+'…' : h; }
// An unset field in a ship line is a placeholder, and a run of them says nothing:
// ` · —` and ` · #—` (a completion with no session task id) collapse before render.
function shipClean(s){ return String(s||'').replace(/( · #?—)+(?= · )/g,''); }
// `time:` is sender-written (0.9.33), and the field writes prose into it —
// "2026-07-24 (crossed-message correction, minutes after your carry-queued note)".
// The column shows the machine head (date · clock) and keeps the sender's own words
// in the tooltip; a value with neither reads as written.
function mtime(t){
  const s = (t||'').trim();
  const d = s.match(/\d{4}-\d{2}-\d{2}/), h = s.match(/\d{1,2}:\d{2}/);
  return [d?d[0]:'', h?h[0]:''].filter(Boolean).join(' ') || s;
}
// Mail & Branches: the 分公司 offices + the mail lane (letters newest-first, unread dot).
function mailView(mm){
  if(!mm) return `<p class='empty'>No mail lane (docs/board/mail).</p>`;
  const br = (mm.branches||[]).map(b=>
    `<div class='brn'><span class='dchip' style='--dh:${hue(b.handle)}'>${esc(b.handle)}</span><span class='pill px'>分</span><span class='brmeta'>${b.letters} letter(s)${b.unread?` · <b>${b.unread} unread</b>`:''}${b.last?` · <span title='${esc(b.last)}'>last ${esc(mtime(b.last))}</span>`:''}</span></div>`).join('');
  const rows = (mm.mail||[]).map(m=>{
    const un = (m.status||'').toLowerCase()==='unread';
    const seatName = (m.seat && m.seat !== '—') ? m.seat : '';
    const deptTxt = (m.dept && m.dept !== '—') ? m.dept : '';
    const seatCell = (name) => {
      if (!seatName || name !== seatName) return esc(name);
      const label = deptTxt ? deptTxt : name;
      return `${esc(label)} <span class='dchip' style='--dh:${hue(seatName)}'>${esc(seatName)}</span>`;
    };
    return `<tr class='${un?'unread':''}'><td class='mstat'>${un?'●':''}</td><td class='mfrom'>${seatCell(m.from)}</td><td class='marrow'>→</td><td class='mto'>${seatCell(m.to)}</td><td class='mre' title='${esc(m.re)}'>${esc(m.re)}</td><td class='mtime' title='${esc(m.time)}'>${esc(mtime(m.time))}</td></tr>`;
  }).join('');
  const shown = (mm.mail||[]).length, total = mm.total || shown;
  return `${br?`<div class='panel'><div class='dsub'>Branch offices</div><div class='brwrap'>${br}</div></div>`:''}
    <div class='dsub' style='margin-top:1.4em'>Mail lane <span class='count'>${total}</span></div>
    <div class='ftable'><table><tbody>${rows||`<tr><td class='empty'>—</td></tr>`}</tbody></table></div>
    ${total>shown?`<div class='blmore'>showing the latest ${shown} · the lane is docs/board/mail</div>`:''}`;
}
// Archive: recently-shipped tail + BACKLOG history. A row is the machine log's record —
// date · dept · status (only when it isn't a clean `done`) · sha · the note that says
// whether an L2 pass was on file. The count is the TRUE total; the list is a slice, and
// says so rather than letting 40 rows imply the history is 40 rows long.
function archiveView(ar){
  if(!ar) return `<p class='empty'>Nothing archived yet.</p>`;
  const ship = (ar.shipped||[]).map(x=>`<div class='shl'>${md(shipClean(x))}</div>`).join('');
  const shown = (ar.backlog||[]).length, total = ar.total || shown;
  const bl = (ar.backlog||[]).map(x=>
    `<div class='blg'><div class='blh'>${x.date?`<span class='decdate'>${esc(x.date)}</span>`:''}${x.dept?`<span class='dchip' style='--dh:${hue(dhead(x.dept))}' title='${esc(x.dept)}'>${esc(dhead(x.dept))}</span>`:''}${x.status&&x.status!=='done'?`<span class='badge ${x.status==='dropped'?'blocked':'review'}'>${esc(x.status)}</span>`:''}${x.sha?`<span class='blsha'>${esc(x.sha)}</span>`:''}</div><div class='dectitle'>${md(x.title)}</div>${x.note?`<div class='blnote' title='${esc(x.note)}'>${esc(x.note)}</div>`:''}</div>`).join('');
  return `${ship?`<div class='panel'><div class='dsub'>Recently shipped</div>${ship}</div>`:''}
    <div class='panel' style='margin-top:${ship?'14px':'0'}'>
      <div class='dsub'>History · BACKLOG <span class='count'>${total}</span></div>${bl||`<p class='empty'>—</p>`}
      ${total>shown?`<div class='blmore'>showing the latest ${shown} · the full log is docs/BACKLOG.md</div>`:''}</div>`;
}
window.addEventListener('error', e => {
  // A thrown handler used to leave the board looking merely idle. Say it out loud: a stuck
  // "Sending…" with no request behind it is indistinguishable from a slow one.
  try{ toast('Page error: ' + (e.message || 'unknown') + ' — reload if things look stuck.'); }catch(_){}
});
async function tick(){
  try{
    const r = await fetch('/state.json', {cache:'no-store'});
    const s = await r.json();
    if (s.version !== undefined && s.version !== VER) { location.reload(); return; }
    const proj = s.project || 'Boss Board';
    document.getElementById('proj').textContent = proj;
    document.title = proj + ' · Boss Board';
    // Re-render ONLY when the data changed — a rebuild every poll would collapse
    // whatever the Boss just expanded and churn the DOM for nothing.
    // `sent` is part of the signature because an ASK changes nothing on its entry — it
    // stays open, unread, untouched — so a question they had just sent did not move `raw`
    // and the thread never redrew to show it.
    const raw = JSON.stringify([s.entries, s.taskboard, s.sot, s.sent, s.seats]);
    fails = 0;
    document.body.style.opacity = "";   // clear a stale "disconnected" dim on reconnect
    ringArrivals(s.entries);
    TARGET = s.send_target || null;      // where Send lands — named in the tray, every poll
    PANES = s.panes || [];               // the seats they can move it to
    SENT = s.sent || [];                 // everything they have said, drawn in the thread
    syncBasket(s.basket); renderTray();  // restore/reflect staged answers every poll
    if (raw === lastRaw){
      retick();   // no redraw, but the ages on the page are still getting older
      marker();   // ...and an ask answered elsewhere must drop its pointer
      setHeader((s.entries||[]).filter(e=>e.status==='open' && !isInfo(e)).length, null);
      return;
    }
    lastRaw = raw; lastChange = new Date();
    document.getElementById('sot').innerHTML = s.sot ? sotBand(s.sot) : '';
    const es = s.entries || [];
    const tb = s.taskboard || {tasks:[], shipped:[]};
    NICKS = s.seats || {};
    const T = {list: tb.tasks, byId: {}};
    tb.tasks.forEach(t=>{ if(t.task_id) T.byId[t.task_id]=t; });
    // Both desk lanes read NEWEST-FIRST. Needs-you used to drain
    // oldest-first so nothing sank — but the Boss reads the top of the desk, and the ask they
    // just watched arrive was landing at the bottom under a week of answered-adjacent
    // history. Age is on every row, so what has waited longest still says so out loud.
    // Parked keeps the queue order: that lane IS the backlog, and it drains from the front.
    const bywait = (a,b)=>(a.created||'').localeCompare(b.created||'');
    const open = es.filter(e=>e.status==='open').sort(bywait);
    const needsOpen = open.filter(e=>!isInfo(e)).reverse();
    const infoOpen  = open.filter(e=>isInfo(e) && !e.read).reverse();
    // A read Information item folds out of the active feed into History (// toggling read collapses the card + sends a brief "id: Read" on the next Send).
    const readInfo  = open.filter(e=>isInfo(e) && e.read)
                          .sort((a,b)=>(b.updated||'').localeCompare(a.updated||''));
    const parked = es.filter(e=>e.status==='parked').sort(bywait);
    const resolved = es.filter(e=>e.status==='resolved')
                       .sort((a,b)=>(b.updated||'').localeCompare(a.updated||''));
    const histAll = readInfo.concat(resolved);
    // Priority sort inside a rail lane: P0 < P1 < P2 < unset lexically; JS sort is
    // stable, so board (id) order holds within a tier.
    const pr = t=>/^P\d$/.test(t.priority||'') ? t.priority : 'P8';
    const psort = arr=>arr.slice().sort((a,b)=>pr(a).localeCompare(pr(b)));
    const shipped = tb.shipped||[];
    // Shipped-line head: `date · #proj · #tid · …` (6-field, 0.9.24)
    // or legacy `date · #tid · …` — pill the leading id(s); the two-id replace fires first
    // and leaves nothing for the one-id pattern to re-match. A LONE leading id is the
    // session task_id (card-less lines), so it wears the NEUTRAL pill — coral is reserved
    // for the durable #NNN. Placeholder runs (" · — · —") collapse before render.
    const pillDone = h => h
      .replace(/^(\d{4}-\d{2}-\d{2}) · (#\d+) · (#\d+) · /, "$1 <span class='pill pj'>$2</span><span class='pill pt'>$3</span> ")
      .replace(/^(\d{4}-\d{2}-\d{2}) · (#\d+) · /, "$1 <span class='pill pt'>$2</span> ");
    const shipLine = raw => { const x = shipClean(raw);
      return `<div class='done-line${xc('s:'+x)}' data-k="${esc('s:'+x)}" tabindex="0" onclick="tog(this)"><div class='dl'>${pillDone(md(x))}</div></div>`; };
    const d = new Date();
    const today = d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
    // Tasks is a card GRID now, not three columns: the pipeline strip carries the state
    // a column used to stand for, and a filter carries the rest. Sorted by what is
    // moving — doing, then the L2 queue, then blocked, then the backlog, then done —
    // with priority holding inside each band (P0 < P1 < P2 < unset, lexically).
    TASKS = tb.tasks.slice().sort((a,b)=>
      (TORDER[a.status]??3)-(TORDER[b.status]??3) || pr(a).localeCompare(pr(b)));
    drawTasks();
    // The desk: one slice per rail row, then draw. Lane rule lives in deskLanes().
    DESKDATA = {
      T, all: es, needs: needsOpen, info: infoOpen, parked, hist: histAll,
      shipped: shipped.filter(x=>x.trim().startsWith(today)), shipLine,
      lastAnsweredTs: resolved.length ? (resolved[0].updated || '') : '',
      work: deskLanes(tb.tasks, psort),
    };
    drawDesk();
    // Departments 花名册 (Departments tab)
    const roster = s.roster || [];
    document.getElementById('depts').innerHTML = roster.length
      ? roster.map(deptCard).join('')
      : `<p class='empty'>No department roster yet — add .claude/agents/&lt;handle&gt;.md files.</p>`;
    // Finance (only surfaces when a finance base is configured — tab hidden otherwise)
    const fin = s.finance;
    const fbtn = document.querySelector('nav.tabs button[data-tab="finance"]');
    if (fbtn) fbtn.style.display = fin ? '' : 'none';
    document.getElementById('finance').innerHTML = financeView(fin);
    document.getElementById('decisions').innerHTML = decisionsView(s.decisions);
    const mbtn = document.querySelector('nav.tabs button[data-tab="mail"]');
    const hasMail = s.mail && (((s.mail.mail||[]).length)||((s.mail.branches||[]).length));
    if (mbtn) mbtn.style.display = hasMail ? '' : 'none';
    document.getElementById('mail').innerHTML = mailView(s.mail);
    document.getElementById('archive').innerHTML = archiveView(s.archive);
    setHeader(needsOpen.length, TASKS.filter(inFlight).length);
    // Each tab carries its own count, so the shape of the org is legible before a click.
    badge('b-tasks', TASKS.filter(inFlight).length);
    badge('b-depts', roster.length);
    badge('b-decisions', s.decisions ? (s.decisions.decisions_total || (s.decisions.decisions||[]).length) : 0);
    badge('b-mail', s.mail ? (s.mail.total || (s.mail.mail||[]).length) : 0);
    badge('b-archive', s.archive ? (s.archive.total || (s.archive.backlog||[]).length) : 0);
  }catch(e){
    // A restarting/reaped server recovers within a poll or two — keep the view.
    // Past that the server is gone: a frozen tab must not impersonate a live board.
    if(++fails >= 4){
      document.body.style.opacity = ".4";
      document.getElementById('stamp').textContent =
        "disconnected — run /board to reopen";
    }
  }
}
tick(); setInterval(tick, POLL);
</script></body></html>""" % (POLL_MS, json.dumps(BUILD))


# Inline-viewable types the browser renders natively. Everything else ships as
# text/plain — never an executable type: html/svg served from the board's origin
# could script against the panel (and any future endpoint on it).
VIEWABLE = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".webp": "image/webp", ".pdf": "application/pdf"}


def _resolve_under(base, p):
    """abspath of `p` under `base`, or None. Guards: relative paths only, realpath
    pinned under base (kills `..` and symlink escapes), regular files only."""
    if not p:
        return None
    p = os.path.expanduser(p)
    # An ABSOLUTE path is accepted only when it lands inside this base — the realpath pin
    # below is the guard either way, so refusing them outright bought nothing and cost
    # every link to a dept worktree, which is exactly where a pre-merge render lives.
    full = os.path.realpath(p if os.path.isabs(p) else os.path.join(base, p))
    baser = os.path.realpath(base)
    if not full.startswith(baser + os.sep):
        return None
    # A DIRECTORY is openable but not servable; the caller decides which it needs.
    if not (os.path.isfile(full) or os.path.isdir(full)):
        return None
    return full


def _linked_worktrees(root):
    """Paths of the repo's linked worktrees (main checkout excluded); [] outside git."""
    try:
        out = subprocess.run(["git", "-C", root, "worktree", "list", "--porcelain"],
                             capture_output=True, text=True, timeout=5).stdout
        wts = [l.split(" ", 1)[1].strip() for l in out.splitlines()
               if l.startswith("worktree ")]
        rootr = os.path.realpath(root)
        return [w for w in wts if os.path.realpath(w) != rootr]
    except Exception:
        return []


_SEARCH_PRUNE = {"node_modules", "__pycache__"}


def _find_by_name(base, name):
    """Every file called `name` under base — hidden dirs and dependency trees pruned,
    each hit re-checked through _resolve_under so the symlink guard holds."""
    hits = []
    for cur, dirs, files in os.walk(base):
        dirs[:] = [x for x in dirs if not x.startswith(".") and x not in _SEARCH_PRUNE]
        if name in files:
            full = _resolve_under(base, os.path.relpath(os.path.join(cur, name), base))
            if full:
                hits.append(full)
    return hits


def resolve_file(root, p):
    """(abspath, content-type) for a project file the panel may serve, else None.
    Backs the /file endpoint that makes paths in asks clickable. A miss in the main
    checkout falls through to the repo's linked worktrees — pre-merge artifacts
    (renders the Boss is asked to eyeball) live only in a dept pane's worktree. The
    main checkout wins when both have the file: post-merge, master is the truth.
    A bare filename (no slash — CEOs abbreviate a sibling artifact to its name alone)
    resolves by basename search under the same roots; newest match wins, because an
    ask points at the render just produced, not last month's namesake."""
    roots = [root] + _linked_worktrees(root)
    for base in roots:
        full = _resolve_under(base, p)
        if full:
            if os.path.isdir(full):
                return full, None          # openable in Finder, never served as bytes
            return full, VIEWABLE.get(os.path.splitext(full)[1].lower(),
                                      "text/plain; charset=utf-8")
    if p and "/" not in p and "\\" not in p:
        for base in roots:
            hits = _find_by_name(base, p)
            if hits:
                full = max(hits, key=os.path.getmtime)
                return full, VIEWABLE.get(os.path.splitext(full)[1].lower(),
                                          "text/plain; charset=utf-8")
    return None


def _launch_default(full):
    """Hand a resolved file to the OS default app — the CLI-click behaviour the Boss
    expects for text-y files the browser would only dump as plain text. Test/verify
    runs set BOARD_SKIP_LAUNCH=1 to exercise routing without apps popping up."""
    if os.environ.get("BOARD_SKIP_LAUNCH"):
        return
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", full])
        elif os.name == "nt":
            os.startfile(full)  # noqa: no-cover — windows only
        else:
            subprocess.Popen(["xdg-open", full])
    except Exception:
        pass


def iterm_target_file(root):
    """Where the Boss's iTerm2 session id (env ITERM_SESSION_ID) is recorded, so Send types
    a reply into THAT exact pane."""
    return os.path.join(runtime_dir(root), "iterm-target")


def capture_iterm_target(root, sid, meta=None, force=False):
    """Record `sid` as the pane Send types into. Called from the Stop path (stop_iterm_
    capture) for the LEAD session only — never at session start: a freshly-spawned teammate's
    transcript isn't stamped yet, so the start-time lead check mis-read it as lead and let it
    overwrite the Boss's target with its own pane (the Legal teammate
    became the target, so replies typed into Legal's input, invisible to the Boss). At turn
    end the transcript is stamped, so lead-vs-teammate is reliable. Fail-open.

    Written as JSON (guid + who/when/where) rather than a bare GUID: the pane id alone can
    only ever answer "does some pane still hold this id", and a pane outlives the session
    that claimed it. The extra fields let Send SHOW their the target and let the interlock
    below refuse a pane that is no longer the session it was pinned for.

    The seat is CLAIMED, not last-writer-wins. Every session with a cwd under the project
    reaches this function at turn end — the Marketing 分公司 in its worktree, and any
    unrelated `claude` they happen to have open in the tree. None of them carry the
    agentName/teamName stamp a teammate has, so the lead guard upstream waves all of them
    through, and the last one to finish a turn used to own the pane Send typed into. So:

      · a 分公司 seat can never take the CEO's pane, whatever it does;
      · a seat they pinned from the board is never overwritten by capture at all;
      · an incumbent that is STILL ALIVE keeps the seat; another session takes over only
        once the pane is gone or has stopped running claude.

    Returns True when the record was written."""
    sid = (sid or "").strip()
    if not sid:
        return False
    rec = {"sid": sid, "guid": sid.split(":")[-1].strip(), "at": _now()}
    for k in ("cwd", "session_id", "transcript_path"):
        v = (meta or {}).get(k)
        if isinstance(v, str) and v:
            rec[k] = v
    if not force:
        if _seat_kind(root, rec.get("cwd")) == "branch":
            return False                              # 分公司 never holds the CEO's pane
        held = read_iterm_target(root)
        if held and held.get("guid") != rec["guid"]:
            same = held.get("session_id") and held.get("session_id") == rec.get("session_id")
            # A record with no session_id is a legacy capture (or one written before this
            # rule existed): it cannot prove whose seat it is, so it does not get to hold
            # one. Without this a long-lived bystander pinned by the old last-writer-wins
            # rule would keep the seat forever and they could only escape via the picker.
            known = held.get("pinned") or held.get("session_id")
            if not same and known and (held.get("pinned") or _target_alive(held)):
                return False                          # incumbent still live — do not steal
    try:
        d = runtime_dir(root)
        tmp = os.path.join(d, "iterm-target.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rec, f)
        os.replace(tmp, os.path.join(d, "iterm-target"))
        return True
    except Exception:
        return False


def _target_alive(rec):
    """True when the recorded pane still exists AND still has a foreground claude. The
    only thing that lets a new session take a seat that is already claimed."""
    if _iterm_disabled():
        return False
    out = _osa(ITERM_PROBE_APPLESCRIPT, (rec or {}).get("guid") or "", timeout=6)
    tty = (out or "").split("\n")[0].strip()
    return bool(tty) and tty in _claude_ttys()


def pin_iterm_target(root, guid):
    """Their explicit choice of seat, from the board's pane picker. Pinned beats every
    automatic claim — they are the only one who actually knows which session is the CEO."""
    guid = (guid or "").strip()
    if not guid:
        return None
    pane = next((p for p in iterm_panes(root) if p["guid"] == guid), None)
    if not pane:
        return None
    capture_iterm_target(root, guid, {"cwd": pane.get("cwd") or ""}, force=True)
    rec = read_iterm_target(root) or {}
    rec["pinned"] = True
    try:
        d = runtime_dir(root)
        tmp = os.path.join(d, "iterm-target.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rec, f)
        os.replace(tmp, os.path.join(d, "iterm-target"))
    except Exception:
        return None
    return iterm_target_info(root)


SOUND_DIR = os.path.expanduser("~/.claude/clock-in-sounds")


def sound_for(kind):
    """The Boss's own ringtone for an arrival, if they have put one there. `needs.*` for a decision,
    `info.*` for an update — any extension afplay can open. Falls back to the system sound
    when the file is absent, so a fresh install still rings."""
    for ext in ("m4a", "mp3", "wav", "aiff", "caf"):
        f = os.path.join(SOUND_DIR, "%s.%s" % (kind, ext))
        if os.path.exists(f):
            return f
    return None


def play_sound(kind):
    """Played by the SERVER, so it rings whether or not the tab is open — and only once,
    which a page-side chime beside it could not promise."""
    f = sound_for(kind)
    if not f:
        return False
    try:
        subprocess.Popen(["/usr/bin/afplay", f],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


NOTIFIER = "/opt/homebrew/bin/terminal-notifier"
# terminal-notifier posts under its own bundle, which macOS never registers in Notification
# Centre — so every banner it sent was accepted (exit 0), and silently dropped. It has no
# entry in com.apple.ncprefs at all, which is why nothing appeared for hours while the code
# reported success. Sending AS an application the system already trusts fixes it; the
# `-appIcon` still overrides the icon, so the board keeps its own mark.
NOTIFY_SENDER = "com.apple.ScriptEditor2"
BOARD_ICON = os.path.expanduser("~/.claude/clock-in-board.png")
NCPREFS = os.path.expanduser("~/Library/Preferences/com.apple.ncprefs.plist")


def _default_browser():
    """The click on a spoofed-sender banner can do exactly ONE thing: activate the
    sender (the -open URL is discarded with -sender, and on this notifier generation
    the native path never gets to ask for permission — deprecated API, no prompt).
    Script Editor's activation is useless; the default browser is where the board tab
    already lives, so its activation is the closest to "open the board" the spoof can
    express. LSHandlers is the on-disk record of the default-browser choice."""
    try:
        import plistlib
        p = os.path.expanduser("~/Library/Preferences/com.apple.LaunchServices/"
                               "com.apple.launchservices.secure.plist")
        with open(p, "rb") as f:
            for h in plistlib.load(f).get("LSHandlers", []):
                if h.get("LSHandlerURLScheme") == "https" and h.get("LSHandlerRoleAll"):
                    return str(h["LSHandlerRoleAll"])
    except Exception:
        pass
    return NOTIFY_SENDER


def _notifier_registered():
    """True once terminal-notifier's OWN bundle has a Notification Centre entry — the
    user has been asked and macOS files banners posted under its own name. Until then a
    native post is accepted (exit 0) and silently dropped, which is the trap the sender
    spoof exists for. Read fresh each time: a banner is rare and the grant, when it
    comes, must take effect inside a long-lived daemon without a restart."""
    try:
        import plistlib
        with open(NCPREFS, "rb") as f:
            apps = plistlib.load(f).get("apps") or []
        return any("terminal-notifier" in str(a.get("bundle-id", "")) for a in apps)
    except Exception:
        return False


PASTE_DIR = os.path.join("docs", "board", "pastes")
PASTE_MAX = 12 * 1024 * 1024
PASTE_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
             "image/webp": ".webp"}


def write_paste(root, name, mime, raw):
    """Write one pasted image into the project and return its project-relative path.

    Only the four image types a clipboard actually produces, capped — this endpoint takes
    bytes from a page, so it stays a narrow door. The filename is generated, never taken
    from the client: a name is the one field that could escape the directory."""
    ext = PASTE_EXT.get(str(mime or "").split(";")[0].strip().lower())
    if not ext or not raw or len(raw) > PASTE_MAX:
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tag = re.sub(r"[^a-zA-Z0-9-]", "", str(name or "")[:24]) or "paste"
    rel = os.path.join(PASTE_DIR, "%s-%s%s" % (stamp, tag, ext))
    full = os.path.join(root, rel)
    try:
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(raw)
    except Exception:
        return None
    return rel


def notify_entry(root, e, port):
    """Bank a macOS banner for one new board entry.

    Sender-first, the way Messages and WeChat write one: the department is the title, the
    item's subject is the subtitle, and the detail is the body. The old shape spent the
    loudest line on "Boss Board · <project>", which the OS already prints above the banner.

    terminal-notifier rather than `osascript display notification`: only it can carry our
    own icon (bare osascript always wears Script Editor's and there is no flag for it),
    click through to the board, and group a banner under its entry id so a re-fired item
    replaces its own banner instead of stacking a second one."""
    if _iterm_disabled() or not os.path.exists(NOTIFIER):
        return False
    native = _notifier_registered()
    dept = str(e.get("dept") or "?")
    info = is_info(e)
    subject, detail = split_ask(e.get("text") or "")
    if not detail:
        subject, detail = "", subject
    kind = "info" if info else "needs"
    own = play_sound(kind)          # theirs, if they have one — and then no system sound
    args = [NOTIFIER,
            "-title", dept if info else "%s · Needs you" % dept,
            "-message", (detail or subject or "(no text)")[:220],
            "-group", "clockin-%s-%s" % (os.path.basename(os.path.abspath(root)), e.get("id")),
            "-open", "http://127.0.0.1:%s/" % port]
    # -sender and -open are mutually exclusive in practice: with -sender the click is
    # delivered to the spoofed app and the URL never opens. Native posting (which would
    # honour -open) needs the notifier's own bundle registered in Notification Centre,
    # and this notifier generation cannot get there on current macOS — so the working
    # best is spoofing the DEFAULT BROWSER: banners deliver under its grant, and the
    # click surfaces the window where the board tab already lives.
    if not native:
        args += ["-sender", _default_browser()]
    if not own:
        args += ["-sound", "Tink" if info else "Submarine"]
    if subject:
        args += ["-subtitle", subject[:90]]
    if os.path.exists(BOARD_ICON):
        args += ["-appIcon", BOARD_ICON]
    try:
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def split_ask(text):
    """(subject, detail) from a `title :: body` entry, else ('', text). The panel splits the
    same way for a bubble's bold first line, so a banner and the board agree on the subject."""
    t = (text or "").strip()
    if "::" in t:
        a, b = t.split("::", 1)
        return a.strip(), b.strip()
    return "", t


def session_file(root):
    return os.path.join(runtime_dir(root), "sessions.json")


SESSION_STALE_S = 3 * 24 * 3600
LABEL_MAX = 52


# User-role rows that are not their: hook injections, inter-session mail, teammate control
# frames, interrupt markers. A label reading "Local time: ..." identifies nothing.
_NOT_HER = re.compile(
    r"^(\{|\[Request interrupted|Another Claude session|This came from another|"
    r"Local time:|Caveat:|This session is being continued|<)", re.I)


def last_prompt(transcript_path):
    """The first line of the newest thing the Boss typed, which is how the Boss recognises a session:
    「can't you restart my board for…」 beats a pane title every time.

    Scans backwards in widening windows rather than a fixed tail: a working session's last
    megabyte can be nothing but tool_result rows, and a fixed 400KB tail found no prompt at
    all in the one transcript it was tested against."""
    for window in (256_000, 1_500_000, 6_000_000):
        try:
            size = os.path.getsize(transcript_path)
            with open(transcript_path, "rb") as f:
                f.seek(max(0, size - window))
                rows = f.read().decode("utf-8", "replace").splitlines()
        except Exception:
            return None
        for ln in reversed(rows):
            try:
                d = json.loads(ln)
            except Exception:
                continue
            if d.get("type") != "user" or d.get("isMeta") or d.get("isCompactSummary"):
                continue
            c = ((d.get("message") or {}).get("content"))
            if isinstance(c, list):
                c = " ".join(p.get("text", "") for p in c
                             if isinstance(p, dict) and p.get("type") == "text")
            if not isinstance(c, str):
                continue
            c = re.sub(r"(?s)<system-reminder>.*?</system-reminder>", " ", c)
            c = re.sub(r"(?s)<[a-z-]+>.*?</[a-z-]+>", " ", c)
            for raw in c.split("\n"):
                s = re.sub(r"\s+", " ", raw).strip()
                if not s or _NOT_HER.match(s):
                    continue
                return s[:LABEL_MAX] + "…" if len(s) > LABEL_MAX else s
        if size <= window:
            break                                   # whole file already scanned
    return None


def register_session(root, meta):
    """One record per SESSION — keyed by session_id, the way LLMPET does it — rather than
    one pinned pane for the whole project.

    A pane is not an identity: it outlives the session, it carries a title Claude Code
    rewrites per task, and it cannot say whether it belongs to the CEO, the Marketing 分公司
    or something they opened to read a file. The hook holds the join nobody else has —
    session_id + transcript_path + cwd + ITERM_SESSION_ID in one payload — so it is written
    here, and the board can then LIST their sessions in the Boss's own words instead of guessing
    which pane is the right one."""
    sid = str((meta or {}).get("session_id") or "").strip()
    if not sid:
        return None
    now = time.time()
    reg = read_sessions(root)
    prev = reg.get(sid) or {}
    rec = {
        "session_id": sid,
        "guid": (str(meta.get("iterm") or "").split(":")[-1].strip()) or prev.get("guid", ""),
        "cwd": meta.get("cwd") or prev.get("cwd", ""),
        "transcript": meta.get("transcript_path") or prev.get("transcript", ""),
        "agent": meta.get("agent") or prev.get("agent", ""),
        "seen": now,
    }
    rec["label"] = last_prompt(rec["transcript"]) or prev.get("label") or ""
    reg[sid] = rec
    for k, v in list(reg.items()):
        if now - (v.get("seen") or 0) > SESSION_STALE_S:
            del reg[k]
    try:
        d = runtime_dir(root)
        tmp = os.path.join(d, "sessions.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(reg, f, ensure_ascii=False)
        os.replace(tmp, session_file(root))
    except Exception:
        return None
    return rec


def read_sessions(root):
    try:
        d = json.load(open(session_file(root), encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def read_iterm_target(root):
    """The recorded target as a dict, or None. Accepts the legacy bare-GUID file so a board
    running against a pre-0.9.84 capture still delivers."""
    try:
        raw = open(iterm_target_file(root), encoding="utf-8").read().strip()
    except Exception:
        return None
    if not raw:
        return None
    try:
        rec = json.loads(raw)
        if isinstance(rec, dict) and rec.get("guid"):
            return rec
    except Exception:
        pass
    return {"guid": raw.split(":")[-1].strip(), "sid": raw}   # legacy: bare ITERM_SESSION_ID


# Delivery: on Send the composed one-line answer is typed into the Boss's PINNED iTerm2 pane
# and submitted for them. No focus steal, no Accessibility grant: `write text` addresses the
# pane by id, and `write text "" newline yes` puts a lone CR (0x0d — the exact byte the Enter
# key sends) on that pane's tty as its own write. The old comment here claimed macOS would
# not let a background process press Return and that only tmux could auto-submit; a raw-mode
# byte probe on 2026-08-03 disproved both (`write text "AB" newline yes` -> 41 42 0d).
#
# Auto-submit only earns its keep behind an interlock, because the failure it buys is a
# sentence executed in the wrong pane. Send therefore proves the target FOUR times before it
# presses anything: the pane still exists; its tty has a foreground `claude`; the pane's own
# screen changed after we typed; and the change is our text (or an input-box paste marker).
# Any check that fails stops at "typed" and leaves the Enter to them.
ITERM_LOOKUP_APPLESCRIPT = (
    "on run argv\n"
    "  set theId to item 1 of argv\n"
    "  tell application \"iTerm2\"\n"
    "    repeat with w in windows\n"
    "      repeat with t in tabs of w\n"
    "        repeat with s in sessions of t\n"
    "          if (id of s) is theId then\n"
    "            return (tty of s) & linefeed & (name of s) & linefeed & ((contents of s) as text)\n"
    "          end if\n"
    "        end repeat\n"
    "      end repeat\n"
    "    end repeat\n"
    "  end tell\n"
    "  return \"\"\n"
    "end run\n")
# Probe, type and read back in ONE round trip. Three separate osascript calls cost ~0.9s
# each, so a send took three seconds and looked hung.
ITERM_TYPE_APPLESCRIPT = (
    "on run argv\n"
    "  set theId to item 1 of argv\n"
    "  set theMsg to item 2 of argv\n"
    "  tell application \"iTerm2\"\n"
    "    repeat with w in windows\n"
    "      repeat with t in tabs of w\n"
    "        repeat with s in sessions of t\n"
    "          if (id of s) is theId then\n"
    "            set b to ((contents of s) as text)\n"
    "            tell s to write text theMsg newline no\n"
    "            delay 0.22\n"
    "            return (tty of s) & linefeed & (name of s) & linefeed & b"
    " & (ASCII character 30) & ((contents of s) as text)\n"
    "          end if\n"
    "        end repeat\n"
    "      end repeat\n"
    "    end repeat\n"
    "  end tell\n"
    "  return \"\"\n"
    "end run\n")
# Write ONLY — no `contents of s`. That read is the expensive half (measured hanging past
# 30s on a live pane while a tty+name probe took 2.9s), and the combined script put the
# `write text` BEHIND it: an 8s timeout then killed osascript with the text already in their
# box, and the caller reported "iTerm could not be reached". That is the worst answer
# available — it is neither true nor safe to retry. Writing alone is fast and its result
# is unambiguous, so "did the text land" is never again inferred from a screen read.
ITERM_WRITE_APPLESCRIPT = (
    "on run argv\n"
    "  set theId to item 1 of argv\n"
    "  set theMsg to item 2 of argv\n"
    "  tell application \"iTerm2\"\n"
    "    repeat with w in windows\n"
    "      repeat with t in tabs of w\n"
    "        repeat with s in sessions of t\n"
    "          if (id of s) is theId then\n"
    "            tell s to write text theMsg newline no\n"
    "            return \"ok\"\n"
    "          end if\n"
    "        end repeat\n"
    "      end repeat\n"
    "    end repeat\n"
    "  end tell\n"
    "  return \"\"\n"
    "end run\n")
ITERM_PROBE_APPLESCRIPT = (
    "on run argv\n"
    "  set theId to item 1 of argv\n"
    "  tell application \"iTerm2\"\n"
    "    repeat with w in windows\n"
    "      repeat with t in tabs of w\n"
    "        repeat with s in sessions of t\n"
    "          if (id of s) is theId then return (tty of s) & linefeed & (name of s)\n"
    "        end repeat\n"
    "      end repeat\n"
    "    end repeat\n"
    "  end tell\n"
    "  return \"\"\n"
    "end run\n")
# Every pane, not just the pinned one — one id/tty/name triple per line. The Boss picks the
# CEO seat from this list when the auto-capture guessed wrong.
ITERM_ROSTER_APPLESCRIPT = (
    "set out to \"\"\n"
    # `tab` is an iTerm2 CLASS inside the tell block, so `& tab &` concatenated the word
    # "tab" into every line instead of a separator. Bind the character outside it.
    "set sep to (ASCII character 9)\n"
    "tell application \"iTerm2\"\n"
    "  repeat with w in windows\n"
    "    repeat with t in tabs of w\n"
    "      repeat with s in sessions of t\n"
    "        set out to out & (id of s) & sep & (tty of s) & sep & (name of s) & linefeed\n"
    "      end repeat\n"
    "    end repeat\n"
    "  end repeat\n"
    "end tell\n"
    "return out\n")
ITERM_READ_APPLESCRIPT = (
    "on run argv\n"
    "  set theId to item 1 of argv\n"
    "  tell application \"iTerm2\"\n"
    "    repeat with w in windows\n"
    "      repeat with t in tabs of w\n"
    "        repeat with s in sessions of t\n"
    "          if (id of s) is theId then return ((contents of s) as text)\n"
    "        end repeat\n"
    "      end repeat\n"
    "    end repeat\n"
    "  end tell\n"
    "  return \"\"\n"
    "end run\n")
ITERM_ENTER_APPLESCRIPT = (
    "on run argv\n"
    "  set theId to item 1 of argv\n"
    "  tell application \"iTerm2\"\n"
    "    repeat with w in windows\n"
    "      repeat with t in tabs of w\n"
    "        repeat with s in sessions of t\n"
    "          if (id of s) is theId then\n"
    "            tell s to write text \"\" newline yes\n"
    "            return \"ok\"\n"
    "          end if\n"
    "        end repeat\n"
    "      end repeat\n"
    "    end repeat\n"
    "  end tell\n"
    "  return \"\"\n"
    "end run\n")


def _iterm_disabled():
    """The single kill switch for everything that can touch a real pane. Checked FIRST in
    every entry point, so a code path added later is inert under it by default rather than
    by remembering. The test suite sets BOARD_SKIP_ITERM for its whole run: on 2026-08-03 a
    unit test composed `QA-1 → use SQLite` and this module delivered it, submitted, into the
    Boss's live session — because board_add now stamps the CALLER's pane as the item's
    origin and the test process inherits ITERM_SESSION_ID like any other."""
    return bool(os.environ.get("BOARD_SKIP_ITERM"))


def _osa(script, *args, timeout=8):
    """Run `script` with argv `args`. Returns stdout, or None on any failure. argv-driven:
    the message never touches a shell or an AppleScript literal."""
    try:
        r = subprocess.run(["osascript", "-", *[str(a) for a in args]], input=script,
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def _tty_runs_claude(tty):
    """True when `tty` has a FOREGROUND claude process. This is the check that separates a
    pane that is still the Boss's session from a pane that merely kept its id after claude
    exited — typing a sentence into a bare zsh and pressing Return is the disaster the
    interlock exists to prevent, and the pane id alone cannot see it."""
    if not tty:
        return False
    try:
        r = subprocess.run(["ps", "-t", tty, "-o", "stat=,command="],
                           capture_output=True, text=True, timeout=4)
    except Exception:
        return False
    for ln in (r.stdout or "").splitlines():
        parts = ln.split(None, 1)
        if len(parts) != 2:
            continue
        stat, cmd = parts[0], parts[1].strip()
        if "+" not in stat:                       # background job — not what they are looking at
            continue
        if os.path.basename(cmd.split()[0]) == "claude" or "/claude " in cmd + " ":
            return True
    return False


def _squash(s):
    return re.sub(r"\s+", "", s or "")


def _claude_ttys():
    """{tty -> cwd} for every FOREGROUND claude process, in two subprocess calls rather
    than one per candidate pane. The cwd is what tells a CEO seat from the Marketing 分公司
    from a session that happens to be open in the same tree."""
    out = {}
    try:
        r = subprocess.run(["ps", "-eo", "pid=,tty=,stat=,command="],
                           capture_output=True, text=True, timeout=6)
    except Exception:
        return out
    pids = {}
    for ln in (r.stdout or "").splitlines():
        parts = ln.split(None, 3)
        if len(parts) < 4 or parts[1] in ("??", "?", "-"):
            continue
        pid, tty, stat, cmd = parts
        if "+" not in stat:
            continue
        if os.path.basename(cmd.split()[0]) != "claude":
            continue
        pids[pid] = "/dev/" + tty if not tty.startswith("/dev/") else tty
    if not pids:
        return out
    cwds = {}
    try:                                   # one lsof for every claude at once
        r = subprocess.run(["lsof", "-a", "-d", "cwd", "-c", "claude", "-Fpn"],
                           capture_output=True, text=True, timeout=8)
        cur = None
        for ln in (r.stdout or "").splitlines():
            if ln[:1] == "p":
                cur = ln[1:]
            elif ln[:1] == "n" and cur:
                cwds.setdefault(cur, ln[1:])
    except Exception:
        pass
    for pid, tty in pids.items():
        out[tty] = cwds.get(pid, "")
    return out


def _codex_ttys():
    """{tty -> cwd} for every FOREGROUND codex process — the contractor seats' panes.
    Same shape as _claude_ttys; the Boss Board's Send path needs both to know which
    contractor pane is alive."""
    out = {}
    try:
        r = subprocess.run(["ps", "-eo", "pid=,tty=,stat=,command="],
                           capture_output=True, text=True, timeout=6)
    except Exception:
        return out
    pids = {}
    for ln in (r.stdout or "").splitlines():
        parts = ln.split(None, 3)
        if len(parts) < 4 or parts[1] in ("??", "?", "-"):
            continue
        pid, tty, stat, cmd = parts
        if "+" not in stat:
            continue
        if os.path.basename(cmd.split()[0]) != "codex":
            continue
        pids[pid] = "/dev/" + tty if not tty.startswith("/dev/") else tty
    if not pids:
        return out
    cwds = {}
    try:
        r = subprocess.run(["lsof", "-a", "-d", "cwd", "-c", "codex", "-Fpn"],
                           capture_output=True, text=True, timeout=8)
        cur = None
        for ln in (r.stdout or "").splitlines():
            if ln[:1] == "p":
                cur = ln[1:]
            elif ln[:1] == "n" and cur:
                cwds.setdefault(cur, ln[1:])
    except Exception:
        pass
    for pid, tty in pids.items():
        out[tty] = cwds.get(pid, "")
    return out


def _roster(root):
    """Dept handles for this project, so a teammate's pane can be told from the CEO's. A
    teammate titles its pane with its own handle ("Registrar", "Frontend")."""
    try:
        cfg = json.load(open(os.path.join(main_checkout(root), ".claude", "orchestrate.json"),
                             encoding="utf-8"))
    except Exception:
        return []
    out = list(cfg.get("roster") or []) + list(cfg.get("onDemand") or [])
    # Plugin-scope seats carry fixed names and never appear in a project roster, but they
    # title their panes the same way a dept does.
    out += ["Registrar", "Auditor", "Inspector", "team-lead"]
    return [str(h) for h in out if h]


def _seat_kind(root, cwd, title="", roster=None):
    """'ceo' | 'dept' | 'branch' | 'other' for a pane sitting in `cwd`.

    A 分公司 runs its own top-level session out of `.claude/worktrees/<handle>`, so it
    carries none of the agentName/teamName stamps a teammate has — `is_lead` deliberately
    calls it a lead. That is exactly why the capture guard never excluded it, and why the
    Marketing branch could take the CEO's pane the moment it finished a turn.

    Teammates DO carry the stamp, so the hook-level guard already keeps them out of the
    capture; `dept` exists only to label them honestly in the picker, since by cwd alone a
    teammate pane in the main checkout looks exactly like the CEO's."""
    if not cwd:
        return "other"
    cwd = os.path.realpath(cwd)
    main = os.path.realpath(main_checkout(root) if root else "")
    if os.path.exists(os.path.join(cwd, ".claude", "office.json")) or \
       (os.sep + ".claude" + os.sep + "worktrees" + os.sep) in cwd + os.sep:
        return "branch"
    if main and (cwd == main or cwd.startswith(main + os.sep)):
        head = re.sub(r"^[^\w]+", "", str(title or "")).split(" (")[0].strip().lower()
        for h in (roster if roster is not None else _roster(root)):
            if head == h.lower():
                return "dept"
        return "ceo"
    return "other"


def iterm_panes(root):
    """Every live iTerm pane running claude, labelled by seat, so the Boss can PICK the CEO
    session instead of trusting whichever one last ended a turn."""
    if _iterm_disabled():
        return []
    out = _osa(ITERM_ROSTER_APPLESCRIPT, timeout=6)
    if out is None:
        return []
    live = _claude_ttys()
    cur = (read_iterm_target(root) or {}).get("guid")
    roster = _roster(root)
    byguid = {}
    for r in read_sessions(root).values():
        if r.get("guid"):
            byguid.setdefault(r["guid"], r)
            if r["seen"] > byguid[r["guid"]]["seen"]:
                byguid[r["guid"]] = r          # a pane reused by a newer session
    panes = []
    for ln in (out or "").splitlines():
        bits = ln.split("\t")
        if len(bits) < 3:
            continue
        guid, tty, name = bits[0].strip(), bits[1].strip(), pane_title(bits[2])
        if not guid or tty not in live:
            continue
        cwd = live[tty]
        reg = byguid.get(guid) or {}
        # The Boss's own words first (registry), the pane's task title second. A pane Claude Code
        # renamed mid-task is unrecognisable; the last thing the Boss typed into it is not.
        panes.append({"guid": guid, "tty": tty, "title": name, "cwd": cwd,
                      "agent": reg.get("agent") or "",
                      "label": reg.get("label") or "", "agent": reg.get("agent") or "",
                      "known": bool(reg),
                      "seat": _seat_kind(root, cwd, name, roster), "current": guid == cur})
    order = {"ceo": 0, "dept": 1, "branch": 2, "other": 3}
    panes.sort(key=lambda p: (order[p["seat"]], not p["known"], p["title"]))
    return panes


_SPINNER_RE = re.compile(r"^[⠀-⣿\s]+")


def pane_title(name):
    """A pane's iTerm session name with the spinner taken off the front.

    Claude Code puts its live status line in the session name, and while the session is
    working that line starts with an animating braille frame (`⠂ ⠐ ⠄ ⠆`). Anything that
    treats the name as an identity then churns several times a second for as long as the
    pane is busy: the destination label beside the composer redrew every poll, the seat
    list re-sorted under their hand, and the composer's own "has anything changed?" check
    said yes forever — which rebuilt the box they was typing into (2026-08-04). A name that
    is nothing but spinner keeps its original text; there is nothing better to call it."""
    s = (name or "").strip()
    return _SPINNER_RE.sub("", s).strip() or s


def iterm_target_info(root):
    """What Send would do right now, for the board to render BEFORE they click: which pane,
    what it is called, and whether it will submit. A Send button that cannot name its target
    is the whole complaint — 'it just seems to find the activated terminal'."""
    rec = read_iterm_target(root)
    if not rec:
        return {"ok": False, "why": "no session pinned yet"}
    if _iterm_disabled():
        return {"ok": False, "why": "delivery disabled"}
    out = _osa(ITERM_PROBE_APPLESCRIPT, rec["guid"], timeout=6)
    if out is None:
        return {"ok": False, "why": "iTerm2 not reachable", "cwd": rec.get("cwd")}
    head = (out or "").split("\n")
    tty = head[0].strip() if head else ""
    if not tty:
        return {"ok": False, "why": "pinned pane is gone", "cwd": rec.get("cwd")}
    name = pane_title(head[1]) if len(head) > 1 else ""
    live = _claude_ttys()
    if tty not in live:
        return {"ok": False, "why": "pane is no longer running claude",
                "tty": tty, "title": name, "cwd": rec.get("cwd")}
    seat = _seat_kind(root, live[tty], name)
    base = {"tty": tty, "title": name, "cwd": live[tty] or rec.get("cwd"), "seat": seat,
            "pinned": bool(rec.get("pinned")), "at": rec.get("at")}
    # An automatic claim that landed on anything other than the CEO's own seat does NOT
    # get to receive their answers. This is the case they reported: the Marketing 分公司 held
    # the main office's target, so Send typed decisions into the branch. Refusing here (rather
    # than only blocking future claims) means an already-poisoned record cannot deliver.
    if seat != "ceo" and not rec.get("pinned"):
        label = {"branch": "the %s 分公司" % os.path.basename(live[tty] or "branch"),
                 "dept": "a teammate pane (%s)" % name,
                 "other": "a session outside this project"}[seat]
        return dict(base, ok=False, why="auto-claimed by %s — pick your CEO session" % label)
    return dict(base, ok=True)


def dept_base(agent):
    """`Frontend-988` -> `Frontend`. A teammate's handle is its department plus the card it
    was dispatched for, so the department is everything before the trailing card number."""
    return re.sub(r"-\d+$", "", str(agent or "").strip())


def _pane_ttys():
    """{guid -> tty} for every iTerm pane, in ONE sweep. Probing seats one at a time cost
    an osascript launch each (~0.9s), so a department with three live seats spent three
    seconds deciding where to send — the whole sweep costs one."""
    out = _osa(ITERM_ROSTER_APPLESCRIPT, timeout=8) or ""
    m = {}
    for ln in out.splitlines():
        b = ln.split("\t")
        if len(b) >= 2 and b[0].strip():
            m[b[0].strip()] = b[1].strip()
    return m


def dept_guid(root, dept, task=None):
    """The seat that owns THIS card, resolved rather than guessed.

    A teammate is dispatched per card and named for it — `Frontend-988` holds `#988` — and
    the board entry already records its card in `task`. So the answer to `Frontend-38`
    (task 988) belongs to `Frontend-988`, exactly, whatever anyone touched most recently.

    Ranking activity was a guess dressed as a rule: two Frontend seats are routinely live
    at once, one waiting on the lead and one waiting on the Boss, and "whoever moved last"
    cannot tell them apart. So:

      1. the seat named for this card wins outright;
      2. failing that, a department with exactly ONE live seat is unambiguous;
      3. more than one and no card match → return None and let the caller say so.
         Guessing here delivers a decision to the wrong desk, which is worse than asking.

    Returns (guid, why) — `why` is '' on success and names the problem otherwise."""
    dept = (dept or "").strip()
    if not dept:
        return None, "no department"
    # The CEO's own session is not a dept seat and registers no agent name, so a roster
    # lookup for it finds nothing at all. The Boss's own seat is precisely what `default_guid`
    # resolves — without this, a message addressed to the CEO conversation reported
    # "CEO has no live seat" and went nowhere.
    if dept.lower() in ("ceo", "boss"):
        g = default_guid(root)
        return (g, "") if g else (None, "no CEO seat pinned")
    live, panes = _claude_ttys(), _pane_ttys()

    def alive(rec):
        g = rec.get("guid")
        return bool(g) and panes.get(g) in live

    seats = [r for r in read_sessions(root).values()
             if dept_base(r.get("agent")).lower() == dept.lower()]
    if task:
        want = ("%s-%s" % (dept, task)).lower()
        for r in seats:
            if str(r.get("agent") or "").lower() == want and alive(r):
                return r["guid"], ""
    up = [r for r in seats if alive(r)]
    if len(up) == 1:
        return up[0]["guid"], ""
    if len(up) > 1:
        names = ", ".join(sorted(str(r.get("agent")) for r in up))
        return None, "%s has %d live seats (%s) and this item names no card" % (
            dept, len(up), names)
    # External contractor seats (docs/board/seats/*.json): agent = 花名, bound to a
    # dept in the sidecar; their panes run `codex`, not `claude`, so liveness uses the
    # union of claude + codex foreground ttys.
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
        seat_dir = os.path.join(root, (cfg.get("board") or "docs/board"), "seats")
        ext = []
        for fn in sorted(os.listdir(seat_dir)):
            if not fn.endswith(".json"):
                continue
            try:
                s = json.load(open(os.path.join(seat_dir, fn), encoding="utf-8"))
            except Exception:
                continue
            if str(s.get("dept") or "").strip().lower() == dept.lower():
                ext.append(s)
    except Exception:
        ext = []
    if ext:
        codex_live = _codex_ttys()
        live_all = dict(live)
        live_all.update(codex_live)
        cands = []
        for s in ext:
            nm = str(s.get("name") or "").strip()
            if not nm:
                continue
            for r in read_sessions(root).values():
                if str(r.get("agent") or "").lower() == nm.lower():
                    g = r.get("guid")
                    if (g and panes.get(g) in live_all
                            and (not task or str(s.get("active_card")) == str(task))):
                        cands.append((nm, g))
        if len(cands) == 1:
            return cands[0][1], ""
        if len(cands) > 1:
            return None, "%s has %d live contractor seats (%s)" % (
                dept, len(cands), ", ".join(sorted(n for n, _ in cands)))
    return None, "%s has no live seat" % dept


def default_guid(root):
    """The pane to use for an item that never recorded where it came from.

    Order: the seat they pinned · the auto-claim when it really is their CEO seat · and if
    neither, the single live CEO-seat pane when there is exactly one. Refusing to deliver
    while the picker was displaying one row labelled CEO was pedantry, not safety."""
    rec = read_iterm_target(root) or {}
    if rec.get("pinned") and rec.get("guid"):
        return rec["guid"]
    info = iterm_target_info(root)
    if info.get("ok"):
        return rec.get("guid")
    ceos = [p for p in iterm_panes(root) if p["seat"] == "ceo"]
    return ceos[0]["guid"] if len(ceos) == 1 else None


def iterm_prime(root, line, guid=None):
    """Type the composed answer `line` into the Boss's PINNED iTerm2 pane and press Return
    for them, but only once the pane has proved it is still their session AND has echoed what
    we typed. Single-line by contract; any stray newline is folded so it stays one input
    line. Returns:

      ok        typed and submitted — nothing left for them to do
      typed     landed in the input box, NOT submitted (they press Enter); the honest
                answer whenever a check could not be passed after the text was already in
      notfound  the pinned pane no longer exists
      nosession the pane exists but has no foreground claude — refused before typing
      wrongseat the pane is a 分公司 / teammate / stranger they never picked — refused
      skip      no pane pinned, or delivery disabled
      err       iTerm2 unreachable

    Never raises; tests set BOARD_SKIP_ITERM."""
    if _iterm_disabled():
        return "skip"
    rec = read_iterm_target(root) or {}
    # An explicit guid is the item's OWN origin: the session that raised the question is
    # by definition the session that should get the answer, so it skips every seat check.
    homing = bool(guid)
    if not homing:
        guid = default_guid(root) or ""
    line = re.sub(r"[\r\n\t]+", " ", line or "").strip()
    if not guid or not line:
        return "skip"

    # The pane is checked BEFORE a character is typed — collapsing that into the typing
    # call would have made the wrong-pane guard useless, which is the whole reason the
    # interlock exists. What did collapse is the read-back: the typing call now returns the
    # screen from both sides of the write, so a send costs two round trips, not three. The
    # probe is the cheap one (tty and name only, no screen).
    probe = _osa(ITERM_PROBE_APPLESCRIPT, guid)
    if probe is None:
        return "err"
    tty = (probe or "").split("\n")[0].strip()
    if not tty:
        return "notfound"
    live = _claude_ttys()
    if tty not in live:
        return "nosession"
    # Only the Boss's own CEO seat receives answers automatically. A seat they pinned by hand is
    # theirs by definition and skips this; an automatic claim on a 分公司 or a teammate pane
    # is exactly the failure they reported, and it must not be reachable by Send.
    pname = (probe or "").split("\n")[1].strip() if "\n" in (probe or "") else ""
    if not homing and not rec.get("pinned") and \
       _seat_kind(root, live[tty], pname) != "ceo":
        return "wrongseat"
    # Read the screen BEFORE typing, then write on its own. Two calls instead of one,
    # deliberately: the read may be slow or may fail, and neither outcome may be allowed
    # to leave the write in an unknown state. A failed read costs us the echo check (we
    # stop at "typed" and they press Enter); a failed write is the only thing that means
    # nothing landed.
    before_body = _squash(_osa(ITERM_READ_APPLESCRIPT, guid) or "")
    if not _osa(ITERM_WRITE_APPLESCRIPT, guid, line):
        return "err"
    time.sleep(0.22)
    after = _osa(ITERM_READ_APPLESCRIPT, guid)
    after_body = _squash(after) if after is not None else ""

    # 4: the screen must carry what we typed. Compare the TAIL — a long line wraps, and the
    # tail is the part the input box keeps visible. Claude Code may fold a bulk write into
    # a "Pasted text #n" chip instead of echoing it; that chip is equally good evidence the
    # text is in the box, so accept a marker that was not there before.
    # Match ANY window of the message, not its tail. `contents of s` returns the VISIBLE
    # screen, so in a narrow pane — one sharing its width with a teammate panel — a long
    # message wraps and its end is simply not on screen. Checking the tail therefore failed
    # every time and the Return was never pressed, on a pane that had taken the text
    # perfectly. A sliding window survives wrapping, truncation and a lost prefix, and it
    # still cannot match a pane the text never reached.
    body = _squash(line)
    W = 18
    windows = [body[i:i + W] for i in range(0, max(1, len(body) - W + 1), 6)] or [body]

    def _seen(screen):
        if any(w and w in screen for w in windows):
            return True
        pasted = re.findall(r"Pastedtext#\d+", screen)
        return bool(pasted) and pasted != re.findall(r"Pastedtext#\d+", before_body)

    # WAIT for the echo rather than sleeping once and giving up. The typing script slept a
    # fixed 0.22s and read the screen exactly once; a long message full of CJK re-wraps the
    # input box, and a TUI that had not finished painting inside that window read as "not
    # echoed", so the text sat in their box unsent and they pressed Return themselves
    # (2026-08-05). Polling is also FASTER in the ordinary case: it returns the moment the
    # text appears instead of always paying the full delay.
    echoed = _seen(after_body)
    waited = 0.0
    while not echoed and waited < 1.6:
        time.sleep(0.2)
        waited += 0.2
        again = _osa(ITERM_READ_APPLESCRIPT, guid)
        if again is None:
            break
        echoed = _seen(_squash(again))
    if not echoed:
        # Whether the text is in the box or not, we will not press Return blind — and if
        # the screen changed into something that is not ours, something else is writing to
        # that pane, which is a reason to refuse rather than a reason to hurry.
        return "typed"

    # One retry on the Return itself: everything above proves the text is sitting in their
    # box, so a single failed keystroke is the one thing left between a delivered answer
    # and one they have to press Enter on themselves.
    return "ok" if (_osa(ITERM_ENTER_APPLESCRIPT, guid)
                    or _osa(ITERM_ENTER_APPLESCRIPT, guid)) else "typed"


def serve(root, port):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    store_path = os.path.join(root, STORE_REL)
    state = {"last_poll": time.time()}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.startswith("/state.json"):
                state["last_poll"] = time.time()
                payload = load_store(store_path)
                payload.pop("outbox", None)      # session-facing only — never rendered
                payload.pop("outbox_seq", None)
                payload["taskboard"] = load_taskboard(root)  # live iteration view
                payload["roster"] = load_roster(root)        # 花名册 · Departments view
                payload["finance"] = load_finance(root)      # Finance view (Obsidian Base), if configured
                payload.pop("direction", None)               # retired: the manual Direction band was noise
                payload["sot"] = load_sot(root)              # Dashboard compass = the maintained SoT `## Now`
                payload["decisions"] = load_decisions(root)  # Decisions/Canon view
                payload["mail"] = load_mail(root)            # Mail & Branches view
                payload["archive"] = load_archive(root)      # Archive view
                payload["version"] = BUILD                   # tab hot-reloads on change
                payload["project"] = os.path.basename(os.path.abspath(root))
                # Where Send would land, plus the seats they can move it to. Both are
                # refreshed by a background thread, NEVER on the request path: resolving
                # them costs an osascript over every iTerm window and put ~0.8s into a poll
                # that runs every few seconds.
                payload["send_target"] = state.get("target") or {"ok": False}
                payload["panes"] = state.get("panes") or []
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            elif self.path.startswith("/open"):
                from urllib.parse import urlparse, parse_qs
                # Side-effect endpoint (launches the default app), so it demands a
                # custom header: a cross-origin page can't send one without a CORS
                # preflight this server never grants — kills drive-by CSRF. Path
                # resolution shares every /file guard (realpath pin, worktrees,
                # bare-name search).
                if self.headers.get("X-Board") != "1":
                    self.send_response(403)
                    self.end_headers()
                    return
                p = parse_qs(urlparse(self.path).query).get("p", [""])[0]
                got = resolve_file(root, p)
                if got:
                    _launch_default(got[0])
                    self.send_response(204)
                else:
                    self.send_response(404)
                self.end_headers()
            elif self.path.startswith("/file"):
                from urllib.parse import urlparse, parse_qs
                p = parse_qs(urlparse(self.path).query).get("p", [""])[0]
                got = resolve_file(root, p)
                if got and got[1]:
                    full, ctype = got
                    body = open(full, "rb").read()
                else:
                    body, ctype = ("not found in this project or its worktrees: %s"
                                   % p).encode("utf-8"), None
                self.send_response(200 if got else 404)
                self.send_header("Content-Type", ctype or "text/plain; charset=utf-8")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            else:
                body = PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)

        def _json(self, code, obj):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            # The board's WRITE path (the reverse channel). Every write demands the
            # X-Board header — a cross-origin page can't send it without a preflight
            # this server never grants (the /open anti-CSRF contract); the socket is
            # 127.0.0.1-only, so only local origins reach here at all.
            from urllib.parse import urlparse, parse_qs
            if self.headers.get("X-Board") != "1":
                self.send_response(403); self.end_headers(); return
            u = urlparse(self.path)
            path = u.path
            n = int(self.headers.get("Content-Length") or 0)
            if path == "/paste":
                # Raw bytes, not base64 in JSON: the encoding grew a screenshot by a third
                # and then every byte of it was escaped, parsed and decoded again — four
                # passes over several megabytes before one of them reached disk.
                if n > PASTE_MAX:
                    self.send_response(413); self.end_headers(); return
                q = parse_qs(u.query)
                got = write_paste(root, q.get("name", [""])[0],
                                  self.headers.get("Content-Type", ""), self.rfile.read(n))
                if not got:
                    self.send_response(400); self.end_headers(); return
                self._json(200, {"path": got}); return
            try:
                body = json.loads(self.rfile.read(n)) if n else {}
            except Exception:
                body = None
            if not isinstance(body, dict):
                self.send_response(400); self.end_headers(); return
            if path == "/basket":
                eid, text = str(body.get("id") or ""), body.get("text")
                if not eid or not isinstance(text, str) or len(text) > 4000:
                    self.send_response(400); self.end_headers(); return
                _locked_mutate(root, lambda s: basket_set(s, eid, body.get("kind"), text, _now()))
                self._json(200, {"ok": True})
            elif path == "/read":
                eid = str(body.get("id") or "")
                if not eid:
                    self.send_response(400); self.end_headers(); return
                _locked_mutate(root, lambda s: set_read(s, eid, bool(body.get("read")), _now()))
                self._json(200, {"ok": True})
            elif path == "/send":
                self._json(200, board_send(root))
            elif path == "/paste":
                # A screenshot is how they explain half of what they mean, and the composer
                # could only take text — so an item needing one could not be answered from
                # the board at all. The bytes are written into the project and the message
                # carries the path, which is what a session can actually open.
                got = save_paste(root, body.get("name"), body.get("data"))
                if not got:
                    self.send_response(400); self.end_headers(); return
                self._json(200, {"path": got})
            elif path == "/ignore":
                # `read` only folds an INFORMATION row; a needs-you item carries no such
                # flag, so ticking it left the ask sitting on the desk. Ignoring resolves
                # it — off the desk, into History — and sends nothing to anyone.
                eid = str(body.get("id") or "")
                if not eid:
                    self.send_response(400); self.end_headers(); return
                _locked_mutate(root, lambda st: set_status(st, eid, "resolved", _now(),
                                                           sum="(ignored — no reply sent)"))
                self._json(200, {"ok": True})
            elif path == "/pin":
                # Their explicit pick of the CEO seat. Answers with the resolved target so
                # the tray relabels immediately rather than at the next probe tick.
                got = pin_iterm_target(root, str(body.get("guid") or ""))
                if not got:
                    self.send_response(400); self.end_headers(); return
                state["target"] = got
                self._json(200, got)
            else:
                self.send_response(404); self.end_headers()

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)

    def reaper():
        while True:
            time.sleep(30)
            if _superseded(root, port):   # record moved on — exit even while polled
                os._exit(0)
            idle = (time.time() - state["last_poll"]) > IDLE_REAP_SECONDS
            opens = any(e["status"] == "open" for e in load_store(store_path)["entries"])
            if idle and not opens:
                os._exit(0)

    def seatprobe():
        """Resolve the Send target and the pane roster off the request path. Two osascript
        sweeps over every iTerm window plus a ps and an lsof is ~0.8s; on the poll thread
        that landed in every board refresh."""
        while True:
            try:
                state["target"] = iterm_target_info(root)
                state["panes"] = iterm_panes(root)
            except Exception:
                pass
            time.sleep(15)

    def watcher():
        """Ring for entries that ARRIVE while the server is up. Seeded from the store on
        the first pass so a restart never re-announces the backlog — the point of a banner
        is that something just happened.

        `first` is cleared OUTSIDE the try: it used to sit inside it, so a single failure
        anywhere in the first pass left the watcher permanently seeding and it never
        announced anything again — silently, because the except swallowed the reason.
        Failures are written to the runtime log instead of vanishing."""
        seen, first = set(), True
        log = os.path.join(runtime_dir(root), "watcher.log")
        # `board_add` writes the entry and THEN calls ensure_server, which replaces a stale
        # daemon — so the very entry that triggered the replacement is already on disk when
        # the new watcher seeds, and was filed as "was already there". Every plugin update
        # therefore swallowed the next arrival, silently. An entry written within this
        # window of startup is treated as an arrival even on the seeding pass.
        born = datetime.now() - timedelta(seconds=30)
        fresh = born.strftime("%Y-%m-%dT%H:%M:%S")
        while True:
            try:
                store = load_store(store_path)
                for e in store.get("entries") or []:
                    eid = e.get("id")
                    if not eid or eid in seen:
                        continue
                    seen.add(eid)
                    arrived = (not first) or (e.get("created") or "") >= fresh
                    if arrived and e.get("status") == "open":
                        ok = notify_entry(root, e, port)
                        try:
                            with open(log, "a", encoding="utf-8") as f:
                                f.write("%s notify %s -> %s\n" % (_now(), eid, ok))
                        except Exception:
                            pass
            except Exception as exc:
                try:
                    with open(log, "a", encoding="utf-8") as f:
                        f.write("%s ERROR %r\n" % (_now(), exc))
                except Exception:
                    pass
            first = False
            time.sleep(4)

    threading.Thread(target=watcher, daemon=True).start()
    threading.Thread(target=reaper, daemon=True).start()
    threading.Thread(target=seatprobe, daemon=True).start()
    httpd.serve_forever()


# ---------------------------------------------------------------- command wrappers
def _now():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _store_path(root):
    return os.path.join(root, STORE_REL)


def _surface(root, force_open=False):
    """Ensure the panel server is up. Open the browser only when we just started it
    (an `add`), or when explicitly asked (`force_open`, e.g. bare /board) — never on
    every ask, which would spawn a duplicate window each time."""
    if _SKIP_SERVER:
        return 0
    port, started = ensure_server(root)
    if started or force_open:
        open_url(board_url(port))
    return port


def board_add(root, dept, kind, text, task=None, batch=None):
    e = _locked_mutate(root, lambda store: add_entry(store, dept, kind, text, _now(),
                                                     task, batch=batch)[0])
    _surface(root)
    return e


def board_notice(root, dept, text):
    e = _locked_mutate(root, lambda store: add_notice(store, dept, text, _now()))
    _surface(root)
    return e


def board_resolve_dept(root, dept, outcome=None):
    """`@BOSS-DONE[<dept>]` — same act as board_done, addressed by department."""
    return _locked_mutate(root,
                          lambda store: resolve_by_dept(store, dept, _now(), outcome))


def board_done(root, eid, outcome=None):
    """`@BOSS-DONE[<id>]` — the session that RAISED an ask withdrawing or closing it.
    Its note goes to `outcome`, never to `sum`: `sum` belongs to them reply.

    It is NOT refused on an item they have already answered. 0.9.122 made it so, on a
    misreading of what they reported — the duplication they was pointing at was prose in the
    pane, not this marker — and refusing a verb that several paths rely on to close their
    own asks risked breaking the register to fix something that was never broken here.
    The two fields already keep their words safe; that was the fix."""
    return _locked_mutate(root,
                          lambda store: set_status(store, eid, "resolved", _now(),
                                                   outcome=outcome))


def board_send(root):
    """Flush the Boss Board basket. Resolves replies on the board (source of truth), marks
    reads, leaves asks open, and types the composed one-line answer into the Boss's PINNED
    iTerm2 pane, submitting it for them once the pane has proved it is still their session. The
    pane id is captured at turn end (stop_iterm_capture) so it locks onto the CEO pane, never
    a teammate. The page falls back to the clipboard when typing can't land. Returns
    {'n','delivery','msg','target'}; delivery in ok|typed|notfound|nosession|skip|err|empty."""
    now = _now()
    rec = _locked_mutate(root, lambda store: board_send_mutate(store, now))
    if not rec:
        return {"n": 0, "delivery": "empty", "msg": ""}
    labels = {r.get("guid"): (r.get("label") or "") for r in read_sessions(root).values()}
    legs = []
    for g in rec["groups"]:
        key, why = g["src"] or "", ""
        dept = task = ""
        src = None if key.startswith("dept:") else (key or None)
        if key.startswith("dept:"):
            dept, _, task = key[5:].partition("#")
            src, why = dept_guid(root, dept, task)   # the seat that owns this card
        legs.append({"src": src or "", "n": len(g["items"]), "msg": g["msg"],
                     "to": labels.get(src) or dept or "", "why": why,
                     "delivery": "ambiguous" if (why and not src) else
                                 iterm_prime(root, g["msg"], src)})
    ok = [l for l in legs if l["delivery"] == "ok"]
    # The whole flush is only "ok" when every leg landed; anything else keeps the honest
    # per-leg detail so the page can copy exactly the ones that did not.
    return {"n": len(rec["items"]), "msg": rec["msg"], "legs": legs,
            "delivery": "ok" if len(ok) == len(legs) else
                        (legs[0]["delivery"] if len(legs) == 1 else "partial")}


def board_direction(root, text):
    d = _locked_mutate(root, lambda store: set_direction(store, text, _now()))
    _surface(root)
    return d


def board_park(root, eid):
    return _locked_mutate(root, lambda store: set_status(store, eid, "parked", _now()))


def board_reopen(root, eid):
    return _locked_mutate(root, lambda store: set_status(store, eid, "open", _now()))


def board_get(root, eid):
    return get_entry(load_store(_store_path(root)), eid)


def board_list(root, dept=None):
    return list_entries(load_store(_store_path(root)), dept)


def board_open(root):
    return _surface(root, force_open=True)


# ---------------------------------------------------------------- CLI
def _opt(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "serve":
        serve(_opt(argv, "--root", "."), int(_opt(argv, "--port", "0")))
        return
    cmd = argv[0] if argv else "open"
    root = project_root()
    if cmd == "add":
        text = _opt(argv, "--text", "")
        if not text.strip():
            # Positional args match no flag → an empty card would post (same
            # flags-only foot-gun as canon.py `set`). Refuse loudly instead.
            sys.stderr.write("add is flags-only — need --text:\n"
                             "  orchestrate-board add --dept <handle> --kind <needs|discuss|info>"
                             " --text \"...\" [--task <id>]\n")
            sys.exit(2)
        # dept = the RAISER's handle. The Boss is the audience, never a dept — the
        # old "Boss" default put their name in every CLI-raised ask's dept column
        # (field report); explicit Boss normalises too.
        dept = _opt(argv, "--dept", "CEO")
        if dept.strip().lower() in ("boss", "老板"):
            dept = "CEO"
        e = board_add(root, dept,
                      _opt(argv, "--kind", "needs"), text,
                      _opt(argv, "--task"))
        print(e["id"])
        # Surface a collision right at the add — the raiser is mid-turn and can
        # close the old ask with its real outcome (the Stop-hook nudge is the net
        # for whoever misses this line). CLI adds carry no batch, so the flag is
        # the only same-turn signal they get.
        live = [o for o in e.get("collides") or []
                if (board_get(root, o) or {}).get("status") == "open"]
        if live:
            print("COLLIDES: %s still open on the same task — if "
                  "this ask replaces it: orchestrate-board done %s --sum \"<outcome>\"; "
                  "if genuinely separate, leave both." % (", ".join(live), live[0]))
    elif cmd == "done":
        e = board_done(root, argv[1], _opt(argv, "--sum")); print(e["id"] if e else "not found")
    elif cmd == "direction":
        if "--clear" in argv:
            board_direction(root, "")
            print("cleared")
        elif _opt(argv, "--text", "").strip():
            board_direction(root, _opt(argv, "--text"))
            print("set")
        elif len(argv) > 1:
            # Positional text matches no flag — same flags-only foot-gun as `add`:
            # silently printing the current banner would read as "it worked".
            sys.stderr.write("direction is flags-only:\n"
                             "  orchestrate-board direction --text \"...\" | --clear\n")
            sys.exit(2)
        else:
            d = load_store(_store_path(root)).get("direction")
            print(d["text"] if d else "(none)")
    elif cmd == "resolve":
        e, opens = board_resolve_dept(root, _opt(argv, "--dept", ""))
        if e:
            print(e["id"])
        else:
            print("ambiguous — %d open for that dept: %s" %
                  (len(opens), ", ".join(o["id"] for o in opens)))
    elif cmd == "park":
        e = board_park(root, argv[1]); print(e["id"] if e else "not found")
    elif cmd == "reopen":
        e = board_reopen(root, argv[1]); print(e["id"] if e else "not found")
    elif cmd == "get":
        e = board_get(root, argv[1]); print(json.dumps(e, ensure_ascii=False) if e else "not found")
    elif cmd == "list":
        for e in board_list(root, _opt(argv, "--dept")):
            print("%s [%s] %s — %s" % (e["id"], e["status"], e["dept"], e["text"]))
    elif cmd in ("open", "stop"):
        if cmd == "stop":
            try:
                os.kill(int(open(pidfile(root)).read().strip()), 15)
            except Exception:
                pass
        else:
            port = board_open(root)
            print(board_url(port) if port else "(server skipped)")
    else:
        sys.stderr.write("usage: orchestrate-board add|done|resolve|park|reopen|get|list|direction|open|stop\n")


if __name__ == "__main__":
    main()
