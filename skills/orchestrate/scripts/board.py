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


def add_entry(store, dept, kind, text, now, task=None):
    dup = find_open_dup(store, dept, text)
    if dup:
        return dup, False
    e = {"id": next_id(store, dept), "dept": dept, "text": (text or "").strip(),
         "kind": kind, "status": "open", "created": now, "updated": now}
    if task:
        e["task"] = str(task)  # platform task_id — lets the panel show the ask's task card
    store["entries"].append(e)
    return e, True


def get_entry(store, eid):
    for e in store["entries"]:
        if e["id"] == eid:
            return e
    return None


def list_entries(store, dept=None):
    return [e for e in store["entries"] if dept is None or e["dept"] == dept]


def set_status(store, eid, status, now):
    e = get_entry(store, eid)
    if e:
        e["status"] = status
        e["updated"] = now
    return e


def open_for_dept(store, dept):
    return [e for e in store["entries"] if e["dept"] == dept and e["status"] == "open"]


def resolve_by_dept(store, dept, now):
    opens = open_for_dept(store, dept)
    if len(opens) == 1:
        opens[0]["status"] = "resolved"
        opens[0]["updated"] = now
        return opens[0], []
    return None, opens


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
DONE_RE = re.compile(r"@BOSS-DONE\[([^\]\s]+)\]")


def parse_markers(text):
    """raises = (dept, task_id-or-None, ask). `misses` = lines that mention @BOSS but
    match neither regex — the hook logs them (marker-misses.log) so a malformed marker
    doesn't vanish without a trace."""
    raises, dones, misses = [], [], []
    for line in (text or "").splitlines():
        m = DONE_RE.search(line)
        if m:
            dones.append(m.group(1).split("#")[0])  # tolerate a symmetric #task suffix
            continue
        m = RAISE_RE.search(line)
        if m:
            raises.append((m.group(1), m.group(2), m.group(3).strip()))
            continue
        if "@BOSS" in line:
            misses.append(line)
    return {"raises": raises, "dones": dones, "misses": misses}


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
                      "status": status,
                      "blocked_on": field("blocked_on"), "what": field("what")})
    shipped = []
    m = re.search(r"<!-- SHIPPED:START -->(.*?)<!-- SHIPPED:END -->", text, re.S)
    seg = m.group(1) if m else _section(text, "Recently shipped")
    for line in seg.splitlines():
        if line.strip().startswith("- ") and not line.strip().startswith("- <"):
            shipped.append(line.strip()[2:])
    return {"tasks": tasks, "shipped": shipped}


def load_taskboard(root):
    rel = "docs/TaskBoard.md"
    try:
        rel = json.load(open(os.path.join(root, ".claude", "orchestrate.json"),
                             encoding="utf-8")).get("taskboard", rel)
    except Exception:
        pass
    return parse_taskboard(os.path.join(root, rel))


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
.rage { flex: none; font-size: .7rem; color: #87867f; margin-top: .25em;
        font-family: ui-monospace, "SF Mono", Menlo, monospace; }
.parked .row { opacity: .6; }
.parked .dot2 { background: #cbc6b9; }
.answered .row { opacity: .72; }
.answered .dot2 { background: #6b9e5f; }
.colempty { text-align: center; padding: 12px 6px 16px; }
.glyph { color: #b6b2a4; margin: .45em 0 .05em; }
html.dark .glyph { color: #6f6d66; }
.chip { display: inline-block; font-size: .72rem; border: 1px solid #d9d4c6; border-radius: 10px;
        padding: 1px 8px; margin: .35em .3em 0 0; color: #6b6a62; }
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
html.dark .parked .dot2 { background: #5c5b57; }
html.dark .answered .dot2 { background: #7fae72; }
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
html.dark code { background: #3e3d3a; }
html.dark a { color: #e08262; text-decoration-color: rgba(224,130,98,.4); }
html.dark a:hover { text-decoration-color: #e08262; }
html.dark .badge.blocked { background: #4a2a20; color: #e08262; }
html.dark .badge.review { background: #3a3050; color: #c4b3e8; }
html.dark [data-k]:focus-visible { outline-color: #d97757; }
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
<header>
  <div class='brand'>Boss Board</div>
  <h1 id='proj'>—</h1>
  <div class='stamp' id='stamp'>—</div>
</header>
<h2>On your desk</h2>
<div class='board top'>
  <div class='col'><h3><span class='dot' style='border-color:#c15f3c'></span>Needs you
    <span class='count' id='askn'>0</span></h3><div id='asks'></div></div>
  <div class='col parked'><h3><span class='dot' style='border-color:#cbc6b9'></span>Parked
    <span class='count' id='parkn'>0</span></h3><div id='parked'></div></div>
  <div class='col answered'><h3><span class='dot' style='border-color:#6b9e5f'></span>Answered
    <span class='count' id='ansn'>0</span></h3><div id='answered'></div></div>
</div>
<h2>Current iteration</h2>
<div class='board' id='board'></div>
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
// Finder. Needs a slash + an extension; a preceding char outside the path charset
// (or start) anchors it, so URL innards (host/a.png) never match; trailing
// punctuation stays outside via the \b. stopPropagation keeps a link click from
// toggling the row/card it sits in.
function paths(h){
  return h.replace(/(^|[^\w.\-\/一-鿿])((?:[\w.\-一-鿿]+\/)+[\w.\-一-鿿]+\.[A-Za-z0-9]{1,5})\b/g,
    (m,pre,p)=>pre+`<a href="/file?p=${encodeURIComponent(p)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">${p}</a>`);
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
function tog(el){
  if (getSelection().toString()) return;   // selecting text is not a toggle
  const k = el.dataset.k;
  el.classList.toggle('x');
  if (el.classList.contains('x')) EXP.add(k); else EXP.delete(k);
}
function xc(k){ return EXP.has(k) ? ' x' : ''; }
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
function chip(t){
  return `<span class="chip"><b>${md(t.label)}${t.task_id?` · #`+esc(t.task_id):''}</b> · ${md(t.name)} · ${esc(t.status||'?')}</span>`;
}
function askRow(e, T, ts){
  // Context for the decision: the explicitly linked task first; else the dept's
  // in-flight cards (its ask is almost always about one of them).
  let linked = (e.task && T.byId[e.task]) ? [T.byId[e.task]]
    : T.list.filter(t=>t.dept===e.dept && ['doing','review','blocked'].includes(t.status)).slice(0,2);
  const a = age(ts || e.created);
  // Long asks enumerate with circled digits (① button label… ② the view… ③ the N…) —
  // break each onto its own line so the expanded wall scans as a list. The lookahead
  // keeps inline REFERENCES ("chain ①②③④ COMPLETE") intact: only a digit that starts
  // a clause (preceded by space, not followed by another digit) breaks.
  const rt = md(e.text).replace(/\s([①-⑳])(?![①-⑳])/g,'<br>$1');
  return `<div class="row${xc(e.id)}" data-k="${esc(e.id)}" tabindex="0" onclick="tog(this)">
    <span class="dot2 k-${esc(e.kind)}"></span>
    <div class="rc">
      <div class="rt">${rt}</div>
      <div class="rm"><b>${esc(e.id)}</b> · ${esc(e.dept)} · ${esc(e.kind)}${e.task?` · task #${esc(e.task)}`:''}</div>
      <div class="rx">${linked.map(chip).join('')}</div>
    </div>
    <span class="rage">${a}</span></div>`;
}
function tCard(t){
  const badge = t.status==='blocked'
      ? `<span class="badge blocked">blocked${t.blocked_on?': '+esc(t.blocked_on):''}</span>`
      : t.status==='review' ? `<span class="badge review">review</span>` : '';
  // Long card bodies clamp to a few lines; click a card to expand it. The s-<status>
  // class gives blocked/review cards their coloured undershade. Hook-born cards have
  // label "#<id>" (skip the redundant id chip) and ·-less headings parse label===name
  // (skip the redundant body line) — show each fact once.
  const k = 't:' + t.label + '#' + (t.task_id||'');
  const id = t.task_id && t.label !== '#'+t.task_id ? ` · #`+esc(t.task_id) : '';
  return `<div class="t s-${esc(t.status||'none')}${xc(k)}" data-k="${esc(k)}" tabindex="0" onclick="tog(this)"><span class="tid">${md(t.label)}${id}</span>${badge}
    ${t.name && t.name !== t.label ? `<div class="nm">${md(t.name)}</div>` : ''}
    <div class="sub">${esc(t.dept)}${t.what?` · `+md(t.what):''}</div></div>`;
}
function col(title, color, cls, inner, n){
  return `<div class="col ${cls}"><h3><span class="dot" style="border-color:${color}"></span>${title}
    <span class="count">${n}</span></h3>${inner||"<p class='empty'>—</p>"}</div>`;
}
let fails = 0, lastRaw = '';
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
    const raw = JSON.stringify([s.entries, s.taskboard]);
    fails = 0;
    document.body.style.opacity = "";   // clear a stale "disconnected" dim on reconnect
    if (raw === lastRaw){
      document.getElementById('stamp').textContent =
        (s.entries||[]).filter(e=>e.status==='open').length + " open · updated " + new Date().toLocaleTimeString();
      return;
    }
    lastRaw = raw;
    const es = s.entries || [];
    const tb = s.taskboard || {tasks:[], shipped:[]};
    const T = {list: tb.tasks, byId: {}};
    tb.tasks.forEach(t=>{ if(t.task_id) T.byId[t.task_id]=t; });
    // Oldest first — the queue drains top-down, and what's waited longest never sinks.
    const bywait = (a,b)=>(a.created||'').localeCompare(b.created||'');
    const open = es.filter(e=>e.status==='open').sort(bywait);
    const parked = es.filter(e=>e.status==='parked').sort(bywait);
    const resolved = es.filter(e=>e.status==='resolved')
                       .sort((a,b)=>(b.updated||'').localeCompare(a.updated||''));
    document.getElementById('askn').textContent = open.length;
    document.getElementById('parkn').textContent = parked.length;
    document.getElementById('ansn').textContent = resolved.length;
    document.getElementById('asks').innerHTML = open.length
      ? open.map(e=>askRow(e,T)).join('')
      : `<div class='colempty'><div class='glyph'>${ICONS.clear}</div><p class='empty'>Nothing waiting on you.</p></div>`;
    document.getElementById('parked').innerHTML = parked.length
      ? parked.map(e=>askRow(e,T)).join('')
      : `<div class='colempty'><div class='glyph'>${ICONS.crab}</div><p class='empty'>Nothing parked — the crab keeps the seat warm.</p></div>`;
    document.getElementById('answered').innerHTML = resolved.length
      ? resolved.slice(0,5).map(e=>askRow(e,T,e.updated)).join('')
      : `<div class='colempty'><div class='glyph'>${ICONS.inbox}</div><p class='empty'>Resolved asks land here.</p></div>`;
    const todo = tb.tasks.filter(t=>['todo','blocked'].includes(t.status)||!t.status);
    const prog = tb.tasks.filter(t=>['doing','review'].includes(t.status));
    const doneT = tb.tasks.filter(t=>t.status==='done');
    const shipped = tb.shipped||[];
    // Done shows the 6 most recent entries only — it's a glance at momentum, not the
    // archive (that's BACKLOG.md). done-status cards first (still on the live board),
    // then the shipped tail (already newest-first).
    const doneAll = doneT.map(tCard).concat(
        shipped.map(x=>`<div class='done-line${xc('s:'+x)}' data-k="${esc('s:'+x)}" tabindex="0" onclick="tog(this)"><div class='dl'>${md(x)}</div></div>`));
    const more = doneAll.length - 6;
    document.getElementById('board').innerHTML =
        col('Todo', '#6b9e5f', 'c-todo', todo.map(tCard).join(''), todo.length)
      + col('In progress', '#c08b2d', 'c-prog', prog.map(tCard).join(''), prog.length)
      + col('Done', '#9c87c9', 'c-done', doneAll.slice(0,6).join('') +
            (more>0?`<p class='empty'>+${more} more → BACKLOG.md</p>`:''), doneT.length+shipped.length);
    document.getElementById('stamp').textContent =
      open.length + " open · updated " + new Date().toLocaleTimeString();
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


def resolve_file(root, p):
    """(abspath, content-type) for a project file the panel may serve, else None.
    Backs the /file endpoint that makes paths in asks clickable. A miss in the main
    checkout falls through to the repo's linked worktrees — pre-merge artifacts
    (renders the Boss is asked to eyeball) live only in a dept pane's worktree. The
    main checkout wins when both have the file: post-merge, master is the truth."""
    for base in [root] + _linked_worktrees(root):
        full = _resolve_under(base, p)
        if full:
            return full, VIEWABLE.get(os.path.splitext(full)[1].lower(),
                                      "text/plain; charset=utf-8")
    return None


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
                payload["taskboard"] = load_taskboard(root)  # live iteration view
                payload["version"] = BUILD                   # tab hot-reloads on change
                payload["project"] = os.path.basename(os.path.abspath(root))
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
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

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)

    def reaper():
        while True:
            time.sleep(30)
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


def board_add(root, dept, kind, text, task=None):
    e = _locked_mutate(root, lambda store: add_entry(store, dept, kind, text, _now(), task)[0])
    _surface(root)
    return e


def board_resolve_dept(root, dept):
    return _locked_mutate(root, lambda store: resolve_by_dept(store, dept, _now()))


def board_done(root, eid):
    return _locked_mutate(root, lambda store: set_status(store, eid, "resolved", _now()))


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
                             "  orchestrate-board add --dept <handle> --kind <needs|discuss>"
                             " --text \"...\" [--task <id>]\n")
            sys.exit(2)
        e = board_add(root, _opt(argv, "--dept", "Boss"),
                      _opt(argv, "--kind", "needs"), text,
                      _opt(argv, "--task"))
        print(e["id"])
    elif cmd == "done":
        e = board_done(root, argv[1]); print(e["id"] if e else "not found")
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
        sys.stderr.write("usage: orchestrate-board add|done|resolve|park|reopen|get|list|open|stop\n")


if __name__ == "__main__":
    main()
