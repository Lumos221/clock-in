# Canonical Answers v2 (Decisions) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a CANON row index a *key in-force decision* — pointer literal `DECISIONS`, resolved by grepping the topmost `[topic-key]` tag in `DECISIONS.md`, with that entry's headline mirrored as the gist.

**Architecture:** Additive logic in the shipped `skills/orchestrate/scripts/canon.py`: a `decision_entry` grep-resolver, a mirrored "Key decisions" section appended by `render`, decision-aware `cmd_set`/`get`, and `save_rows` building the mirror dict. Table schema, CLI verbs, the `orchestrate-canon` launcher, the marker parser, and the `stop_canon.py` hook are all unchanged. Docs teach the `[token]` convention and drop SoT's "Key decisions" section.

**Tech Stack:** Python 3 standard library only. Tests use stdlib `unittest`, run via `python3 skills/orchestrate/scripts/test_canon.py -v`.

## Global Constraints

- **Zero third-party dependencies** — stdlib only.
- **Tests use `unittest`**, run `python3 skills/orchestrate/scripts/test_canon.py -v`. All existing v1 tests must keep passing.
- **Decision pointer:** the literal string `DECISIONS` in the `file` column (discriminator vs a file path). No new table columns.
- **Tag format:** a key decision's `DECISIONS.md` headline contains `[<topic-key>]`, e.g. `## 2026-06-30 · [monetization-model] Monetization model: …`. ASCII kebab token.
- **Resolution:** topmost (first-from-top = newest, per 新在上) `##`/`###` headline line containing `[<topic-key>]`. Grep-by-token — never a line number or markdown `#anchor`.
- **Decision `version`** = that entry's date (`YYYY-MM-DD`); `—` if no tagged entry. File rows keep git-sha `version`.
- **Mirror is display-only:** the "Key decisions" section is regenerated each render and ignored by `load_rows` (which parses only `|` table lines). Never stored.
- **Marker unchanged:** `@CANON[<dept>] <topic> → DECISIONS (affects: …)` already parses to `file="DECISIONS"`.
- **Fail-visible / fail-open:** a missing tag renders `(no [topic] entry in DECISIONS.md — tag it)`, never a crash.
- **Constants to add:** `DECISIONS_REL = os.path.join("docs", "DECISIONS.md")`.

---

### Task 1: `decision_entry` grep-resolver

**Files:**
- Modify: `skills/orchestrate/scripts/canon.py` (add constant + resolver, after `git_short_sha`)
- Test: `skills/orchestrate/scripts/test_canon.py` (append `DecisionResolve`)

**Interfaces:**
- Consumes: `_today` (existing).
- Produces:
  - `DECISIONS_REL: str`
  - `decision_entry(root: str, topic: str) -> tuple[str|None, str|None]` — `(date, gist)` of the topmost `DECISIONS.md` headline tagged `[topic]`; `(None, None)` if absent. `gist` = the headline text with the `[token]` and leading `date ·` stripped.

- [ ] **Step 1: Write the failing test**

Append to `skills/orchestrate/scripts/test_canon.py` (above `if __name__`):

```python
class DecisionResolve(unittest.TestCase):
    def _write(self, d, body):
        os.makedirs(os.path.join(d, "docs"), exist_ok=True)
        open(os.path.join(d, "docs", "DECISIONS.md"), "w", encoding="utf-8").write(body)

    def test_resolves_tag_strips_date_and_token(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d, "# log\n\n## 2026-06-30 · [monetization-model] Free=credits · Paid=packs\n- Why: x\n")
            date, gist = canon.decision_entry(d, "monetization-model")
            self.assertEqual(date, "2026-06-30")
            self.assertEqual(gist, "Free=credits · Paid=packs")

    def test_topmost_wins_on_date_collision_and_supersede(self):
        with tempfile.TemporaryDirectory() as d:
            # newest on top: a later monetization entry sits above the older one
            self._write(d,
                "## 2026-07-02 · [monetization-model] v2 credits model\n- Why: revised\n\n"
                "## 2026-06-30 · [pricing-tier] unrelated same-ish day\n\n"
                "## 2026-06-30 · [monetization-model] v1 credits model\n")
            date, gist = canon.decision_entry(d, "monetization-model")
            self.assertEqual((date, gist), ("2026-07-02", "v2 credits model"))

    def test_missing_tag_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d, "## 2026-06-30 · [other] thing\n")
            self.assertEqual(canon.decision_entry(d, "monetization-model"), (None, None))

    def test_no_decisions_file_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(canon.decision_entry(d, "x"), (None, None))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 skills/orchestrate/scripts/test_canon.py -v`
Expected: FAIL — `AttributeError: module 'canon' has no attribute 'decision_entry'`.

- [ ] **Step 3: Write minimal implementation**

In `canon.py`, add the constant next to `CANON_REL` (near the top):

```python
DECISIONS_REL = os.path.join("docs", "DECISIONS.md")
```

Then add the resolver after `git_short_sha` (before `archive_file`):

```python
def decision_entry(root, topic):
    """(date, gist) of the topmost DECISIONS.md headline tagged [topic]; (None, None) if absent.
    gist = headline with the [token] and a leading 'YYYY-MM-DD ·' stripped."""
    try:
        text = open(os.path.join(root, DECISIONS_REL), encoding="utf-8").read()
    except Exception:
        return (None, None)
    tag = "[%s]" % topic
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("#") or tag not in s:
            continue
        head = s.lstrip("#").strip().replace(tag, " ")
        m = re.match(r"\s*(\d{4}-\d{2}-\d{2})[\s·:\-]*(.*)$", head)
        if m:
            return (m.group(1), re.sub(r"\s+", " ", m.group(2)).strip(" ·"))
        return (None, re.sub(r"\s+", " ", head).strip(" ·"))
    return (None, None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 skills/orchestrate/scripts/test_canon.py -v`
Expected: PASS — `DecisionResolve` OK; all v1 tests still OK.

- [ ] **Step 5: Commit**

```bash
git add skills/orchestrate/scripts/canon.py skills/orchestrate/scripts/test_canon.py
git commit -m "feat(canon): decision_entry — grep topmost [topic] tag in DECISIONS.md"
```

---

### Task 2: mirrored "Key decisions" section in `render`

**Files:**
- Modify: `skills/orchestrate/scripts/canon.py` (`render` signature + section)
- Test: `skills/orchestrate/scripts/test_canon.py` (append `RenderMirror`)

**Interfaces:**
- Consumes: `fmt_list`, `HEADER`, `COLS` (existing).
- Produces: `render(rows, project, decisions=None) -> str` — `decisions` is an optional `{topic: gist}` dict; when a row has `file == "DECISIONS"`, its gist (from `decisions`, else a fail-visible placeholder) is listed under a `## Key decisions (mirrored …)` section. Backward-compatible: `render(rows, project)` behaves as v1 for file-only rows.

- [ ] **Step 1: Write the failing test**

Append to `skills/orchestrate/scripts/test_canon.py`:

```python
class RenderMirror(unittest.TestCase):
    def test_decision_row_gets_mirrored_section(self):
        rows = []
        canon.apply_set(rows, "Fin", "monetization-model", "DECISIONS", "2026-06-30", ["Marketing"], "2026-07-01")
        out = canon.render(rows, "demo", {"monetization-model": "Free=credits · Paid=packs"})
        self.assertIn("## Key decisions (mirrored", out)
        self.assertIn("- `monetization-model` · Fin — Free=credits · Paid=packs → `docs/DECISIONS.md`", out)
        self.assertIn("| monetization-model | Fin | DECISIONS |", out)   # still in the table

    def test_missing_gist_is_fail_visible(self):
        rows = []
        canon.apply_set(rows, "Fin", "monetization-model", "DECISIONS", "—", [], "2026-07-01")
        out = canon.render(rows, "demo", {})
        self.assertIn("(no [monetization-model] entry in DECISIONS.md", out)

    def test_no_decision_rows_no_section(self):
        rows = []
        canon.apply_set(rows, "Fin", "pricing-tier", "docs/财务/pricing-tier.md", "a76", [], "2026-07-01")
        out = canon.render(rows, "demo")
        self.assertNotIn("Key decisions", out)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 skills/orchestrate/scripts/test_canon.py -v`
Expected: FAIL — `render()` takes no `decisions` arg / no "Key decisions" section.

- [ ] **Step 3: Write minimal implementation**

Replace the existing `render` in `canon.py` with:

```python
def render(rows, project, decisions=None):
    flagged = [r for r in rows if r["needs_recheck"]]
    recheck = "\n".join("- `%s` → %s (updated %s)" % (r["topic"], ", ".join(r["needs_recheck"]), r["updated"])
                        for r in flagged) or "- none"
    body = ["| %s |" % " | ".join(COLS), "|%s|" % "|".join(["---"] * len(COLS))]
    for r in rows:
        body.append("| %s |" % " | ".join([
            r["topic"], r["dept"], r["file"], r["version"], r["updated"],
            fmt_list(r["affects"]), fmt_list(r["needs_recheck"])]))
    out = (HEADER % project) + recheck + "\n\n## Registry\n" + "\n".join(body) + "\n"
    dec_rows = [r for r in rows if r["file"] == "DECISIONS"]
    if dec_rows:
        lines = []
        for r in dec_rows:
            gist = (decisions or {}).get(r["topic"]) or "(no [%s] entry in DECISIONS.md — tag it)" % r["topic"]
            lines.append("- `%s` · %s — %s → `docs/DECISIONS.md`" % (r["topic"], r["dept"], gist))
        out += "\n## Key decisions (mirrored from DECISIONS.md · read-only)\n" + "\n".join(lines) + "\n"
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 skills/orchestrate/scripts/test_canon.py -v`
Expected: PASS — `RenderMirror` OK; the v1 `test_render_shows_needs_recheck_block` still OK.

- [ ] **Step 5: Commit**

```bash
git add skills/orchestrate/scripts/canon.py skills/orchestrate/scripts/test_canon.py
git commit -m "feat(canon): render mirrored 'Key decisions' section for DECISIONS rows"
```

---

### Task 3: decision-aware I/O (save mirror, set version, get display) + hook flow

**Files:**
- Modify: `skills/orchestrate/scripts/canon.py` (`save_rows`, `cmd_set`, add `cmd_get_display`, `main` get branch)
- Test: `skills/orchestrate/scripts/test_canon.py` (append `DecisionIO`)

**Interfaces:**
- Consumes: `decision_entry` (Task 1), `render` (Task 2), `find_row`, `apply_set`, `load_rows`, `canon_path`, `git_short_sha`, `archive_file`.
- Produces:
  - `save_rows(path, rows, project)` — now resolves a `{topic: gist}` mirror dict (root derived from `path`) and passes it to `render`.
  - `cmd_set(root, dept, topic, file, affects)` — for `file == "DECISIONS"`, `version` = `decision_entry` date (else git sha).
  - `cmd_get_display(root, topic) -> str` — decision → `"<gist> → docs/DECISIONS.md"`; file → the path; missing → `"not found"`.
  - `main()` `get` prints `cmd_get_display`.

- [ ] **Step 1: Write the failing test**

Append to `skills/orchestrate/scripts/test_canon.py`:

```python
class DecisionIO(unittest.TestCase):
    def _proj(self, d, decisions_body):
        os.makedirs(os.path.join(d, ".claude"))
        open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
        os.makedirs(os.path.join(d, "docs"))
        open(os.path.join(d, "docs", "DECISIONS.md"), "w", encoding="utf-8").write(decisions_body)

    def test_marker_parses_decisions_pointer(self):
        out = canon.parse_canon_markers("@CANON[Fin] monetization-model → DECISIONS (affects: Marketing)")
        self.assertEqual(out["registers"], [("Fin", "monetization-model", "DECISIONS", ["Marketing"])])

    def test_set_decision_stamps_date_and_mirrors_on_disk(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d, "## 2026-06-30 · [monetization-model] Free=credits · Paid=packs\n")
            canon.cmd_set(d, "Fin", "monetization-model", "DECISIONS", ["Marketing"])
            row = canon.find_row(canon.load_rows(canon.canon_path(d)), "monetization-model")
            self.assertEqual(row["file"], "DECISIONS")
            self.assertEqual(row["version"], "2026-06-30")
            self.assertIn("Free=credits · Paid=packs", open(canon.canon_path(d), encoding="utf-8").read())

    def test_supersede_bumps_version_and_flags(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d, "## 2026-06-30 · [monetization-model] v1\n")
            canon.cmd_set(d, "Fin", "monetization-model", "DECISIONS", ["Marketing"])
            canon.cmd_ack(d, "monetization-model", "Marketing")
            # log a newer tagged entry ON TOP, then re-register
            body = "## 2026-07-02 · [monetization-model] v2\n\n## 2026-06-30 · [monetization-model] v1\n"
            open(os.path.join(d, "docs", "DECISIONS.md"), "w", encoding="utf-8").write(body)
            canon.cmd_set(d, "Fin", "monetization-model", "DECISIONS", ["Marketing"])
            row = canon.find_row(canon.load_rows(canon.canon_path(d)), "monetization-model")
            self.assertEqual(row["version"], "2026-07-02")
            self.assertEqual(row["needs_recheck"], ["Marketing"])

    def test_get_display_decision_vs_file(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d, "## 2026-06-30 · [monetization-model] Free=credits\n")
            canon.cmd_set(d, "Fin", "monetization-model", "DECISIONS", [])
            self.assertEqual(canon.cmd_get_display(d, "monetization-model"),
                             "Free=credits → docs/DECISIONS.md")
            canon.cmd_set(d, "Fin", "pricing-tier", "docs/财务/pricing-tier.md", [])
            self.assertEqual(canon.cmd_get_display(d, "pricing-tier"), "docs/财务/pricing-tier.md")
            self.assertEqual(canon.cmd_get_display(d, "nope"), "not found")

    def test_roundtrip_ignores_mirrored_section(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d, "## 2026-06-30 · [monetization-model] Free=credits\n")
            canon.cmd_set(d, "Fin", "monetization-model", "DECISIONS", ["Marketing"])
            rows = canon.load_rows(canon.canon_path(d))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["file"], "DECISIONS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 skills/orchestrate/scripts/test_canon.py -v`
Expected: FAIL — `cmd_get_display` missing; decision `version` is a git sha, not the date; no mirrored gist on disk.

- [ ] **Step 3: Write minimal implementation**

In `canon.py`, replace `save_rows` with:

```python
def save_rows(path, rows, project):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    root = os.path.dirname(os.path.dirname(os.path.abspath(path)))  # <root>/docs/CANON.md -> <root>
    decisions = {r["topic"]: decision_entry(root, r["topic"])[1]
                 for r in rows if r["file"] == "DECISIONS"}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(render(rows, project, decisions))
    os.replace(tmp, path)
```

Replace `cmd_set` with (decision-aware version stamping):

```python
def cmd_set(root, dept, topic, file, affects):
    p = canon_path(root)
    rows = load_rows(p)
    version = (decision_entry(root, topic)[0] or "—") if file == "DECISIONS" else git_short_sha(root, file)
    res = apply_set(rows, dept, topic, file, version, affects, _today())
    if res["old_file"] and res["old_file"] != "DECISIONS":
        archive_file(root, res["old_file"])
    save_rows(p, rows, project_name(root))
    return res
```

Add `cmd_get_display` after `cmd_get`:

```python
def cmd_get_display(root, topic):
    r = find_row(load_rows(canon_path(root)), topic)
    if not r:
        return "not found"
    if r["file"] == "DECISIONS":
        gist = decision_entry(root, topic)[1] or "(no [%s] entry in DECISIONS.md)" % topic
        return "%s → docs/DECISIONS.md" % gist
    return r["file"]
```

In `main`, replace the `get` branch:

```python
    elif cmd == "get":
        print(cmd_get_display(root, argv[1] if len(argv) > 1 else ""))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 skills/orchestrate/scripts/test_canon.py -v`
Expected: PASS — `DecisionIO` OK; all prior tests OK.

- [ ] **Step 5: Hook end-to-end smoke (the hook is unchanged)**

In a scratch project with `.claude/orchestrate.json` (active) and a tagged `docs/DECISIONS.md`, feed the hook a transcript ending with the marker and confirm a decision row lands:

```bash
SC=/private/tmp/claude-501/-Users-genius-Projects-clock-in/640a09f8-ec17-44b3-a00e-2143cafc2057/scratchpad/canon-dec
rm -rf "$SC"; mkdir -p "$SC/.claude" "$SC/docs"
echo '{"active":true}' > "$SC/.claude/orchestrate.json"
printf '## 2026-06-30 · [monetization-model] Free=credits · Paid=packs\n' > "$SC/docs/DECISIONS.md"
printf '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"done\\n@CANON[Fin] monetization-model \\u2192 DECISIONS (affects: Marketing)"}]}}\n' > "$SC/t.jsonl"
printf '{"transcript_path":"%s/t.jsonl","cwd":"%s"}' "$SC" "$SC" | python3 hooks/stop_canon.py
sed -n '/Key decisions/,$p' "$SC/docs/CANON.md"
```
Expected: the `## Key decisions (mirrored …)` section lists `- \`monetization-model\` · Fin — Free=credits · Paid=packs → \`docs/DECISIONS.md\``.

- [ ] **Step 6: Commit**

```bash
git add skills/orchestrate/scripts/canon.py skills/orchestrate/scripts/test_canon.py
git commit -m "feat(canon): decision-aware set/get/save (date version, live mirror on disk)"
```

---

### Task 4: docs — tag convention, dept line, reference, SoT slim

**Files:**
- Modify: `skills/orchestrate/templates/DECISIONS.md` (tag convention)
- Modify: `skills/orchestrate/templates/department.md` (decision-register line)
- Modify: `skills/orchestrate/reference/canon.md` (Decisions subsection)
- Modify: `skills/orchestrate/templates/SoT.md` (drop "Key decisions" — if present) 
- Modify: `skills/orchestrate/reference/departments.md` (one note)

**Interfaces:** documentation only.

- [ ] **Step 1: Tag convention in the DECISIONS template**

In `skills/orchestrate/templates/DECISIONS.md`, replace the `Entry = …` line with:

```markdown
Entry = `## <date> · <one-line decision>` + **Why** + **By** (+ optional **Affects**). Newest on top.

> **Key/binding decision?** tag the headline with its topic-key so it earns a read-first `docs/CANON.md` row: `## <date> · [topic-key] <one-line decision>`, then register it once with `@CANON[<dept>] <topic-key> → DECISIONS (affects: …)`. CANON greps the **topmost** `[topic-key]` and mirrors this headline. Tactical/local decisions stay **untagged** (log-only). To supersede: add a **new** tagged entry on top + re-register.
```

- [ ] **Step 2: Decision-register line in the dept template**

In `skills/orchestrate/templates/department.md`, in the "Cross-domain facts (canonical answers)" section, after the "Finalised an answer…" bullet, add:

```markdown
- **Settled a key *decision* the project acts on?** tag its `DECISIONS.md` headline `## <date> · [<topic>] …`, then end your turn with `@CANON[<your-handle>] <topic> → DECISIONS (affects: <depts>)` — CANON mirrors the headline as the gist. (Files use a path; decisions use the literal `DECISIONS`.)
```

- [ ] **Step 3: Decisions subsection in reference/canon.md**

In `skills/orchestrate/reference/canon.md`, after the "File convention" section, add:

```markdown
## Decisions (a row can point at a decision, not just a file)
A **key in-force decision** earns a row too — pointer = the literal `DECISIONS`. Tag its `DECISIONS.md` headline with the topic-key (`## <date> · [monetization-model] …`); canon greps the **topmost** `[topic-key]` (newest, per 新在上) and **mirrors that headline** as the gist under "Key decisions (mirrored)". Author the one-liner once in `DECISIONS.md`; it can't drift.
- **Register / supersede:** `@CANON[<dept>] <topic> → DECISIONS (affects: …)`. Reverse by logging a new tagged entry on top + re-registering; canon re-points and flags dependents. The old entry stays in the log as history.
- **Lookup:** `orchestrate-canon get <topic>` → the mirrored headline + `docs/DECISIONS.md` (the why).
- Only **key/binding** decisions are tagged; tactical ones stay log-only. `DECISIONS.md` remains the full on-demand why-log.
```

- [ ] **Step 4: Drop SoT's "Key decisions" section (if present)**

In `skills/orchestrate/templates/SoT.md`, if a `## Decisions` / `## Key decisions` section exists (from an older template), replace it with a single pointer; if the template only has the v1 `## Canonical answers → docs/CANON.md` pointer already, add a clause noting decisions live there too:

```markdown
## Canonical answers & key decisions
→ `docs/CANON.md`  (machine-maintained — current file **and** in-force key decision per question; **read-first**, don't restate its rows here)
```

(Replace the existing `## Canonical answers` heading + line from v1 with the above.)

- [ ] **Step 5: One note in departments.md**

In `skills/orchestrate/reference/departments.md`, in the "Canonical file — which output 'matters'" paragraph, append to the "How it's tracked" sentence:

```markdown
 A **key binding decision** (no file) earns a row the same way — pointer `DECISIONS`, headline mirrored from `DECISIONS.md` (see `reference/canon.md`).
```

- [ ] **Step 6: Verify + full suite**

Run:
```bash
grep -q "topic-key" skills/orchestrate/templates/DECISIONS.md && echo "decisions-tpl OK"
grep -q "→ DECISIONS" skills/orchestrate/templates/department.md && echo "dept-tpl OK"
grep -q "Decisions (a row can point" skills/orchestrate/reference/canon.md && echo "reference OK"
grep -q "key decision" skills/orchestrate/templates/SoT.md && echo "sot OK"
python3 skills/orchestrate/scripts/test_canon.py 2>&1 | tail -2
python3 skills/orchestrate/scripts/test_board.py 2>&1 | tail -2
git status --porcelain docs/TaskBoard.md docs/BACKLOG.md 2>/dev/null && echo "(none above = task files untouched)"
```
Expected: the four `… OK`; both suites PASS; nothing from the last command.

- [ ] **Step 7: Commit**

```bash
git add skills/orchestrate/templates/DECISIONS.md skills/orchestrate/templates/department.md skills/orchestrate/reference/canon.md skills/orchestrate/templates/SoT.md skills/orchestrate/reference/departments.md
git commit -m "docs(canon): DECISIONS [topic] tag convention, dept decision-register, reference + SoT decisions"
```

---

## Self-Review

**Spec coverage**
- §5 CANON.md v2 layout (Registry table + mirrored Key-decisions section, loader ignores it) → Task 2 `render` + Task 3 `load_rows` unchanged (verified by `test_roundtrip_ignores_mirrored_section`). ✓
- §6 tag + grep-topmost resolution, fail-visible → Task 1 `decision_entry` (collision/supersede/missing tested). ✓
- §7.1 `decision_entry`, `cmd_set` date-version, `render` mirror, `cmd_get` display, marker unchanged, load/save → Tasks 1-3. ✓
- §7.2 docs (DECISIONS tag, dept line, reference, SoT drop, departments note) → Task 4. ✓
- §8 register/mirror/supersede/handoff/lookup + same-date edge → Task 3 (`test_supersede_bumps_version_and_flags`, `test_get_display…`) + hook smoke. ✓
- §10 verification items → covered across the four test classes + the hook smoke.

**Placeholder scan:** none — every step has real code/commands. Task 4 Step 4 is conditional ("if present") because the live `SoT.md` template state may already carry the v1 pointer; the exact replacement text is given either way.

**Type consistency:** `decision_entry` returns `(date|None, gist|None)` — used as `[0]` (version) in `cmd_set` and `[1]` (gist) in `save_rows`/`cmd_get_display`/render dict; `render(rows, project, decisions=None)` matches all call sites (`save_rows` passes the dict; v1 tests pass none); `file == "DECISIONS"` is the single discriminator everywhere; `DECISIONS_REL` shared by `decision_entry`.
