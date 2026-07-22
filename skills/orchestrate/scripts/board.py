#!/usr/bin/env python3
"""Boss Board — a live "Needs-You" panel aggregating every pending ask for the
Boss across panes. Panes raise `@BOSS[<dept>]: <ask>` (a Stop hook captures it)
and resolve with `@BOSS-DONE[<dept>]`; the Boss raises via the `/board` command.
A singleton localhost server serves a self-polling page that always shows the
current open asks. Stdlib only; degrades, never hard-fails. See
docs/design/specs/2026-06-30-boss-board-design.md."""
import sys, os, re, json, time, html, hashlib, socket, tempfile, subprocess
from datetime import datetime

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
    card number (refcheck CEO-143/144). No key → never auto-superseded."""
    if task:
        return str(task)
    m = ASK_TASK_RE.search((text or "").split("::", 1)[0])
    return m.group(1) if m else None


def add_entry(store, dept, kind, text, now, task=None, batch=None, supersede=True):
    dup = find_open_dup(store, dept, text)
    if dup:
        return dup, False
    e = {"id": next_id(store, dept), "dept": dept, "text": (text or "").strip(),
         "kind": kind, "status": "open", "created": now, "updated": now}
    if task:
        e["task"] = str(task)  # platform task_id — lets the panel show the ask's task card
    if batch:
        e["batch"] = batch  # same-turn marker batch — batch-mates never supersede each other
    # Supersede COLLISION detection: a NEW decision ask about the same task as an
    # older open one flags the new entry — the Stop hook turns the flag into a
    # ONE-TIME nudge so the raiser closes the old ask WITH a real outcome, or
    # deliberately keeps both (field failures cured: CEO-27/28, CEO-143/144 — a
    # revised re-raise leaving both open). The Boss's call (0.9.21): CEO-in-the-loop
    # BEFORE any supersede — nothing here auto-resolves. 0.9.36 dropped the
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
    r"((?:[\w.\-一-鿿]+/)+[\w.\-一-鿿]+\.[A-Za-z0-9]{1,5}"
    r"|[\w一-鿿][\w.\-一-鿿]*\."
    r"(?:png|jpe?g|gif|webp|pdf|svg|md|txt|csv|json|log|html?|ya?ml|toml))\b")


def desk_files(text):
    out = []
    for m in DESK_FILE_RE.finditer(" " + (text or "")):
        p = m.group(2)
        if p not in out:
            out.append(p)
    return out


def _desk_section(e):
    """The desk section an entry files under (panel parity); None = not mirrored.
    Numbered prefixes make Bases' lexical group sort match the panel's order."""
    info = (e.get("kind") == "info" or e.get("notice")
            or (e.get("dept") or "").lower().startswith("inspector"))
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
    file paths in their own column (Boss's ask, 2026-07-21). GENERATED, machine-
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
        if e.get("status") == "resolved" and e.get("sum"):
            lines += ["**答复:** %s" % e["sum"], ""]
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


def set_status(store, eid, status, now, sum=None):
    e = get_entry(store, eid)
    if e:
        e["status"] = status
        e["updated"] = now
        if sum:
            e["sum"] = sum  # one-line outcome — the answered row's collapsed face
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
    question (item stays open). One staged answer per entry — a re-stage overwrites.
    Persisted in the store so a page reload restores the tray."""
    b = [x for x in store.get("basket", []) if x.get("id") != eid]
    if (text or "").strip():
        b.append({"id": eid, "kind": ("ask" if kind == "ask" else "reply"),
                  "text": text.strip(), "ts": now})
    store["basket"] = b
    return b


def compose_basket(basket):
    """One SINGLE-LINE message carrying every staged answer with its id. Single-line
    because iTerm2 `write text` submits at each newline — the whole basket must land
    as ONE prompt. Replies are flagged already-resolved (so the session never re-runs
    @BOSS-DONE); asks are flagged still-open."""
    reps = [x for x in basket if x.get("kind") != "ask"]
    asks = [x for x in basket if x.get("kind") == "ask"]

    def one(x):
        t = re.sub(r"\s+", " ", x.get("text", "")).strip()
        return "%s %s %s" % (x["id"], "asks:" if x.get("kind") == "ask" else "→", t)

    note = []
    if reps:
        note.append("%d repl%s ALREADY resolved on the board (do NOT re-run @BOSS-DONE — "
                    "just act on %s)" % (len(reps), "y" if len(reps) == 1 else "ies",
                                         "it" if len(reps) == 1 else "them"))
    if asks:
        note.append("%d question%s still open" % (len(asks), "" if len(asks) == 1 else "s"))
    return ("[Boss Board] The Boss answered on the panel — %s. %s"
            % ("; ".join(note), " · ".join(one(x) for x in basket)))


def board_send_mutate(store, now):
    """Flush the basket: resolve reply items (sum = the reply text), leave asks open,
    append the composed message to the outbox as a PENDING record, clear the basket.
    The inbox hook is the sole deliverer — it flips pending → delivered when it hands
    the message to the model. Returns the record, or None when the basket is empty."""
    basket = list(store.get("basket") or [])
    if not basket:
        return None
    for x in basket:
        if x.get("kind") != "ask":
            set_status(store, x["id"], "resolved", now, sum=x.get("text"))
    rec = {"msg": compose_basket(basket), "items": [x["id"] for x in basket],
           "ts": now, "delivered": False}
    store.setdefault("outbox", []).append(rec)
    store["basket"] = []
    return rec


def take_pending_outbox(store):
    """Undelivered outbox records, marked delivered in the SAME locked pass so each
    message injects exactly once. Keeps the outbox bounded (tail is just audit)."""
    pend = [r for r in store.get("outbox", []) if not r.get("delivered")]
    for r in pend:
        r["delivered"] = True
    ob = store.get("outbox", [])
    if len(ob) > 50:
        store["outbox"] = ob[-50:]
    return pend


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


def resolve_by_dept(store, dept, now, sum=None):
    # Ambiguity notices describe the queue — counting them as part of it made each
    # notice amplify the next ("2 asks open" begets "3 asks open" listing the first
    # notice) and left a dept-level DONE permanently ambiguous once one existed.
    opens = [e for e in open_for_dept(store, dept) if not e.get("notice")]
    if len(opens) == 1:
        set_status(store, opens[0]["id"], "resolved", now, sum)
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
RAISE_RE = re.compile(r"@BOSS\[([^\]\s#]+)(?:#([A-Za-z0-9_-]+))?\]:\s*(.+)")
# `@BOSS-DONE[<dept>|<id>]: <one-line outcome>` — the optional outcome becomes the
# answered row's collapsed line on the panel (an essay ask folds to its result).
DONE_RE = re.compile(r"@BOSS-DONE\[([^\]\s]+)\](?::\s*(.+))?")
# `@BOSS-INFO[<dept>#<task_id>]: <fact>` — information for the Boss that needs NO
# decision (verdicts, 复盘 outcomes, FYI status). Lands in the panel's Information
# column, never in Needs-you (Boss's call, 2026-07-18: verdicts were crowding the
# decision queue).
INFO_RE = re.compile(r"@BOSS-INFO\[([^\]\s#]+)(?:#([A-Za-z0-9_-]+))?\]:\s*(.+)")


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
    refcheck keeps *Recently shipped* ABOVE *Active* — so never split positionally."""
    m = re.search(r"(?m)^##\s+%s[^\n]*\n(.*?)(?=^##\s|\Z)" % re.escape(title), text, re.S | re.M)
    return m.group(1) if m else ""


STATUS_RE = re.compile(r"\b(todo|doing|review|blocked|done)\b", re.I)
# Hand-struck "tombstone" headings — a finished card closed by striking the heading
# instead of TaskUpdate→completed (field case: refcheck 07-14; such cards have no
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
                      "status": status, "priority": field("priority"),
                      "blocked_on": field("blocked_on"), "what": field("what"),
                      "done-when": field("done-when"), "artifacts": field("artifacts")})
    shipped = []
    m = re.search(r"<!-- SHIPPED:START -->(.*?)<!-- SHIPPED:END -->", text, re.S)
    seg = m.group(1) if m else _section(text, "Recently shipped")
    for line in seg.splitlines():
        if line.strip().startswith("- ") and not line.strip().startswith("- <"):
            shipped.append(line.strip()[2:])
    return {"tasks": tasks, "shipped": shipped}


def load_taskboard(root):
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
    return tb


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
        # Effective model = the CEO's in-session spawn override if any, else the
        # frontmatter default (which is NOT the truth once overridden — the Boss's call).
        out.append({"handle": handle, "model": live or default_model,
                    "default_model": default_model, "live": bool(live),
                    "role": fm.get("role") or fm.get("description") or "",
                    "external": handle.lower() in ext, "cards": len(cards),
                    "active": len([c for c in cards if c.get("status") in ("doing", "review", "blocked")]),
                    "statuses": [c.get("status") for c in cards]})
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
    """The Dashboard's compass — the SoT's `## Now` section (State · Blocked-on-her ·
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
    """The org's decision memory for the Decisions view: recent DECISIONS.md rulings
    (`## <date> · [key] <title>`, newest first — the file is prepend-ordered) and the
    CANON.md topic index (`` `topic` → <pointer> (updated <date>) ``, the settled answer
    for each question). Returns {decisions, canon} or None when neither exists."""
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
    except Exception:
        cfg = {}
    out = {"decisions": [], "canon": []}
    try:
        dec = open(os.path.join(root, cfg.get("decisions", "docs/DECISIONS.md")), encoding="utf-8").read()
        for m in re.finditer(r"(?m)^##\s+(\d{4}-\d{2}-\d{2})\b[ ·:\-]*(.+)$", dec):
            rest = m.group(2).strip()
            km = re.match(r"\[([^\]]+)\]\s*(.*)", rest)
            out["decisions"].append({"date": m.group(1), "key": km.group(1) if km else "",
                                     "title": (km.group(2).strip() if km else rest)})
            if len(out["decisions"]) >= limit:
                break
    except Exception:
        pass
    try:
        canon = open(os.path.join(root, cfg.get("canon", "docs/CANON.md")), encoding="utf-8").read()
        for m in re.finditer(r"(?m)^-\s+`([^`]+)`\s*(?:→|->)\s*(.+?)\s*(?:\(updated\s+([^)]+)\))?\s*$", canon):
            out["canon"].append({"topic": m.group(1), "ptr": m.group(2).strip(),
                                 "updated": (m.group(3) or "").strip()})
            if len(out["canon"]) >= 80:
                break
    except Exception:
        pass
    return out if (out["decisions"] or out["canon"]) else None


def load_mail(root, limit=30):
    """Mail & Branches view: the 分公司 mail lane (docs/board/mail/*.md frontmatter:
    time·from·to·re·status, newest first — filenames lead with the YYYYMMDD-HHMM stamp)
    plus the branch offices (orchestrate.json `external` depts, badged with their letter
    + unread counts). Returns {mail, branches} or None."""
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
    except Exception:
        cfg = {}
    mdir = os.path.join(root, cfg.get("board", "docs/board"), "mail")
    mail = []
    try:
        for f in sorted(os.listdir(mdir), reverse=True):
            if not f.endswith(".md"):
                continue
            try:
                fm = _agent_frontmatter(open(os.path.join(mdir, f), encoding="utf-8").read())
            except OSError:
                continue
            if not (fm.get("to") or fm.get("from")):
                continue  # dead letter (no headers) — the postmaster's problem, not a row
            mail.append({"file": f, "from": fm.get("from", ""), "to": fm.get("to", ""),
                         "re": fm.get("re", ""), "time": fm.get("time", ""),
                         "status": fm.get("status", "")})
            if len(mail) >= limit:
                break
    except OSError:
        pass
    branches = []
    for h in (cfg.get("external") or []):
        hl = str(h).lower()
        involved = [m for m in mail if m["from"].lower() == hl or m["to"].lower() == hl]
        branches.append({"handle": str(h), "letters": len(involved),
                         "unread": len([m for m in involved if (m["status"] or "").lower() == "unread"]),
                         "last": involved[0]["time"] if involved else ""})
    return {"mail": mail, "branches": branches} if (mail or branches) else None


def load_archive(root, limit=25):
    """Archive view: finished-work history — the taskboard's Recently-shipped tail plus
    the DONE entries in BACKLOG.md (`> **✅ DONE — <title>** (<dept, sha, …, date>) — …`,
    newest first). Returns {shipped, backlog} or None."""
    shipped = load_taskboard(root).get("shipped", [])
    backlog = []
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
        text = open(os.path.join(root, cfg.get("backlog", "docs/BACKLOG.md")), encoding="utf-8").read()
        for m in re.finditer(r"(?m)^>\s*\*\*✅\s*DONE\s*[—:-]\s*(.+?)\*\*\s*(?:\(([^)]*)\))?", text):
            meta = (m.group(2) or "").strip()
            dm = re.search(r"(\d{4}-\d{2}-\d{2})", meta)
            # the meta is `(<dept>, <sha>, …)` OR `(<topic-key>, <dept>, <sha>, …)` — the
            # dept is the first Capitalised token (Ops · Backend-IO); a lowercase-hyphen
            # topic-key or a hex sha never matches, so it is never mislabelled a dept.
            dept = next((p.strip() for p in meta.split(",")
                         if re.match(r"^[A-Z][A-Za-z][A-Za-z_-]*$", p.strip())), "")
            backlog.append({"title": m.group(1).strip(), "dept": dept,
                            "date": (dm.group(1) if dm else "")})
            if len(backlog) >= limit:
                break
    except Exception:
        pass
    return {"shipped": shipped, "backlog": backlog} if (shipped or backlog) else None


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


def _server_is_current(root):
    """True iff the recorded server was spawned from THIS build. A live daemon holds
    its page + logic in memory indefinitely, so after an update a stale server keeps
    serving the old panel while every hook politely reuses it — the 'board still looks
    old after an update' trap."""
    try:
        return open(versionfile(root), encoding="utf-8").read().strip() == BUILD
    except Exception:
        return False


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
    lost. Field case (refcheck 2026-07-17): a 0.9.6 zombie held the derived port
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
    """True iff the on-disk record (version stamp · port) no longer names this
    server. The idle reaper alone cannot retire a stale server: an open tab keeps
    polling it (immortal) while the freshly spawned current one, unpolled, reaps
    itself — the system converges on serving old code. Missing record → False
    (standalone `serve` runs have none)."""
    try:
        if open(versionfile(root), encoding="utf-8").read().strip() != BUILD:
            return True
        if int(open(portfile(root)).read().strip()) != port:
            return True
    except Exception:
        pass
    return False


def ensure_server(root):
    """Return (port, started) — `started` True only when THIS call spawned the server
    (so the caller can open the browser once, not on every ask). The check+spawn window
    runs under the store lock: two hooks reacting to the same Stop event could otherwise
    both see "no server" and spawn twice — the loser's pidfile then points at a dead
    process, which reads as "no server" and drifts the port on the next check."""
    with _StoreLock(root):
        port = server_info(root)
        if port and _server_is_current(root):
            return port, False
        if port:
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
            f.write(BUILD)
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
    return port, True


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
header { padding-bottom: 14px; border-bottom: 1px solid #dcd8cb; margin-bottom: 20px; }
.brand { font-size: .66rem; font-weight: 600; letter-spacing: .16em; text-transform: uppercase;
         color: #c15f3c; margin-bottom: 3px; }
h1 { font-family: "Tiempos Text", ui-serif, Georgia, "Songti SC", serif;
     font-size: 1.55rem; font-weight: 600; letter-spacing: 0; margin: 0 0 3px; }
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
.dot2 { width: 9px; height: 9px; border-radius: 50%%; margin-top: .45em; flex: none; }
.k-needs { background: #be4b32; }
.k-discuss { background: #6e8ca8; }
.k-info { background: #5b7fa6; }
.rc { flex: 1; min-width: 0; }
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
.parked .row { opacity: .6; }
.parked .dot2 { background: #cbc6b9; }
/* Information: fresh verdicts/FYIs stay visible (they're why the column exists);
   resolved history dims and folds behind the History sub-header — collapsed by
   default, fold class on the static h4 so it survives the per-poll re-render. */
.info #hist .row { opacity: .72; }
.info #hist .dot2 { background: #6b9e5f; }
.info h4.hist { font-size: .68rem; margin: .55em 0 .15em; display: flex; align-items: center;
                gap: 6px; color: #87867f; cursor: pointer; text-transform: uppercase;
                letter-spacing: .06em; }
.info h4.hist::after { content: '▸'; margin-left: auto; font-size: .82em; }
.info h4.hist.x::after { content: '▾'; }
.info h4.hist:not(.x) + div { display: none; }
/* Structured asks: the detail body lives in the expansion; extracted file paths
   get their own quiet row under a hairline so the Boss never hunts inside prose. */
.rx .files { margin-top: 6px; padding-top: 5px; border-top: 1px solid #e9e5d8; font-size: .74rem; }
/* SoT compass — the Dashboard's maintained "where we stand" band (SoT `## Now`),
   replacing the retired manual Direction band. Boxed as a quiet card: it reads as
   live status, not a masthead motto (which is exactly why the old banner went stale). */
.sotband { margin: 2px 0 6px; padding: 13px 15px; border: 1px solid #dfdacc; border-radius: 10px;
  background: #faf9f5; box-shadow: 0 1px 2px rgba(31,30,29,.05); }
.skick { display: flex; align-items: center; gap: 8px; font-size: .64rem; font-weight: 600;
  letter-spacing: .12em; text-transform: uppercase; color: #c15f3c; margin-bottom: 8px; }
.sage { margin-left: auto; letter-spacing: 0; text-transform: none; font-weight: 400; color: #a8a49a; }
.srow { font-size: .82rem; line-height: 1.5; margin: 3px 0; color: #4b4a45; }
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
.pill.pr-0 { background: #e8b4a0; color: #7c2d12; }  /* P0 — drop everything */
.pill.pr-1 { background: #f0ddb8; color: #7c5a12; }  /* P1 — next up */
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
.col { border: 1px solid #dfdacc; border-radius: 8px; padding: 9px 11px;
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
html.dark body { color: #eceae4; background: #262624; }
html.dark header { border-bottom-color: #3e3d3a; }
html.dark .brand { color: #d97757; }
html.dark .col, html.dark .t, html.dark .done-line { border-color: #3e3d3a; box-shadow: none; }
html.dark .done-line, html.dark .col { background: #30302e; }
html.dark .row { border-top-color: #3a3936; }
html.dark .row:hover { background: rgba(217,119,87,.07); }
html.dark .k-needs { background: #e08262; }
html.dark .k-discuss { background: #8fa9c4; }
html.dark .k-info { background: #7f9cc0; }
html.dark .parked .dot2 { background: #5c5b57; }
html.dark .info #hist .dot2 { background: #7fae72; }
html.dark .info h4.hist { color: #a3a199; }
html.dark .rx .files { border-top-color: #3a3936; }
html.dark .sotband { background: #30302e; border-color: #3e3d3a; box-shadow: none; }
html.dark .skick { color: #d97757; }
html.dark .srow { color: #d8d5cc; } html.dark .srow b { color: #eceae4; }
html.dark .rx .orig { border-left-color: #4a4945; color: #b8b5ac; }
html.dark .col.c-todo { background: #2c312a; }
html.dark .col.c-prog { background: #363023; }
html.dark .col.c-done { background: #322e37; }
html.dark .t { background: #383734; }
html.dark .t.s-blocked { background: #45302a; }
html.dark .t.s-review { background: #3b3444; }
html.dark .stamp, html.dark h2, html.dark .rm, html.dark .rage,
html.dark .t .sub, html.dark .done-line, html.dark .empty { color: #a3a199; }
html.dark .rm b, html.dark .t .tid { color: #c2c0b6; }
html.dark .count { background: #3e3d3a; color: #b8b5ac; }
html.dark .chip { border-color: #4a4945; color: #b8b5ac; }
html.dark .pill.pj { background: #453026; color: #e09b78; }
html.dark .pill.pt { background: #3a3935; color: #b8b5ac; }
html.dark .pill.px { background: #263c48; color: #86b6cf; }
html.dark .pill.pr-0 { background: #4a2318; color: #f0a284; }
html.dark .pill.pr-1 { background: #453a1c; color: #dcc27a; }
html.dark .fdot .fm { color: #e09b78; }
html.dark .dchip { background: hsl(var(--dh,40),20%%,27%%); color: hsl(var(--dh,40),35%%,76%%); }
html.dark .dchip.d0 { background: #3a3935; color: #8f8d85; }
html.dark .tl { color: #7f7d76; border-top-color: #3a3936; }
html.dark code { background: #3e3d3a; }
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
.rdchk { display: inline-flex; align-items: center; gap: 4px; font-size: .66rem; color: #87867f;
  cursor: pointer; user-select: none; }
.rdchk input { cursor: pointer; margin: 0; }
.row.rd { opacity: .5; }
.row.rd:hover { opacity: .85; }
body.haspanel { padding-bottom: 108px; }   /* clear the fixed bottom bar */
#tray { position: fixed; left: 0; right: 0; bottom: 0; z-index: 20; display: none;
        background: #faf9f5; border-top: 1px solid #dcd8cb; box-shadow: 0 -2px 12px rgba(31,30,29,.07);
        padding: 11px 24px 14px; }
#tray.on { display: block; }
.trayhd { display: flex; align-items: center; gap: 10px; max-width: 1060px; margin: 0 auto; }
#traycount { font-size: .74rem; color: #87867f; }
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
#compose { position: fixed; left: 0; right: 0; bottom: 0; z-index: 30; display: none;
           background: #fffefb; border-top: 2px solid #c15f3c; box-shadow: 0 -3px 16px rgba(31,30,29,.11);
           padding: 13px 24px 15px; }
#compose.on { display: block; }
.cwrap { max-width: 1060px; margin: 0 auto; }
.chd { font-size: .74rem; color: #87867f; margin-bottom: 6px; }
.chd b { color: #a2542f; font-family: ui-monospace, "SF Mono", Menlo, monospace; }
#ctext { width: 100%%; min-height: 64px; resize: vertical; font: inherit; color: inherit; padding: 9px 11px;
         border: 1px solid #d9d4c6; border-radius: 8px; background: #faf9f5; }
#ctext:focus { outline: 2px solid #c15f3c; outline-offset: 1px; border-color: #c15f3c; }
.cbtns { display: flex; gap: 8px; margin-top: 9px; }
.cbtns button { font: 600 .8rem -apple-system, sans-serif; border: 1px solid #d9d4c6; background: #faf9f5;
                color: #4b4a45; border-radius: 8px; padding: 6px 16px; cursor: pointer; }
.cbtns .primary { background: #c15f3c; color: #fff; border-color: #c15f3c; }
.cbtns .primary:hover { background: #a2542f; }
#toast { position: fixed; bottom: 122px; left: 50%%; transform: translateX(-50%%); z-index: 40;
         max-width: 82vw; text-align: center; background: #1f1e1d; color: #f0eee6; font-size: .78rem;
         padding: 9px 16px; border-radius: 9px; opacity: 0; transition: opacity .22s; pointer-events: none; }
#toast.on { opacity: .96; }
html.dark .bbtn { background: #30302e; border-color: #4a4945; color: #b8b5ac; }
html.dark .bbtn:hover { border-color: #d97757; color: #e09b78; }
html.dark .bbtn.staged { background: #453026; border-color: #d97757; color: #e09b78; }
html.dark #tray { background: #30302e; border-top-color: #3e3d3a; }
html.dark #traycount { color: #a3a199; }
html.dark .tchip { background: #383734; border-color: #4a4945; }
html.dark .tchip .tt { color: #d8d5cc; }
html.dark #compose { background: #262624; }
html.dark .chd { color: #a3a199; }
html.dark #ctext { background: #30302e; border-color: #4a4945; }
html.dark .cbtns button { background: #30302e; border-color: #4a4945; color: #d8d5cc; }
html.dark .cbtns .primary { background: #c15f3c; border-color: #c15f3c; color: #fff; }
html.dark #toast { background: #0d0d0c; color: #eceae4; }
/* ---- dashboard: tab bar + the monitor glance strip (edict's monitor, distilled) ---- */
nav.tabs { display: flex; gap: 2px; margin: 4px 0 20px; border-bottom: 1px solid #dcd8cb; }
nav.tabs button { font: 600 .82rem -apple-system, "SF Pro Text", Helvetica, sans-serif; background: none;
  border: none; cursor: pointer; padding: 8px 15px; color: #87867f; border-bottom: 2px solid transparent;
  margin-bottom: -1px; }
nav.tabs button:hover { color: #1f1e1d; }
nav.tabs button.on { color: #a2542f; border-bottom-color: #c15f3c; }
section.tabpane { display: none; }
section.tabpane.on { display: block; }
.monitor { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 2px 0 24px; }
@media (max-width: 620px) { .monitor { grid-template-columns: repeat(2, 1fr); } }
.tile { border: 1px solid #dfdacc; border-radius: 10px; padding: 13px 15px; background: #faf9f5;
  box-shadow: 0 1px 2px rgba(31,30,29,.05); }
.tile .tn { font: 700 1.95rem/1 "Tiempos Text", ui-serif, Georgia, "Songti SC", serif;
  font-variant-numeric: tabular-nums; color: #1f1e1d; display: flex; align-items: center; gap: 9px; }
.tile .th { width: 9px; height: 9px; border-radius: 50%%; flex: none; }
.tile .tlab { font-size: .67rem; text-transform: uppercase; letter-spacing: .09em; color: #87867f; margin-top: 7px; }
.th.calm { background: #9bb892; } .th.warn { background: #d9a441; } .th.attn { background: #c15f3c; }
html.dark nav.tabs { border-bottom-color: #3e3d3a; }
html.dark nav.tabs button { color: #a3a199; }
html.dark nav.tabs button:hover { color: #eceae4; }
html.dark nav.tabs button.on { color: #e09b78; border-bottom-color: #d97757; }
html.dark .tile { background: #30302e; border-color: #3e3d3a; box-shadow: none; }
html.dark .tile .tn { color: #eceae4; }
html.dark .tile .tlab { color: #a3a199; }
html.dark .th.calm { background: #7fae72; }
/* ---- Departments 花名册: one card per dept, showing the model it runs on ---- */
.depts { display: grid; grid-template-columns: repeat(auto-fill, minmax(238px, 1fr)); gap: 12px; }
.dept { border: 1px solid #dfdacc; border-radius: 10px; padding: 12px 14px; background: #faf9f5;
  box-shadow: 0 1px 2px rgba(31,30,29,.05); }
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
html.dark .dept { background: #30302e; border-color: #3e3d3a; box-shadow: none; }
html.dark .drole { color: #b8b5ac; } html.dark .dstats { color: #a3a199; }
html.dark .m-opus { background: #3a2c47; color: #c9a9e0; } html.dark .m-sonnet { background: #263c48; color: #86b6cf; }
html.dark .m-haiku { background: #2c3a26; color: #9cc78a; } html.dark .m-fable { background: #453a1c; color: #dcc27a; }
html.dark .m-other { background: #3a3935; color: #b8b5ac; } html.dark .m-none { background: #333230; color: #7f7d76; }
html.dark .stpill { background: #3a3935; color: #b8b5ac; }
html.dark .stpill.st-doing { background: #363023; color: #dcc27a; } html.dark .stpill.st-review { background: #322c40; color: #c4b3e8; }
html.dark .stpill.st-blocked { background: #45302a; color: #e08262; } html.dark .stpill.st-todo { background: #2c312a; color: #9cbf8a; }
.mlive { margin-left: 5px; font-size: .8em; font-weight: 700; opacity: .7; text-transform: uppercase; letter-spacing: .04em; }
.msrc { font-size: .64rem; color: #a8a49a; margin-top: 6px; font-family: ui-monospace, "SF Mono", Menlo, monospace; }
html.dark .msrc { color: #7f7d76; }
/* ---- Finance: the Obsidian-Base ledger rendered as a table ---- */
.fmeta { font-size: .72rem; color: #87867f; margin-bottom: 12px; }
.ftable { overflow-x: auto; border: 1px solid #dfdacc; border-radius: 10px; background: #faf9f5;
  box-shadow: 0 1px 2px rgba(31,30,29,.05); }
.ftable table { border-collapse: collapse; width: 100%%; font-size: .82rem; }
.ftable th { text-align: left; font-size: .63rem; text-transform: uppercase; letter-spacing: .07em;
  color: #87867f; font-weight: 600; padding: 10px 14px; border-bottom: 1px solid #e2ddd0; white-space: nowrap; }
.ftable td { padding: 9px 14px; border-bottom: 1px solid #edeae0; white-space: nowrap; }
.ftable tr:last-child td { border-bottom: none; }
.ftable td.num { text-align: right; font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-variant-numeric: tabular-nums; }
.ftable .e { color: #c7c3b6; }
html.dark .ftable { background: #30302e; border-color: #3e3d3a; box-shadow: none; }
html.dark .ftable th { color: #a3a199; border-bottom-color: #3e3d3a; }
html.dark .ftable td { border-bottom-color: #3a3936; }
html.dark .fmeta { color: #a3a199; }
/* ---- Decisions / Canon: recent rulings + the settled-answer index ---- */
/* minmax(0,1fr) not 1fr: a long unbroken topic-key gave the left column a huge
   min-content, squishing it to a sliver and char-wrapping the key (Boss 2026-07-22). */
.dcol2 { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 22px; align-items: start; }
@media (max-width: 720px) { .dcol2 { grid-template-columns: 1fr; } }
.dsub { font-size: .74rem; text-transform: uppercase; letter-spacing: .06em; color: #87867f;
  margin: 0 0 .7em; font-weight: 600; }
.dec { border-top: 1px solid #edeae0; padding: 9px 2px; }
.dec:first-of-type { border-top: none; }
.dech { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }
.decdate { font: 600 .68rem ui-monospace, "SF Mono", Menlo, monospace; color: #87867f; font-variant-numeric: tabular-nums; }
.deckey { font: 600 .63rem ui-monospace, "SF Mono", Menlo, monospace; background: #f0ddd2; color: #a2542f;
  border-radius: 7px; padding: 1px 7px; min-width: 0; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; max-width: 100%%; }
.dectitle { font-size: .8rem; line-height: 1.45; color: #4b4a45;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
.cx { display: flex; gap: 9px; align-items: baseline; padding: 5px 2px; border-top: 1px solid #edeae0; font-size: .75rem; }
.cx:first-of-type { border-top: none; }
.ctopic { font: 600 .72rem ui-monospace, "SF Mono", Menlo, monospace; color: #6b6a62; flex: 0 1 auto;
  min-width: 0; max-width: 46%%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cptr { color: #6b6a62; flex: 1 1 auto; min-width: 0; overflow-wrap: anywhere; }
.cupd { color: #a8a49a; flex: 0 0 auto; white-space: nowrap; font-variant-numeric: tabular-nums; }
html.dark .dsub { color: #a3a199; }
html.dark .dec { border-top-color: #3a3936; }
html.dark .decdate { color: #a3a199; }
html.dark .deckey { background: #453026; color: #e09b78; }
html.dark .dectitle { color: #d8d5cc; }
html.dark .ctable { background: #30302e; border-color: #3e3d3a; }
html.dark .ctable td { border-bottom-color: #3a3936; }
html.dark .ctopic, html.dark .cptr { color: #b8b5ac; }
html.dark .cupd { color: #7f7d76; }
/* ---- Mail & Branches · Archive ---- */
.brwrap { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 6px; }
.brn { display: inline-flex; align-items: center; gap: 6px; border: 1px solid #dfdacc; border-radius: 9px;
  padding: 5px 10px; background: #faf9f5; font-size: .74rem; }
.brmeta { color: #87867f; }
.mstat { color: #be4b32; text-align: center; width: 1.4em; }
.marrow { color: #a8a49a; text-align: center; }
.mfrom, .mto { font-weight: 600; white-space: nowrap; }
.mre { color: #6b6a62; }
.mtime { color: #a8a49a; white-space: nowrap; font-variant-numeric: tabular-nums; }
.ftable tr.unread td { background: rgba(190,75,50,.05); }
.shl { font-size: .8rem; padding: 6px 2px; border-top: 1px solid #edeae0; color: #4b4a45; }
.shl:first-child { border-top: none; }
.blg { border-top: 1px solid #edeae0; padding: 9px 2px; }
.blg:first-of-type { border-top: none; }
.blh { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }
html.dark .brn { background: #30302e; border-color: #3e3d3a; }
html.dark .brmeta, html.dark .mtime { color: #a3a199; }
html.dark .mre { color: #b8b5ac; }
html.dark .shl { border-top-color: #3a3936; color: #d8d5cc; }
html.dark .blg { border-top-color: #3a3936; }
html.dark .ftable tr.unread td { background: rgba(224,130,98,.08); }
/* ---- cohesion: a left side-rail + one main column, so the tabs read as one instrument ---- */
body { max-width: 1240px; }
.shell { display: flex; align-items: flex-start; gap: 34px; }
.rail { width: 186px; flex: none; position: sticky; top: 26px; }
.rail .brand { margin-bottom: 3px; }
.rail h1 { font-size: 1.32rem; line-height: 1.14; margin: 0 0 5px; }
.rail .stamp { font-size: .68rem; }
.main { flex: 1; min-width: 0; }
.main > section > h2:first-child { margin-top: .15em; }
nav.tabs { display: flex; flex-direction: column; gap: 1px; border-bottom: none; margin: 20px 0 0; }
nav.tabs button { text-align: left; padding: 7px 11px; margin: 0; border-bottom: none;
  border-left: 2px solid transparent; border-radius: 0 7px 7px 0; }
nav.tabs button:hover { background: rgba(193,95,60,.05); }
nav.tabs button.on { border-bottom-color: transparent; border-left-color: #c15f3c; background: rgba(193,95,60,.08); }
@media (max-width: 780px) {
  .shell { flex-direction: column; gap: 8px; }
  .rail { width: auto; position: static; border-bottom: 1px solid #dcd8cb; padding-bottom: 10px; }
  nav.tabs { flex-direction: row; flex-wrap: wrap; margin-top: 12px; gap: 2px; }
  nav.tabs button { border-left: none; border-radius: 6px; }
  nav.tabs button.on { border-left-color: transparent; }
}
html.dark .rail { border-bottom-color: #3e3d3a; }
html.dark nav.tabs button:hover { background: rgba(217,119,87,.06); }
html.dark nav.tabs button.on { border-left-color: #d97757; background: rgba(217,119,87,.09); }
/* collapsible rail: a ‹ handle in the rail hides it; a ☰ button brings it back */
#railtog { float: right; width: 24px; height: 24px; border: 1px solid #dcd8cb; background: #faf9f5;
  border-radius: 7px; cursor: pointer; color: #87867f; font-size: 15px; line-height: 22px; padding: 0; }
#railtog:hover { border-color: #c15f3c; color: #a2542f; }
#railopen { display: none; position: fixed; top: 18px; left: 16px; z-index: 30; width: 32px; height: 32px;
  border: 1px solid #dcd8cb; background: #faf9f5; border-radius: 8px; cursor: pointer; color: #6b6a62;
  font-size: 16px; line-height: 30px; box-shadow: 0 1px 3px rgba(31,30,29,.1); }
#railopen:hover { border-color: #c15f3c; color: #a2542f; }
body.railoff .rail { display: none; }
body.railoff #railopen { display: block; }
body.railoff .main { padding-left: 40px; }
html.dark #railtog, html.dark #railopen { background: #30302e; border-color: #4a4945; color: #a3a199; }
html.dark #railtog:hover, html.dark #railopen:hover { border-color: #d97757; color: #e09b78; }
</style>
<script>
(function(){
  const q = new URLSearchParams(location.search).get('theme');
  const mq = matchMedia('(prefers-color-scheme: dark)');
  const set = () => document.documentElement.classList.toggle('dark', q ? q === 'dark' : mq.matches);
  set(); mq.addEventListener('change', set);
})();
</script>
</head><body>
<button id='railopen' onclick='toggleRail()' title='Show sidebar' aria-label='Show sidebar'>☰</button>
<div class='shell'>
<aside class='rail'>
  <button id='railtog' onclick='toggleRail()' title='Hide sidebar' aria-label='Hide sidebar'>‹</button>
  <div class='brand'>Boss Board</div>
  <h1 id='proj'>—</h1>
  <div class='stamp' id='stamp'>—</div>
  <nav class='tabs'>
    <button data-tab='dash' class='on' onclick='showTab("dash")'>Dashboard</button>
    <button data-tab='tasks' onclick='showTab("tasks")'>Tasks</button>
    <button data-tab='depts' onclick='showTab("depts")'>Departments</button>
    <button data-tab='decisions' onclick='showTab("decisions")'>Decisions</button>
    <button data-tab='mail' onclick='showTab("mail")' style='display:none'>Mail &amp; Branches</button>
    <button data-tab='archive' onclick='showTab("archive")'>Archive</button>
    <button data-tab='finance' onclick='showTab("finance")' style='display:none'>Finance</button>
  </nav>
</aside>
<main class='main'>
<section class='tabpane on' id='tab-dash'>
  <div class='monitor' id='monitor'></div>
  <div id='sot'></div>
  <h2>On your desk</h2>
  <div class='board top'>
    <div class='col'><h3><span class='dot' style='border-color:#c15f3c'></span>Needs you
      <span class='count' id='askn'>0</span></h3><div id='asks'></div></div>
    <div class='col parked'><h3><span class='dot' style='border-color:#cbc6b9'></span>Parked
      <span class='count' id='parkn'>0</span></h3><div id='parked'></div></div>
    <div class='col info'><h3><span class='dot' style='border-color:#5b7fa6'></span>Information
      <span class='count' id='infon'>0</span></h3><div id='infos'></div>
      <h4 class='hist' data-k='histcol' tabindex='0' onclick='tog(this)'>History
      <span class='count' id='histn'>0</span></h4><div id='hist'></div></div>
  </div>
</section>
<section class='tabpane' id='tab-tasks'>
  <h2>Current iteration</h2>
  <div class='board' id='board'></div>
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
  <div class='trayhd'><span id='traycount'></span><button class='sendbtn' onclick='sendBasket()'>Send to session</button></div>
  <div class='traylist' id='traylist'></div>
</div>
<div id='compose'><div class='cwrap'>
  <div class='chd' id='chd'></div>
  <textarea id='ctext'></textarea>
  <div class='cbtns'><button class='primary' onclick='stageCompose()'>Stage</button><button onclick='closeCompose()'>Cancel</button></div>
</div></div>
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
const PATH_RE = /(^|[^\w.\-\/一-鿿])((?:[\w.\-一-鿿]+\/)+[\w.\-一-鿿]+\.[A-Za-z0-9]{1,5}|[\w一-鿿][\w.\-一-鿿]*\.(?:png|jpe?g|gif|webp|pdf|svg|md|txt|csv|json|log|html?|ya?ml|toml))\b/g;
// The path charset admits no HTML-escapable characters, so `p` is safe raw in
// href (encoded), label AND the inline onclick string.
// Two click behaviours (Boss's ask, 2026-07-18): types the browser renders
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
// fmt(): the essay formatter (Boss's ask 2026-07-21 — "organized, structured,
// ADHD-friendly"). CEO asks are single-line essays glued with · and sentence
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
  // The SoT `## Now` bullets (State · Blocked-on-her · Money) — each a maintained
  // status line; the leading "**Label:**" bolds via md(), circled digits break to rows.
  const rows = sot.now.split('\n').map(l=>l.replace(/^\s*[-*]\s*/,'').trim()).filter(Boolean);
  return `<div class='sotband'><div class='skick'>Source of truth${sot.as_of?`<span class='sage'>${esc(sot.as_of)}</span>`:''}</div>
    ${rows.map(l=>`<div class='srow'>${brk(l)}</div>`).join('')}</div>`;
}
// Information ≠ decisions: info-kind entries never sit in Needs-you — they get the
// third column, fresh ones visible, history folded. Legacy Inspector entries (posted
// as needs/discuss by pre-0.9.18 stores) route by DEPT so live boards migrate on
// render, no store surgery.
function isInfo(e){ return e.kind==='info' || /^inspector/i.test(e.dept||''); }
function chip(t){
  // Hook-born cards have label "#<id>" and ·-less headings parse label===name —
  // show each fact once (same guards as tCard).
  const id = t.task_id && t.label !== '#'+t.task_id ? ` · #`+esc(t.task_id) : '';
  const nm = t.name && t.name !== t.label ? ` · `+md(t.name) : '';
  return `<span class="chip"><b>${md(t.label)}${id}</b>${nm} · ${esc(t.status||'?')}</span>`;
}
function askRow(e, T, ts){
  // Context for the decision: the explicitly linked task first; else the dept's
  // in-flight cards (its ask is almost always about one of them).
  let linked = (e.task && T.byId[e.task]) ? [T.byId[e.task]]
    : T.list.filter(t=>t.dept===e.dept && ['doing','review','blocked'].includes(t.status)).slice(0,2);
  const a = age(ts || e.created);
  // A resolved ask with a recorded outcome wears the outcome as its face; the ask
  // it answered is quoted behind the click. Reopening shows the full ask again.
  // A structured ask (`title :: body`) wears the title; the body waits in the
  // expansion, above the task chips, with its file paths extracted to a files row.
  const sum = e.status==='resolved' && e.sum;
  const [title, body] = splitAsk(e.text);
  const rt = brk(sum ? e.sum : (title || e.text));
  const files = filesOf(e.text);
  // The id·dept·kind meta line is a quiet FOOTER in both states: collapsed it sits
  // under the clamped title; expanded it must not wedge between title and body
  // (Boss's 2026-07-21 report — mid-card it read as a divider), so .rx comes first.
  return `<div class="row${xc(e.id)}${e.read?' rd':''}" data-k="${esc(e.id)}" tabindex="0" onclick="tog(this)">
    <span class="dot2 k-${esc(e.kind)}"></span>
    <div class="rc">
      <div class="rt">${rt}</div>
      <div class="rx">${!sum && body?`<div class='body'>${fmt(body)}</div>`:''}${sum?`<div class='orig'>${fmt(e.text)}</div>`:''}${linked.map(chip).join('')}${files.length?`<div class='files'>${files.map(flink).join(' · ')}</div>`:''}</div>
      <div class="rm"><b>${esc(e.id)}</b> · ${esc(e.dept)} · ${esc(e.kind)}${e.task?` · task #${esc(e.task)}`:''}</div>
      ${rowCtl(e)}
    </div>
    <span class="rage">${a}</span></div>`;
}
// Deterministic per-dept hue (edict's per-ministry colour coding, Anthropic-muted):
// the handle hashes to a hue, CSS derives the pastel pair per theme from --dh.
function hue(s){ let h = 0; for (const c of s) h = (h*31 + c.codePointAt(0)) %% 360; return h; }
function dchip(t){
  const d = (t.dept||'').trim();
  if(!d) return `<span class="dchip d0">未派</span>`;
  return `<span class="dchip" style="--dh:${hue(d)}">${esc(d)}</span>${t.external?` <span class='pill px'>分</span>`:''}`;
}
// A labelled compartment (fielded card, the edict lesson): tiny uppercase label
// over the formatted content; absent fields render nothing at all.
function sect(label, v){ return v ? `<div class="tl">${label}</div>${fmt(v)}` : ''; }
function tCard(t){
  const badge = t.status==='blocked'
      ? `<span class="badge blocked">blocked${t.blocked_on?': '+esc(t.blocked_on):''}</span>`
      : t.status==='review' ? `<span class="badge review">review</span>` : '';
  // Collapsed: compact clamp (dept chip + what flow). Expanded: the fielded card —
  // dept chip row, then labelled compartments What / Done when / Blocked on /
  // Artifacts, each through fmt(). The s-<status> class keeps the undershade;
  // hook-born "#<id>" labels and ·-less headings show each fact once, as before.
  const k = 't:' + t.label + '#' + (t.task_id||'');
  const lab = /^#\d+$/.test(t.label) ? `<span class='pill pj'>${esc(t.label)}</span>` : md(t.label);
  const id = t.task_id && t.label !== '#'+t.task_id ? `<span class='pill pt'>#${esc(t.task_id)}</span>` : '';
  const pp = /^P[01]$/.test(t.priority||'') ? `<span class='pill pr-${t.priority==='P0'?'0':'1'}'>${t.priority}</span>` : '';
  // Collapsed = title-only (Boss's call 2026-07-21): pills + name + dept chip, no
  // prose — the board scans as a list of titles; the fielded card waits behind the
  // click (or #x). The name's own "SLUG — description" carries the gist.
  return `<div class="t s-${esc(t.status||'none')}${xc(k)}" data-k="${esc(k)}" tabindex="0" onclick="tog(this)"><span class="tid">${pp}${lab}${id}</span>${badge}
    ${t.name && t.name !== t.label ? `<div class="nm">${md(t.name)}</div>` : ''}
    <div class="sub">${dchip(t)}</div>
    <div class="tx"><div class="dr">${dchip(t)}</div>${sect('What', t.what)}${sect('Done when', t['done-when'])}${sect('Blocked on', t.blocked_on)}${sect('Artifacts', t.artifacts)}</div></div>`;
}
function col(title, color, cls, inner, n){
  return `<div class="col ${cls}"><h3><span class="dot" style="border-color:${color}"></span>${title}
    <span class="count">${n}</span></h3>${inner||"<p class='empty'>—</p>"}</div>`;
}
let fails = 0, lastRaw = '';
// ---- interactive desk: reply/ask basket + outbox tray + composer ----
// The tray and composer are FIXED bars outside #asks, so a background board update
// (a dept posting mid-reply) re-renders the columns without ever wiping an answer in
// progress. BASKET is the client mirror of the store's staged basket (server-persisted
// so a reload restores it). Nothing sends until "Send to session" flushes it as ONE
// message; replies resolve their item on the board at that moment (never re-run here).
const BASKET = new Map();   // id -> {kind:'reply'|'ask', text}
let basketInit = false, cTarget = null;
function syncBasket(server){
  // Adopt the store basket on first load and on any reconnect with nothing staged
  // locally — never mid-compose (that would fight the Boss typing).
  if (basketInit && BASKET.size) return;
  BASKET.clear();
  (server||[]).forEach(x=>BASKET.set(x.id,{kind:x.kind,text:x.text}));
  basketInit = true;
}
function staged(e){ return BASKET.get(e.id); }
function rowCtl(e){
  if (e.status!=='open') return '';          // Reply/Ask only on live asks
  const s = staged(e);
  const rep = isInfo(e) ? '' :               // info needs no decision — Ask only
    `<button class="bbtn${s&&s.kind!=='ask'?' staged':''}" onclick="event.stopPropagation();openCompose('${esc(e.id)}','reply')">${s&&s.kind!=='ask'?'✎ Reply staged':'Reply'}</button>`;
  const ask =
    `<button class="bbtn${s&&s.kind==='ask'?' staged':''}" onclick="event.stopPropagation();openCompose('${esc(e.id)}','ask')">${s&&s.kind==='ask'?'✎ Question staged':'Ask'}</button>`;
  // Information needs no decision, only a "seen" tick — mechanical, never touches the session.
  const read = isInfo(e)
    ? `<label class="rdchk" onclick="event.stopPropagation()"><input type="checkbox" ${e.read?'checked':''} onchange="toggleRead('${esc(e.id)}',this.checked)">read</label>`
    : '';
  return `<div class="rowbtns">${rep}${ask}${read}</div>`;
}
function toggleRead(id, read){ post('/read',{id,read}).catch(()=>{}); lastRaw=''; }
function openCompose(id, kind){
  cTarget = {id, kind};
  const cur = BASKET.get(id);
  document.getElementById('chd').innerHTML = (kind==='ask'?'Question about ':'Reply to ')+'<b>'+esc(id)+'</b>'+(kind==='ask'?' — sent to the session, the item stays open':' — resolves the item and is sent to the session');
  const ta = document.getElementById('ctext');
  ta.placeholder = kind==='ask' ? 'Your question…' : 'Your decision…';
  ta.value = cur ? cur.text : '';
  document.getElementById('compose').classList.add('on');
  document.body.classList.add('haspanel');
  ta.focus();
}
function closeCompose(){ cTarget=null; document.getElementById('compose').classList.remove('on'); renderTray(); }
function post(path, body){
  return fetch(path,{method:'POST',headers:{'X-Board':'1','Content-Type':'application/json'},body:JSON.stringify(body||{})});
}
function stageCompose(){
  if(!cTarget) return;
  const text = document.getElementById('ctext').value.trim();
  if(text) BASKET.set(cTarget.id,{kind:cTarget.kind,text}); else BASKET.delete(cTarget.id);
  post(`/basket`,{id:cTarget.id,kind:cTarget.kind,text}).catch(()=>{});
  lastRaw=''; closeCompose();                // force a re-render so the row button reflects staged
}
function unstage(id){ BASKET.delete(id); post(`/basket`,{id,text:''}).catch(()=>{}); lastRaw=''; renderTray(); }
function renderTray(){
  const tray = document.getElementById('tray');
  const items = [...BASKET.entries()];
  const composeOn = document.getElementById('compose').classList.contains('on');
  if(!items.length){
    tray.classList.remove('on'); document.getElementById('traylist').innerHTML='';
    if(!composeOn) document.body.classList.remove('haspanel');
    return;
  }
  document.getElementById('traycount').textContent = items.length+(items.length===1?' answer staged':' answers staged');
  document.getElementById('traylist').innerHTML = items.map(([id,v])=>
    `<span class="tchip${v.kind==='ask'?' ask':''}"><span class="tk">${esc(id)}${v.kind==='ask'?' ?':''}</span><span class="tt" title="${esc(v.text)}">${esc(v.text)}</span><span class="tx2" title="unstage" onclick="unstage('${esc(id)}')">✕</span></span>`).join('');
  if(!composeOn) tray.classList.add('on');
  document.body.classList.add('haspanel');
}
function toast(msg){
  const t=document.getElementById('toast'); t.textContent=msg; t.classList.add('on');
  clearTimeout(t._t); t._t=setTimeout(()=>t.classList.remove('on'),3800);
}
const SENT = {
  ok:'Ready in your terminal — press Enter there to hand over your answers.',
  notfound:'Queued — your terminal pane was not found; type anything + Enter in your Claude terminal to hand them over.',
  skip:'Queued — type anything + Enter in your Claude terminal (or restart it once so the board can prime it).',
  err:'Queued — type anything + Enter in your Claude terminal to hand them over.',
  empty:'Nothing staged.'};
async function sendBasket(){
  if(!BASKET.size) return;
  try{
    const j = await (await post(`/send`,{})).json();
    BASKET.clear(); basketInit=true; lastRaw=''; closeCompose(); renderTray();
    toast(SENT[j.delivery] || 'Saved on the board.');
  }catch(e){ toast('Send failed — your answers are still staged.'); }
}
// Dashboard tabs (Dashboard glance · Tasks kanban home). Persisted in localStorage;
// #x expand-all still works independently of the active tab.
function showTab(name){
  document.querySelectorAll('nav.tabs button').forEach(b=>b.classList.toggle('on', b.dataset.tab===name));
  document.querySelectorAll('section.tabpane').forEach(s=>s.classList.toggle('on', s.id==='tab-'+name));
  try{ localStorage.setItem('board-tab', name); }catch(e){}
}
try{ const _t=localStorage.getItem('board-tab'); if(_t && document.getElementById('tab-'+_t)) showTab(_t); }catch(e){}
function toggleRail(){ document.body.classList.toggle('railoff'); try{localStorage.setItem('board-rail', document.body.classList.contains('railoff')?'off':'on');}catch(e){} }
try{ if(localStorage.getItem('board-rail')==='off') document.body.classList.add('railoff'); }catch(e){}
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
  // Honest about source: 'default' is the frontmatter fallback; 'running' is the live
  // spawn override the CEO chose this session (the real answer to "what runs this dept").
  const src = !d.model ? '' : (d.live
    ? `running ${esc(d.model)}${d.default_model&&d.default_model!==d.model?` · default ${esc(d.default_model)}`:''}`
    : `default model — no live override this session`);
  return `<div class="dept">
    <div class="dhd">${handle}${d.external?`<span class='pill px'>分</span>`:''}${modelPill(d.model, d.live)}</div>
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
  // the table's row heights into huge blank cells (Boss 2026-07-22). Pointers are prose,
  // so no paths() link-wrapping either.
  const canon = (dd.canon||[]).map(x=>
    `<div class='cx'><span class='ctopic' title='${esc(x.topic)}'>${esc(x.topic)}</span><span class='cptr'>${esc(x.ptr)}</span>${x.updated?`<span class='cupd'>${esc(x.updated)}</span>`:''}</div>`).join('') || `<p class='empty'>—</p>`;
  return `<div><h3 class='dsub'>Recent rulings <span class='count'>${(dd.decisions||[]).length}</span></h3>${decs}</div>
    <div><h3 class='dsub'>Canon · settled answers <span class='count'>${(dd.canon||[]).length}</span></h3>${canon}</div>`;
}
// Mail & Branches: the 分公司 offices + the mail lane (letters newest-first, unread dot).
function mailView(mm){
  if(!mm) return `<p class='empty'>No mail lane (docs/board/mail).</p>`;
  const br = (mm.branches||[]).map(b=>
    `<div class='brn'><span class='dchip' style='--dh:${hue(b.handle)}'>${esc(b.handle)}</span><span class='pill px'>分</span><span class='brmeta'>${b.letters} letter(s)${b.unread?` · <b>${b.unread} unread</b>`:''}${b.last?` · ${esc(b.last)}`:''}</span></div>`).join('');
  const rows = (mm.mail||[]).map(m=>{
    const un = (m.status||'').toLowerCase()==='unread';
    return `<tr class='${un?'unread':''}'><td class='mstat'>${un?'●':''}</td><td class='mfrom'>${esc(m.from)}</td><td class='marrow'>→</td><td class='mto'>${esc(m.to)}</td><td class='mre'>${esc(m.re)}</td><td class='mtime'>${esc(m.time)}</td></tr>`;
  }).join('');
  return `${br?`<div class='dsub'>Branch offices</div><div class='brwrap'>${br}</div>`:''}
    <div class='dsub' style='margin-top:1.4em'>Mail lane <span class='count'>${(mm.mail||[]).length}</span></div>
    <div class='ftable'><table><tbody>${rows||`<tr><td class='empty'>—</td></tr>`}</tbody></table></div>`;
}
// Archive: recently-shipped tail + BACKLOG history (title clamped; full record in the file).
function archiveView(ar){
  if(!ar) return `<p class='empty'>Nothing archived yet.</p>`;
  const ship = (ar.shipped||[]).map(x=>`<div class='shl'>${md(x)}</div>`).join('');
  const bl = (ar.backlog||[]).map(x=>
    `<div class='blg'><div class='blh'>${x.date?`<span class='decdate'>${esc(x.date)}</span>`:''}${x.dept?`<span class='dchip' style='--dh:${hue(x.dept)}'>${esc(x.dept)}</span>`:''}</div><div class='dectitle'>${md(x.title)}</div></div>`).join('');
  return `${ship?`<div class='dsub'>Recently shipped</div>${ship}`:''}
    <div class='dsub' style='margin-top:${ship?'1.4em':'0'}'>History · BACKLOG <span class='count'>${(ar.backlog||[]).length}</span></div>${bl||`<p class='empty'>—</p>`}`;
}
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
    const raw = JSON.stringify([s.entries, s.taskboard, s.sot]);
    fails = 0;
    document.body.style.opacity = "";   // clear a stale "disconnected" dim on reconnect
    syncBasket(s.basket); renderTray();  // restore/reflect staged answers every poll
    if (raw === lastRaw){
      document.getElementById('stamp').textContent =
        (s.entries||[]).filter(e=>e.status==='open' && !isInfo(e)).length + " open · updated " + new Date().toLocaleTimeString();
      return;
    }
    lastRaw = raw;
    document.getElementById('sot').innerHTML = s.sot ? sotBand(s.sot) : '';
    const es = s.entries || [];
    const tb = s.taskboard || {tasks:[], shipped:[]};
    const T = {list: tb.tasks, byId: {}};
    tb.tasks.forEach(t=>{ if(t.task_id) T.byId[t.task_id]=t; });
    // Needs-you drains oldest-first (what's waited longest never sinks); Information
    // reads newest-first (it's a feed, not a queue — the freshest fact sits on top).
    const bywait = (a,b)=>(a.created||'').localeCompare(b.created||'');
    const open = es.filter(e=>e.status==='open').sort(bywait);
    const needsOpen = open.filter(e=>!isInfo(e));
    const infoOpen  = open.filter(isInfo).reverse();
    const parked = es.filter(e=>e.status==='parked').sort(bywait);
    const resolved = es.filter(e=>e.status==='resolved')
                       .sort((a,b)=>(b.updated||'').localeCompare(a.updated||''));
    document.getElementById('askn').textContent = needsOpen.length;
    document.getElementById('parkn').textContent = parked.length;
    document.getElementById('infon').textContent = infoOpen.length;
    document.getElementById('histn').textContent = resolved.length;
    document.getElementById('asks').innerHTML = needsOpen.length
      ? needsOpen.map(e=>askRow(e,T)).join('')
      : `<div class='colempty'><div class='glyph'>${ICONS.clear}</div><p class='empty'>Nothing waiting on you.</p></div>`;
    document.getElementById('parked').innerHTML = parked.length
      ? parked.map(e=>askRow(e,T)).join('')
      : `<div class='colempty'><div class='glyph'>${ICONS.crab}</div><p class='empty'>Nothing parked — the crab keeps the seat warm.</p></div>`;
    document.getElementById('infos').innerHTML = infoOpen.length
      ? infoOpen.map(e=>askRow(e,T)).join('')
      : `<div class='colempty'><div class='glyph'>${ICONS.inbox}</div><p class='empty'>Verdicts and FYIs land here.</p></div>`;
    document.getElementById('hist').innerHTML = resolved.length
      ? resolved.slice(0,5).map(e=>askRow(e,T,e.updated)).join('')
      : `<p class='empty'>—</p>`;
    // Priority sort inside the working columns: P0 < P1 < P2 < unset lexically; JS
    // sort is stable, so board (id) order holds within a tier. Done keeps recency.
    const pr = t=>/^P\d$/.test(t.priority||'') ? t.priority : 'P8';
    const psort = arr=>arr.slice().sort((a,b)=>pr(a).localeCompare(pr(b)));
    const todo = psort(tb.tasks.filter(t=>['todo','blocked'].includes(t.status)||!t.status));
    const prog = psort(tb.tasks.filter(t=>['doing','review'].includes(t.status)));
    const doneT = tb.tasks.filter(t=>t.status==='done');
    const shipped = tb.shipped||[];
    // Done is a glance at momentum, not the archive (that's BACKLOG.md): the 5 most
    // recent entries — but a hot day must not vanish behind the cap, so when today
    // ships more than 5 the cap stretches to keep every today-stamped row. done-status
    // cards first (still on the live board), then the shipped tail (newest-first).
    // Shipped-line head: `date · #proj · #tid · …` (6-field, 0.9.24) or legacy
    // `date · #tid · …` — pill the leading id(s); the two-id replace fires first
    // and leaves nothing for the one-id pattern to re-match. A LONE leading id is
    // the session task_id (legacy / card-less lines), so it wears the NEUTRAL pill
    // — coral is reserved for the durable #NNN. Placeholder runs (" · — · —") from
    // card-less completions collapse before render: quiet lines, no dash noise.
    const pillDone = h => h
      .replace(/^(\d{4}-\d{2}-\d{2}) · (#\d+) · (#\d+) · /, "$1 <span class='pill pj'>$2</span><span class='pill pt'>$3</span> ")
      .replace(/^(\d{4}-\d{2}-\d{2}) · (#\d+) · /, "$1 <span class='pill pt'>$2</span> ");
    const doneAll = doneT.map(tCard).concat(
        shipped.map(raw=>{ const x = raw.replace(/( · —)+(?= · )/g,'');
          return `<div class='done-line${xc('s:'+x)}' data-k="${esc('s:'+x)}" tabindex="0" onclick="tog(this)"><div class='dl'>${pillDone(md(x))}</div></div>`; }));
    const d = new Date();
    const today = d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
    const cap = Math.max(5, doneT.length + shipped.filter(x=>x.trim().startsWith(today)).length);
    const more = doneAll.length - cap;
    document.getElementById('board').innerHTML =
        col('Todo', '#6b9e5f', 'c-todo', todo.map(tCard).join(''), todo.length)
      + col('In progress', '#c08b2d', 'c-prog', prog.map(tCard).join(''), prog.length)
      + col('Done', '#9c87c9', 'c-done', doneAll.slice(0,cap).join('') +
            (more>0?`<p class='empty'>+${more} more → BACKLOG.md</p>`:''), doneT.length+shipped.length);
    // Monitor glance strip (Dashboard tab): live counts + a health dot.
    const blocked = tb.tasks.filter(t=>t.status==='blocked').length;
    const doneToday = shipped.filter(x=>x.trim().startsWith(today)).length;
    const tile = (n,lab,h)=>`<div class='tile'><div class='tn'>${n}<span class='th ${h}'></span></div><div class='tlab'>${lab}</div></div>`;
    document.getElementById('monitor').innerHTML =
        tile(needsOpen.length,'Needs you', needsOpen.length?'attn':'calm')
      + tile(prog.length,'In progress','calm')
      + tile(blocked,'Blocked', blocked?'warn':'calm')
      + tile(doneToday,'Shipped today','calm');
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
    document.getElementById('stamp').textContent =
      needsOpen.length + " open · updated " + new Date().toLocaleTimeString();
  }catch(e){
    // A restarting/reaped server recovers within a poll or two — keep the view.
    // Past that the server is gone: a frozen tab must not impersonate a live board.
    if(++fails >= 4){
      document.body.style.opacity = ".4";
      document.getElementById('stamp').textContent =
        "disconnected — this panel is no longer live; run /board to reopen";
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
    if not p or p.startswith(("/", "~")):
        return None
    full = os.path.realpath(os.path.join(base, p))
    baser = os.path.realpath(base)
    if not full.startswith(baser + os.sep) or not os.path.isfile(full):
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
    """Where session_start records the Boss's iTerm2 session id (env ITERM_SESSION_ID),
    so Send can push a reply into THAT exact pane."""
    return os.path.join(runtime_dir(root), "iterm-target")


# Delivery: the content always travels via the outbox + the UserPromptSubmit inbox hook
# (one deliverer, which marks it delivered), so a reply can never be "resolved but not
# delivered". A turn still has to FIRE for the hook to run, and macOS silently drops a
# synthetic Return posted by a background process (field-proven 2026-07-22: osascript
# reports success, the key never registers) — so true auto-submit is impossible from
# here. Instead we PRIME the pane: type a short nudge into the input (no focus steal —
# write text targets the session by id) and let the Boss press Enter, which fires the
# turn. tmux sessions get real hands-off via `tmux send-keys` (a genuine input event the
# TUI accepts); see iterm-target capture. argv-driven (no shell/AppleScript injection);
# the GUID pins the paste to exactly one pane.
BOARD_NUDGE = "Deliver my Boss Board answers."
ITERM_PRIME_APPLESCRIPT = (
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
    "  return \"notfound\"\n"
    "end run\n")


def iterm_prime(root):
    """Prime the Boss's PINNED iTerm2 pane with the delivery nudge — no submit (macOS
    won't let a background process press a real Return), so the Boss presses Enter, which
    fires the turn and the inbox hook hands over the queued answers. No focus steal
    (write text targets the session by id). Returns 'ok' | 'notfound' | 'skip' | 'err'.
    Never raises; tests set BOARD_SKIP_ITERM."""
    if os.environ.get("BOARD_SKIP_ITERM"):
        return "skip"
    try:
        guid = open(iterm_target_file(root), encoding="utf-8").read().strip()
    except Exception:
        return "skip"                       # no captured session (not iTerm2, or pre-capture)
    guid = guid.split(":")[-1].strip()      # ITERM_SESSION_ID is "wNtMpK:GUID"; id = the GUID tail
    if not guid:
        return "skip"
    try:
        r = subprocess.run(["osascript", "-", guid, BOARD_NUDGE],
                           input=ITERM_PRIME_APPLESCRIPT, capture_output=True,
                           text=True, timeout=5)
        out = (r.stdout or "").strip()
        return out if out in ("ok", "notfound") else "err"
    except Exception:
        return "err"


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
                if got:
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
            from urllib.parse import urlparse
            if self.headers.get("X-Board") != "1":
                self.send_response(403); self.end_headers(); return
            path = urlparse(self.path).path
            try:
                n = int(self.headers.get("Content-Length") or 0)
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

    threading.Thread(target=reaper, daemon=True).start()
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


def board_resolve_dept(root, dept, sum=None):
    return _locked_mutate(root, lambda store: resolve_by_dept(store, dept, _now(), sum))


def board_done(root, eid, sum=None):
    return _locked_mutate(root, lambda store: set_status(store, eid, "resolved", _now(), sum))


def board_send(root):
    """Flush the Boss Board basket. Resolves replies on the board (source of truth) and
    queues the composed answer in the outbox as PENDING; the UserPromptSubmit inbox hook
    is the ONE deliverer (it injects the content and marks it delivered), so nothing is
    ever resolved-but-not-delivered. We PRIME the pane with the nudge so the Boss just
    presses Enter to fire the turn. Returns {'n','delivery','msg'}; delivery in
    ok|notfound|skip|err|empty."""
    now = _now()
    rec = _locked_mutate(root, lambda store: board_send_mutate(store, now))
    if not rec:
        return {"n": 0, "delivery": "empty", "msg": ""}
    return {"n": len(rec["items"]), "delivery": iterm_prime(root), "msg": rec["msg"]}


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
        # old "Boss" default put her name in every CLI-raised ask's dept column
        # (her ruling 2026-07-21: "Boss is not dept"); explicit Boss normalises too.
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
