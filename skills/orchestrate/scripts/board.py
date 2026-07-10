#!/usr/bin/env python3
"""Boss Board — a live "Needs-You" panel aggregating every pending ask for the
Boss across panes. Panes raise `@BOSS[<dept>]: <ask>` (a Stop hook captures it)
and resolve with `@BOSS-DONE[<dept>]`; the Boss raises via the `/board` command.
A singleton localhost server serves a self-polling page that always shows the
current open asks. Stdlib only; degrades, never hard-fails. See
docs/superpowers/specs/2026-06-30-boss-board-design.md."""
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
        tasks.append({"label": clean(label) or head, "name": clean(name) or clean(label),
                      "dept": field("dept"), "task_id": field("task_id"),
                      "status": sm.group(1).lower() if sm else "",
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


def _server_is_current(root):
    """True iff the recorded server was spawned from THIS plugin version. A live
    daemon holds its page + logic in memory indefinitely, so after a plugin update a
    stale server keeps serving the old panel while every hook politely reuses it —
    the 'board still looks old after an update' trap."""
    try:
        return open(versionfile(root), encoding="utf-8").read().strip() == _plugin_version()
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
            f.write(_plugin_version())
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
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font: 14px/1.5 -apple-system, "SF Pro Text", Helvetica, "PingFang SC", Arial, sans-serif;
       max-width: 1060px; margin: 24px auto; padding: 0 20px; color: #1c1c1e; }
h1 { font-size: 1.3rem; margin: 0 0 .1em; }
.stamp { color: #8e8e93; font-size: .8rem; margin-bottom: 1.1em; }
h2 { font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: #8e8e93;
     margin: 1.4em 0 .5em; }
.count { display: inline-block; background: #e3e3e8; border-radius: 10px; padding: 0 8px;
         font-size: .72rem; color: #48484a; vertical-align: 2px; }
#asks { max-width: 78ch; }   /* cap the reading line — full-width asks were ~180ch */
.card { border: 1px solid #e3e3e8; border-left: 3px solid #b3261e; border-radius: 6px;
        padding: 7px 10px; margin: .35em 0; background: rgba(179,38,30,.03);
        font-size: .84rem; line-height: 1.45; cursor: pointer; }
.card.discuss { border-left-color: #0a84ff; background: rgba(10,132,255,.035); }
.card .meta { font-size: .7rem; color: #8e8e93; margin-bottom: .1em; }
.card .id { font-variant-numeric: tabular-nums; font-weight: 600; color: #636366; }
.card .txt { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 4;
             overflow: hidden; }
.card.x .txt { -webkit-line-clamp: unset; }
.age { float: right; color: #8e8e93; }
.chip { display: inline-block; font-size: .72rem; border: 1px solid #d1d1d6; border-radius: 10px;
        padding: 1px 8px; margin: .35em .3em 0 0; color: #48484a; }
.chip b { font-variant-numeric: tabular-nums; }
code { font: .85em ui-monospace, "SF Mono", Menlo, monospace;
       background: rgba(127,127,127,.14); border-radius: 4px; padding: 0 4px; }
b { font-weight: 600; }
.t .nm, .t .sub { display: -webkit-box; -webkit-box-orient: vertical; overflow: hidden; }
.t .nm { -webkit-line-clamp: 2; }
.t .sub { -webkit-line-clamp: 3; }
.t.x .nm, .t.x .sub { -webkit-line-clamp: unset; }
.t { cursor: pointer; }
.parked .card { opacity: .5; border-left-color: #c7c7cc; }
.empty { color: #8e8e93; font-style: italic; margin: .3em 0; }
.board { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; align-items: start; }
@media (max-width: 760px) { .board { grid-template-columns: 1fr; } }
.col { border: 1px solid #e3e3e8; border-radius: 8px; padding: 8px 10px; }
.col.c-todo { background: rgba(87,171,90,.05); }
.col.c-prog { background: rgba(198,144,38,.06); }
.col.c-done { background: rgba(152,110,226,.05); }
.col h3 { font-size: .82rem; margin: .1em 0 .4em; display: flex; align-items: center; gap: 7px; }
.dot { width: 9px; height: 9px; border-radius: 50%%; display: inline-block; border: 2px solid; }
.t { border: 1px solid #e3e3e8; border-radius: 6px; padding: 6px 9px; margin: .35em 0; background: #fff; }
.t.s-blocked { background: rgba(179,38,30,.07); }
.t.s-review { background: rgba(111,66,193,.07); }
.t .tid { font-size: .72rem; font-weight: 600; color: #636366; font-variant-numeric: tabular-nums; }
.t .nm { font-size: .84rem; }
.t .sub { font-size: .7rem; color: #8e8e93; }
.badge { font-size: .66rem; border-radius: 8px; padding: 1px 7px; margin-left: 4px; }
.badge.blocked { background: #fdecea; color: #b3261e; }
.badge.review { background: #efe7fd; color: #6f42c1; }
.done-line { font-size: .76rem; color: #6e6e73; margin: .35em 0; padding: 6px 9px;
             border: 1px solid #e3e3e8; border-radius: 6px; background: #fff;
             cursor: pointer; }
/* clamp on an inner box, not the padded card — clamping the padded element lets a
   sliver of the cropped 3rd line bleed into the bottom padding */
.done-line .dl { display: -webkit-box; -webkit-box-orient: vertical;
                 -webkit-line-clamp: 2; overflow: hidden; }
.done-line.x .dl { -webkit-line-clamp: unset; }
@media (prefers-color-scheme: dark) {
  body { color: #e3e3e8; background: #1c1c1e; }
  .card, .col, .t, .done-line { border-color: #3a3a3c; }
  .done-line { background: #2c2c2e; }
  .card { background: rgba(255,105,97,.05); }
  .card.discuss { background: rgba(10,132,255,.07); }
  .col.c-todo { background: rgba(87,171,90,.08); }
  .col.c-prog { background: rgba(198,144,38,.09); }
  .col.c-done { background: rgba(152,110,226,.08); }
  .t { background: #2c2c2e; }
  .t.s-blocked { background: rgba(255,105,97,.10); }
  .t.s-review { background: rgba(195,155,245,.10); }
  .count { background: #3a3a3c; color: #c7c7cc; }
  .chip { border-color: #48484a; color: #c7c7cc; }
  .badge.blocked { background: #3a1210; color: #ff6961; }
  .badge.review { background: #2a1e3f; color: #c39bf5; }
}
</style></head><body>
<h1>⚠ Needs you <span class='count' id='askn'>0</span></h1><div class='stamp' id='stamp'>—</div>
<div id='asks'></div>
<h2>Current iteration</h2>
<div class='board' id='board'></div>
<script>
const POLL = %d;
const VER = %s;  // page generation — a version change from the server hot-reloads the tab
// Escape EVERY field: dept/kind/task text come from markers/files any pane can write —
// unescaped they'd be an HTML injection straight into the Boss's panel.
function esc(s){return (s||"").replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
// Minimal markdown AFTER escaping (order matters — esc first keeps the XSS guarantee):
// **bold** and `code` are what markers/cards actually use. A leftover unpaired ** —
// panes use "** " as a bullet — is stripped rather than shown literally.
function md(s){
  return esc(s).replace(/^\*\*\s+/,'')                       // "** " used as a bullet, not bold
               .replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>')
               .replace(/`([^`]+)`/g,'<code>$1</code>')
               .replace(/\*\*/g,'');
}
function age(ts){
  if(!ts) return '';
  const d = (Date.now() - new Date(ts).getTime())/1000;
  if(!isFinite(d) || d < 0) return '';
  if(d < 90) return 'now';
  if(d < 5400) return Math.round(d/60)+'m';
  if(d < 129600) return Math.round(d/3600)+'h';
  return Math.round(d/86400)+'d';
}
function chip(t){
  return `<span class="chip"><b>${esc(t.label)}${t.task_id?` · #`+esc(t.task_id):''}</b> · ${esc(t.name)} · ${esc(t.status||'?')}</span>`;
}
function askCard(e, T){
  // Context for the decision: the explicitly linked task first; else the dept's
  // in-flight cards (its ask is almost always about one of them).
  let linked = (e.task && T.byId[e.task]) ? [T.byId[e.task]]
    : T.list.filter(t=>t.dept===e.dept && ['doing','review','blocked'].includes(t.status)).slice(0,2);
  const a = age(e.created);
  return `<div class="card ${esc(e.kind)}" onclick="this.classList.toggle('x')">
    <div class="meta"><span class="id">${esc(e.id)}</span> · ${esc(e.dept)}${e.task?` · task #${esc(e.task)}`:''} · ${esc(e.kind)}${a?`<span class="age">waiting ${a}</span>`:''}</div>
    <div class="txt">${md(e.text)}</div><div>${linked.map(chip).join('')}</div></div>`;
}
function tCard(t){
  const badge = t.status==='blocked'
      ? `<span class="badge blocked">blocked${t.blocked_on?': '+esc(t.blocked_on):''}</span>`
      : t.status==='review' ? `<span class="badge review">review</span>` : '';
  // Long card bodies clamp to a few lines; click a card to expand it. The s-<status>
  // class gives blocked/review cards their coloured undershade.
  return `<div class="t s-${esc(t.status||'none')}" onclick="this.classList.toggle('x')"><span class="tid">${esc(t.label)}${t.task_id?` · #`+esc(t.task_id):''}</span>${badge}
    <div class="nm">${md(t.name)}</div>
    <div class="sub">${esc(t.dept)}${t.what?` · `+md(t.what):''}</div></div>`;
}
function col(title, color, cls, inner, n){
  return `<div class="col ${cls}"><h3><span class="dot" style="border-color:${color}"></span>${title}
    <span class="count">${n}</span></h3>${inner||"<p class='empty'>—</p>"}</div>`;
}
let fails = 0;
async function tick(){
  try{
    const r = await fetch('/state.json', {cache:'no-store'});
    const s = await r.json();
    if (s.version !== undefined && s.version !== VER) { location.reload(); return; }
    const es = s.entries || [];
    const tb = s.taskboard || {tasks:[], shipped:[]};
    const T = {list: tb.tasks, byId: {}};
    tb.tasks.forEach(t=>{ if(t.task_id) T.byId[t.task_id]=t; });
    // Oldest first — the queue drains top-down, and what's waited longest never sinks.
    const bywait = (a,b)=>(a.created||'').localeCompare(b.created||'');
    const open = es.filter(e=>e.status==='open').sort(bywait);
    const parked = es.filter(e=>e.status==='parked').sort(bywait);
    document.getElementById('askn').textContent = open.length;
    document.getElementById('asks').innerHTML =
      (open.length ? open.map(e=>askCard(e,T)).join('') : "<p class='empty'>Nothing waiting on you. 🎉</p>")
      + (parked.length ? `<div class='parked'><h2>Parked</h2>${parked.map(e=>askCard(e,T)).join('')}</div>` : '');
    const todo = tb.tasks.filter(t=>['todo','blocked'].includes(t.status)||!t.status);
    const prog = tb.tasks.filter(t=>['doing','review'].includes(t.status));
    const doneT = tb.tasks.filter(t=>t.status==='done');
    const shipped = tb.shipped||[];
    // Done shows the 6 most recent entries only — it's a glance at momentum, not the
    // archive (that's BACKLOG.md). done-status cards first (still on the live board),
    // then the shipped tail (already newest-first).
    const doneAll = doneT.map(tCard).concat(
        shipped.map(x=>`<div class='done-line' onclick="this.classList.toggle('x')"><div class='dl'>${md(x)}</div></div>`));
    const more = doneAll.length - 6;
    document.getElementById('board').innerHTML =
        col('Todo', '#57ab5a', 'c-todo', todo.map(tCard).join(''), todo.length)
      + col('In progress', '#c69026', 'c-prog', prog.map(tCard).join(''), prog.length)
      + col('Done', '#986ee2', 'c-done', doneAll.slice(0,6).join('') +
            (more>0?`<p class='empty'>+${more} more → BACKLOG.md</p>`:''), doneT.length+shipped.length);
    document.body.style.opacity = "";
    fails = 0;
    document.getElementById('stamp').textContent =
      open.length + " open · updated " + new Date().toLocaleTimeString();
  }catch(e){
    // A restarting/reaped server recovers within a poll or two — keep the view.
    // Past that the server is gone: a frozen tab must not impersonate a live board.
    if(++fails >= 4){
      document.body.style.opacity = ".4";
      document.getElementById('stamp').textContent =
        "⚠ disconnected — this panel is no longer live; run /board to reopen";
    }
  }
}
tick(); setInterval(tick, POLL);
</script></body></html>""" % (POLL_MS, json.dumps(_plugin_version()))


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
                payload["version"] = _plugin_version()       # tab hot-reloads on change
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
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
        e = board_add(root, _opt(argv, "--dept", "Boss"),
                      _opt(argv, "--kind", "needs"), _opt(argv, "--text", ""),
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
