import os, sys, json, tempfile, time, subprocess, unittest
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


if __name__ == "__main__":
    unittest.main()
