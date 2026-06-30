# Boss Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A live, always-open "Needs-You" panel aggregating every pending ask for the Boss across all panes, raised/resolved by panes via markers and a Stop hook, with a `/board` command for the Boss.

**Architecture:** A single stdlib-only Python script (`board.py`) holds the JSON store layer, a marker parser, a singleton localhost web server with a self-polling page, and a CLI. A `bin/orchestrate-board` launcher puts it on PATH. A new fail-open `Stop`/`SubagentStop` hook reads the last assistant message, extracts `@BOSS[..]` / `@BOSS-DONE[..]` markers, and calls into `board.py`. A `/board` command and minimal docs wire it into the founder-mode workflow. Nothing touches the dept TaskBoard, the platform task system, or the two existing task hooks.

**Tech Stack:** Python 3 standard library only (`http.server`, `json`, `re`, `hashlib`, `socket`, `subprocess`, `threading`, `tempfile`, `datetime`). Tests use the stdlib `unittest`. Bash for the launcher. Markdown for command/docs.

## Global Constraints

- **Zero third-party dependencies** — Python standard library only, matching `brief.py` / `log.py`.
- **Tests use `unittest`** (stdlib), run via `python3 skills/orchestrate/scripts/test_board.py -v` — do NOT introduce pytest.
- **Store path:** `<project-root>/.claude/boss-board.json`, where project-root is the nearest ancestor containing `.claude/orchestrate.json`, else cwd. Store is gitignored runtime state.
- **Entry ids:** dept-prefixed + per-dept sequential, format `"<dept>-<n>"` (e.g. `QA-1`, `Boss-1`); sequence never reused.
- **States:** `open`, `resolved`, `parked` only. No staleness/age logic anywhere.
- **Markers (exact):** raise `@BOSS[<dept>]: <ask>`; resolve `@BOSS-DONE[<dept>]` or `@BOSS-DONE[<id>]`. Authored by the model; executed by the hook.
- **Hooks fail-open:** any error or missing active marker → no-op, never block a turn. Match the style of `pretool_review_gate.py` (cwd-based `.claude/orchestrate.json` lookup, `cfg.get("active")` check).
- **Port range:** private range 49152–65535, derived from project path, probe upward on collision.
- **No coupling:** do not read/write `TaskBoard.md`, `BACKLOG.md`, `docs/reviews/`, or call `TaskCreate`/`TaskUpdate`.

---

### Task 1: Store core (pure functions) + tests

**Files:**
- Create: `skills/orchestrate/scripts/board.py`
- Test: `skills/orchestrate/scripts/test_board.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `normalize(text: str) -> str`
  - `next_id(store: dict, dept: str) -> str`
  - `find_open_dup(store: dict, dept: str, text: str) -> dict | None`
  - `add_entry(store: dict, dept: str, kind: str, text: str, now: str) -> tuple[dict, bool]` — returns `(entry, created)`; idempotent per `(dept, normalize(text))` while open.
  - `get_entry(store: dict, eid: str) -> dict | None`
  - `list_entries(store: dict, dept: str | None = None) -> list[dict]`
  - `set_status(store: dict, eid: str, status: str, now: str) -> dict | None`
  - `open_for_dept(store: dict, dept: str) -> list[dict]`
  - `resolve_by_dept(store: dict, dept: str, now: str) -> tuple[dict | None, list[dict]]` — resolves iff exactly one open; else `(None, opens)`.
  - `load_store(path: str) -> dict`, `save_store(path: str, store: dict) -> None`
  - Store shape: `{"entries": [entry, ...]}`; entry keys: `id, dept, text, kind, status, created, updated`.

- [ ] **Step 1: Write the failing test**

Create `skills/orchestrate/scripts/test_board.py`:

```python
import os, sys, json, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board

NOW = "2026-06-30T12:00:00"


class StoreCore(unittest.TestCase):
    def test_add_creates_dept_prefixed_sequential_ids(self):
        s = {"entries": []}
        e1, c1 = board.add_entry(s, "QA", "needs", "Postgres or SQLite?", NOW)
        e2, c2 = board.add_entry(s, "QA", "needs", "Where do logs go?", NOW)
        e3, c3 = board.add_entry(s, "RnD", "needs", "Bump node?", NOW)
        self.assertEqual((e1["id"], e2["id"], e3["id"]), ("QA-1", "QA-2", "RnD-1"))
        self.assertTrue(c1 and c2 and c3)
        self.assertEqual(e1["status"], "open")
        self.assertEqual(e1["kind"], "needs")

    def test_add_is_idempotent_per_dept_and_normalised_text(self):
        s = {"entries": []}
        e1, c1 = board.add_entry(s, "QA", "needs", "Postgres or SQLite?", NOW)
        e2, c2 = board.add_entry(s, "QA", "needs", "  postgres or  SQLITE? ", NOW)
        self.assertTrue(c1)
        self.assertFalse(c2)              # duplicate -> no new entry
        self.assertEqual(e1["id"], e2["id"])
        self.assertEqual(len(s["entries"]), 1)

    def test_resolved_entry_frees_text_for_a_new_open_one(self):
        s = {"entries": []}
        e1, _ = board.add_entry(s, "QA", "needs", "same ask", NOW)
        board.set_status(s, e1["id"], "resolved", NOW)
        e2, c2 = board.add_entry(s, "QA", "needs", "same ask", NOW)
        self.assertTrue(c2)               # prior was resolved -> not a dup
        self.assertEqual(e2["id"], "QA-2")

    def test_resolve_by_dept_single_vs_ambiguous(self):
        s = {"entries": []}
        board.add_entry(s, "QA", "needs", "a", NOW)
        e, opens = board.resolve_by_dept(s, "QA", NOW)
        self.assertIsNotNone(e)
        self.assertEqual(e["status"], "resolved")
        board.add_entry(s, "RnD", "needs", "b", NOW)
        board.add_entry(s, "RnD", "needs", "c", NOW)
        e2, opens2 = board.resolve_by_dept(s, "RnD", NOW)
        self.assertIsNone(e2)             # two open -> ambiguous
        self.assertEqual(len(opens2), 2)

    def test_get_and_list_filter_by_dept(self):
        s = {"entries": []}
        board.add_entry(s, "QA", "needs", "a", NOW)
        board.add_entry(s, "RnD", "needs", "b", NOW)
        self.assertEqual(board.get_entry(s, "QA-1")["text"], "a")
        self.assertIsNone(board.get_entry(s, "QA-9"))
        self.assertEqual([e["id"] for e in board.list_entries(s, "RnD")], ["RnD-1"])
        self.assertEqual(len(board.list_entries(s)), 2)

    def test_set_status_park_reopen(self):
        s = {"entries": []}
        board.add_entry(s, "Boss", "discuss", "ToS read", NOW)
        self.assertEqual(board.set_status(s, "Boss-1", "parked", NOW)["status"], "parked")
        self.assertEqual(board.set_status(s, "Boss-1", "open", NOW)["status"], "open")
        self.assertIsNone(board.set_status(s, "Boss-9", "open", NOW))

    def test_load_save_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, ".claude", "boss-board.json")
            self.assertEqual(board.load_store(p), {"entries": []})  # missing -> empty
            s = {"entries": []}
            board.add_entry(s, "QA", "needs", "ask", NOW)
            board.save_store(p, s)
            self.assertEqual(board.load_store(p)["entries"][0]["id"], "QA-1")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 skills/orchestrate/scripts/test_board.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'board'` (or `AttributeError` once the file exists but functions don't).

- [ ] **Step 3: Write minimal implementation**

Create `skills/orchestrate/scripts/board.py` with the store layer (header + pure functions only for now):

```python
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

def add_entry(store, dept, kind, text, now):
    dup = find_open_dup(store, dept, text)
    if dup:
        return dup, False
    e = {"id": next_id(store, dept), "dept": dept, "text": (text or "").strip(),
         "kind": kind, "status": "open", "created": now, "updated": now}
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 skills/orchestrate/scripts/test_board.py -v`
Expected: PASS — all 7 `StoreCore` tests OK.

- [ ] **Step 5: Commit**

```bash
git add skills/orchestrate/scripts/board.py skills/orchestrate/scripts/test_board.py
git commit -m "feat(board): store core — idempotent add, dept-prefixed ids, status moves"
```

---

### Task 2: Marker parser (pure) + tests

**Files:**
- Modify: `skills/orchestrate/scripts/board.py` (append parser)
- Test: `skills/orchestrate/scripts/test_board.py` (append `MarkerParse` case)

**Interfaces:**
- Consumes: nothing.
- Produces: `parse_markers(text: str) -> dict` returning `{"raises": [(dept, ask), ...], "dones": [dept_or_id, ...]}`. One marker per line; `@BOSS-DONE[..]` is recognised before `@BOSS[..]:`.

- [ ] **Step 1: Write the failing test**

Append to `skills/orchestrate/scripts/test_board.py` (above the `if __name__` line):

```python
class MarkerParse(unittest.TestCase):
    def test_raise_marker_extracts_dept_and_one_line_ask(self):
        out = board.parse_markers("blah\n@BOSS[QA]: Postgres or SQLite?\nmore")
        self.assertEqual(out["raises"], [("QA", "Postgres or SQLite?")])
        self.assertEqual(out["dones"], [])

    def test_done_marker_by_dept_and_by_id(self):
        out = board.parse_markers("@BOSS-DONE[QA]\nx\n@BOSS-DONE[RnD-2]")
        self.assertEqual(out["dones"], ["QA", "RnD-2"])
        self.assertEqual(out["raises"], [])

    def test_no_marker_is_empty(self):
        out = board.parse_markers("just a normal message, discuss this later")
        self.assertEqual(out, {"raises": [], "dones": []})

    def test_done_line_is_not_also_a_raise(self):
        out = board.parse_markers("@BOSS-DONE[QA]")
        self.assertEqual(out["raises"], [])
        self.assertEqual(out["dones"], ["QA"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 skills/orchestrate/scripts/test_board.py -v`
Expected: FAIL — `AttributeError: module 'board' has no attribute 'parse_markers'`.

- [ ] **Step 3: Write minimal implementation**

Append to `board.py` after the store layer:

```python
# ---------------------------------------------------------------- markers
RAISE_RE = re.compile(r"@BOSS\[([^\]\s]+)\]:\s*(.+)")
DONE_RE = re.compile(r"@BOSS-DONE\[([^\]\s]+)\]")

def parse_markers(text):
    raises, dones = [], []
    for line in (text or "").splitlines():
        m = DONE_RE.search(line)
        if m:
            dones.append(m.group(1))
            continue
        m = RAISE_RE.search(line)
        if m:
            raises.append((m.group(1), m.group(2).strip()))
    return {"raises": raises, "dones": dones}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 skills/orchestrate/scripts/test_board.py -v`
Expected: PASS — `StoreCore` + `MarkerParse` all OK.

- [ ] **Step 5: Commit**

```bash
git add skills/orchestrate/scripts/board.py skills/orchestrate/scripts/test_board.py
git commit -m "feat(board): @BOSS / @BOSS-DONE marker parser"
```

---

### Task 3: Runtime, server, page + CLI

**Files:**
- Modify: `skills/orchestrate/scripts/board.py` (append runtime/server/page/CLI)
- Test: `skills/orchestrate/scripts/test_board.py` (append `Runtime` case)

**Interfaces:**
- Consumes: store layer (Task 1), `parse_markers` (Task 2).
- Produces:
  - `project_root(start=None) -> str`
  - `proj_hash(root) -> str`, `runtime_dir(root) -> str`, `pidfile(root) -> str`, `portfile(root) -> str`
  - `derive_port(root) -> int`, `port_free(port) -> bool`, `pick_port(root) -> int`
  - `server_info(root) -> int | None`, `ensure_server(root) -> int`, `open_url(url) -> None`, `board_url(port) -> str`
  - `serve(root, port) -> None` (blocking; internal `serve` subcommand)
  - `PAGE: str` (embedded HTML)
  - Command wrappers used by CLI **and** the hook: `board_add(root, dept, kind, text) -> dict`, `board_resolve_dept(root, dept) -> tuple[dict|None, list]`, `board_done(root, eid) -> dict|None`, `board_park(root, eid)`, `board_reopen(root, eid)`, `board_get(root, eid)`, `board_list(root, dept=None)`, `board_open(root) -> int`
  - `main()` CLI entry.

- [ ] **Step 1: Write the failing test**

Append to `skills/orchestrate/scripts/test_board.py`:

```python
class Runtime(unittest.TestCase):
    def test_project_root_finds_marker_else_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write("{}")
            sub = os.path.join(d, "a", "b")
            os.makedirs(sub)
            self.assertEqual(os.path.realpath(board.project_root(sub)),
                             os.path.realpath(d))

    def test_derive_port_is_deterministic_and_in_range(self):
        with tempfile.TemporaryDirectory() as d:
            p1 = board.derive_port(d)
            p2 = board.derive_port(d)
            self.assertEqual(p1, p2)
            self.assertTrue(49152 <= p1 <= 65535)

    def test_board_add_persists_and_is_idempotent_via_disk(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
            board._SKIP_SERVER = True   # test hook: don't spawn the server/open browser
            e1 = board.board_add(d, "QA", "needs", "ask one")
            e2 = board.board_add(d, "QA", "needs", "ask one")
            self.assertEqual(e1["id"], "QA-1")
            self.assertEqual(e2["id"], "QA-1")
            store = board.load_store(os.path.join(d, board.STORE_REL))
            self.assertEqual(len(store["entries"]), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 skills/orchestrate/scripts/test_board.py -v`
Expected: FAIL — `AttributeError: module 'board' has no attribute 'project_root'`.

- [ ] **Step 3: Write minimal implementation**

Append to `board.py` after the markers section:

```python
# ---------------------------------------------------------------- project root
def project_root(start=None):
    d = os.path.abspath(start or os.getcwd())
    if os.path.isfile(d):
        d = os.path.dirname(d)
    cur = d
    while True:
        if os.path.exists(os.path.join(cur, ".claude", "orchestrate.json")):
            return cur
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

def derive_port(root):
    h = int(hashlib.sha1(("port:" + os.path.abspath(root)).encode()).hexdigest(), 16)
    return 49152 + (h % (65535 - 49152))

def port_free(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
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
    port = server_info(root)
    if port:
        return port
    port = pick_port(root)
    with open(portfile(root), "w") as f:
        f.write(str(port))
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
    return port

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

PAGE = """<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Boss Board · Needs you</title>
<style>
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font: 15px/1.5 -apple-system, "SF Pro Text", Helvetica, "PingFang SC", Arial, sans-serif;
       max-width: 640px; margin: 28px auto; padding: 0 20px; color: #1c1c1e; }
h1 { font-size: 1.4rem; margin: 0 0 .1em; }
.stamp { color: #8e8e93; font-size: .8rem; margin-bottom: 1.4em; }
h2 { font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: #8e8e93;
     margin: 1.4em 0 .5em; }
.card { border: 1px solid #e3e3e8; border-left: 3px solid #b3261e; border-radius: 8px;
        padding: 10px 13px; margin: .45em 0; }
.card.discuss { border-left-color: #0a84ff; }
.card .meta { font-size: .72rem; color: #8e8e93; margin-bottom: .15em; }
.card .id { font-variant-numeric: tabular-nums; font-weight: 600; color: #636366; }
.parked .card, .resolved .card { opacity: .5; border-left-color: #c7c7cc; }
.empty { color: #8e8e93; font-style: italic; }
@media (prefers-color-scheme: dark) {
  body { color: #e3e3e8; background: #1c1c1e; }
  .card { border-color: #3a3a3c; }
}
</style></head><body>
<h1>⚠ Needs you</h1><div class='stamp' id='stamp'>—</div>
<div id='root'></div>
<script>
const POLL = %d;
function card(e){
  return `<div class="card ${e.kind}"><div class="meta"><span class="id">${e.id}</span>
    · ${e.dept} · ${e.kind}</div><div>${esc(e.text)}</div></div>`;
}
function esc(s){return (s||"").replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function section(title, items){
  if(!items.length) return "";
  return `<h2>${title}</h2>` + items.map(card).join("");
}
async function tick(){
  try{
    const r = await fetch('/state.json', {cache:'no-store'});
    const s = await r.json();
    const es = s.entries || [];
    const open = es.filter(e=>e.status==='open');
    const parked = es.filter(e=>e.status==='parked');
    const root = document.getElementById('root');
    let h = "";
    h += open.length ? section('Open', open)
                     : "<p class='empty'>Nothing waiting on you. 🎉</p>";
    if(parked.length) h += `<div class='parked'>${section('Parked', parked)}</div>`;
    root.innerHTML = h;
    document.getElementById('stamp').textContent =
      open.length + " open · updated " + new Date().toLocaleTimeString();
  }catch(e){ /* server reaped or restarting; keep last view */ }
}
tick(); setInterval(tick, POLL);
</script></body></html>""" % POLL_MS

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
                body = json.dumps(load_store(store_path)).encode("utf-8")
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

def _surface(root):
    if _SKIP_SERVER:
        return 0
    port = ensure_server(root)
    open_url(board_url(port))
    return port

def board_add(root, dept, kind, text):
    p = _store_path(root)
    store = load_store(p)
    e, _created = add_entry(store, dept, kind, text, _now())
    save_store(p, store)
    _surface(root)
    return e

def board_resolve_dept(root, dept):
    p = _store_path(root)
    store = load_store(p)
    e, opens = resolve_by_dept(store, dept, _now())
    save_store(p, store)
    return e, opens

def board_done(root, eid):
    p = _store_path(root)
    store = load_store(p)
    e = set_status(store, eid, "resolved", _now())
    save_store(p, store)
    return e

def board_park(root, eid):
    p = _store_path(root)
    store = load_store(p)
    e = set_status(store, eid, "parked", _now())
    save_store(p, store)
    return e

def board_reopen(root, eid):
    p = _store_path(root)
    store = load_store(p)
    e = set_status(store, eid, "open", _now())
    save_store(p, store)
    return e

def board_get(root, eid):
    return get_entry(load_store(_store_path(root)), eid)

def board_list(root, dept=None):
    return list_entries(load_store(_store_path(root)), dept)

def board_open(root):
    return _surface(root)

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
                      _opt(argv, "--kind", "needs"), _opt(argv, "--text", ""))
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 skills/orchestrate/scripts/test_board.py -v`
Expected: PASS — `StoreCore` + `MarkerParse` + `Runtime` all OK.

- [ ] **Step 5: Manual smoke test the live panel**

Run from a project that has `.claude/orchestrate.json` (or `mkdir -p .claude && echo '{"active":true}' > .claude/orchestrate.json` in a scratch dir first):

```bash
python3 skills/orchestrate/scripts/board.py add --dept QA --kind needs --text "Postgres or SQLite for the job queue?"
python3 skills/orchestrate/scripts/board.py add --dept RnD --kind needs --text "Bump Node to 22?"
python3 skills/orchestrate/scripts/board.py list
```

Expected: a browser tab opens at `http://127.0.0.1:<port>/` showing two Open cards (QA-1, RnD-1) that refresh on their own. `list` prints both. Then:

```bash
python3 skills/orchestrate/scripts/board.py done QA-1   # card clears from the panel within ~1.5s
python3 skills/orchestrate/scripts/board.py stop        # stop the server
```

- [ ] **Step 6: Commit**

```bash
git add skills/orchestrate/scripts/board.py skills/orchestrate/scripts/test_board.py
git commit -m "feat(board): singleton server, self-polling panel, CLI"
```

---

### Task 4: `bin/orchestrate-board` launcher

**Files:**
- Create: `bin/orchestrate-board`

**Interfaces:**
- Consumes: `skills/orchestrate/scripts/board.py` (`main`).
- Produces: a PATH-exposed `orchestrate-board` command forwarding all args to `board.py`.

- [ ] **Step 1: Write the launcher**

Create `bin/orchestrate-board` (mirrors `bin/orchestrate-brief`):

```bash
#!/usr/bin/env bash
# orchestrate-board — the Boss Board: a live "Needs-You" panel of pending asks.
# Exposed on PATH via the plugin's bin/ dir, so any pane calls it by bare name:
#   orchestrate-board add --dept QA --kind needs --text "Postgres or SQLite?"
#   orchestrate-board done QA-1
# Resolves board.py relative to ITS OWN location — works from any cwd. Passes
# all args through.
here="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$here/../skills/orchestrate/scripts/board.py" "$@"
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x bin/orchestrate-board`

- [ ] **Step 3: Smoke test via the launcher**

Run (in a dir with an active marker):

```bash
./bin/orchestrate-board add --dept QA --kind needs --text "launcher works?"
./bin/orchestrate-board list
./bin/orchestrate-board stop
```

Expected: prints `QA-1`, lists it, panel opens; matches the direct-`python3` behaviour.

- [ ] **Step 4: Commit**

```bash
git add bin/orchestrate-board
git commit -m "feat(board): orchestrate-board PATH launcher"
```

---

### Task 5: Stop / SubagentStop hook + registration

**Files:**
- Create: `hooks/stop_boss_board.py`
- Modify: `hooks/hooks.json` (add `Stop` + `SubagentStop` blocks)
- Test: `skills/orchestrate/scripts/test_board.py` (append `HookFlow` case that drives the hook end-to-end)

**Interfaces:**
- Consumes: `board.py` (`project_root`, `parse_markers`, `board_add`, `board_resolve_dept`, `board_done`, `load_store`, `STORE_REL`).
- Produces: a hook that reads `{transcript_path, cwd}` on stdin, extracts the last assistant message text, and applies any markers. Fail-open; only acts under an active `.claude/orchestrate.json`.

> **Note on the transcript schema:** Claude Code passes `transcript_path` (a JSONL file). The reader below is defensive — it scans lines from the end for the last object that looks like an assistant message and concatenates its text. During this task, eyeball one real transcript line (`tail -1` of a live `transcript_path`) and confirm the `last_assistant_text` extraction matches; adjust the field access if the shape differs. The logic ("apply markers from the last assistant message") does not change.

- [ ] **Step 1: Write the failing test**

Append to `skills/orchestrate/scripts/test_board.py`:

```python
class HookFlow(unittest.TestCase):
    def _run_hook(self, root, transcript_text):
        import subprocess, json as _json
        tpath = os.path.join(root, "transcript.jsonl")
        with open(tpath, "w", encoding="utf-8") as f:
            f.write(_json.dumps({"type": "assistant",
                                 "message": {"role": "assistant",
                                             "content": [{"type": "text", "text": transcript_text}]}}) + "\n")
        hook = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))), "hooks", "stop_boss_board.py")
        env = dict(os.environ, BOSS_BOARD_SKIP_SERVER="1")
        subprocess.run([sys.executable, hook], input=_json.dumps({"transcript_path": tpath, "cwd": root}),
                       text=True, env=env, timeout=20)

    def test_raise_marker_adds_open_entry(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
            self._run_hook(d, "Working on it.\n@BOSS[QA]: Postgres or SQLite?")
            store = board.load_store(os.path.join(d, board.STORE_REL))
            self.assertEqual(len(store["entries"]), 1)
            self.assertEqual(store["entries"][0]["dept"], "QA")
            self.assertEqual(store["entries"][0]["status"], "open")

    def test_done_marker_resolves(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
            self._run_hook(d, "@BOSS[QA]: ask?")
            self._run_hook(d, "Thanks, done.\n@BOSS-DONE[QA]")
            store = board.load_store(os.path.join(d, board.STORE_REL))
            self.assertEqual(store["entries"][0]["status"], "resolved")

    def test_inactive_marker_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            # no .claude/orchestrate.json -> hook must do nothing
            self._run_hook(d, "@BOSS[QA]: ignored?")
            self.assertFalse(os.path.exists(os.path.join(d, board.STORE_REL)))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 skills/orchestrate/scripts/test_board.py -v`
Expected: FAIL — hook file does not exist, so `subprocess.run` can't launch it and the store assertions fail.

- [ ] **Step 3: Write the hook**

Create `hooks/stop_boss_board.py`:

```python
#!/usr/bin/env python3
"""Stop / SubagentStop hook — when a pane's turn ends, scan its last assistant
message for Boss-Board markers and apply them: `@BOSS[<dept>]: <ask>` raises an
ask; `@BOSS-DONE[<dept>]` / `@BOSS-DONE[<id>]` resolves one. The model writes one
cheap line of intent; this hook does the board mechanics (single-sourced in
board.py). Fail-open: any error -> no-op. Acts only inside an active
.claude/orchestrate.json project. Never blocks a turn (always exit 0)."""
import sys, os, json

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "skills", "orchestrate", "scripts")
sys.path.insert(0, SCRIPTS)
try:
    import board
except Exception:
    board = None


def find_root(start):
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


def last_assistant_text(transcript_path):
    """Defensive: scan JSONL from the end for the last assistant message; return
    its concatenated text. Tolerates content as a string or a list of blocks."""
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
        if msg.get("role") != "assistant" and obj.get("type") != "assistant":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            if parts:
                return "\n".join(parts)
    return ""


def main():
    if board is None:
        return
    if os.environ.get("BOSS_BOARD_SKIP_SERVER"):
        board._SKIP_SERVER = True
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    root = find_root(data.get("cwd") or os.getcwd())
    if not root:
        return
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
    except Exception:
        return
    if not cfg.get("active"):
        return
    text = last_assistant_text(data.get("transcript_path", ""))
    if not text:
        return
    markers = board.parse_markers(text)
    for dept, ask in markers["raises"]:
        try:
            board.board_add(root, dept, "needs", ask)
        except Exception:
            pass
    for token in markers["dones"]:
        try:
            if "-" in token and board.board_get(root, token):
                board.board_done(root, token)
            else:
                board.board_resolve_dept(root, token)
        except Exception:
            pass


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 skills/orchestrate/scripts/test_board.py -v`
Expected: PASS — `HookFlow` cases OK (entry added; resolved; inactive no-op).

- [ ] **Step 5: Register the hook in `hooks.json`**

Modify `hooks/hooks.json` — add two top-level keys inside `"hooks"` (alongside `SessionStart`, `PreToolUse`, `PostToolUse`):

```json
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}\"/hooks/stop_boss_board.py" }
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}\"/hooks/stop_boss_board.py" }
        ]
      }
    ]
```

- [ ] **Step 6: Validate `hooks.json` is well-formed**

Run: `python3 -c "import json; json.load(open('hooks/hooks.json')); print('hooks.json OK')"`
Expected: `hooks.json OK`

- [ ] **Step 7: Commit**

```bash
git add hooks/stop_boss_board.py hooks/hooks.json skills/orchestrate/scripts/test_board.py
git commit -m "feat(board): Stop/SubagentStop hook captures @BOSS markers"
```

---

### Task 6: `/board` slash command

**Files:**
- Create: `commands/board.md`

**Interfaces:**
- Consumes: `orchestrate-board` (PATH launcher).
- Produces: a `/board` command available in any pane.

- [ ] **Step 1: Write the command**

Create `commands/board.md` (mirrors the style of `commands/brief.md`):

```markdown
---
description: Open the Boss Board (live "needs-you" panel), or add/resolve one of your own items.
---

The **Boss Board** is your live panel of every pending ask for you across panes. Run the matching command from `$ARGUMENTS`:

- **no args** → just surface the panel:
  `orchestrate-board open`
- **plain text** (a thing you want to raise/discuss) → add it as your own item and open the panel:
  `orchestrate-board add --dept Boss --kind discuss --text "<the text>"`
- **`done <id>` / `park <id>` / `reopen <id>`** → change an item's status:
  `orchestrate-board <done|park|reopen> <id>`
- **`list`** → print the current items in this pane (no panel needed):
  `orchestrate-board list`

Panes raise their own asks automatically with `@BOSS[<dept>]: <ask>` (a Stop hook captures them) and resolve with `@BOSS-DONE[<dept>]` — you don't run those; this command is for *your* side.

$ARGUMENTS
```

- [ ] **Step 2: Verify front-matter + body render**

Run: `python3 -c "import sys; t=open('commands/board.md').read(); assert t.startswith('---') and 'orchestrate-board' in t; print('board.md OK')"`
Expected: `board.md OK`

- [ ] **Step 3: Commit**

```bash
git add commands/board.md
git commit -m "feat(board): /board slash command for the Boss side"
```

---

### Task 7: Wiring + docs (gitignore, dept template, reference, SKILL.md)

**Files:**
- Modify: `.gitignore` (ignore the runtime store)
- Modify: `skills/orchestrate/templates/department.md:60` (add the marker convention to "Boss direct access")
- Create: `skills/orchestrate/reference/boss-board.md`
- Modify: `skills/orchestrate/SKILL.md` (§4 pointer + References line)

**Interfaces:**
- Consumes: everything above.
- Produces: documentation + the gitignore rule. No code.

- [ ] **Step 1: Gitignore the runtime store**

Append to `.gitignore`:

```
# clock-in Boss Board — runtime state, not a product doc
.claude/boss-board.json
```

- [ ] **Step 2: Teach depts the marker (one line in the template)**

In `skills/orchestrate/templates/department.md`, append to the **Boss direct access** section (after line 60):

```markdown

**Flag the Boss when you need them (Boss Board):** when — and only when — you need the Boss's input, end your turn with `@BOSS[<your-handle>]: <one-line ask>` (a hook surfaces it on the Boss's live panel). Once the Boss has answered and you've acted, end with `@BOSS-DONE[<your-handle>]`. **Raise each ask once** — repeats are ignored; don't re-flag every idle turn.
```

- [ ] **Step 3: Write the reference page**

Create `skills/orchestrate/reference/boss-board.md`:

```markdown
# Boss Board — `scripts/board.py`

> A live **"Needs-You" panel**: every pending ask *for the Boss*, across all panes, in one always-open window. Separate from `TaskBoard.md` (dept work) — it does not touch the task system or its gates. Design: `docs/superpowers/specs/2026-06-30-boss-board-design.md`.

## What it is
The Boss works solo and multi-pane; the one message that needs the Boss gets buried. The Boss Board surfaces those asks into a single self-refreshing panel on the Boss's laptop. Mostly mechanical — the model writes a one-line marker; a Stop hook does the panel work.

## How an ask is raised / resolved
- **A pane needs the Boss:** end the turn with `@BOSS[<dept>]: <one-line ask>`. The `Stop`/`SubagentStop` hook (`hooks/stop_boss_board.py`) captures it → `orchestrate-board add`. The panel opens (or refreshes) on the Boss's screen.
- **The Boss answered, pane moves on:** end with `@BOSS-DONE[<dept>]` (its one open ask) or `@BOSS-DONE[<id>]` (a specific one).
- **The Boss's own items:** the `/board` command — `/board <text>` adds a discuss item; bare `/board` opens the panel; `/board park <id>` / `done <id>` / `reopen <id>` change status.

## States & ownership
`open → resolved`, plus `parked`. Panes drive open→resolved; the **Boss** owns park/reopen. The panel is read-only display.

## Anti-spam & token-saving
- `add` is **idempotent per (dept, normalised text)** while open — a pane re-flagging every idle turn never piles up duplicates.
- Ids are dept-prefixed (`QA-1`); `orchestrate-board get <id>` and `list --dept <dept>` read only what's needed, so a pane never parses the whole board.

## The panel
A singleton localhost server (port derived from the project path; pidfile = "is it up"). The page polls every ~1.5 s and re-renders. It **self-reaps** when there are no open items and it hasn't been polled for ~10 min; the next `add` respawns it. Stdlib only; degrades to no-op if a browser can't open.

## CLI (the launcher is `orchestrate-board`, on PATH)
`add --dept <h> --kind <needs|discuss> --text "…"` · `done <id>` · `resolve --dept <h>` · `park <id>` · `reopen <id>` · `get <id>` · `list [--dept <h>]` · `open` · `stop`.
```

- [ ] **Step 4: Point SKILL.md §4 at it (≈2 lines)**

In `skills/orchestrate/SKILL.md` §4, immediately after the **Morning brief (overnight runs)** paragraph, add:

```markdown

**Boss Board (live "needs-you" panel)** — a single always-open panel aggregating every pending ask *for the Boss* across panes, separate from `TaskBoard.md`. A pane flags with `@BOSS[<dept>]: <ask>` (a Stop hook surfaces it) and clears with `@BOSS-DONE[<dept>]`; the Boss uses `/board [text|done <id>|park <id>]`. Detail → `reference/boss-board.md`.
```

Then extend the **References** line at the bottom of SKILL.md by appending:

` · reference/boss-board.md (Boss Board) · scripts/board.py (Boss Board panel)`

- [ ] **Step 5: Verify the docs reference real things**

Run:
```bash
python3 -c "import os; assert os.path.exists('skills/orchestrate/reference/boss-board.md'); print('reference OK')"
grep -q "boss-board.json" .gitignore && echo "gitignore OK"
grep -q "@BOSS\[" skills/orchestrate/templates/department.md && echo "template OK"
grep -q "Boss Board" skills/orchestrate/SKILL.md && echo "skill OK"
```
Expected: `reference OK`, `gitignore OK`, `template OK`, `skill OK`.

- [ ] **Step 6: Full test run + no-side-effects check**

Run:
```bash
python3 skills/orchestrate/scripts/test_board.py -v
git status --porcelain docs/TaskBoard.md docs/BACKLOG.md docs/reviews 2>/dev/null
```
Expected: all tests PASS; the second command prints nothing (the Boss Board never touched dept files).

- [ ] **Step 7: Commit**

```bash
git add .gitignore skills/orchestrate/templates/department.md skills/orchestrate/reference/boss-board.md skills/orchestrate/SKILL.md
git commit -m "docs(board): gitignore, dept marker convention, reference, SKILL.md pointer"
```

---

## Self-Review

**Spec coverage**
- §3 panel (singleton, self-refresh, self-reap, ~15-20 MB) → Task 3 (`serve`, `reaper`, port logic). ✓
- §4 states + who-edits (panes open→resolved; Boss park/reopen; read-only) → Tasks 1, 3, 6. ✓
- §5 store at `.claude/boss-board.json` gitignored; entry shape; dept-prefixed ids → Tasks 1, 7. ✓
- §6.1 CLI verbs incl. ambiguous-resolve notice → Task 3 `main()` / `board_resolve_dept`. ✓
- §6.2 launcher → Task 4. ✓
- §6.3 Stop hook, fail-open, active-marker gate, calls board.py → Task 5. ✓
- §6.4 `/board` → Task 6. ✓
- §6.5 dept template line, reference, SKILL.md ≈2 lines → Task 7. ✓
- §7 marker protocol → Task 2 (`parse_markers`) + Task 5 (apply). ✓
- §8.1 idempotent add → Task 1 (`find_open_dup`/`add_entry`), tested. ✓
- §8.2 targeted reads (`get`, `list --dept`) → Tasks 1, 3. ✓
- §8.3 port derivation + upward probe → Task 3 (`derive_port`/`pick_port`). ✓
- §8.4 server lifecycle (detect/open/refresh, self-reap, cross-platform open) → Task 3. ✓
- §9 no coupling → enforced by construction; verified in Task 7 Step 6. ✓
- §10 verification items → covered by `test_board.py` + the smoke tests in Tasks 3-4.

**Placeholder scan:** none — all steps carry real code/commands. The one schema note in Task 5 is a verify-against-reality instruction, not missing logic (a defensive reader is provided).

**Type consistency:** `add_entry` returns `(entry, created)` everywhere; `resolve_by_dept` returns `(entry|None, opens)` used consistently in `main()` and the hook; `_SKIP_SERVER` / `BOSS_BOARD_SKIP_SERVER` honoured in `board_add`→`_surface` and set by both the `Runtime` test and the hook; ids are `"<dept>-<n>"` throughout; store path constant `STORE_REL` shared by board + hook + tests.
