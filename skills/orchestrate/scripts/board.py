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
    """Return (port, started) — `started` True only when THIS call spawned the server
    (so the caller can open the browser once, not on every ask)."""
    port = server_info(root)
    if port:
        return port, False
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
.parked .card { opacity: .5; border-left-color: #c7c7cc; }
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
