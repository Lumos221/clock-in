import contextlib, io, os, sys, json, tempfile, time, subprocess, unittest
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

    def test_notice_never_counts_toward_dept_resolution(self):
        # Field case (board screenshot 07-15): ambiguity notices were plain open
        # entries, so each one inflated the next ambiguous DONE's count and a
        # dept-level DONE could never resolve again once a notice existed.
        s = {"entries": []}
        board.add_entry(s, "Ops", "needs", "a", NOW)
        board.add_entry(s, "Ops", "needs", "b", NOW)
        board.add_notice(s, "Ops", "2 asks open (Ops-1, Ops-2)", NOW)
        e, opens = board.resolve_by_dept(s, "Ops", NOW)
        self.assertIsNone(e)
        self.assertEqual([o["id"] for o in opens], ["Ops-1", "Ops-2"])  # notice not listed

    def test_fresh_notice_supersedes_stale_unchanged_rerun_dedups(self):
        s = {"entries": []}
        n1 = board.add_notice(s, "Ops", "2 asks open (Ops-1, Ops-2)", NOW)
        n2 = board.add_notice(s, "Ops", "2 asks open (Ops-1, Ops-2)", NOW)
        self.assertEqual(n1["id"], n2["id"])                 # unchanged re-raise -> same card
        n3 = board.add_notice(s, "Ops", "3 asks open (Ops-1, Ops-2, Ops-4)", NOW)
        self.assertEqual(board.get_entry(s, n1["id"])["status"], "resolved")  # superseded
        self.assertEqual([e["id"] for e in board.open_notices(s, "Ops")], [n3["id"]])

    def test_successful_dept_resolve_sweeps_moot_notice(self):
        s = {"entries": []}
        board.add_entry(s, "Ops", "needs", "a", NOW)
        board.add_entry(s, "Ops", "needs", "b", NOW)
        n = board.add_notice(s, "Ops", "2 asks open (Ops-1, Ops-2)", NOW)
        board.set_status(s, "Ops-1", "resolved", NOW)        # Boss answers one by id
        e, _ = board.resolve_by_dept(s, "Ops", NOW)          # dept DONE now unambiguous
        self.assertEqual(e["id"], "Ops-2")
        self.assertEqual(board.get_entry(s, n["id"])["status"], "resolved")  # moot -> swept

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


class MarkerParse(unittest.TestCase):
    def test_raise_marker_extracts_dept_and_one_line_ask(self):
        out = board.parse_markers("blah\n@BOSS[QA]: Postgres or SQLite?\nmore")
        self.assertEqual(out["raises"], [("QA", None, "Postgres or SQLite?")])
        self.assertEqual(out["dones"], [])

    def test_raise_marker_with_task_link(self):
        out = board.parse_markers("@BOSS[RnD#5]: bcrypt or argon2? argon2 recommended (OWASP default)")
        self.assertEqual(out["raises"], [("RnD", "5", "bcrypt or argon2? argon2 recommended (OWASP default)")])

    def test_done_marker_tolerates_task_suffix(self):
        out = board.parse_markers("@BOSS-DONE[RnD#5]")
        self.assertEqual(out["dones"], ["RnD"])

    def test_done_marker_by_dept_and_by_id(self):
        out = board.parse_markers("@BOSS-DONE[QA]\nx\n@BOSS-DONE[RnD-2]")
        self.assertEqual(out["dones"], ["QA", "RnD-2"])
        self.assertEqual(out["raises"], [])

    def test_no_marker_is_empty(self):
        out = board.parse_markers("just a normal message, discuss this later")
        self.assertEqual(out, {"raises": [], "dones": [], "misses": []})

    def test_done_line_is_not_also_a_raise(self):
        out = board.parse_markers("@BOSS-DONE[QA]")
        self.assertEqual(out["raises"], [])
        self.assertEqual(out["dones"], ["QA"])

    def test_malformed_marker_is_reported_as_miss(self):
        # Marker-shaped but unparseable lines must surface, not vanish silently.
        out = board.parse_markers("@BOSS(QA): wrong brackets\n@BOSS[QA missing close\nplain line")
        self.assertEqual(out["raises"], [])
        self.assertEqual(len(out["misses"]), 2)


class Runtime(unittest.TestCase):
    def test_project_root_finds_marker_else_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write("{}")
            sub = os.path.join(d, "a", "b")
            os.makedirs(sub)
            self.assertEqual(os.path.realpath(board.project_root(sub)),
                             os.path.realpath(d))

    def test_project_root_pierces_linked_worktree_to_main_checkout(self):
        # Regression: a linked worktree checks out its own orchestrate.json, so panes
        # inside it used to get a private board+server+tab the Boss never watches.
        with tempfile.TemporaryDirectory() as d:
            main = os.path.join(d, "main")
            wt = os.path.join(main, ".claude", "worktrees", "agent-x")
            for root in (main, wt):
                os.makedirs(os.path.join(root, ".claude"), exist_ok=True)
                open(os.path.join(root, ".claude", "orchestrate.json"), "w").write("{}")
            os.makedirs(os.path.join(main, ".git", "worktrees", "agent-x"))
            open(os.path.join(wt, ".git"), "w").write(
                "gitdir: %s\n" % os.path.join(main, ".git", "worktrees", "agent-x"))
            sub = os.path.join(wt, "src")
            os.makedirs(sub)
            self.assertEqual(os.path.realpath(board.project_root(sub)),
                             os.path.realpath(main))

    def test_server_version_stamp_gates_reuse(self):
        """A live daemon from a previous plugin version must NOT be reused — it holds
        the old panel in memory forever (the 'board still looks old after an update'
        trap, seen in the field 2026-07-10 with two 25-hour-old servers)."""
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(board._server_is_current(d))          # no stamp recorded
            with open(board.versionfile(d), "w") as f:
                f.write("0.0.1")
            self.assertFalse(board._server_is_current(d))          # stale stamp
            # stamp = version + content hash, so a CODE edit re-deploys without a bump
            self.assertIn("+", board.BUILD)
            self.assertTrue(board._plugin_version())               # resolvable from repo
            with open(board.versionfile(d), "w") as f:
                f.write(board.BUILD)
            self.assertTrue(board._server_is_current(d))

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


class TaskboardParse(unittest.TestCase):
    BOARD = """# demo · TaskBoard

## Active

### TASK-001 · login form
- **dept:** RnD
- **task_id:** 3
- **status:** doing
- **blocked_on:** \u2014
- **what:** build the login form
- **done-when:** tests green

### TASK-002 · privacy page
- **dept:** Legal
- **task_id:** <CEO fills at dispatch: the platform id>
- **status:** blocked
- **blocked_on:** Boss sign-off

## Recently shipped
prose line, not a row
<!-- SHIPPED:START -->
- 2026-07-10 \u00b7 #2 \u00b7 QA \u00b7 smoke suite \u00b7 abc1234
<!-- SHIPPED:END -->
"""

    def test_parses_cards_placeholders_and_shipped(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "TaskBoard.md")
            open(p, "w", encoding="utf-8").write(self.BOARD)
            tb = board.parse_taskboard(p)
            self.assertEqual(len(tb["tasks"]), 2)
            t1, t2 = tb["tasks"]
            self.assertEqual((t1["label"], t1["name"], t1["dept"], t1["task_id"], t1["status"]),
                             ("TASK-001", "login form", "RnD", "3", "doing"))
            self.assertEqual(t1["blocked_on"], "")            # \u2014 normalised to empty
            self.assertEqual(t2["task_id"], "")               # <placeholder> filtered
            self.assertEqual(t2["blocked_on"], "Boss sign-off")
            self.assertEqual(tb["shipped"], ["2026-07-10 \u00b7 #2 \u00b7 QA \u00b7 smoke suite \u00b7 abc1234"])

    def test_missing_file_is_empty(self):
        self.assertEqual(board.parse_taskboard("/nonexistent/TaskBoard.md"),
                         {"tasks": [], "shipped": []})

    def test_struck_tombstone_heading_parses_as_done(self):
        """Field case (refcheck 07-14): finished cards hand-closed by striking the
        heading (`### ~~LABEL~~ ALL SHIPPED …`, no status field) garbled the panel's
        Todo column. A tombstone heading must file as done, not status-less."""
        BOARD = ("# real · TaskBoard\n\n## Active\n\n"
                 "### ~~FE-BATCH1~~ ALL SHIPPED 07-14 (detail = BACKLOG) — card closes.\n"
                 "- **Vitest mystery CLOSED:** 45 DB-gated skips explained.\n\n"
                 "### ~~COPY-SWEEP · ZH-SWEEP~~ RETIRED 07-14 (superseded)\n\n"
                 "### LIVE-01 · genuinely new hand card\n"
                 "- **status:** todo\n")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "TaskBoard.md")
            open(p, "w", encoding="utf-8").write(BOARD)
            tb = board.parse_taskboard(p)
            self.assertEqual([t["status"] for t in tb["tasks"]], ["done", "done", "todo"])

    def test_explicit_status_field_beats_tombstone_heading(self):
        BOARD = ("# t · TaskBoard\n\n## Active\n\n"
                 "### ~~REOPENED~~ SHIPPED too early\n- **status:** doing\n")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "TaskBoard.md")
            open(p, "w", encoding="utf-8").write(BOARD)
            self.assertEqual(board.parse_taskboard(p)["tasks"][0]["status"], "doing")

    def test_lowercase_closure_words_are_not_tombstones(self):
        """Live card names legitimately contain 'shipped'/'done-when' in prose —
        only SHOUTED closure words / strike marks / 'card closes' mean a tombstone."""
        BOARD = ("# t · TaskBoard\n\n## Active\n\n"
                 "### T-3 · polish the shipped-list and done-when copy\n")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "TaskBoard.md")
            open(p, "w", encoding="utf-8").write(BOARD)
            self.assertEqual(board.parse_taskboard(p)["tasks"][0]["status"], "")

    def test_field_layout_shipped_first_and_prose_statuses(self):
        """Regression against a real board (refcheck): Recently-shipped ABOVE Active
        (positional split returned 0 tasks), prose status lines, and non-card bullets
        in the shipped section that must not flood the Done column."""
        BOARD = ("# real · TaskBoard\n\n"
                 "## Recently shipped (newest first; detail in BACKLOG)\n"
                 "- #82 · QA · smoke suite green\n"
                 "prose note, not a row\n\n"
                 "## Parked → v0.2\n"
                 "### OLD-01 · parked thing\n- **status:** todo\n\n"
                 "## Active\n\n"
                 "### QA1-FIX · nickname read-path  (task#2 · SESSION-HANDOFF)\n"
                 "- **task_id:** 2\n"
                 "- **status:** doing — L1 PASS 3rd round (refutes 1–2 were real catches)\n\n"
                 "### TASK-020 · records rebuild\n"
                 "- **task_id:** —\n"
                 "- **status:** ✅ DONE + L2-passed (`docs/reviews/x.pass`)\n")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "TaskBoard.md")
            open(p, "w", encoding="utf-8").write(BOARD)
            tb = board.parse_taskboard(p)
            self.assertEqual([t["label"] for t in tb["tasks"]], ["QA1-FIX", "TASK-020"])  # parked excluded
            self.assertEqual([t["status"] for t in tb["tasks"]], ["doing", "done"])
            self.assertEqual(tb["tasks"][0]["task_id"], "2")
            self.assertEqual(tb["tasks"][1]["task_id"], "")          # "—" normalised
            self.assertEqual(tb["shipped"], ["#82 · QA · smoke suite green"])  # bounded to its section


class FileServe(unittest.TestCase):
    """resolve_file guards the panel's /file endpoint: project files only (no
    traversal, no symlink escape), inline-viewable types whitelisted, everything
    else text/plain so nothing active ever runs in the board's origin."""

    def test_project_relative_png_and_cjk_path(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "docs", "营销"))
            open(os.path.join(d, "docs", "营销", "渲染.png"), "wb").write(b"x")
            full, ctype = board.resolve_file(d, "docs/营销/渲染.png")
            self.assertEqual(ctype, "image/png")
            self.assertTrue(full.endswith("渲染.png"))

    def test_text_and_active_types_serve_as_plain(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("a.md", "b.html", "c.svg"):
                open(os.path.join(d, name), "w").write("hi")
                self.assertEqual(board.resolve_file(d, name)[1],
                                 "text/plain; charset=utf-8")

    def test_traversal_absolute_and_missing_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(board.resolve_file(d, "../../etc/hosts"))
            self.assertIsNone(board.resolve_file(d, "/etc/hosts"))
            self.assertIsNone(board.resolve_file(d, "docs/nope.png"))
            self.assertIsNone(board.resolve_file(d, ""))

    def test_symlink_escaping_root_rejected(self):
        with tempfile.TemporaryDirectory() as d, tempfile.NamedTemporaryFile() as out:
            os.symlink(out.name, os.path.join(d, "sneaky.png"))
            self.assertIsNone(board.resolve_file(d, "sneaky.png"))

    def test_falls_back_to_linked_worktrees(self):
        """Field case (refcheck CEO-89): pre-merge renders live only in a dept pane's
        worktree — exactly what the Boss is asked to eyeball. A miss in the main
        checkout must fall through to the repo's linked worktrees."""
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            main, wt = os.path.join(d, "main"), os.path.join(d, "wt")
            os.makedirs(main)
            run = lambda *a: subprocess.run(a, cwd=main, capture_output=True, check=True)
            run("git", "init", "-q", ".")
            run("git", "-c", "user.email=t@t", "-c", "user.name=t",
                "commit", "-q", "--allow-empty", "-m", "root")
            run("git", "worktree", "add", "-q", wt, "-b", "pane")
            os.makedirs(os.path.join(wt, "docs", "mockups"))
            open(os.path.join(wt, "docs", "mockups", "v5.png"), "wb").write(b"x")
            got = board.resolve_file(main, "docs/mockups/v5.png")
            self.assertIsNotNone(got)
            self.assertEqual(got[1], "image/png")
            self.assertTrue(got[0].startswith(os.path.realpath(wt)))
            # main checkout wins when both have the file
            os.makedirs(os.path.join(main, "docs", "mockups"))
            open(os.path.join(main, "docs", "mockups", "v5.png"), "wb").write(b"y")
            self.assertTrue(board.resolve_file(main, "docs/mockups/v5.png")[0]
                            .startswith(os.path.realpath(main)))


class BareNameResolve(unittest.TestCase):
    """Field case (refcheck CEO-102): the CEO writes the first artifact with its full
    path and abbreviates the sibling to its bare filename — same folder, natural prose
    economy. A bare name (no slash) must resolve by basename search so the second file
    is just as clickable; all the /file guards still apply per match."""

    def test_bare_name_found_by_basename_search(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "docs", "mockups"))
            open(os.path.join(d, "docs", "mockups", "字段-optional.png"), "wb").write(b"x")
            got = board.resolve_file(d, "字段-optional.png")
            self.assertIsNotNone(got)
            self.assertEqual(got[1], "image/png")
            self.assertTrue(got[0].endswith(os.path.join("docs", "mockups", "字段-optional.png")))

    def test_ambiguous_bare_name_newest_wins(self):
        """Asks point at fresh renders — when two files share the name, serve the
        one just produced, not last month's."""
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "old")); os.makedirs(os.path.join(d, "new"))
            open(os.path.join(d, "old", "r.png"), "wb").write(b"x")
            open(os.path.join(d, "new", "r.png"), "wb").write(b"y")
            os.utime(os.path.join(d, "old", "r.png"), (1, 1))
            self.assertTrue(board.resolve_file(d, "r.png")[0]
                            .endswith(os.path.join("new", "r.png")))

    def test_hidden_and_heavy_dirs_not_searched(self):
        with tempfile.TemporaryDirectory() as d:
            for sub in (".claude", "node_modules", "__pycache__"):
                os.makedirs(os.path.join(d, sub))
                open(os.path.join(d, sub, "h.png"), "wb").write(b"x")
            self.assertIsNone(board.resolve_file(d, "h.png"))

    def test_symlink_escape_in_search_rejected(self):
        with tempfile.TemporaryDirectory() as d, tempfile.NamedTemporaryFile() as out:
            os.makedirs(os.path.join(d, "docs"))
            os.symlink(out.name, os.path.join(d, "docs", "sneaky.png"))
            self.assertIsNone(board.resolve_file(d, "sneaky.png"))

    def test_bare_name_falls_back_to_worktrees_main_wins(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            main, wt = os.path.join(d, "main"), os.path.join(d, "wt")
            os.makedirs(main)
            run = lambda *a: subprocess.run(a, cwd=main, capture_output=True, check=True)
            run("git", "init", "-q", ".")
            run("git", "-c", "user.email=t@t", "-c", "user.name=t",
                "commit", "-q", "--allow-empty", "-m", "root")
            run("git", "worktree", "add", "-q", wt, "-b", "pane")
            os.makedirs(os.path.join(wt, "docs", "mockups"))
            open(os.path.join(wt, "docs", "mockups", "pre-merge.png"), "wb").write(b"x")
            got = board.resolve_file(main, "pre-merge.png")
            self.assertIsNotNone(got)
            self.assertTrue(got[0].startswith(os.path.realpath(wt)))
            # main checkout wins when both have a file of that name
            os.makedirs(os.path.join(main, "docs"))
            open(os.path.join(main, "docs", "pre-merge.png"), "wb").write(b"y")
            self.assertTrue(board.resolve_file(main, "pre-merge.png")[0]
                            .startswith(os.path.realpath(main)))


class ConcurrencySafety(unittest.TestCase):
    """Regression for the lost-update bug: stop_boss_board.py and stop_refute_tally.py
    both call board_add on the same Stop event. Without a lock around the store's
    load-modify-save window, whichever finishes saving last silently wipes out the
    other's entry. Runs two real OS processes (not threads) so it exercises the same
    cross-process race the two hook subprocesses hit in production."""

    def _spawn(self, root, delay_before_save, dept, text):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        code = (
            "import sys, time\n"
            "sys.path.insert(0, %r)\n"
            "import board\n"
            "board._SKIP_SERVER = True\n"
            "orig_save = board.save_store\n"
            "def slow_save(path, store):\n"
            "    time.sleep(%r)\n"
            "    orig_save(path, store)\n"
            "board.save_store = slow_save\n"
            "board.board_add(%r, %r, 'needs', %r)\n"
        ) % (script_dir, delay_before_save, root, dept, text)
        return subprocess.Popen([sys.executable, "-c", code])

    def test_two_processes_racing_on_the_same_store_both_persist(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
            # A holds the lock through a slow save; B starts mid-A and must wait, not clobber.
            pA = self._spawn(d, 0.2, "CEO", "storyboard sign-off")
            time.sleep(0.05)
            pB = self._spawn(d, 0.0, "Fin", "unrelated tally item")
            self.assertEqual(pA.wait(timeout=20), 0)
            self.assertEqual(pB.wait(timeout=20), 0)
            store = board.load_store(os.path.join(d, board.STORE_REL))
            self.assertEqual(sorted(e["dept"] for e in store["entries"]), ["CEO", "Fin"])

    def test_stale_lock_from_a_crashed_hook_is_reaped_not_deadlocked(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            board._SKIP_SERVER = True   # test hook: don't spawn the server/open browser
            lock_path = os.path.join(d, board.LOCK_REL)
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            old = time.time() - board.LOCK_STALE_AGE - 1
            os.utime(lock_path, (old, old))
            e = board.board_add(d, "QA", "needs", "should not hang")
            self.assertEqual(e["id"], "QA-1")


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

    def test_task_linked_raise_stores_task(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
            self._run_hook(d, "@BOSS[RnD#5]: bcrypt or argon2? recommend argon2 (OWASP default)")
            store = board.load_store(os.path.join(d, board.STORE_REL))
            self.assertEqual(store["entries"][0].get("task"), "5")

    def test_ambiguous_done_is_surfaced_not_swallowed(self):
        # Two open asks + @BOSS-DONE[<dept>]: which one the Boss answered is unknowable,
        # so neither is resolved — but the ambiguity must land on the board, not vanish.
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
            self._run_hook(d, "@BOSS[QA]: ask one?\n@BOSS[QA]: ask two?")
            self._run_hook(d, "@BOSS-DONE[QA]")
            store = board.load_store(os.path.join(d, board.STORE_REL))
            opens = [e for e in store["entries"] if e["status"] == "open"]
            self.assertEqual(len([e for e in opens if e["kind"] == "needs"]), 2)  # both still open
            flags = [e for e in opens if e["kind"] == "discuss" and "ambiguous" in e["text"]]
            self.assertEqual(len(flags), 1)

    def test_repeated_ambiguous_done_does_not_compound(self):
        # Field case (board screenshot 07-15): Ops-9 read "2 asks open (Ops-7, Ops-8)",
        # then Ops-10 read "3 asks open" — listing Ops-9, the previous notice, as one
        # of the asks. Notices must neither stack nor count themselves.
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
            self._run_hook(d, "@BOSS[Ops]: ask one?\n@BOSS[Ops]: ask two?")
            self._run_hook(d, "@BOSS-DONE[Ops]")
            self._run_hook(d, "@BOSS-DONE[Ops]")
            store = board.load_store(os.path.join(d, board.STORE_REL))
            flags = [e for e in store["entries"] if e.get("notice") and e["status"] == "open"]
            self.assertEqual(len(flags), 1)
            self.assertIn("2 asks open", flags[0]["text"])   # real asks only, no self-count
            # Boss answers one by id; the dept's next DONE resolves the other and
            # sweeps the now-moot notice — nothing lingers open.
            board._SKIP_SERVER = True
            board.board_done(d, "Ops-1")
            self._run_hook(d, "@BOSS-DONE[Ops]")
            store = board.load_store(os.path.join(d, board.STORE_REL))
            self.assertEqual([e["id"] for e in store["entries"] if e["status"] == "open"], [])

    def test_malformed_marker_lands_in_miss_log(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
            self._run_hook(d, "@BOSS(QA): wrong brackets")
            log = os.path.join(d, ".claude", "marker-misses.log")
            self.assertTrue(os.path.exists(log))
            self.assertIn("wrong brackets", open(log, encoding="utf-8").read())


class SurfaceOpen(unittest.TestCase):
    """Regression: a new ask must NOT pop a fresh browser window each time —
    only when the server was just started. Explicit /board still opens."""
    def _patch(self, ensure):
        saved = (board.ensure_server, board.open_url, board._SKIP_SERVER)
        opened = []
        board._SKIP_SERVER = False
        board.open_url = lambda url: opened.append(url)
        board.ensure_server = ensure
        return saved, opened

    def _restore(self, saved):
        board.ensure_server, board.open_url, board._SKIP_SERVER = saved

    def test_add_opens_only_when_server_just_started(self):
        state = {"started": True}
        saved, opened = self._patch(lambda root: (7777, state["started"]))
        try:
            board._surface("/x")             # first add → server just started → opens
            state["started"] = False
            board._surface("/x"); board._surface("/x")   # already running → no reopen
            self.assertEqual(len(opened), 1)
        finally:
            self._restore(saved)

    def test_board_open_forces_open_even_when_running(self):
        saved, opened = self._patch(lambda root: (7777, False))   # already running
        try:
            board.board_open("/x")           # explicit /board → surfaces anyway
            self.assertEqual(len(opened), 1)
        finally:
            self._restore(saved)


class AddCliGuard(unittest.TestCase):
    def test_positional_add_exits_loud_instead_of_empty_card(self):
        # Same flags-only foot-gun as canon.py `set`: positional text matches no
        # flag and an empty card would post under the default dept.
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
            argv, cwd = sys.argv, os.getcwd()
            sys.argv = ["board.py", "add", "need a decision on pricing"]
            os.chdir(d)
            err = io.StringIO()
            try:
                with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
                    board.main()
            finally:
                sys.argv = argv
                os.chdir(cwd)
            self.assertEqual(cm.exception.code, 2)
            self.assertIn("--text", err.getvalue())
            self.assertFalse(os.path.exists(os.path.join(d, board.STORE_REL)))


if __name__ == "__main__":
    unittest.main()
