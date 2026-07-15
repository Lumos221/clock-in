# Canonical Answers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A mechanically-maintained `docs/CANON.md` registry of current canonical answers — owning depts register via a `@CANON` marker caught by a Stop hook, peers look up by topic instead of guessing filenames, and dependents are flagged when an answer changes.

**Architecture:** A single stdlib-only Python script (`canon.py`) owns a committed markdown-table registry (`docs/CANON.md`): pure table/marker functions, plus I/O command wrappers (git-sha stamping, archive-on-path-change) and a CLI. A `bin/orchestrate-canon` launcher puts it on PATH. A fail-open `Stop`/`SubagentStop` hook turns `@CANON[..]` / `@CANON-ACK[..]` markers into registry mutations. Docs/templates wire the convention into the founder-mode workflow. Mirrors the Boss Board spine; touches nothing in the task system or Boss Board.

**Tech Stack:** Python 3 standard library only (`re`, `subprocess`, `os`, `datetime`). Tests use stdlib `unittest`. Bash launcher. Markdown for the registry + docs.

## Global Constraints

- **Zero third-party dependencies** — Python standard library only (matches `brief.py` / `board.py` / `log.py`).
- **Tests use `unittest`** (stdlib), run via `python3 skills/orchestrate/scripts/test_canon.py -v` — do NOT introduce pytest.
- **Registry file:** `<project-root>/docs/CANON.md` — committed, machine-maintained markdown; project-root = nearest ancestor with `.claude/orchestrate.json`, else cwd. Auto-created on first `set` (like `BACKLOG.md`).
- **Columns (fixed order):** `topic · dept · file · version · updated · affects · needs-recheck`. Pointer-only — no answer summary.
- **v1 indexes canonical FILES only.** The `file` column holds a dept file path. DECISIONS.md integration is parked (non-goal).
- **Markers (exact):** register `@CANON[<dept>] <topic> → <path> (affects: a,b)` (arrow `→` or `->`; `(affects: …)` optional); ack `@CANON-ACK[<dept>] <topic>`. Authored by the dept; executed by the hook.
- **Auto-register as current** (L2 already vetted the output); no proposed/confirmed gate. CEO can correct via the CLI.
- **Change-detection:** a real change = `file` path differs OR `version` (git sha) differs. Only a real change re-flags `needs-recheck`; identical re-emit is a no-op.
- **Archive-on-path-change:** when `set` re-points to a *different* path, move the old file to `<its dir>/archive/`. `supersede` removes the row + archives its file.
- **Hooks fail-open:** any error / missing marker / inactive `.claude/orchestrate.json` → no-op, never block a turn (match `stop_boss_board.py`).
- **No coupling:** do not touch `TaskBoard.md`, the platform task system, the task hooks, or the Boss Board.

---

### Task 1: Registry table model (pure) + tests

**Files:**
- Create: `skills/orchestrate/scripts/canon.py`
- Test: `skills/orchestrate/scripts/test_canon.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `parse_cell_list(s: str) -> list[str]`, `fmt_list(lst: list) -> str`
  - `find_row(rows, topic) -> dict | None`
  - `apply_set(rows, dept, topic, file, version, affects, now) -> dict` → `{"action": "created"|"changed"|"unchanged", "old_file": str|None}`
  - `apply_ack(rows, topic, dept) -> bool`
  - `apply_supersede(rows, topic) -> dict | None`
  - `get_file(rows, topic) -> str | None`
  - `list_rows(rows, dept=None) -> list[dict]`
  - `load_rows(path) -> list[dict]`, `save_rows(path, rows, project) -> None`, `render(rows, project) -> str`
  - Row dict keys: `topic, dept, file, version, updated, affects(list), needs_recheck(list)`.

- [ ] **Step 1: Write the failing test**

Create `skills/orchestrate/scripts/test_canon.py`:

```python
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import canon

NOW = "2026-07-01"


class TableModel(unittest.TestCase):
    def test_set_creates_row_and_flags_affects(self):
        rows = []
        res = canon.apply_set(rows, "Fin", "pricing-tier", "docs/财务/pricing-tier.md",
                              "a7643d1", ["Marketing"], NOW)
        self.assertEqual(res["action"], "created")
        self.assertIsNone(res["old_file"])
        r = canon.find_row(rows, "pricing-tier")
        self.assertEqual(r["dept"], "Fin")
        self.assertEqual(r["needs_recheck"], ["Marketing"])

    def test_reemit_identical_is_noop(self):
        rows = []
        canon.apply_set(rows, "Fin", "pricing-tier", "f.md", "v1", ["Marketing"], NOW)
        canon.apply_ack(rows, "pricing-tier", "Marketing")          # clear the flag
        res = canon.apply_set(rows, "Fin", "pricing-tier", "f.md", "v1", ["Marketing"], NOW)
        self.assertEqual(res["action"], "unchanged")
        self.assertEqual(canon.find_row(rows, "pricing-tier")["needs_recheck"], [])  # not re-flagged

    def test_real_change_reflags_and_reports_old_file_on_path_change(self):
        rows = []
        canon.apply_set(rows, "Fin", "pricing-tier", "old.md", "v1", ["Marketing"], NOW)
        canon.apply_ack(rows, "pricing-tier", "Marketing")
        res = canon.apply_set(rows, "Fin", "pricing-tier", "new.md", "v2", ["Marketing"], NOW)
        self.assertEqual(res["action"], "changed")
        self.assertEqual(res["old_file"], "old.md")
        self.assertEqual(canon.find_row(rows, "pricing-tier")["needs_recheck"], ["Marketing"])
        self.assertEqual(canon.find_row(rows, "pricing-tier")["file"], "new.md")

    def test_version_change_same_path_is_a_change_no_archive(self):
        rows = []
        canon.apply_set(rows, "Fin", "pricing-tier", "f.md", "v1", [], NOW)
        res = canon.apply_set(rows, "Fin", "pricing-tier", "f.md", "v2", [], NOW)
        self.assertEqual(res["action"], "changed")
        self.assertIsNone(res["old_file"])     # same path -> nothing to archive

    def test_ack_supersede_get_list(self):
        rows = []
        canon.apply_set(rows, "Fin", "pricing-tier", "f.md", "v1", ["Marketing"], NOW)
        canon.apply_set(rows, "Legal", "redline", "r.md", "v1", [], NOW)
        self.assertTrue(canon.apply_ack(rows, "pricing-tier", "Marketing"))
        self.assertFalse(canon.apply_ack(rows, "nope", "X"))
        self.assertEqual(canon.get_file(rows, "redline"), "r.md")
        self.assertEqual([r["topic"] for r in canon.list_rows(rows, "Fin")], ["pricing-tier"])
        gone = canon.apply_supersede(rows, "redline")
        self.assertEqual(gone["file"], "r.md")
        self.assertIsNone(canon.find_row(rows, "redline"))

    def test_save_load_roundtrip_with_unicode_and_lists(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "docs", "CANON.md")
            rows = []
            canon.apply_set(rows, "Fin", "pricing-tier", "docs/财务/pricing-tier.md",
                            "a7643d1", ["Marketing", "Docs"], NOW)
            canon.save_rows(p, rows, "demo")
            back = canon.load_rows(p)
            self.assertEqual(len(back), 1)
            self.assertEqual(back[0]["file"], "docs/财务/pricing-tier.md")
            self.assertEqual(back[0]["affects"], ["Marketing", "Docs"])
            self.assertEqual(back[0]["needs_recheck"], ["Marketing", "Docs"])

    def test_render_shows_needs_recheck_block(self):
        rows = []
        canon.apply_set(rows, "Fin", "pricing-tier", "f.md", "v1", ["Marketing"], NOW)
        out = canon.render(rows, "demo")
        self.assertIn("## ⚠ Needs re-check", out)
        self.assertIn("`pricing-tier` → Marketing", out)
        self.assertIn("| pricing-tier | Fin |", out)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 skills/orchestrate/scripts/test_canon.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'canon'`.

- [ ] **Step 3: Write minimal implementation**

Create `skills/orchestrate/scripts/canon.py`:

```python
#!/usr/bin/env python3
"""Canonical Answers — a machine-maintained registry (docs/CANON.md) of the current
authoritative file per answered question. Owning depts register via a `@CANON[..]`
marker (a Stop hook applies it); peers look up by topic instead of guessing filenames;
dependents are flagged when an answer changes. Stdlib only; degrades, never hard-fails.
See docs/design/specs/2026-06-30-canonical-answers-design.md."""
import sys, os, re, subprocess
from datetime import datetime

COLS = ["topic", "dept", "file", "version", "updated", "affects", "needs-recheck"]
CANON_REL = os.path.join("docs", "CANON.md")

HEADER = (
    "# %s · CANON — canonical answers (read-first · machine-maintained · do not hand-edit)\n\n"
    "> Each row = the current authoritative file for one answered question.\n"
    "> Register via `@CANON[<dept>] <topic> -> <path> (affects: …)`; the CEO may correct via `orchestrate-canon`.\n"
    "> Use a cross-domain fact: `orchestrate-canon get <topic>` -> read the named file. **Never browse a peer's folder.**\n\n"
    "## ⚠ Needs re-check\n")


# ---------------------------------------------------------------- cell helpers
def parse_cell_list(s):
    s = (s or "").strip()
    if s in ("", "—", "-"):
        return []
    return [p.strip() for p in s.split(",") if p.strip() and p.strip() not in ("—", "-")]


def fmt_list(lst):
    return ", ".join(lst) if lst else "—"


# ---------------------------------------------------------------- table model
def find_row(rows, topic):
    for r in rows:
        if r["topic"] == topic:
            return r
    return None


def apply_set(rows, dept, topic, file, version, affects, now):
    row = find_row(rows, topic)
    if row is None:
        rows.append({"topic": topic, "dept": dept, "file": file, "version": version,
                     "updated": now, "affects": list(affects), "needs_recheck": list(affects)})
        return {"action": "created", "old_file": None}
    real_change = (row["file"] != file) or (row["version"] != version)
    if not real_change:
        return {"action": "unchanged", "old_file": None}
    old_file = row["file"] if row["file"] != file else None
    row["dept"] = dept
    if affects:
        row["affects"] = list(affects)
    row["needs_recheck"] = sorted(set(row["needs_recheck"]) | set(row["affects"]))
    row["file"] = file
    row["version"] = version
    row["updated"] = now
    return {"action": "changed", "old_file": old_file}


def apply_ack(rows, topic, dept):
    r = find_row(rows, topic)
    if r is None:
        return False
    r["needs_recheck"] = [d for d in r["needs_recheck"] if d != dept]
    return True


def apply_supersede(rows, topic):
    r = find_row(rows, topic)
    if r is None:
        return None
    rows.remove(r)
    return r


def get_file(rows, topic):
    r = find_row(rows, topic)
    return r["file"] if r else None


def list_rows(rows, dept=None):
    return [r for r in rows if dept is None or r["dept"] == dept]


# ---------------------------------------------------------------- load / render / save
def load_rows(path):
    rows = []
    try:
        text = open(path, encoding="utf-8").read()
    except Exception:
        return rows
    in_table = False
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            in_table = False
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if cells and cells[0] == "topic":          # header row
            in_table = True
            continue
        if set("".join(cells)) <= set("-: "):       # separator row
            continue
        if not in_table or len(cells) < 7:
            continue
        rows.append({"topic": cells[0], "dept": cells[1], "file": cells[2],
                     "version": cells[3], "updated": cells[4],
                     "affects": parse_cell_list(cells[5]),
                     "needs_recheck": parse_cell_list(cells[6])})
    return rows


def render(rows, project):
    flagged = [r for r in rows if r["needs_recheck"]]
    recheck = "\n".join("- `%s` → %s (updated %s)" % (r["topic"], ", ".join(r["needs_recheck"]), r["updated"])
                        for r in flagged) or "- none"
    body = ["| %s |" % " | ".join(COLS), "|%s|" % "|".join(["---"] * len(COLS))]
    for r in rows:
        body.append("| %s |" % " | ".join([
            r["topic"], r["dept"], r["file"], r["version"], r["updated"],
            fmt_list(r["affects"]), fmt_list(r["needs_recheck"])]))
    return (HEADER % project) + recheck + "\n\n## Registry\n" + "\n".join(body) + "\n"


def save_rows(path, rows, project):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(render(rows, project))
    os.replace(tmp, path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 skills/orchestrate/scripts/test_canon.py -v`
Expected: PASS — all 7 `TableModel` tests OK.

- [ ] **Step 5: Commit**

```bash
git add skills/orchestrate/scripts/canon.py skills/orchestrate/scripts/test_canon.py
git commit -m "feat(canon): registry table model — set/ack/supersede, change-detection, render"
```

---

### Task 2: Marker parser (pure) + tests

**Files:**
- Modify: `skills/orchestrate/scripts/canon.py` (append parser)
- Test: `skills/orchestrate/scripts/test_canon.py` (append `MarkerParse`)

**Interfaces:**
- Consumes: `parse_cell_list` (Task 1).
- Produces: `parse_canon_markers(text: str) -> dict` → `{"registers": [(dept, topic, file, affects_list)], "acks": [(dept, topic)]}`.

- [ ] **Step 1: Write the failing test**

Append to `skills/orchestrate/scripts/test_canon.py` (above the `if __name__` line):

```python
class MarkerParse(unittest.TestCase):
    def test_register_with_affects_and_unicode_path(self):
        out = canon.parse_canon_markers("ok\n@CANON[Fin] pricing-tier → docs/财务/pricing-tier.md (affects: Marketing, Docs)")
        self.assertEqual(out["registers"], [("Fin", "pricing-tier", "docs/财务/pricing-tier.md", ["Marketing", "Docs"])])
        self.assertEqual(out["acks"], [])

    def test_register_without_affects_and_ascii_arrow(self):
        out = canon.parse_canon_markers("@CANON[Legal] redline -> docs/合规/红线法律依据.md")
        self.assertEqual(out["registers"], [("Legal", "redline", "docs/合规/红线法律依据.md", [])])

    def test_ack_marker(self):
        out = canon.parse_canon_markers("done\n@CANON-ACK[Marketing] pricing-tier")
        self.assertEqual(out["acks"], [("Marketing", "pricing-tier")])
        self.assertEqual(out["registers"], [])

    def test_ack_is_not_parsed_as_register(self):
        out = canon.parse_canon_markers("@CANON-ACK[Marketing] pricing-tier")
        self.assertEqual(out["registers"], [])

    def test_no_marker(self):
        self.assertEqual(canon.parse_canon_markers("nothing here"), {"registers": [], "acks": []})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 skills/orchestrate/scripts/test_canon.py -v`
Expected: FAIL — `AttributeError: module 'canon' has no attribute 'parse_canon_markers'`.

- [ ] **Step 3: Write minimal implementation**

Append to `canon.py` after the cell helpers (the parser uses `parse_cell_list`):

```python
# ---------------------------------------------------------------- markers
CANON_ACK_RE = re.compile(r"@CANON-ACK\[([^\]\s]+)\]\s+(\S+)")
CANON_RE = re.compile(r"@CANON\[([^\]\s]+)\]\s+(\S+)\s*(?:→|->)\s*(\S+?)\s*(?:\(affects:\s*([^)]*)\))?\s*$")


def parse_canon_markers(text):
    registers, acks = [], []
    for line in (text or "").splitlines():
        m = CANON_ACK_RE.search(line)
        if m:
            acks.append((m.group(1), m.group(2)))
            continue
        m = CANON_RE.search(line)
        if m:
            registers.append((m.group(1), m.group(2), m.group(3), parse_cell_list(m.group(4))))
    return {"registers": registers, "acks": acks}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 skills/orchestrate/scripts/test_canon.py -v`
Expected: PASS — `TableModel` + `MarkerParse` all OK.

- [ ] **Step 5: Commit**

```bash
git add skills/orchestrate/scripts/canon.py skills/orchestrate/scripts/test_canon.py
git commit -m "feat(canon): @CANON / @CANON-ACK marker parser"
```

---

### Task 3: I/O command wrappers + CLI

**Files:**
- Modify: `skills/orchestrate/scripts/canon.py` (append root/git/archive/cmd/CLI)
- Test: `skills/orchestrate/scripts/test_canon.py` (append `Commands`)

**Interfaces:**
- Consumes: Task 1 model, Task 2 parser.
- Produces:
  - `project_root(start=None) -> str`, `canon_path(root) -> str`, `project_name(root) -> str`
  - `git_short_sha(root, file) -> str` (fail-soft `—`)
  - `archive_file(root, file) -> str | None` (move to `<dir>/archive/`)
  - `cmd_set(root, dept, topic, file, affects) -> dict`, `cmd_get(root, topic) -> str|None`, `cmd_list(root, dept=None) -> list`, `cmd_ack(root, topic, dept) -> bool`, `cmd_supersede(root, topic) -> dict|None`, `cmd_archive(root, file) -> str|None`
  - `main()`.

- [ ] **Step 1: Write the failing test**

Append to `skills/orchestrate/scripts/test_canon.py`:

```python
class Commands(unittest.TestCase):
    def _proj(self, d):
        os.makedirs(os.path.join(d, ".claude"))
        open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')

    def test_project_root_finds_marker(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            sub = os.path.join(d, "a"); os.makedirs(sub)
            self.assertEqual(os.path.realpath(canon.project_root(sub)), os.path.realpath(d))

    def test_set_persists_and_get_list(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            canon.cmd_set(d, "Fin", "pricing-tier", "docs/财务/pricing-tier.md", ["Marketing"])
            self.assertEqual(canon.cmd_get(d, "pricing-tier"), "docs/财务/pricing-tier.md")
            self.assertEqual([r["topic"] for r in canon.cmd_list(d, "Fin")], ["pricing-tier"])

    def test_set_repoint_archives_old_file(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            fin = os.path.join(d, "docs", "财务"); os.makedirs(fin)
            old = os.path.join(fin, "old.md"); open(old, "w").write("old")
            new = os.path.join(fin, "pricing-tier.md"); open(new, "w").write("new")
            canon.cmd_set(d, "Fin", "pricing-tier", "docs/财务/old.md", [])
            canon.cmd_set(d, "Fin", "pricing-tier", "docs/财务/pricing-tier.md", ["Marketing"])
            self.assertFalse(os.path.exists(old))                          # moved
            self.assertTrue(os.path.exists(os.path.join(fin, "archive", "old.md")))
            self.assertEqual(canon.cmd_get(d, "pricing-tier"), "docs/财务/pricing-tier.md")

    def test_ack_clears_flag(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            canon.cmd_set(d, "Fin", "pricing-tier", "f.md", ["Marketing"])
            self.assertTrue(canon.cmd_ack(d, "pricing-tier", "Marketing"))
            self.assertEqual(canon.cmd_list(d, "Fin")[0]["needs_recheck"], [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 skills/orchestrate/scripts/test_canon.py -v`
Expected: FAIL — `AttributeError: module 'canon' has no attribute 'project_root'`.

- [ ] **Step 3: Write minimal implementation**

Append to `canon.py` after the markers section:

```python
# ---------------------------------------------------------------- project root / IO
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
            return d
        cur = parent


def canon_path(root):
    return os.path.join(root, CANON_REL)


def project_name(root):
    return os.path.basename(os.path.abspath(root))


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def git_short_sha(root, file):
    for cmd in (["git", "-C", root, "log", "-1", "--format=%h", "--", file],
                ["git", "-C", root, "rev-parse", "--short", "HEAD"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            sha = out.stdout.strip()
            if sha:
                return sha
        except Exception:
            pass
    return "—"


def archive_file(root, file):
    src = file if os.path.isabs(file) else os.path.join(root, file)
    if not os.path.exists(src):
        return None
    arch = os.path.join(os.path.dirname(src), "archive")
    os.makedirs(arch, exist_ok=True)
    dst = os.path.join(arch, os.path.basename(src))
    os.replace(src, dst)
    return dst


# ---------------------------------------------------------------- command wrappers
def cmd_set(root, dept, topic, file, affects):
    p = canon_path(root)
    rows = load_rows(p)
    res = apply_set(rows, dept, topic, file, git_short_sha(root, file), affects, _today())
    if res["old_file"]:
        archive_file(root, res["old_file"])
    save_rows(p, rows, project_name(root))
    return res


def cmd_get(root, topic):
    return get_file(load_rows(canon_path(root)), topic)


def cmd_list(root, dept=None):
    return list_rows(load_rows(canon_path(root)), dept)


def cmd_ack(root, topic, dept):
    p = canon_path(root)
    rows = load_rows(p)
    ok = apply_ack(rows, topic, dept)
    save_rows(p, rows, project_name(root))
    return ok


def cmd_supersede(root, topic):
    p = canon_path(root)
    rows = load_rows(p)
    r = apply_supersede(rows, topic)
    if r:
        archive_file(root, r["file"])
    save_rows(p, rows, project_name(root))
    return r


def cmd_archive(root, file):
    return archive_file(root, file)


# ---------------------------------------------------------------- CLI
def _opt(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def main():
    argv = sys.argv[1:]
    cmd = argv[0] if argv else ""
    root = project_root()
    if cmd == "set":
        res = cmd_set(root, _opt(argv, "--dept", "?"), _opt(argv, "--topic", ""),
                      _opt(argv, "--file", ""), parse_cell_list(_opt(argv, "--affects", "")))
        print("%s %s" % (res["action"], _opt(argv, "--topic", "")))
    elif cmd == "get":
        f = cmd_get(root, argv[1] if len(argv) > 1 else "")
        print(f if f else "not found")
    elif cmd == "list":
        for r in cmd_list(root, _opt(argv, "--dept")):
            flag = (" ⚠ recheck: " + ", ".join(r["needs_recheck"])) if r["needs_recheck"] else ""
            print("%s [%s] %s%s" % (r["topic"], r["dept"], r["file"], flag))
    elif cmd == "ack":
        ok = cmd_ack(root, argv[1] if len(argv) > 1 else "", _opt(argv, "--dept", "?"))
        print("ack ok" if ok else "topic not found")
    elif cmd == "supersede":
        r = cmd_supersede(root, argv[1] if len(argv) > 1 else "")
        print(("superseded " + r["topic"]) if r else "topic not found")
    elif cmd == "archive":
        dst = cmd_archive(root, argv[1] if len(argv) > 1 else "")
        print(("archived → " + dst) if dst else "file not found")
    else:
        sys.stderr.write("usage: orchestrate-canon set|get|list|ack|supersede|archive\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 skills/orchestrate/scripts/test_canon.py -v`
Expected: PASS — `TableModel` + `MarkerParse` + `Commands` all OK.

- [ ] **Step 5: Manual smoke test the CLI**

In a scratch project dir (`mkdir -p /tmp/canon-smoke/.claude && echo '{"active":true}' > /tmp/canon-smoke/.claude/orchestrate.json && mkdir -p /tmp/canon-smoke/docs/财务 && echo x > /tmp/canon-smoke/docs/财务/pricing-tier.md`):

```bash
( cd /tmp/canon-smoke && python3 ~/Projects/clock-in/skills/orchestrate/scripts/canon.py set --dept Fin --topic pricing-tier --file docs/财务/pricing-tier.md --affects Marketing )
( cd /tmp/canon-smoke && python3 ~/Projects/clock-in/skills/orchestrate/scripts/canon.py get pricing-tier )
( cd /tmp/canon-smoke && python3 ~/Projects/clock-in/skills/orchestrate/scripts/canon.py list )
cat /tmp/canon-smoke/docs/CANON.md
```

Expected: `created pricing-tier`; `get` prints the path; `list` shows the row with `⚠ recheck: Marketing`; `CANON.md` has the header, the "⚠ Needs re-check" block, and the table.

- [ ] **Step 6: Commit**

```bash
git add skills/orchestrate/scripts/canon.py skills/orchestrate/scripts/test_canon.py
git commit -m "feat(canon): IO wrappers (git sha, archive-on-repoint) + CLI"
```

---

### Task 4: `bin/orchestrate-canon` launcher

**Files:**
- Create: `bin/orchestrate-canon`

**Interfaces:**
- Consumes: `skills/orchestrate/scripts/canon.py` (`main`).
- Produces: a PATH-exposed `orchestrate-canon` command.

- [ ] **Step 1: Write the launcher**

Create `bin/orchestrate-canon` (mirrors `bin/orchestrate-board`):

```bash
#!/usr/bin/env bash
# orchestrate-canon — the canonical-answers registry (docs/CANON.md).
# Exposed on PATH via the plugin's bin/ dir, so any pane calls it by bare name:
#   orchestrate-canon set --dept Fin --topic pricing-tier --file docs/财务/pricing-tier.md --affects Marketing
#   orchestrate-canon get pricing-tier
# Resolves canon.py relative to ITS OWN location — works from any cwd. Passes args through.
here="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$here/../skills/orchestrate/scripts/canon.py" "$@"
```

- [ ] **Step 2: Make it executable + smoke test**

```bash
chmod +x bin/orchestrate-canon
( cd /tmp/canon-smoke && ~/Projects/clock-in/bin/orchestrate-canon list )
```
Expected: prints the `pricing-tier` row — same as the direct-`python3` call.

- [ ] **Step 3: Commit**

```bash
git add bin/orchestrate-canon
git commit -m "feat(canon): orchestrate-canon PATH launcher"
```

---

### Task 5: Stop / SubagentStop hook + registration

**Files:**
- Create: `hooks/stop_canon.py`
- Modify: `hooks/hooks.json` (add `stop_canon.py` to the existing `Stop` + `SubagentStop` blocks)
- Test: `skills/orchestrate/scripts/test_canon.py` (append `HookFlow`)

**Interfaces:**
- Consumes: `canon.py` (`parse_canon_markers`, `cmd_set`, `cmd_ack`, `cmd_get`, `load_rows`, `canon_path`).
- Produces: a fail-open Stop hook that reads the last assistant message and applies markers; acts only under an active `.claude/orchestrate.json`.

> **Transcript schema note:** same defensive last-assistant-message reader as `stop_boss_board.py`. During this task, confirm extraction against one real `transcript_path` line if convenient; the logic ("apply markers from the last assistant message") does not change.

- [ ] **Step 1: Write the failing test**

Append to `skills/orchestrate/scripts/test_canon.py`:

```python
class HookFlow(unittest.TestCase):
    def _run_hook(self, root, text):
        import subprocess, json as _json
        tpath = os.path.join(root, "t.jsonl")
        with open(tpath, "w", encoding="utf-8") as f:
            f.write(_json.dumps({"type": "assistant", "message": {"role": "assistant",
                    "content": [{"type": "text", "text": text}]}}) + "\n")
        hook = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))), "hooks", "stop_canon.py")
        subprocess.run([sys.executable, hook],
                       input=_json.dumps({"transcript_path": tpath, "cwd": root}),
                       text=True, timeout=20)

    def test_register_marker_writes_row(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
            self._run_hook(d, "done\n@CANON[Fin] pricing-tier → docs/财务/pricing-tier.md (affects: Marketing)")
            self.assertEqual(canon.cmd_get(d, "pricing-tier"), "docs/财务/pricing-tier.md")

    def test_ack_marker_clears_flag(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
            self._run_hook(d, "@CANON[Fin] pricing-tier → f.md (affects: Marketing)")
            self._run_hook(d, "@CANON-ACK[Marketing] pricing-tier")
            self.assertEqual(canon.cmd_list(d)[0]["needs_recheck"], [])

    def test_inactive_project_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            self._run_hook(d, "@CANON[Fin] pricing-tier → f.md")
            self.assertFalse(os.path.exists(os.path.join(d, "docs", "CANON.md")))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 skills/orchestrate/scripts/test_canon.py -v`
Expected: FAIL — the hook file does not exist, so `cmd_get` returns `None` and the assertions fail.

- [ ] **Step 3: Write the hook**

Create `hooks/stop_canon.py`:

```python
#!/usr/bin/env python3
"""Stop / SubagentStop hook — when a pane's turn ends, scan its last assistant message
for canonical-answer markers and apply them: `@CANON[<dept>] <topic> → <path> (affects: …)`
registers/re-points the current canonical file; `@CANON-ACK[<dept>] <topic>` clears a
re-check flag. The dept writes one marker line; this hook does the registry mechanics
(single-sourced in canon.py), so the CEO relay is out of the critical path. Fail-open:
any error -> no-op. Acts only inside an active .claude/orchestrate.json project."""
import sys, os, json

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "skills", "orchestrate", "scripts")
sys.path.insert(0, SCRIPTS)
try:
    import canon
except Exception:
    canon = None


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
    if canon is None:
        return
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
    markers = canon.parse_canon_markers(text)
    for dept, topic, file, affects in markers["registers"]:
        try:
            canon.cmd_set(root, dept, topic, file, affects)
        except Exception:
            pass
    for dept, topic in markers["acks"]:
        try:
            canon.cmd_ack(root, topic, dept)
        except Exception:
            pass


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 skills/orchestrate/scripts/test_canon.py -v`
Expected: PASS — `HookFlow` cases OK.

- [ ] **Step 5: Register the hook in `hooks.json`**

In `hooks/hooks.json`, add the canon hook as a second entry inside BOTH the existing `Stop` and `SubagentStop` arrays (alongside `stop_boss_board.py`). Each array becomes:

```json
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}\"/hooks/stop_boss_board.py" }
        ]
      },
      {
        "hooks": [
          { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}\"/hooks/stop_canon.py" }
        ]
      }
    ],
```

Apply the identical second entry to the `SubagentStop` array.

- [ ] **Step 6: Validate `hooks.json`**

Run: `python3 -c "import json; d=json.load(open('hooks/hooks.json')); print('OK', [h['hooks'][0]['command'].split('/')[-1] for k in ('Stop','SubagentStop') for h in d['hooks'][k]])"`
Expected: `OK ['stop_boss_board.py', 'stop_canon.py', 'stop_boss_board.py', 'stop_canon.py']`

- [ ] **Step 7: Commit**

```bash
git add hooks/stop_canon.py hooks/hooks.json skills/orchestrate/scripts/test_canon.py
git commit -m "feat(canon): Stop/SubagentStop hook applies @CANON / @CANON-ACK markers"
```

---

### Task 6: Wiring + docs

**Files:**
- Modify: `skills/orchestrate/templates/department.md` (add cross-domain section)
- Modify: `skills/orchestrate/reference/departments.md:41,43-44` (off-limits list + canonical paragraph → registry)
- Create: `skills/orchestrate/reference/canon.md`
- Modify: `skills/orchestrate/skills`… `skills/orchestrate/SKILL.md` (Files table row + References line)
- Modify: `skills/orchestrate/templates/SoT.md` (Canonical files section → pointer)

**Interfaces:**
- Consumes: everything above. Produces: documentation only, no code.

- [ ] **Step 1: Teach depts the convention (template)**

In `skills/orchestrate/templates/department.md`, append a new section after the **Boss direct access** section:

```markdown

## Cross-domain facts (canonical answers)
**Read `docs/CANON.md` first** — the project's index of current binding answers across depts. Re-reading it each session is what stops you acting on pre-decision memory.
- **Need another domain's fact?** `orchestrate-canon get <topic>` → read the file it names. **Never browse a peer's `docs/<其领域>/` and guess a filename.**
- **Finalised an answer the project will act on?** end your turn with `@CANON[<your-handle>] <topic> → <path> (affects: <depts>)` — a hook registers it (no CEO relay to lose it). Register only cross-cutting *answers*, not drafts or rounds.
- **Your handle under ⚠ Needs re-check?** re-read the named file, then `@CANON-ACK[<your-handle>] <topic>`.
- **Answer files:** one stable, suffix-free name per question (`pricing-tier.md`, not `pricing-v2-核算.md`); superseding archives the old path under `archive/`.
```

- [ ] **Step 2: Point the departments.md canonical paragraph at the registry**

In `skills/orchestrate/reference/departments.md`, replace the **How it's set** sentence in the "Canonical file" paragraph (the `**How it's set:** the **dept proposes** … points `SoT.md` at it …` text, lines ~44) with:

```markdown
**How it's set (mechanical):** the owning dept registers the current file with `@CANON[<handle>] <topic> → <path> (affects: …)` — a Stop hook writes it to `docs/CANON.md` (the read-first registry; full detail in `reference/canon.md`). Auto-registers as current (the output already passed L2 审查); the CEO may correct via `orchestrate-canon`. Peers look it up with `orchestrate-canon get <topic>` and read the named file — they never browse a peer's folder. One stable file per question; superseding archives the old path.
```

Then add `docs/CANON.md` to the off-limits list on line 41 (after `docs/DECISIONS.md`): change `\`docs/DECISIONS.md\`,` to `\`docs/DECISIONS.md\`, \`docs/CANON.md\`,`.

- [ ] **Step 3: Write the reference page**

Create `skills/orchestrate/reference/canon.md`:

```markdown
# Canonical Answers — `scripts/canon.py`

> A machine-maintained registry of the **current authoritative file per answered question**: `docs/CANON.md`. Read-first by every dept; registered mechanically so the CEO relay can't drop a pointer. Separate from `DECISIONS.md` (full why-log, on-demand). Design: `docs/design/specs/2026-06-30-canonical-answers-design.md`.

## Why
A decision settled in one dept must reach the depts that act on it. `CANON.md` is the lean, read-first index of current binding answers — a dept that re-reads it each session can't carry pre-decision memory, and a peer needing a cross-domain fact looks it up by topic instead of guessing a filename.

## Register / look up / hand off
- **Register (owning dept):** end a turn with `@CANON[<dept>] <topic> → <path> (affects: <depts>)`. The `Stop`/`SubagentStop` hook (`hooks/stop_canon.py`) writes the row. Auto-registers as current (L2 already vetted the output). Register only cross-cutting *answers*, not drafts/rounds.
- **Look up (any dept):** `orchestrate-canon get <topic>` → the current file path; read that file. `CANON.md` is also in your read-first set. **Never browse a peer's `docs/<其领域>/`.**
- **Hand off on change:** when an answer changes, its `affects` depts are written into `needs-recheck` and surfaced under "⚠ Needs re-check". A flagged dept re-reads the file, then `@CANON-ACK[<dept>] <topic>` (or `orchestrate-canon ack <topic> --dept <dept>`).

## File convention
One **stable, suffix-free** file per question (`pricing-tier.md`, not `pricing-v2.md`) — bare name = current. Updates are in-place (git holds history). Re-pointing to a *different* path archives the old one under `<dir>/archive/`. The ASCII topic-key is decoupled from the filename (which may stay Chinese).

## Anti-bloat
One row per *question*, not per file/version — updates re-point the same row. Only an explicit `@CANON` registers (nothing sweeps a folder in). Only cross-cutting settled answers qualify. So `CANON.md` grows with distinct cross-cutting questions (small, stable), not file count.

## CLI (`orchestrate-canon`, on PATH)
`set --dept <h> --topic <k> --file <path> [--affects a,b]` · `get <topic>` · `list [--dept <h>]` · `ack <topic> --dept <h>` · `supersede <topic>` · `archive <path>`. The registry auto-creates on first `set`.
```

- [ ] **Step 4: Add the Files-table row + References line in SKILL.md**

In `skills/orchestrate/SKILL.md`, in the **Files** table, add a row after the `docs/DECISIONS.md` row:

```markdown
| `docs/CANON.md` | **canonical-answer registry** — current authoritative file per answered question (cross-domain lookup) | **`canon.py`** (auto, via `@CANON` hook) | read-first by depts (small) |
```

Then extend the References line at the bottom by appending before the final period:

` · `reference/canon.md` (canonical answers) · `scripts/canon.py` (canon registry)`

- [ ] **Step 5: Slim the SoT template**

In `skills/orchestrate/templates/SoT.md`, replace the `## Canonical files` section (the heading + its `<…>` note + the `- <What…> → …` line) with:

```markdown
## Canonical answers
→ `docs/CANON.md`  (machine-maintained registry — current file per answered question; **read-first**, don't duplicate its pointers here)
```

- [ ] **Step 6: Verify the wiring**

Run:
```bash
python3 -c "import os; assert os.path.exists('skills/orchestrate/reference/canon.md'); print('reference OK')"
grep -q "@CANON\[" skills/orchestrate/templates/department.md && echo "template OK"
grep -q "docs/CANON.md" skills/orchestrate/SKILL.md && echo "skill OK"
grep -q "Canonical answers" skills/orchestrate/templates/SoT.md && echo "sot OK"
grep -q "CANON.md" skills/orchestrate/reference/departments.md && echo "departments OK"
```
Expected: `reference OK`, `template OK`, `skill OK`, `sot OK`, `departments OK`.

- [ ] **Step 7: Full test run + no-side-effects check**

Run:
```bash
python3 skills/orchestrate/scripts/test_canon.py -v
python3 skills/orchestrate/scripts/test_board.py -v
git status --porcelain docs/TaskBoard.md docs/BACKLOG.md 2>/dev/null
```
Expected: both suites PASS; the third command prints nothing (canon touched no task files).

- [ ] **Step 8: Commit**

```bash
git add skills/orchestrate/templates/department.md skills/orchestrate/reference/departments.md skills/orchestrate/reference/canon.md skills/orchestrate/SKILL.md skills/orchestrate/templates/SoT.md
git commit -m "docs(canon): dept convention, departments.md, reference page, SKILL.md Files row, SoT pointer"
```

---

## Self-Review

**Spec coverage**
- §4 one markdown registry, machine-maintained, columns, pointer-only → Task 1 (`render`/`load_rows`/`COLS`). ✓
- §5.1 CLI verbs (set/get/list/ack/supersede/archive) → Task 3 `main()`. ✓
- §5.2 launcher → Task 4. ✓
- §5.3 Stop hook, fail-open, active-gate, marker→canon → Task 5. ✓
- §5.4 dept template, departments.md, reference/canon.md, SKILL.md, SoT pointer → Task 6. ✓
- §6.1 registration + change-detection + no re-flag spam + auto-register → Task 1 `apply_set` (tested: created/unchanged/changed). ✓
- §6.2 lookup (`get`, read-first) → Task 3 + Task 6. ✓
- §6.3 affects → needs-recheck → ack + "⚠ Needs re-check" block → Task 1 (`render`, `apply_ack`) + Task 5. ✓
- §6.4 stable name + archive-on-path-change; topic-key decoupled → Task 3 `archive_file` (tested) + Task 6 convention. ✓
- §6.5 migration helper (`archive` verb) → Task 3. ✓ (refcheck adoption is separate, per spec.)
- Non-goals (DECISIONS integration, SoT "Now", task system) → not implemented, by design. ✓

**Placeholder scan:** none — every step has real code/commands. The Task 5 transcript-schema note is a verify-against-reality instruction, not missing logic (a defensive reader is provided, identical to the shipped `stop_boss_board.py`).

**Type consistency:** `apply_set` returns `{"action","old_file"}` everywhere; row keys `topic/dept/file/version/updated/affects/needs_recheck` consistent across model, render, load, and `cmd_*`; `parse_canon_markers` returns `{"registers":[(dept,topic,file,affects)],"acks":[(dept,topic)]}` consumed exactly so in Task 5; `COLS` drives both `render` and `load_rows` column order; `CANON_REL` shared by `canon_path` and tests.
