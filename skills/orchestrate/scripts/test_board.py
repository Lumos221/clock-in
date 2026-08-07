import contextlib, io, os, re, sys, json, shutil, tempfile, time, subprocess, unittest
import unittest.mock


def _board_source():
    """board.py's own text — the panel's JS lives inside it, so a divergence
    between two copies of one rule is checkable without a browser."""
    return open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "board.py"), encoding="utf-8").read()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board

NOW = "2026-06-30T12:00:00"

# Nothing in this suite may reach a real iTerm pane. board_add stamps the CALLER's pane as
# an item's origin, and board_send delivers there — under pytest that meant a fixture's
# "QA-1 → use SQLite" was typed and SUBMITTED into the Boss's live session (2026-08-03).
os.environ["BOARD_SKIP_ITERM"] = "1"


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

    def test_info_never_blocks_a_dept_level_done(self):
        """An info item asks nothing of them — it is never what a DONE resolves, and it
        leaves the desk only when they toggle it read. Counting it made
        `@BOSS-DONE[<dept>]` permanently ambiguous for any dept holding one: on their live
        board the CEO had 7 open info items, the oldest 5 days old, so every dept-level
        DONE raised an ambiguity notice instead of resolving — and the notice then
        inflated the desk count that produced the next one."""
        s = {"entries": []}
        board.add_entry(s, "CEO", "info", "standing launch-day reminder", NOW)
        board.add_entry(s, "CEO", "info", "cookie banner closed", NOW)
        board.add_entry(s, "CEO", "needs", "register an NCBI key", NOW)
        e, opens = board.resolve_by_dept(s, "CEO", NOW)
        self.assertIsNotNone(e)
        self.assertEqual(e["kind"], "needs")           # the one real ask resolved
        self.assertEqual([x["status"] for x in s["entries"] if x["kind"] == "info"],
                         ["open", "open"])             # info untouched, still theirs to read

    def test_all_info_dept_resolves_nothing_and_lists_nothing(self):
        s = {"entries": []}
        board.add_entry(s, "CEO", "info", "fyi one", NOW)
        board.add_entry(s, "CEO", "info", "fyi two", NOW)
        e, opens = board.resolve_by_dept(s, "CEO", NOW)
        self.assertIsNone(e)
        self.assertEqual(opens, [])   # nothing to resolve is NOT an ambiguity to notice

    def test_desk_section_and_the_panel_agree_that_a_notice_is_information(self):
        """The two surfaces read ONE register, so a notice must file the same way on
        both. It did not: Python's mirror excluded notices, the panel's isInfo did not,
        and the masthead read one higher than the Obsidian panel for the same data."""
        s = {"entries": []}
        board.add_entry(s, "Ops", "needs", "a", NOW)
        board.add_entry(s, "Ops", "needs", "b", NOW)
        n = board.add_notice(s, "Ops", "2 asks open (Ops-1, Ops-2)", NOW)
        self.assertEqual(board._desk_section(n), "3 Information")
        js = board.HTML if hasattr(board, "HTML") else _board_source()
        m = re.search(r"function isInfo\(e\)\{([^}]*)\}", js)
        self.assertIsNotNone(m, "isInfo not found in the panel source")
        self.assertIn("notice", m.group(1))

    def test_in_flight_is_defined_once_and_used_everywhere(self):
        """Three places count in flight — masthead chip, tab badge, In-flight filter.
        Each carried its own copy, and 0.9.61 taught only the filter that a passed card
        is still in flight, so the other two would have read one low the moment a card
        cleared L2."""
        js = _board_source()
        self.assertEqual(js.count("function inFlight(t)"), 1)
        self.assertEqual(js.count("TASKS.filter(inFlight)"), 2)
        self.assertIn("k==='active' ? inFlight(t)", js)
        self.assertNotIn("TASKS.filter(t=>['doing','review','blocked']", js)

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

    def test_resolve_with_outcome_stores_sum(self):
        s = {"entries": []}
        board.add_entry(s, "QA", "needs", "an essay of an ask", NOW)
        board.set_status(s, "QA-1", "resolved", NOW, "Chose Postgres.")   # THE BOSS'S reply
        self.assertEqual(board.get_entry(s, "QA-1")["sum"], "Chose Postgres.")
        board.add_entry(s, "RnD", "needs", "b", NOW)
        # A dept-addressed DONE is the raiser's own note, so it lands in `outcome`.
        e, _ = board.resolve_by_dept(s, "RnD", NOW, "Approved.")
        self.assertEqual(e["outcome"], "Approved.")
        self.assertIsNone(e.get("sum"))

    def test_direction_set_replace_clear(self):
        s = {"entries": []}
        self.assertIsNone(board.set_direction(s, "  ", NOW))       # empty -> no banner
        d = board.set_direction(s, "LAUNCH CHECKLIST → gate", NOW)
        self.assertEqual(d["text"], "LAUNCH CHECKLIST → gate")
        d2 = board.set_direction(s, "post-launch: retention", NOW) # one slot, whole replace
        self.assertEqual(s["direction"]["text"], "post-launch: retention")
        self.assertIsNone(board.set_direction(s, "", NOW))         # clear
        self.assertNotIn("direction", s)

    def test_load_save_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, ".claude", "boss-board.json")
            self.assertEqual(board.load_store(p), {"entries": []})  # missing -> empty
            s = {"entries": []}
            board.add_entry(s, "QA", "needs", "ask", NOW)
            board.save_store(p, s)
            self.assertEqual(board.load_store(p)["entries"][0]["id"], "QA-1")


class SupersedeCollision(unittest.TestCase):
    """0.9.21: a new decision ask about the same task as an older OPEN one FLAGS the
    new entry (`collides`) — nothing auto-resolves; the Stop hook turns the flag into
    a one-time nudge so the raiser closes the old ask itself. 0.9.36: the task key
    alone is the identity — dept and kind no longer gate (one ask registered via CLI
    AND marker wore different dept and kind, blinding the old key)."""

    def test_same_dept_kind_task_field_flags_across_turns(self):
        s = {"entries": []}
        old, _ = board.add_entry(s, "CEO", "sign", "sign the string", NOW, task="129", batch="t1")
        new, _ = board.add_entry(s, "CEO", "sign", "sign the FINAL screens", NOW, task="129", batch="t2")
        self.assertEqual(old["status"], "open")          # never auto-resolved
        self.assertEqual(new["collides"], [old["id"]])

    def test_title_hash_number_is_the_fallback_key(self):
        # the CEO-143/144 field case: no task field, titles lead with #129
        s = {"entries": []}
        old, _ = board.add_entry(s, "CEO", "sign", "SIGN: #129 zh body line (then #127 remains)", NOW)
        new, _ = board.add_entry(s, "CEO", "sign", "GLANCE: #129 final screens per your marks", NOW)
        self.assertEqual(new["collides"], [old["id"]])

    def test_detail_numbers_do_not_key(self):
        # #NNN only counts in the TITLE (before ::) — detail references are context
        s = {"entries": []}
        board.add_entry(s, "QA", "needs", "pick a DB :: relates to #129 evidence", NOW)
        new, _ = board.add_entry(s, "QA", "needs", "pick a cache :: also touches #129", NOW)
        self.assertNotIn("collides", new)

    def test_cross_kind_and_dept_flag_info_and_keyless_never(self):
        s = {"entries": []}
        a, _ = board.add_entry(s, "CEO", "needs", "#129 pick option A/B", NOW)
        b, _ = board.add_entry(s, "CEO", "sign", "#129 sign the string", NOW)      # kind differs → flags
        i, _ = board.add_entry(s, "CEO", "info", "#129 merged and deployed", NOW)  # info never
        c, _ = board.add_entry(s, "CEO", "needs", "budget call, no task ref", NOW)   # keyless
        self.assertEqual(b["collides"], [a["id"]])
        self.assertNotIn("collides", i)
        self.assertNotIn("collides", c)

    def test_desk_mirror_sections_files_and_prune(self):
        import tempfile as tf
        board._SKIP_SERVER = True   # board_add must not spawn a panel here
        with tf.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            board.board_add(d, "CEO", "needs",
                            "Pick the DB :: evidence in docs/mockups/db-shot.png and 报告.md",
                            task="7")
            board.board_add(d, "CEO", "info", "FYI merged")
            done = board.board_add(d, "QA", "needs", "#9 old question")
            board.board_done(d, done["id"], "answered: option B")
            board.desk_mirror(d)
            ddir = os.path.join(d, "docs", "board", "desk")
            notes = {fn: open(os.path.join(ddir, fn), encoding="utf-8").read()
                     for fn in os.listdir(ddir)}
            ask = notes["CEO-1.md"]
            self.assertIn('section: "1 Needs you"', ask)
            self.assertIn('- "[[docs/mockups/db-shot.png]]"', ask)   # clickable list items
            self.assertIn('- "[[报告.md]]"', ask)
            self.assertIn("files: []", notes["CEO-2.md"])            # type-stable when empty
            self.assertIn('task: "#7"', ask)
            self.assertIn("- [docs/mockups/db-shot.png](docs/mockups/db-shot.png)", ask)
            self.assertIn('section: "3 Information"', notes["CEO-2.md"])
            self.assertIn('section: "4 Answered"', notes["QA-1.md"])
            # board_done is the RAISER closing its own ask, so the mirror files it under
            # 结案 — 答复 is reserved for what the Boss actually replied.
            self.assertIn("**结案（提问方）:** answered: option B", notes["QA-1.md"])
            self.assertNotIn("**答复:**", notes["QA-1.md"])
            # foreign files survive the prune; a resolved entry beyond the cap goes
            with open(os.path.join(ddir, "hand-note.md"), "w") as f:
                f.write("---\nmine: yes\n---\nboss's own note\n")
            board.board_done(d, "CEO-2", "seen")
            board.desk_mirror(d)
            self.assertTrue(os.path.exists(os.path.join(ddir, "hand-note.md")))
            self.assertIn('section: "4 Answered"',
                          open(os.path.join(ddir, "CEO-2.md"), encoding="utf-8").read())
            # byte-stable: a second run rewrites nothing
            before = os.path.getmtime(os.path.join(ddir, "CEO-1.md"))
            board.desk_mirror(d)
            self.assertEqual(os.path.getmtime(os.path.join(ddir, "CEO-1.md")), before)

    def test_cli_plus_marker_double_registration_flags(self):
        # the Boss-13/CEO-166 field case: the trailer nudge fired, the CEO registered
        # via `orchestrate-board add` (dept defaulted to Boss, kind discuss, key from
        # the title's #197) AND re-ended with the @BOSS[CEO#197] marker — two rows,
        # different dept AND kind, same ask
        s = {"entries": []}
        cli, _ = board.add_entry(s, "Boss", "discuss",
                                 "Confirm reading of order ② (#197 Ops shapes)", NOW)
        mark, _ = board.add_entry(s, "CEO", "needs",
                                  "Confirm reading :: re-aim if you meant a bug", NOW,
                                  task="197", batch="turn2")
        self.assertEqual(mark["collides"], [cli["id"]])
        self.assertEqual(cli["status"], "open")  # nothing auto-resolves

    def test_same_batch_marker_lines_coexist_next_turn_flags_both(self):
        # one turn = one batch: separate decisions on the same task never flag each
        # other; the NEXT turn's revision flags against both
        s = {"entries": []}
        a, _ = board.add_entry(s, "QA", "needs", "#7 pick the DB", NOW, batch="turn1")
        b, _ = board.add_entry(s, "QA", "needs", "#7 pick the cache", NOW, batch="turn1")
        self.assertNotIn("collides", a)
        self.assertNotIn("collides", b)
        c, _ = board.add_entry(s, "QA", "needs", "#7 revised: one combined pick", NOW, batch="turn2")
        self.assertEqual(sorted(c["collides"]), sorted([a["id"], b["id"]]))
        self.assertEqual(a["status"], "open")
        self.assertEqual(b["status"], "open")

    def test_notices_neither_flag_nor_get_flagged(self):
        s = {"entries": []}
        n = board.add_notice(s, "QA", "#9 DONE ambiguous — 2 open", NOW)
        old, _ = board.add_entry(s, "QA", "needs", "#9 the real ask", NOW, batch="t1")
        self.assertNotIn("collides", old)                # notice is not a collider
        new, _ = board.add_entry(s, "QA", "needs", "#9 a revised ask", NOW, batch="t2")
        self.assertEqual(new["collides"], [old["id"]])   # the real ask is
        self.assertEqual(n["status"], "open")

    def test_cli_add_prints_collision_warning(self):
        # the 0.9.21 field miss: CLI adds (a live project CEO-151/152) never met the
        # marker-path nudge — the CLI itself now warns in its own output
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
            argv, cwd = sys.argv, os.getcwd()
            os.environ["BOSS_BOARD_SKIP_SERVER"] = "1"
            os.chdir(d)
            try:
                for text, in (("#137 GLANCE round 2 :: v1",), ("#137 FINAL GLANCE :: v2",)):
                    sys.argv = ["board.py", "add", "--dept", "CEO",
                                "--kind", "discuss", "--text", text]
                    out = io.StringIO()
                    with contextlib.redirect_stdout(out):
                        board.main()
                self.assertIn("COLLIDES: CEO-1 still open", out.getvalue())
                self.assertIn("orchestrate-board done CEO-1", out.getvalue())
            finally:
                sys.argv, _ = argv, os.chdir(cwd)
                os.environ.pop("BOSS_BOARD_SKIP_SERVER", None)


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
        self.assertEqual(out["dones"], [("RnD", None)])

    def test_done_marker_by_dept_and_by_id(self):
        out = board.parse_markers("@BOSS-DONE[QA]\nx\n@BOSS-DONE[RnD-2]")
        self.assertEqual(out["dones"], [("QA", None), ("RnD-2", None)])
        self.assertEqual(out["raises"], [])

    def test_done_marker_with_outcome_line(self):
        out = board.parse_markers("@BOSS-DONE[CEO-116]: Launch checklist confirmed.")
        self.assertEqual(out["dones"], [("CEO-116", "Launch checklist confirmed.")])
        self.assertEqual(out["raises"], [])  # the `:` suffix must not read as a raise

    def test_no_marker_is_empty(self):
        out = board.parse_markers("just a normal message, discuss this later")
        self.assertEqual(out, {"raises": [], "dones": [], "infos": [], "misses": []})

    def test_info_marker_with_and_without_task_link(self):
        out = board.parse_markers("@BOSS-INFO[Inspector#76]: root cause = CEO review-window drift\n"
                                  "@BOSS-INFO[QA]: nightly suite green 3 days running")
        self.assertEqual(out["infos"], [("Inspector", "76", "root cause = CEO review-window drift"),
                                        ("QA", None, "nightly suite green 3 days running")])
        self.assertEqual(out["raises"], [])   # an INFO line must not double as a raise
        self.assertEqual(out["dones"], [])
        self.assertEqual(out["misses"], [])

    def test_done_line_is_not_also_a_raise(self):
        out = board.parse_markers("@BOSS-DONE[QA]")
        self.assertEqual(out["raises"], [])
        self.assertEqual(out["dones"], [("QA", None)])

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
            self.assertTrue(board._supersedes(board.BUILD, ""))         # no stamp recorded
            self.assertTrue(board._supersedes(board.BUILD, "0.0.1+a"))  # stale stamp
            # stamp = version + content hash, so a CODE edit re-deploys without a bump
            self.assertIn("+", board.BUILD)
            self.assertTrue(board._plugin_version())                    # resolvable from repo
            self.assertFalse(board._supersedes(board.BUILD, board.BUILD))

    def test_superseded_record_retires_server(self):
        """Field case (a live project 07-17): an open tab's polling defeats the idle reap,
        so a stale server lives forever unless it notices the record moved on."""
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(board._superseded(d, 55555))     # no record: standalone run
            with open(board.versionfile(d), "w") as f:
                f.write(board.BUILD)
            with open(board.portfile(d), "w") as f:
                f.write("55555")
            self.assertFalse(board._superseded(d, 55555))     # record names us
            self.assertTrue(board._superseded(d, 55556))      # port moved on
            # A NEWER record retires us. An older one must not: this assertion used to
            # read "any different build", which let an old install standing beside a new
            # one order the new server to exit — half of the kill-each-other loop.
            with open(board.versionfile(d), "w") as f:
                f.write("99.0.0+newer")
            self.assertTrue(board._superseded(d, 55555))      # build moved on
            with open(board.versionfile(d), "w") as f:
                f.write("0.0.1+older")
            self.assertFalse(board._superseded(d, 55555))     # an older install cannot

    def test_reclaim_kills_only_a_proven_board_zombie(self):
        """A zombie whose pidfile generation was lost holds the derived port; reclaim
        must free it — but only after the process answers as THIS root's board, so an
        innocent squatter on the port is never shot. Real subprocess, real socket."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        with tempfile.TemporaryDirectory() as d:
            root = os.path.join(d, "zomb")
            os.makedirs(os.path.join(root, ".claude"))
            port = board.pick_port(root)
            z = subprocess.Popen([sys.executable, os.path.join(script_dir, "board.py"),
                                  "serve", "--root", root, "--port", str(port)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(100):
                    if not board.port_free(port):
                        break
                    time.sleep(0.05)
                self.assertFalse(board.port_free(port))
                other = os.path.join(d, "innocent")
                os.makedirs(other)
                board._reclaim_port(port, other)              # wrong root: must NOT kill
                self.assertFalse(board.port_free(port))
                board._reclaim_port(port, root)               # right root: reclaimed
                self.assertTrue(board.port_free(port))
            finally:
                try:
                    z.kill()
                except Exception:
                    pass

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
        """Field case (a live project 07-14): finished cards hand-closed by striking the
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
        """Regression against a real board (a live project): Recently-shipped ABOVE Active
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
        """Field case (a live project CEO-89): pre-merge renders live only in a dept pane's
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
    """Field case (a live project CEO-102): the CEO writes the first artifact with its full
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

    def test_done_with_outcome_lands_on_the_entry(self):
        # The outcome line becomes the answered row's collapsed face on the panel.
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
            self._run_hook(d, "@BOSS[QA]: Postgres or SQLite? recommend Postgres")
            self._run_hook(d, "@BOSS-DONE[QA]: Postgres it is.")
            store = board.load_store(os.path.join(d, board.STORE_REL))
            self.assertEqual(store["entries"][0]["status"], "resolved")
            # The marker is the raiser closing its own ask — its note is the OUTCOME.
            # `sum` stays empty because they never replied to this one.
            self.assertEqual(store["entries"][0]["outcome"], "Postgres it is.")
            self.assertIsNone(store["entries"][0].get("sum"))

    def test_info_marker_files_as_info_kind(self):
        # @BOSS-INFO lands in the Information column: kind "info", never "needs".
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
            self._run_hook(d, "@BOSS-INFO[QA#7]: nightly suite green 3 days running")
            store = board.load_store(os.path.join(d, board.STORE_REL))
            self.assertEqual(store["entries"][0]["kind"], "info")
            self.assertEqual(store["entries"][0].get("task"), "7")

    def test_inspector_raise_autofiles_as_info(self):
        # The Inspector's @BOSS channel carries verdicts, not asks — auto-info
        # (suffixed respawns like Inspector-2 included); other depts stay "needs".
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
            self._run_hook(d, "@BOSS[Inspector-2]: 复盘 #76 verdict: root cause = CEO drift\n"
                              "@BOSS[QA]: Postgres or SQLite?")
            store = board.load_store(os.path.join(d, board.STORE_REL))
            kinds = {e["dept"]: e["kind"] for e in store["entries"]}
            self.assertEqual(kinds["Inspector-2"], "info")
            self.assertEqual(kinds["QA"], "needs")

    def test_direction_persists_via_wrapper(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            board._SKIP_SERVER = True
            board.board_direction(d, "LAUNCH CHECKLIST (live) → LAUNCH-GATE")
            got = board.load_store(os.path.join(d, board.STORE_REL))["direction"]
            self.assertEqual(got["text"], "LAUNCH CHECKLIST (live) → LAUNCH-GATE")
            board.board_direction(d, "")
            self.assertNotIn("direction", board.load_store(os.path.join(d, board.STORE_REL)))

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


class _NudgeFixture(unittest.TestCase):
    """Shared fixture for the stop_boss_board block-string nudges."""

    @classmethod
    def setUpClass(cls):
        hooks = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))), "hooks")
        sys.path.insert(0, hooks)
        import stop_boss_board
        cls.mod = stop_boss_board

    def _proj(self, d):
        os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
        open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')

    def _transcript(self, d, work=True, final_text="Still open for you: A or B?"):
        p = os.path.join(d, "t.jsonl")
        rows = [{"type": "user", "message": {"role": "user", "content": "开始上班"}}]
        if work:
            rows.append({"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}]}})
            rows.append({"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}})
        rows.append({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": final_text}]}})
        with open(p, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        return p

    def _run(self, d, work=True, text="Progress report.\nStill open for you: A or B?",
             prompt="p1"):
        env = os.environ.get("BOSS_BOARD_SKIP_SERVER")
        os.environ["BOSS_BOARD_SKIP_SERVER"] = "1"
        try:
            return self.mod.run({"cwd": d, "transcript_path": self._transcript(d, work),
                                 "prompt_id": prompt}, text)
        finally:
            if env is None:
                os.environ.pop("BOSS_BOARD_SKIP_SERVER", None)

class AskNudge(_NudgeFixture):
    """0.9.18 unmarked-trailing-ask nudge (stop_boss_board.run returns a block string):
    a lead WORK turn (used tools) ending on a question with no @BOSS marker blocks the
    stop once; conversational turns, marker-carrying turns and repeats pass."""

    def test_work_turn_trailing_question_blocks_once(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            ret = self._run(d)
            self.assertIn("@BOSS", ret or "")
            self.assertIsNone(self._run(d))                    # same prompt → pass

    def test_new_prompt_nudges_again(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            self.assertTrue(self._run(d, prompt="p1"))
            self.assertIsNone(self._run(d, prompt="p1"))
            self.assertTrue(self._run(d, prompt="p2"))

    def test_marker_carrying_turn_passes(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            ret = self._run(d, text="@BOSS[CEO#5]: A or B? :: context here\nanything?")
            self.assertIsNone(ret)

    def test_conversational_turn_never_trips(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            self.assertIsNone(self._run(d, work=False))

    def test_statement_ending_passes(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            self.assertIsNone(self._run(d, text="All dispatched. Waiting on QA."))

    def test_fullwidth_question_mark_counts(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            self.assertTrue(self._run(d, text="收尾。\n邀请门槛还等 #116 吗？"))

    def test_needs_you_trailer_without_marker_blocks(self):
        # field case 2026-07-19: "---Needs you: …" ends in a full stop, so the
        # question-mark heuristic slept while the ask lived only in prose
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            ret = self._run(d, text="All merged.\n---Needs you: the raw text glance "
                                    "and the button render — otherwise nothing.")
            self.assertIn("@BOSS", ret or "")

    def test_needs_you_nothing_trailer_passes(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            self.assertIsNone(self._run(d, text="All merged.\nNeeds you: nothing."))
            self.assertIsNone(self._run(d, text="收尾完成。\n需要你：无", prompt="p9"))
            self.assertIsNone(self._run(d, text="Done.\n---Needs you: nothing right now.",
                                        prompt="p10"))
            # a clause continuing past the nil word IS an ask
            ret = self._run(d, text="Done.\nNeeds you: none of the options work, pick one",
                            prompt="p11")
            self.assertIn("@BOSS", ret or "")


class CollisionNudge(_NudgeFixture):
    """0.9.21 supersede collision nudge: a fresh ask on the same task as an older open
    same-dept+kind ask blocks the stop ONCE with the close-or-keep instruction — the
    nudge lands BEFORE anything supersedes (the raiser handles it)."""

    def test_second_turn_revision_blocks_once_then_capped(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            self.assertIsNone(self._run(d, text="@BOSS[CEO#129]: sign the string :: v1"))
            ret = self._run(d, text="@BOSS[CEO#129]: sign the FINAL screens :: v2")
            self.assertIn("@BOSS-DONE", ret or "")       # nudged with the fix
            self.assertIn("CEO-1", ret or "")            # names the open collider
            store = json.load(open(os.path.join(d, ".claude", "boss-board.json")))
            self.assertTrue(all(e["status"] == "open" for e in store["entries"]))  # nothing auto-resolved
            ret2 = self._run(d, text="@BOSS[CEO#129]: sign the FINAL screens :: v2")
            self.assertIsNone(ret2)                      # once per collision set

    def test_done_in_same_turn_passes_clean(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            self.assertIsNone(self._run(d, text="@BOSS[CEO#129]: sign the string :: v1"))
            ret = self._run(d, text="@BOSS-DONE[CEO-1]: superseded by v2\n"
                                    "@BOSS[CEO#129]: sign the FINAL screens :: v2")
            self.assertIsNone(ret)                       # old closed this turn → no nudge
            store = json.load(open(os.path.join(d, ".claude", "boss-board.json")))
            by = {e["id"]: e for e in store["entries"]}
            self.assertEqual(by["CEO-1"]["status"], "resolved")
            self.assertEqual(by["CEO-2"]["status"], "open")

    def test_same_turn_batch_never_nudges(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            ret = self._run(d, text="@BOSS[QA#7]: pick the DB :: a\n@BOSS[QA#7]: pick the cache :: b")
            self.assertIsNone(ret)

    def test_cli_added_collision_caught_at_stop(self):
        # the 0.9.21 field miss: asks added via `orchestrate-board add` (no markers
        # in any pane text) collided in the store but the marker-only nudge never
        # saw them — the Stop net now reads the flag from the store itself
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            os.environ["BOSS_BOARD_SKIP_SERVER"] = "1"
            try:
                import board as b
                b.board_add(d, "CEO", "discuss", "#137 GLANCE round 2 :: v1")
                b.board_add(d, "CEO", "discuss", "#137 FINAL GLANCE :: v2")
            finally:
                os.environ.pop("BOSS_BOARD_SKIP_SERVER", None)
            ret = self._run(d, text="Round 2 render posted for the Boss.")
            self.assertIn("CEO-1", ret or "")            # names the open collider
            self.assertIsNone(self._run(d, text="idle."))  # capped persistently


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


class BasketAndSend(unittest.TestCase):
    """The interactive reverse channel: stage answers, flush with Send — resolve replies
    on the board, mark reads, compose the one-line message that gets typed into the pane."""

    def test_basket_stage_replace_and_unstage(self):
        s = {"entries": []}
        board.basket_set(s, "QA-1", "reply", "use SQLite", NOW)
        board.basket_set(s, "CEO-2", "ask", "what deadline?", NOW)
        self.assertEqual([(x["id"], x["kind"]) for x in s["basket"]],
                         [("QA-1", "reply"), ("CEO-2", "ask")])
        board.basket_set(s, "QA-1", "reply", "use Postgres", NOW)   # one per id: replace
        self.assertEqual({x["id"]: x["text"] for x in s["basket"]}["QA-1"], "use Postgres")
        self.assertEqual(len(s["basket"]), 2)
        board.basket_set(s, "QA-1", "reply", "   ", NOW)            # empty -> unstage
        self.assertEqual([x["id"] for x in s["basket"]], ["CEO-2"])

    def test_compose_is_single_line_and_flags_replies_vs_asks(self):
        basket = [{"id": "QA-1", "kind": "reply", "text": "use SQLite"},
                  {"id": "CEO-2", "kind": "ask", "text": "what deadline?"}]
        msg = board.compose_basket(basket)
        self.assertNotIn("\n", msg)                 # one prompt, one submit
        for frag in ("QA-1", "CEO-2", "use SQLite", "what deadline?"):
            self.assertIn(frag, msg)
        # No preamble: the message is the answers. It used to lead with a count of what
        # was being sent and an instruction not to re-run the done-marker, which arrived in
        # front of every answer they wrote.
        self.assertNotIn("resolved on the board", msg)
        self.assertNotIn("still open", msg)
        self.assertNotIn("BOSS-DONE", msg)
        self.assertTrue(msg.startswith("[Boss Board] QA-1 →"))

    def test_send_mutate_resolves_replies_keeps_asks_and_composes(self):
        s = {"entries": []}
        board.add_entry(s, "QA", "needs", "db?", NOW)      # QA-1
        board.add_entry(s, "CEO", "info", "fyi", NOW)      # CEO-1
        board.basket_set(s, "QA-1", "reply", "SQLite", NOW)
        board.basket_set(s, "CEO-1", "ask", "when?", NOW)
        rec = board.board_send_mutate(s, NOW)
        self.assertEqual(board.get_entry(s, "QA-1")["status"], "resolved")
        self.assertEqual(board.get_entry(s, "QA-1")["sum"], "SQLite")
        self.assertEqual(board.get_entry(s, "CEO-1")["status"], "open")   # an ask stays open
        self.assertEqual(s["basket"], [])                                 # cleared on send
        self.assertEqual(rec["items"], ["QA-1", "CEO-1"])
        self.assertIn("QA-1", rec["msg"]); self.assertIn("CEO-1", rec["msg"])
        self.assertNotIn("outbox", s)                                     # no queue — typed to the pane

    def test_send_mutate_empty_basket_is_noop(self):
        self.assertIsNone(board.board_send_mutate({"entries": []}, NOW))

    def test_iterm_prime_skips_without_a_captured_pane(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(board.iterm_prime(d, "hi"), "skip")   # no iterm-target -> save on board

    def test_set_read_flag_toggles_without_touching_status(self):
        s = {"entries": []}
        board.add_entry(s, "CEO", "info", "fyi", NOW)
        board.set_read(s, "CEO-1", True, NOW)
        self.assertTrue(board.get_entry(s, "CEO-1")["read"])
        self.assertEqual(board.get_entry(s, "CEO-1")["status"], "open")
        board.set_read(s, "CEO-1", False, NOW)
        self.assertFalse(board.get_entry(s, "CEO-1")["read"])

    def test_board_send_composes_resolves_and_clears(self):
        board._SKIP_SERVER = True
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            board.board_add(d, "QA", "needs", "Postgres or SQLite?")
            board._locked_mutate(d, lambda st: board.basket_set(
                st, "QA-1", "reply", "use SQLite", board._now()))
            res = board.board_send(d)
            self.assertEqual(res["n"], 1)
            self.assertIn("QA-1", res["msg"])            # the message the page copies to the clipboard
            st = board.load_store(board._store_path(d))
            self.assertEqual(board.get_entry(st, "QA-1")["status"], "resolved")
            self.assertEqual(st["basket"], [])
            self.assertNotIn("outbox", st)               # no queue, no daemon keystroke

    def test_archiving_an_update_tells_the_session_nothing(self):
        # Reading an update is the Boss filing it, not sending anything. The
        # board used to append "Read: CEO-1" plus a "N marked read (acknowledged, no
        # action)" note — a sentence asking the reader to do exactly nothing.
        s = {"entries": []}
        board.add_entry(s, "CEO", "info", "fyi", NOW)          # CEO-1 (Information)
        board.set_read(s, "CEO-1", True, NOW)                  # archive applies at the click
        e = board.get_entry(s, "CEO-1")
        self.assertTrue(e["read"])
        self.assertEqual(e["status"], "open")                  # folds to History, NOT resolved
        self.assertIsNone(board.board_send_mutate(s, NOW))     # nothing to send

    def test_a_legacy_staged_read_never_reaches_the_session(self):
        s = {"entries": []}
        board.add_entry(s, "CEO", "info", "fyi", NOW)
        board.add_entry(s, "QA", "needs", "pick one", NOW)
        board.basket_set(s, "CEO-1", "read", "read", NOW)      # staged by an older page
        board.basket_set(s, "QA-1", "reply", "do it", NOW)
        rec = board.board_send_mutate(s, NOW)
        self.assertNotIn("CEO-1", rec["msg"])
        self.assertNotIn("marked read", rec["msg"])
        self.assertEqual(rec["items"], ["QA-1"])
        self.assertEqual(s["basket"], [])                      # and the basket still clears

    def test_send_marks_an_asked_info_item_read(self):
        """Asking about an update IS reading it. The ask used to leave the item sitting
        in the feed, demanding a manual tick and then a SECOND Send just for the ack."""
        s = {"entries": []}
        board.add_entry(s, "CEO", "info", "fyi", NOW)          # CEO-1 (Information)
        board.basket_set(s, "CEO-1", "ask", "which one?", NOW)
        board.board_send_mutate(s, NOW)
        e = board.get_entry(s, "CEO-1")
        self.assertTrue(e["read"])                             # folds to History with the send
        self.assertEqual(e["status"], "open")                  # a question, not a resolution

    def test_send_leaves_an_asked_decision_unread(self):
        """The fold is Information-only: a Needs-you item they question is still theirs
        to answer — it must stay in the queue, not slip into History."""
        s = {"entries": []}
        board.add_entry(s, "QA", "needs", "db?", NOW)          # QA-1 (Needs you)
        board.basket_set(s, "QA-1", "ask", "what constraints?", NOW)
        board.board_send_mutate(s, NOW)
        e = board.get_entry(s, "QA-1")
        self.assertFalse(e.get("read"))
        self.assertEqual(e["status"], "open")


class ArchiveHistory(unittest.TestCase):
    """The Archive view reads BOTH eras of BACKLOG.md. It used to read only the
    hand-written `> **✅ DONE**` blocks, which stopped being written when the machine
    task-log took over — so the panel froze at the last prose entry while hundreds of
    real rows accumulated below it (a live project: 24 shown, 442 on file)."""

    def _root(self, d, backlog_text):
        os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
        open(os.path.join(d, ".claude", "orchestrate.json"), "w").write("{}")
        os.makedirs(os.path.join(d, "docs"), exist_ok=True)
        open(os.path.join(d, "docs", "BACKLOG.md"), "w", encoding="utf-8").write(backlog_text)
        return d

    def test_machine_rows_are_read_with_every_field(self):
        rows = board._backlog_rows(
            "| date | id | dept | task | status | sha | note |\n"
            "|---|---|---|---|---|---|---|\n"
            "| 2026-07-25 | 12 | Ops | #340 SHIP-IT | done | abc1234 | 42 tests green |\n")
        self.assertEqual(rows, [{"date": "2026-07-25", "task_id": "12", "dept": "Ops",
                                 "title": "#340 SHIP-IT", "status": "done",
                                 "sha": "abc1234", "note": "42 tests green"}])

    def test_placeholders_read_as_absent_and_a_taskless_row_is_dropped(self):
        rows = board._backlog_rows(
            "| 2026-07-25 | — | — | #341 REAL | done | — | — |\n"
            "| 2026-07-25 | 4 | — | — | done | b5a6269c | — |\n")   # card-less bookkeeping
        self.assertEqual([r["title"] for r in rows], ["#341 REAL"])
        self.assertEqual((rows[0]["task_id"], rows[0]["dept"], rows[0]["sha"]), ("", "", ""))

    def test_escaped_pipe_inside_a_cell_survives_the_split(self):
        rows = board._backlog_rows("| 2026-07-25 | 1 | QA | #7 A \\| B | done | s | n |\n")
        self.assertEqual(rows[0]["title"], "#7 A | B")
        self.assertEqual(rows[0]["note"], "n")

    def test_both_eras_merge_newest_first_and_the_machine_row_wins_a_collision(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._root(d,
                "> **✅ DONE — #51 old prose entry** (Ops, `d3172fd`, 2026-07-09) — text\n"
                "> **✅ DONE — #99 also on the table** (QA, `beef123`, 2026-07-01) — text\n"
                "| 2026-07-25 | 1 | Ops | #99 also on the table | done | abc1234 | swept |\n")
            ar = board.load_archive(root)
            self.assertEqual(ar["total"], 2)                       # #99 deduped, not doubled
            titles = [r["title"] for r in ar["backlog"]]
            self.assertEqual(titles[0], "#99 also on the table")   # newest first
            self.assertEqual(ar["backlog"][0]["sha"], "abc1234")   # the machine row's record
            self.assertIn("#51 old prose entry", titles[1])        # legacy era still read

    def test_total_is_honest_behind_the_limit(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._root(d, "".join(
                "| 2026-07-%02d | %d | Ops | #%d T%d | done | s%d | — |\n" % (
                    (i % 28) + 1, i, i, i, i)
                for i in range(1, 60)))
            ar = board.load_archive(root, limit=10)
            self.assertEqual(len(ar["backlog"]), 10)
            self.assertEqual(ar["total"], 59)


class PipelineFields(unittest.TestCase):
    """The Tasks pane draws each card's place in the org pipeline and its time in that
    stage, so `since` has to survive the digest round-trip into the panel's payload."""

    def test_since_reaches_the_panel(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "TaskBoard.md")
            open(p, "w", encoding="utf-8").write(
                "## Active\n\n### #7 · SHIP-IT\n"
                "- **dept:** Frontend\n- **task_id:** 3\n- **status:** review\n"
                "- **since:** 2026-07-21T14:03\n- **priority:** P1\n")
            t = board.parse_taskboard(p)["tasks"][0]
            self.assertEqual(t["since"], "2026-07-21T14:03")
            self.assertEqual((t["status"], t["task_id"], t["priority"]), ("review", "3", "P1"))

    def test_a_card_without_the_stamp_carries_an_empty_string(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "TaskBoard.md")
            open(p, "w", encoding="utf-8").write(
                "## Active\n\n### #8 · OLD\n- **status:** todo\n- **since:** —\n")
            self.assertEqual(board.parse_taskboard(p)["tasks"][0]["since"], "")


class SliceHonesty(unittest.TestCase):
    """Every list on the panel is a slice of a longer file. The badge counts the FILE;
    the view says how much of it is on screen. Counting the slice made a 252-ruling log
    read as 14 and a 75-letter lane as 30."""

    def _root(self, d):
        os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
        open(os.path.join(d, ".claude", "orchestrate.json"), "w").write(
            '{"external": ["Marketing"]}')
        os.makedirs(os.path.join(d, "docs", "board", "mail"), exist_ok=True)
        return d

    def test_decisions_count_the_log_not_the_page(self):
        with tempfile.TemporaryDirectory() as d:
            self._root(d)
            open(os.path.join(d, "docs", "DECISIONS.md"), "w", encoding="utf-8").write(
                "".join("## 2026-07-%02d · [k%d] ruling %d\n\ntext\n\n" % ((i % 28) + 1, i, i)
                        for i in range(40)))
            dd = board.load_decisions(d, limit=14)
            self.assertEqual(len(dd["decisions"]), 14)
            self.assertEqual(dd["decisions_total"], 40)

    def test_mail_lane_and_branch_counts_speak_for_the_whole_lane(self):
        with tempfile.TemporaryDirectory() as d:
            self._root(d)
            mdir = os.path.join(d, "docs", "board", "mail")
            for i in range(40):
                open(os.path.join(mdir, "2026072%d-l%02d.md" % (i % 10, i)), "w",
                     encoding="utf-8").write(
                    "---\nfrom: Marketing\nto: CEO\nre: letter %d\ntime: \"2026-07-24\"\n---\nbody\n" % i)
            open(os.path.join(mdir, "dead.md"), "w", encoding="utf-8").write("no headers\n")
            mm = board.load_mail(d, limit=10)
            self.assertEqual(len(mm["mail"]), 10)
            self.assertEqual(mm["total"], 40)                    # the dead letter is not a row
            self.assertEqual(mm["branches"][0]["letters"], 40)   # not 10


class ServerReplacement(unittest.TestCase):
    """Two installs must never kill each other's server.

    The plugin runs from a VERSIONED cache directory, so a long-running session pins an
    old copy while a newer one sits alongside it. Both call ensure_server; under the old
    rule — replace whenever the recorded stamp is not mine — each read the other as
    stale and killed the other's server on every call. The port was dead between each
    kill and bind (a refused connection in the open tab) and every call reported that it
    had started the server, which opened a fresh browser tab each time.

    Field state that produced it: four cache directories alive at once, two of them
    holding byte-identical code but different plugin versions, so their build stamps
    disagreed while their behaviour did not."""

    def test_replacement_is_monotonic(self):
        """The property that terminates the loop: for any two builds, at most one of
        them replaces the other."""
        builds = ["0.9.72+aaaa", "0.9.74+bbbb", "0.9.77+cccc", "0.10.0+dddd"]
        for a in builds:
            for b in builds:
                if a == b:
                    continue
                both = board._supersedes(a, b) and board._supersedes(b, a)
                self.assertFalse(both, "%s and %s replace each other" % (a, b))

    def test_an_older_install_reuses_a_newer_server(self):
        """The exact field case: identical code, versions 0.9.72 and 0.9.77, because the
        stamp carries the version of the cache directory the copy happens to sit in."""
        self.assertFalse(board._supersedes("0.9.72+b8674c33", "0.9.77+b8674c33"))
        self.assertTrue(board._supersedes("0.9.77+b8674c33", "0.9.72+b8674c33"))

    def test_a_newer_install_still_replaces_an_old_panel(self):
        """The behaviour the stamp exists for is not lost: an updated plugin must not
        keep serving the old panel out of a daemon's memory."""
        self.assertTrue(board._supersedes("0.9.77+aaaa", "0.9.7+bbbb"))
        self.assertTrue(board._supersedes("0.10.0+aaaa", "0.9.99+bbbb"))

    def test_an_edited_working_copy_self_deploys(self):
        """Same version, different code: a code edit re-deploys without a version bump."""
        self.assertTrue(board._supersedes("0.9.77+aaaa", "0.9.77+bbbb"))

    def test_an_unstamped_server_is_replaceable(self):
        self.assertTrue(board._supersedes("0.9.77+aaaa", ""))

    def test_a_server_only_stands_down_for_a_newer_record(self):
        """An OLDER install rewriting the record must never make a newer server exit —
        that was the other half of the loop."""
        with tempfile.TemporaryDirectory() as d:
            with open(board.versionfile(d), "w") as f:
                f.write("0.0.1+old")
            with open(board.portfile(d), "w") as f:
                f.write("55555")
            self.assertFalse(board._superseded(d, 55555), "an older record cannot retire us")

    def test_replacing_a_live_server_does_not_ask_for_a_new_tab(self):
        """`started` means "there was nothing running", which is the only case where a
        browser window is needed. A replacement leaves the tab where it was; the page
        reloads itself once /state.json answers with a new version."""
        with tempfile.TemporaryDirectory() as d:
            spawned = []
            orig = (board.server_info, board.subprocess.Popen, board.port_free,
                    board._reclaim_port)
            live = [True]
            try:
                board.server_info = lambda root: 41234 if live[0] else None
                board.port_free = lambda port: False
                board._reclaim_port = lambda port, root: None
                board.subprocess.Popen = lambda *a, **k: spawned.append(a) or type(
                    "P", (), {"pid": 4242})()
                with open(board.versionfile(d), "w") as f:
                    f.write("0.0.1+ancient")           # live, and genuinely older
                os.utime(board.versionfile(d), (0, 0))  # older than BOARD_MIN_LIFE
                port, started = board.ensure_server(d)
                self.assertTrue(spawned, "a strictly newer build still replaces")
                self.assertFalse(started, "a replacement must not open a second tab")

                live[0] = False                        # nothing running at all
                spawned.clear()
                port, started = board.ensure_server(d)
                self.assertTrue(spawned)
                self.assertTrue(started, "with no server, the browser does need opening")
            finally:
                (board.server_info, board.subprocess.Popen, board.port_free,
                 board._reclaim_port) = orig

    def test_the_record_describes_the_spawned_code_not_the_parents_import(self):
        """The record must name the code the CHILD will run, read fresh from disk.

        ensure_server execs the FILE, so a long-lived importer (the MCP board channel
        holds board.py in memory for days across every update) spawns CURRENT code while
        its own `BUILD` is a fossil. Field case 2026-07-29: the record read a build that
        existed nowhere on disk. The lie always reads as OLD, so every newer install kept
        judging the live server stale and replacing it — and each replacement leaves a
        window with nothing listening, where the next call reports `started` and opens a
        browser window. That is the 0.9.78 symptom revived from the other end."""
        with tempfile.TemporaryDirectory() as d:
            spawned = []
            orig = (board.server_info, board.subprocess.Popen, board.port_free,
                    board._reclaim_port, board.BUILD)
            try:
                board.server_info = lambda root: None      # nothing running → spawn path
                board.port_free = lambda port: False
                board._reclaim_port = lambda port, root: None
                board.subprocess.Popen = lambda *a, **k: spawned.append(a) or type(
                    "P", (), {"pid": 4242})()
                board.BUILD = "0.9.75+fossil"              # the long-lived parent
                board.ensure_server(d)
                self.assertTrue(spawned)
                rec = board._recorded_build(d)
                self.assertNotEqual(rec, "0.9.75+fossil",
                                    "the parent's stale import must never be recorded")
                self.assertEqual(rec, board._build_stamp(),
                                 "the record names the on-disk code that was exec'd")
            finally:
                (board.server_info, board.subprocess.Popen, board.port_free,
                 board._reclaim_port, board.BUILD) = orig

    def test_a_fossil_parent_no_longer_replaces_a_current_server(self):
        """The other half: a stale in-memory BUILD must not make its owner judge a
        current server stale. Reusing settles the churn instead of feeding it."""
        with tempfile.TemporaryDirectory() as d:
            orig = (board.server_info, board.BUILD)
            try:
                board.server_info = lambda root: 41234
                board.BUILD = "0.9.75+fossil"
                with open(board.versionfile(d), "w") as f:
                    f.write(board._build_stamp())          # a CURRENT server is running
                os.utime(board.versionfile(d), (0, 0))     # past BOARD_MIN_LIFE
                port, started = board.ensure_server(d)
                self.assertEqual(port, 41234, "current server reused, not killed")
                self.assertFalse(started)
            finally:
                board.server_info, board.BUILD = orig

    def test_a_fossil_parent_still_retires_a_genuinely_stale_server(self):
        """The comparison must use the on-disk build too, not just the record write.

        Judging with the parent's fossil import makes it decline to replace a server
        that IS stale — so an updated plugin keeps serving the old panel out of a
        daemon's memory, which is the failure `_supersedes` exists to prevent. The
        deciding case needs three distinct builds: fossil parent < stale server < disk."""
        with tempfile.TemporaryDirectory() as d:
            spawned = []
            orig = (board.server_info, board.subprocess.Popen, board.port_free,
                    board._reclaim_port, board.BUILD, board._build_stamp)
            try:
                board.server_info = lambda root: 41234
                board.port_free = lambda port: False
                board._reclaim_port = lambda port, root: None
                board.subprocess.Popen = lambda *a, **k: spawned.append(a) or type(
                    "P", (), {"pid": 4242})()
                board.BUILD = "0.9.75+fossil"          # long-lived parent's import
                board._build_stamp = lambda: "0.9.81+ondisk"   # what it would exec
                with open(board.versionfile(d), "w") as f:
                    f.write("0.9.77+stale")            # a genuinely outdated server
                os.utime(board.versionfile(d), (0, 0))
                board.ensure_server(d)
                self.assertTrue(spawned, "current code must retire the stale server")
                self.assertEqual(board._recorded_build(d), "0.9.81+ondisk")
            finally:
                (board.server_info, board.subprocess.Popen, board.port_free,
                 board._reclaim_port, board.BUILD, board._build_stamp) = orig

    def test_spawn_build_falls_back_to_import_when_disk_is_unreadable(self):
        """An unreadable file yields no version; recording that would read as OLDER than
        everything and hand every install a licence to replace. Fall back instead."""
        orig = board._build_stamp
        try:
            board._build_stamp = lambda: "+0"
            self.assertEqual(board._spawn_build(), board.BUILD)
        finally:
            board._build_stamp = orig

    def test_a_freshly_replaced_server_is_not_replaced_straight_back(self):
        """Backstop for anything the ordering cannot rank, so no cause can produce a
        kill-respawn loop faster than one swap per window."""
        with tempfile.TemporaryDirectory() as d:
            with open(board.versionfile(d), "w") as f:
                f.write("0.0.1+ancient")
            self.assertLess(board._server_age(d), board.BOARD_MIN_LIFE)
            orig = board.server_info
            try:
                board.server_info = lambda root: 41234
                port, started = board.ensure_server(d)
                self.assertEqual(port, 41234, "reused, despite being older than us")
                self.assertFalse(started)
            finally:
                board.server_info = orig


class CanonPanel(unittest.TestCase):
    """The panel read the wrong half of CANON.md.

    It ran a bullet regex of its own, which matches nothing in the registry TABLE and
    everything in the `## ⚠ Needs re-check` list printed above it. So "Canon · settled
    answers" was in fact listing the entries that were NOT settled, and its count was
    the size of the re-check queue. Clearing that queue emptied the panel, which reads
    as the canon disappearing when it is the opposite. The registry is now read with
    canon.py's own parser — one reader, so the two cannot drift apart again."""

    HEADER = ("# p · CANON\n\n> blurb\n\n## ⚠ Needs re-check\n%s\n\n## Registry\n"
              "| topic | dept | file | version | updated | affects | needs-recheck |\n"
              "|---|---|---|---|---|---|---|\n")

    def _write(self, d, rows, recheck="- none"):
        os.makedirs(os.path.join(d, "docs"), exist_ok=True)
        os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
        open(os.path.join(d, ".claude", "orchestrate.json"), "w").write("{}")
        body = "".join("| %s |\n" % " | ".join(r) for r in rows)
        open(os.path.join(d, "docs", "CANON.md"), "w", encoding="utf-8").write(
            (self.HEADER % recheck) + body)

    def test_the_registry_is_what_the_panel_shows(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d, [
                ["what colour?", "Frontend", "docs/DESIGN.md", "abc1234", "2026-07-28", "Frontend", "—"],
                ["what price?", "Marketing", "docs/pricing.md", "def5678", "2026-07-27", "Fin, Ops", "—"],
            ])
            dd = board.load_decisions(d)
            self.assertEqual(dd["canon_total"], 2)
            self.assertEqual([c["topic"] for c in dd["canon"]], ["what colour?", "what price?"])
            self.assertEqual(dd["canon"][0]["file"], "docs/DESIGN.md")
            self.assertEqual(dd["canon"][0]["dept"], "Frontend")

    def test_an_empty_recheck_queue_does_not_empty_the_panel(self):
        """The field case exactly: the registry was rebuilt clean, every flag cleared,
        and the panel went to zero — good news rendered as a disappearance."""
        with tempfile.TemporaryDirectory() as d:
            self._write(d, [["q", "CEO", "docs/a.md", "-", "2026-07-28", "all", "—"]],
                        recheck="- none")
            dd = board.load_decisions(d)
            self.assertEqual(dd["canon_total"], 1)
            self.assertEqual(dd["recheck_total"], 0)

    def test_a_flagged_row_is_marked_not_counted_as_the_whole_canon(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d, [
                ["stale one", "CEO", "docs/a.md", "-", "2026-07-01", "all", "Frontend, Ops"],
                ["fresh one", "CEO", "docs/b.md", "-", "2026-07-28", "all", "—"],
            ], recheck="- `stale one` → Frontend, Ops (updated 2026-07-01)")
            dd = board.load_decisions(d)
            self.assertEqual(dd["canon_total"], 2, "both rows are canon")
            self.assertEqual(dd["recheck_total"], 1, "one of them is flagged")
            self.assertEqual(dd["canon"][0]["recheck"], "Frontend, Ops")
            self.assertEqual(dd["canon"][1]["recheck"], "")

    def test_the_recheck_list_is_never_mistaken_for_registry_rows(self):
        """The old regex counted the bullets above the table. With four flagged topics
        and two registry rows it reported six, none of them a registry entry."""
        with tempfile.TemporaryDirectory() as d:
            self._write(d, [
                ["q1", "CEO", "docs/a.md", "-", "2026-07-28", "all", "—"],
                ["q2", "CEO", "docs/b.md", "-", "2026-07-28", "all", "—"],
            ], recheck="\n".join("- `t%d` → Frontend (updated 2026-07-01)" % i for i in range(4)))
            dd = board.load_decisions(d)
            self.assertEqual(dd["canon_total"], 2)
            self.assertNotIn("t0", [c["topic"] for c in dd["canon"]])


class RetiredCards(unittest.TestCase):
    """Retired cards used to leave the panel entirely: the digest is regenerated from the
    ACTIVE card dir, so a finished card moved to <board>/done/ stopped existing rather
    than landing in Done."""

    def _card(self, ddir, num, name="THING", **fields):
        os.makedirs(ddir, exist_ok=True)
        fm = {"id": num, "name": name, "status": "done", "dept": "Ops"}
        fm.update(fields)
        body = "---\n" + "".join("%s: %s\n" % (k, v) for k, v in fm.items()) + "---\n\nb\n"
        p = os.path.join(ddir, "%s-%s.md" % (num, name))
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
        return p

    def test_a_retired_card_comes_back_as_a_done_task(self):
        with tempfile.TemporaryDirectory() as d:
            self._card(d, "409", "CHECKOUT", shipped="2026-07-27", task_id="113")
            rows = board.retired_tasks(d)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["label"], "#409")
            self.assertEqual(rows[0]["status"], "done")
            self.assertEqual(rows[0]["task_id"], "113")
            self.assertTrue(rows[0]["retired"])

    def test_the_shipped_date_drives_the_today_split(self):
        with tempfile.TemporaryDirectory() as d:
            self._card(d, "1", "A", shipped="2026-07-27")
            self.assertEqual(board.retired_tasks(d)[0]["date"], "2026-07-27")

    def test_since_is_the_fallback_when_nothing_shipped_it(self):
        with tempfile.TemporaryDirectory() as d:
            self._card(d, "1", "A", since='"2026-07-25T10:00"')
            self.assertEqual(board.retired_tasks(d)[0]["date"], "2026-07-25")

    def test_a_dateless_card_still_appears(self):
        """A lingering done card with no traceable date falls to Earlier, not to nowhere."""
        with tempfile.TemporaryDirectory() as d:
            self._card(d, "1", "A")
            self.assertEqual(len(board.retired_tasks(d)), 1)

    def test_newest_first(self):
        with tempfile.TemporaryDirectory() as d:
            self._card(d, "1", "OLD", shipped="2026-07-01")
            self._card(d, "2", "NEW", shipped="2026-07-27")
            self.assertEqual([r["label"] for r in board.retired_tasks(d)], ["#2", "#1"])

    def test_done_is_a_tail_not_the_whole_archive(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(40):
                self._card(d, str(100 + i), "C%d" % i, shipped="2026-07-%02d" % (i % 28 + 1))
            self.assertEqual(len(board.retired_tasks(d)), board.DONE_TAIL)

    def test_the_cap_keeps_the_NEWEST(self):
        """A cap that dropped recent completions would recreate the bug it fixes."""
        with tempfile.TemporaryDirectory() as d:
            for i in range(30):
                self._card(d, str(200 + i), "C%d" % i, shipped="2026-06-%02d" % (i % 28 + 1))
            self._card(d, "999", "NEWEST", shipped="2026-12-31")
            self.assertEqual(board.retired_tasks(d)[0]["label"], "#999")

    def test_a_branch_office_card_keeps_its_badge(self):
        with tempfile.TemporaryDirectory() as d:
            self._card(d, "5", "ART", dept="Marketing", shipped="2026-07-27")
            self.assertTrue(board.retired_tasks(d, ext=["marketing"])[0]["external"])

    def test_non_cards_are_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "README.md"), "w").close()
            open(os.path.join(d, "notes.txt"), "w").close()
            self.assertEqual(board.retired_tasks(d), [])

    def test_a_missing_done_dir_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(board.retired_tasks(os.path.join(d, "nope")), [])


class SendInterlock(unittest.TestCase):
    """Send now presses Return for them, so every check that stands between a staged answer
    and a keystroke in the wrong pane is load-bearing. Each test here names one of them."""

    LOOKUP = "/dev/ttys002\n✳ some claude session\nscreen text before\n"

    def setUp(self):
        # Re-enabled ONLY here, and only with every pane-touching call mocked out (see
        # _run). Never by unsetting the env var: that would also un-gate anything this
        # suite calls indirectly.
        self._off = unittest.mock.patch.object(board, "_iterm_disabled", lambda: False)
        self._off.start(); self.addCleanup(self._off.stop)
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        board.capture_iterm_target(self.d.name, "w1t0p0:GUID-1", {"cwd": "/x"})

    def _run(self, line, scripts, runs_claude=True, seat="ceo"):
        """Drive iterm_prime with a scripted osascript. `scripts` maps the AppleScript
        constant to its stdout; the calls it actually made land in self.calls."""
        self.calls = []

        def fake_osa(script, *args, **kw):
            name = ("lookup" if script in (board.ITERM_LOOKUP_APPLESCRIPT,
                                           board.ITERM_PROBE_APPLESCRIPT) else
                    "write" if script is board.ITERM_WRITE_APPLESCRIPT else
                    "type" if script is board.ITERM_TYPE_APPLESCRIPT else
                    # The echo is WAITED for, not sampled once; each re-read of the screen
                    # is its own call and must be answerable separately, or an unnamed
                    # script falls through to "enter" and the harness presses Return on a
                    # pane it never saw the text on.
                    "read" if script is board.ITERM_READ_APPLESCRIPT else "enter")
            self.calls.append(name)
            v = scripts.get(name)
            if isinstance(v, list):                 # answer successive reads in order
                return v.pop(0) if v else None
            return v

        live = {"/dev/ttys002": "/x"} if runs_claude else {}
        guid = (board.read_iterm_target(self.d.name) or {}).get("guid")
        with unittest.mock.patch.object(board, "_osa", fake_osa), \
             unittest.mock.patch.object(board, "_claude_ttys", lambda: live), \
             unittest.mock.patch.object(board, "_tty_runs_claude", lambda t: runs_claude), \
             unittest.mock.patch.object(board, "_seat_kind", lambda *a, **k: seat), \
             unittest.mock.patch.object(board, "iterm_panes", lambda r: []), \
             unittest.mock.patch.object(board, "default_guid", lambda r: guid):
            return board.iterm_prime(self.d.name, line)

    def test_echoed_text_is_submitted(self):
        got = self._run("ship it", {"lookup": self.LOOKUP, "write": "ok",
                                    "read": "> ship it", "enter": "ok"})
        self.assertEqual(got, "ok")
        self.assertEqual(self.calls, ["lookup", "read", "write", "read", "enter"])

    def test_a_write_that_lands_but_cannot_be_confirmed_is_typed_not_err(self):
        """The reported failure. `contents of s` can hang (measured past 30s on a live
        pane while a tty+name probe took 2.9s) and the write used to sit BEHIND it in one
        script — so the 8s timeout killed osascript with the text already in their box and
        the caller said "iTerm could not be reached". Neither true nor safe to retry.
        The write is its own call now: a screen read that fails costs the echo check and
        nothing else."""
        got = self._run("ship it", {"lookup": self.LOOKUP, "write": "ok",
                                    "read": None, "enter": "ok"})
        self.assertEqual(got, "typed")
        self.assertNotIn("enter", self.calls)     # never pressed on an unconfirmed screen

    def test_only_a_failed_WRITE_means_nothing_landed(self):
        got = self._run("ship it", {"lookup": self.LOOKUP, "write": None})
        self.assertEqual(got, "err")
        self.assertNotIn("enter", self.calls)

    def test_a_pane_without_claude_is_refused_before_typing(self):
        got = self._run("ship it", {"lookup": self.LOOKUP}, runs_claude=False)
        self.assertEqual(got, "nosession")
        self.assertEqual(self.calls, ["lookup"])      # nothing was typed into it at all

    def test_a_seat_that_is_not_hers_is_refused_before_typing(self):
        # The reported failure: an external 分公司 held the main office's target, so Send typed
        # their decisions into the branch. Blocking future claims is not enough — an already
        # poisoned record must not deliver either.
        got = self._run("ship it", {"lookup": self.LOOKUP}, seat="branch")
        self.assertEqual(got, "wrongseat")
        self.assertEqual(self.calls, ["lookup"])

    def test_a_seat_she_pinned_herself_is_never_second_guessed(self):
        rec = board.read_iterm_target(self.d.name); rec["pinned"] = True
        open(board.iterm_target_file(self.d.name), "w").write(json.dumps(rec))
        got = self._run("ship it", {"lookup": self.LOOKUP, "write": "ok",
                                    "read": "> ship it", "enter": "ok"},
                        seat="other")
        self.assertEqual(got, "ok")

    def test_a_missing_pane_is_refused_before_typing(self):
        self.assertEqual(self._run("ship it", {"lookup": "\n"}), "notfound")
        self.assertEqual(self.calls, ["lookup"])

    def test_return_is_never_pressed_when_the_echo_is_not_seen(self):
        # The pane took the text somewhere we cannot see. Leaving it unsubmitted is the
        # whole safety story: a blind Return here is a sentence run as a command.
        got = self._run("ship it", {"lookup": self.LOOKUP, "write": "ok",
                                    "read": ["before", "before"], "enter": "ok"})
        self.assertEqual(got, "typed")
        self.assertNotIn("enter", self.calls)

    def test_a_new_paste_chip_counts_as_the_echo(self):
        # Claude Code folds a bulk write into "Pasted text #n" instead of echoing it; the
        # chip is equally good evidence the text is in the input box.
        long = "x" * 400
        got = self._run(long, {"lookup": self.LOOKUP, "write": "ok",
                               "read": ["before-only", "[Pasted text #1 +6 lines]"],
                               "enter": "ok"})
        self.assertEqual(got, "ok")

    def test_a_paste_chip_that_was_already_there_does_not_count(self):
        chip = "[Pasted text #1 +6 lines]"
        got = self._run("x" * 400, {"lookup": "/dev/ttys002\n✳ s", "write": "ok",
                                    "read": [chip, chip, chip, chip, chip, chip, chip,
                                             chip, chip, chip],
                                    "enter": "ok"})
        self.assertEqual(got, "typed")
        self.assertNotIn("enter", self.calls)

    def test_target_record_is_json_and_carries_who_and_where(self):
        rec = board.read_iterm_target(self.d.name)
        self.assertEqual(rec["guid"], "GUID-1")
        self.assertEqual(rec["cwd"], "/x")
        self.assertTrue(rec["at"])

    def test_a_legacy_bare_guid_file_still_delivers(self):
        with tempfile.TemporaryDirectory() as d:
            open(board.iterm_target_file(d), "w").write("w1t0p0:OLD-GUID")
            self.assertEqual(board.read_iterm_target(d)["guid"], "OLD-GUID")

    def test_a_branch_session_can_never_take_the_ceo_seat(self):
        # The Marketing 分公司 runs as its OWN top-level session out of a worktree, so it
        # carries none of the teammate stamps the lead guard looks for — is_lead calls it a
        # lead. Last-writer-wins therefore handed it the CEO's pane at its first turn end.
        with tempfile.TemporaryDirectory() as main:
            wt = os.path.join(main, ".claude", "worktrees", "Marketing")
            os.makedirs(os.path.join(wt, ".claude"))
            open(os.path.join(wt, ".claude", "office.json"), "w").write('{"office":"Marketing"}')
            board.capture_iterm_target(main, "w:CEO-PANE", {"cwd": main, "session_id": "ceo"})
            self.assertFalse(board.capture_iterm_target(
                main, "w:BRANCH-PANE", {"cwd": wt, "session_id": "mkt"}))
            self.assertEqual(board.read_iterm_target(main)["guid"], "CEO-PANE")
            self.assertEqual(board._seat_kind(main, wt), "branch")
            self.assertEqual(board._seat_kind(main, main), "ceo")
            self.assertEqual(board._seat_kind(main, "/somewhere/else"), "other")

    def test_a_live_incumbent_keeps_the_seat_against_a_bystander(self):
        with tempfile.TemporaryDirectory() as main:
            board.capture_iterm_target(main, "w:CEO-PANE", {"cwd": main, "session_id": "ceo"})
            with unittest.mock.patch.object(board, "_target_alive", lambda r: True):
                self.assertFalse(board.capture_iterm_target(
                    main, "w:OTHER", {"cwd": main, "session_id": "bystander"}))
            self.assertEqual(board.read_iterm_target(main)["guid"], "CEO-PANE")
            # …and releases it once that pane is gone.
            with unittest.mock.patch.object(board, "_target_alive", lambda r: False):
                self.assertTrue(board.capture_iterm_target(
                    main, "w:OTHER", {"cwd": main, "session_id": "bystander"}))
            self.assertEqual(board.read_iterm_target(main)["guid"], "OTHER")

    def test_the_holder_refreshes_its_own_seat_every_turn(self):
        with tempfile.TemporaryDirectory() as main:
            board.capture_iterm_target(main, "w:PANE-A", {"cwd": main, "session_id": "ceo"})
            with unittest.mock.patch.object(board, "_target_alive", lambda r: True):
                # same session, new pane (they moved the tab) — always allowed
                self.assertTrue(board.capture_iterm_target(
                    main, "w:PANE-B", {"cwd": main, "session_id": "ceo"}))
            self.assertEqual(board.read_iterm_target(main)["guid"], "PANE-B")

    def test_a_pinned_seat_survives_every_automatic_claim(self):
        with tempfile.TemporaryDirectory() as main:
            board.capture_iterm_target(main, "w:BOSSPANE", {"cwd": main, "session_id": "ceo"},
                                       force=True)
            rec = board.read_iterm_target(main); rec["pinned"] = True
            open(board.iterm_target_file(main), "w").write(json.dumps(rec))
            with unittest.mock.patch.object(board, "_target_alive", lambda r: False):
                self.assertFalse(board.capture_iterm_target(
                    main, "w:OTHER", {"cwd": main, "session_id": "other"}))
            self.assertEqual(board.read_iterm_target(main)["guid"], "BOSSPANE")

    def test_a_legacy_record_does_not_get_to_hold_a_seat(self):
        # Written by the old last-writer-wins rule: it cannot say whose seat it is, so the
        # first real claim after the upgrade takes it rather than being locked out.
        with tempfile.TemporaryDirectory() as main:
            open(board.iterm_target_file(main), "w").write("w1t0p0:LEGACY")
            with unittest.mock.patch.object(board, "_target_alive", lambda r: True):
                self.assertTrue(board.capture_iterm_target(
                    main, "w:CEO-PANE", {"cwd": main, "session_id": "ceo"}))
            self.assertEqual(board.read_iterm_target(main)["guid"], "CEO-PANE")

    def test_tty_runs_claude_ignores_background_and_non_claude(self):
        def ps(out):
            return unittest.mock.patch.object(
                board.subprocess, "run",
                lambda *a, **k: unittest.mock.Mock(stdout=out, returncode=0))
        with ps("Ss   login -fp genius\nS    -zsh\n"):
            self.assertFalse(board._tty_runs_claude("/dev/ttys002"))
        with ps("S    /usr/bin/claude\n"):            # backgrounded — not the live session
            self.assertFalse(board._tty_runs_claude("/dev/ttys002"))
        with ps("S+   /opt/homebrew/bin/claude -c\n"):
            self.assertTrue(board._tty_runs_claude("/dev/ttys002"))
        self.assertFalse(board._tty_runs_claude(""))



if __name__ == "__main__":
    unittest.main()


class SessionRegistry(unittest.TestCase):
    """One record per session_id, labelled with the last thing the Boss typed. A pane is not an
    identity; the hook holds the only join between a session and its pane."""

    def _t(self, d, rows, name="t.jsonl"):
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        return p

    def _user(self, text):
        return {"type": "user", "message": {"role": "user", "content": text}}

    def test_the_label_is_her_last_prompt(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._t(d, [self._user("first thing"), self._user("restart my board")])
            self.assertEqual(board.last_prompt(p), "restart my board")

    def test_hook_injections_and_control_frames_are_not_her(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._t(d, [
                self._user("the real question"),
                self._user('{"type":"shutdown_request","requestId":"x"}'),
                self._user("Another Claude session sent a message: hi"),
                self._user("<system-reminder>Local time: 10:00</system-reminder>"),
                {"type": "user", "isMeta": True, "message": {"role": "user", "content": "meta"}},
                {"type": "user", "message": {"role": "user", "content": [
                    {"type": "tool_result", "content": "output"}]}},
            ])
            self.assertEqual(board.last_prompt(p), "the real question")

    def test_a_prompt_survives_a_megabyte_of_tool_results(self):
        # A working session's last megabyte can be nothing but tool_result rows; a fixed
        # tail found no prompt at all in the transcript it was first tested against.
        with tempfile.TemporaryDirectory() as d:
            rows = [self._user("buried but mine")]
            rows += [{"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "content": "x" * 4000}]}} for _ in range(400)]
            p = self._t(d, rows)
            self.assertGreater(os.path.getsize(p), 1_500_000)
            self.assertEqual(board.last_prompt(p), "buried but mine")

    def test_a_session_registers_itself_and_stale_ones_are_pruned(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._t(d, [self._user("ship the thing")])
            board.register_session(d, {"session_id": "s1", "cwd": d, "transcript_path": p,
                                       "iterm": "w1t0p0:GUID-1", "agent": "Frontend"})
            reg = board.read_sessions(d)
            self.assertEqual(reg["s1"]["label"], "ship the thing")
            self.assertEqual(reg["s1"]["guid"], "GUID-1")
            self.assertEqual(reg["s1"]["agent"], "Frontend")
            reg["s1"]["seen"] = 0                      # older than SESSION_STALE_S
            open(board.session_file(d), "w").write(json.dumps(reg))
            board.register_session(d, {"session_id": "s2", "cwd": d, "transcript_path": p,
                                       "iterm": "w1t0p0:GUID-2"})
            self.assertEqual(sorted(board.read_sessions(d)), ["s2"])

    def test_registering_needs_a_session_id(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(board.register_session(d, {"cwd": d}))
            self.assertEqual(board.read_sessions(d), {})


class OriginRouting(unittest.TestCase):
    """An answer goes back to the session that raised the question. The origin is knowable
    at the moment the item is written, so nothing downstream has to guess a destination."""

    def test_an_item_records_the_pane_that_raised_it(self):
        with unittest.mock.patch.dict(os.environ, {"ITERM_SESSION_ID": "w1t0p0:PANE-A"}), \
             unittest.mock.patch.object(board, "_iterm_disabled", lambda: False):
            s = {"entries": []}
            e, _ = board.add_entry(s, "QA", "needs", "Postgres or SQLite?", NOW)
        self.assertEqual(e["src"], "PANE-A")

    def test_answers_split_by_origin_one_message_per_session(self):
        s = {"entries": []}
        board.add_entry(s, "QA", "needs", "a?", NOW, src="PANE-A")
        board.add_entry(s, "Ops", "needs", "b?", NOW, src="PANE-B")
        board.add_entry(s, "Legal", "needs", "c?", NOW, src="PANE-A")
        for eid, txt in (("QA-1", "yes"), ("Ops-1", "no"), ("Legal-1", "later")):
            board.basket_set(s, eid, "reply", txt, NOW)
        rec = board.board_send_mutate(s, NOW)
        by = {g["src"]: g for g in rec["groups"]}
        self.assertEqual(sorted(by), ["PANE-A", "PANE-B"])
        self.assertEqual(by["PANE-A"]["items"], ["QA-1", "Legal-1"])
        self.assertEqual(by["PANE-B"]["items"], ["Ops-1"])
        self.assertIn("yes", by["PANE-A"]["msg"])
        self.assertNotIn("no", by["PANE-A"]["msg"])      # Ops's answer never reaches QA

    def test_items_with_no_origin_route_by_department(self):
        # An item that recorded no pane is keyed by its DEPARTMENT, so the send path can
        # look up that department's own live seat instead of falling to the lead's box.
        s = {"entries": []}
        board.add_entry(s, "QA", "needs", "a?", NOW, src="")
        board.basket_set(s, "QA-1", "reply", "yes", NOW)
        rec = board.board_send_mutate(s, NOW)
        self.assertEqual([g["src"] for g in rec["groups"]], ["dept:QA#"])

    def test_delivery_is_inert_while_the_kill_switch_is_on(self):
        # The guard that was missing when a fixture's answer was submitted into their session.
        self.assertTrue(board._iterm_disabled())
        self.assertEqual(board.raiser_pane(), "")
        self.assertEqual(board.iterm_panes("/tmp"), [])
        with tempfile.TemporaryDirectory() as d:
            board.capture_iterm_target(d, "w:G", {"cwd": d, "session_id": "s"}, force=True)
            self.assertEqual(board.iterm_prime(d, "hi", "G"), "skip")


class DeptRouting(unittest.TestCase):
    """A teammate writes to the board from a process with no ITERM_SESSION_ID, so its items
    record no pane. Falling back to the board's default seat put the answer in the lead's
    input box — the department that asked has its own live session, and the registry has
    known where it is all along."""

    def test_an_item_with_no_pane_groups_by_department(self):
        s = {"entries": []}
        board.add_entry(s, "Frontend", "needs", "merge it?", NOW, src="")
        board.add_entry(s, "QA", "needs", "sign off?", NOW, src="")
        board.add_entry(s, "CEO", "needs", "which order?", NOW, src="CEO-PANE")
        for eid in ("Frontend-1", "QA-1", "CEO-1"):
            board.basket_set(s, eid, "reply", "yes", NOW)
        keys = sorted(g["src"] for g in board.board_send_mutate(s, NOW)["groups"])
        self.assertEqual(keys, ["CEO-PANE", "dept:Frontend#", "dept:QA#"])

    def test_dept_base_strips_the_card_number(self):
        self.assertEqual(board.dept_base("Frontend-988"), "Frontend")
        self.assertEqual(board.dept_base("Backend-IO-42"), "Backend-IO")
        self.assertEqual(board.dept_base("Registrar"), "Registrar")
        self.assertEqual(board.dept_base(""), "")

    def _reg(self, d, rows):
        open(board.session_file(d), "w").write(json.dumps(
            {str(i): r for i, r in enumerate(rows)}))

    def _live(self, guids):
        # one sweep reports every pane's tty; only the listed guids sit on a claude tty
        return (unittest.mock.patch.object(
                    board, "_pane_ttys", lambda: {g: "/dev/tty-%s" % g for g in guids}),
                unittest.mock.patch.object(
                    board, "_claude_ttys", lambda: {("/dev/tty-%s" % g): "/x" for g in guids}))

    def test_the_seat_named_for_the_card_wins_outright(self):
        # A teammate is dispatched per card and named for it, and the entry records its
        # card. That is an identity, not a ranking — verified against a live board where
        # Frontend-988 and Frontend-1018 were BOTH up, one waiting on the lead and one on
        # the Boss, so "whoever moved last" could not tell them apart.
        with tempfile.TemporaryDirectory() as d:
            self._reg(d, [{"agent": "Frontend-988",  "guid": "A", "seen": 100},
                          {"agent": "Frontend-1018", "guid": "B", "seen": 900}])
            p1, p2 = self._live({"A", "B"})
            with p1, p2:
                self.assertEqual(board.dept_guid(d, "Frontend", "988"), ("A", ""))
                self.assertEqual(board.dept_guid(d, "Frontend", "1018"), ("B", ""))

    def test_two_live_seats_and_no_card_is_refused_not_guessed(self):
        with tempfile.TemporaryDirectory() as d:
            self._reg(d, [{"agent": "Frontend-988",  "guid": "A", "seen": 100},
                          {"agent": "Frontend-1018", "guid": "B", "seen": 900}])
            p1, p2 = self._live({"A", "B"})
            with p1, p2:
                guid, why = board.dept_guid(d, "Frontend", "")
                self.assertIsNone(guid)                       # never the newest
                self.assertIn("2 live seats", why)
                self.assertIn("Frontend-988", why)
                self.assertIn("Frontend-1018", why)
                # a card with no seat of its own is equally refused
                self.assertIsNone(board.dept_guid(d, "Frontend", "1017")[0])

    def test_one_live_seat_is_unambiguous_with_or_without_a_card(self):
        with tempfile.TemporaryDirectory() as d:
            self._reg(d, [{"agent": "Frontend-988",  "guid": "A", "seen": 100},
                          {"agent": "Frontend-1018", "guid": "B", "seen": 900}])
            p1, p2 = self._live({"A"})                        # only 988 is still up
            with p1, p2:
                self.assertEqual(board.dept_guid(d, "Frontend", "")[0], "A")
                self.assertEqual(board.dept_guid(d, "Frontend", "1017")[0], "A")

    def test_a_department_whose_seat_is_dead_falls_through(self):
        with tempfile.TemporaryDirectory() as d:
            open(board.session_file(d), "w").write(
                json.dumps({"a": {"agent": "Frontend-988", "guid": "GONE", "seen": 100}}))
            with unittest.mock.patch.object(board, "_pane_ttys", lambda: {}), \
                 unittest.mock.patch.object(board, "_claude_ttys", lambda: {}):
                guid, why = board.dept_guid(d, "Frontend", "988")
                self.assertIsNone(guid)
                self.assertIn("no live seat", why)


class AgesAreTicked(unittest.TestCase):
    """Every age drawn on the page must carry `data-ts`, because `retick()` is the ONLY
    thing that keeps them honest: the panel redraws on data change, so a rendered age is
    frozen from the moment it is written until the data moves — which on a quiet board is
    never. The conversation rail shipped without it and sat at `11m` for twelve minutes."""

    def _panel(self):
        return _board_source()

    def test_retick_updates_anything_carrying_data_ts(self):
        s = self._panel()
        self.assertIn("document.querySelectorAll('[data-ts]')", s)

    def test_the_conversation_rail_age_is_ticked(self):
        s = self._panel()
        self.assertIn("class='ctime' data-ts=", s)

    def test_no_rendered_age_escapes_the_tick(self):
        # Scan the conversation layer for an age() written into markup without data-ts on
        # the same line. A new lane that forgets it is exactly how this recurs.
        s = self._panel()
        seg = s[s.index("// ---- Conversations (layout A)"):s.index("// ---- the persistent composer")]
        bad = [ln.strip() for ln in seg.split("\n")
               if "${" in ln and "age(" in ln and "data-ts" not in ln]
        self.assertEqual(bad, [], "age rendered without data-ts: %s" % bad)

    def test_a_quiet_poll_still_reticks(self):
        # The no-change early return must call retick() before it returns, or every clock
        # on the page stops the moment the board goes quiet.
        s = self._panel()
        i = s.index("if (raw === lastRaw)")
        self.assertIn("retick()", s[i:i + 240])


class PastedImages(unittest.TestCase):
    """The composer takes text only, so an item that needed a screenshot could not be
    answered from the board at all. A pasted image is written into the project and the
    message carries its path — the one form of an image the far session can open. The bytes
    arrive raw: base64-in-JSON grew a screenshot by a third and then escaped, parsed and
    decoded every one of them, four passes before a byte reached disk."""

    PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 64

    def test_an_image_lands_in_the_project_and_returns_its_path(self):
        with tempfile.TemporaryDirectory() as d:
            rel = board.write_paste(d, "Frontend-39", "image/png", self.PNG)
            self.assertTrue(rel.startswith("docs/board/pastes/"))
            self.assertTrue(rel.endswith("-Frontend-39.png"))
            self.assertTrue(os.path.exists(os.path.join(d, rel)))
            self.assertEqual(open(os.path.join(d, rel), "rb").read(), self.PNG)

    def test_only_image_types_are_written(self):
        with tempfile.TemporaryDirectory() as d:
            for bad in ("text/html", "application/json", "", "image/svg+xml", None):
                self.assertIsNone(board.write_paste(d, "x", bad, self.PNG), repr(bad))
            self.assertIsNone(board.write_paste(d, "x", "image/png", b""))

    def test_a_content_type_with_parameters_still_resolves(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(board.write_paste(d, "x", "image/png; charset=binary", self.PNG))

    def test_the_filename_cannot_escape_the_directory(self):
        # The name is a label, never a path: it is stripped to [A-Za-z0-9-] and the real
        # filename is generated. A client-supplied name is the one field that could climb.
        with tempfile.TemporaryDirectory() as d:
            rel = board.write_paste(d, "../../etc/passwd", "image/png", self.PNG)
            self.assertTrue(rel.startswith("docs/board/pastes/"))
            self.assertNotIn("..", rel)
            full = os.path.realpath(os.path.join(d, rel))
            self.assertTrue(full.startswith(os.path.realpath(d) + os.sep))

    def test_an_oversized_paste_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(board.write_paste(d, "big", "image/png",
                                                b"x" * (board.PASTE_MAX + 1)))


class ClickablePaths(unittest.TestCase):
    """The two forms a render is actually cited as — an absolute path into a dept worktree,
    and the FOLDER holding the set — were the two the link could not open. An absolute path
    was refused before the realpath pin even ran, and a directory was refused for being one."""

    def test_a_directory_resolves_and_is_marked_unservable(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "docs", "mockups", "1019-render"))
            got = board.resolve_file(d, "docs/mockups/1019-render/")
            self.assertIsNotNone(got)
            self.assertIsNone(got[1], "a directory has no content type — /file must refuse it")

    def test_an_absolute_path_inside_the_project_resolves(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "docs"))
            f = os.path.join(d, "docs", "x.md")
            open(f, "w").write("x")
            got = board.resolve_file(d, f)
            self.assertIsNotNone(got)
            self.assertEqual(os.path.realpath(got[0]), os.path.realpath(f))

    def test_the_realpath_pin_still_holds(self):
        with tempfile.TemporaryDirectory() as d:
            for bad in ("/etc/passwd", "/etc/", "../../etc/passwd", "~/.ssh/", "/"):
                self.assertIsNone(board.resolve_file(d, bad), bad)

    def test_both_matchers_take_a_trailing_slash_directory(self):
        # The panel's regex and its python twin must agree on what a path is, or the desk
        # mirror and the page disagree about what to link.
        t = "图在 /a/b/docs/mockups/1019-render-2026-08-03/(01 亮色) 和 docs/x.png"
        self.assertIn("/a/b/docs/mockups/1019-render-2026-08-03/",
                      [m[1] for m in board.DESK_FILE_RE.findall(t)])
        src = _board_source()
        self.assertIn("(?:\\/?(?:[\\w.\\-一-鿿]+\\/){2,})", src)


class DarkRulesKeepTheirSelector(unittest.TestCase):
    """A dark-mode declaration that loses its `html.dark` prefix applies in BOTH themes —
    the theme toggle shipped as a black blob in light mode twice, because the edit that
    dropped the prefix failed silently and the check that was supposed to catch it matched
    the `:hover` line instead of the rule itself."""

    # the panel's dark chrome backgrounds; none of these may sit on a bare selector
    DARK_BG = ("#232120", "#262422", "#2b2825", "#201e1c", "#282523", "#1c1a18")

    def _css(self):
        s = _board_source()
        return s[s.index("<style>"):s.index("</style>")]

    def test_no_bare_selector_paints_a_dark_background(self):
        css, bad = self._css(), []
        for m in re.finditer(r"([^\n{}]+)\{([^}]*)\}", css):
            sel, body = m.group(1).strip(), m.group(2)
            if sel.startswith(("html.dark", "@", ":root")) or "dark" in sel:
                continue
            for c in self.DARK_BG:
                if re.search(r"background(?:-color)?\s*:\s*%s\b" % re.escape(c), body):
                    bad.append((sel[:60], c))
        self.assertEqual(bad, [], "dark background on a bare selector: %s" % bad)

    def test_the_theme_toggle_keeps_its_dark_prefix(self):
        css = self._css()
        self.assertIn("html.dark #themetog { background: #232120", css)
        self.assertNotIn("\n#themetog { background: #232120", css)

    def test_the_sound_switch_is_declared_once(self):
        css = self._css()
        self.assertEqual(css.count("#sndtog { background: none"), 1)


class TheWriterGetsTheAnswer(unittest.TestCase):
    """Whoever wrote an item gets the answer. `src` is the pane the WRITING process sat in,
    so an item the lead relayed on a department's behalf answers to the LEAD — it relayed
    the question, so it has to see the decision. Preferring the department's own seat cut
    the lead out of a conversation it was carrying."""

    def test_a_relayed_item_answers_to_the_relayer(self):
        s = {"entries": []}
        board.add_entry(s, "Prof_Academic", "needs", "a?", NOW, src="LEAD-PANE")
        board.basket_set(s, "Prof_Academic-1", "reply", "y", NOW)
        self.assertEqual([g["src"] for g in board.board_send_mutate(s, NOW)["groups"]],
                         ["LEAD-PANE"])

    def test_an_item_a_department_wrote_itself_answers_to_that_department(self):
        s = {"entries": []}
        board.add_entry(s, "Frontend", "needs", "a?", NOW, src="FE-PANE")
        board.basket_set(s, "Frontend-1", "reply", "y", NOW)
        self.assertEqual([g["src"] for g in board.board_send_mutate(s, NOW)["groups"]],
                         ["FE-PANE"])

    def test_an_item_with_no_pane_still_falls_back_to_its_department(self):
        s = {"entries": []}
        board.add_entry(s, "QA", "needs", "a?", NOW, src="")
        board.basket_set(s, "QA-1", "reply", "y", NOW)
        self.assertEqual([g["src"] for g in board.board_send_mutate(s, NOW)["groups"]],
                         ["dept:QA#"])


class StagedAnswersSurvive(unittest.TestCase):
    """Staged answers lived only in memory and in a fire-and-forget POST, and `syncBasket`
    CLEARED the local basket to adopt the server's. A restarted server — whose store had not
    caught the last POST — therefore emptied a page of typed answers. It happened once. The
    page is now the record: it writes to localStorage the moment anything is staged, and the
    server can only ADD what this browser has not seen."""

    def _panel(self):
        return _board_source()

    def test_sync_merges_and_never_clears(self):
        seg = self._panel()
        i = seg.index("function syncBasket(")
        body = seg[i:i + 700]
        self.assertNotIn("BASKET.clear()", body, "the server must not be able to empty the page")
        self.assertIn("if(!BASKET.has(x.id))", body, "the server may only add what is unseen")

    def test_every_basket_mutation_persists(self):
        # Each place the basket changes must persist before anything downstream can fail.
        src = _board_source()
        for site in ("function unstage(", "function archive(", "BASKET.clear(); basketSave()"):
            i = src.index(site)
            self.assertIn("basketSave()", src[i:i + 260], site)

    def test_the_page_restores_its_basket_on_load(self):
        seg = self._panel()
        self.assertIn("basketLoad();", seg)
        self.assertIn("localStorage.getItem(BKEY)", seg)

    def test_staging_also_reaches_the_clipboard(self):
        src = _board_source()
        i = src.index("if(text) BASKET.set(id,{kind,text})")
        self.assertIn("clipboard", src[i:i + 700],
                      "whatever else breaks, the words must survive")


class EchoSurvivesAWrappedPane(unittest.TestCase):
    """`contents of s` returns the VISIBLE screen, so in a narrow pane — one sharing its
    width with a teammate panel — a long message wraps and its END is not on screen.
    Checking the tail therefore failed every time and the Return was never pressed, on a
    pane that had taken the text perfectly. Field case: Prof_Academic-11."""

    SCREEN = "@Prof_Academic-1020 ──\n❯ Prof_Academic-11 \n  asks: (board"
    MSG = "[Boss Board] Prof_Academic-11 asks: (board self-test — ignore)"

    def _run(self, msg, after, seat="ceo"):
        d = tempfile.TemporaryDirectory(); self.addCleanup(d.cleanup)
        board.capture_iterm_target(d.name, "w:G", {"cwd": "/x", "session_id": "s"})
        look = "/dev/ttys009\n✳ pane\nbefore-only"
        calls = []

        def osa(script, *a, **k):
            n = ("lookup" if script in (board.ITERM_LOOKUP_APPLESCRIPT,
                                        board.ITERM_PROBE_APPLESCRIPT) else
                 "type" if script is board.ITERM_TYPE_APPLESCRIPT else
                 # Re-reads while waiting for the echo see the SAME screen: this pane's
                 # answer does not change, so waiting cannot turn a refusal into a send.
                 "read" if script is board.ITERM_READ_APPLESCRIPT else "enter")
            calls.append(n)
            return {"lookup": look, "type": look + "\n" + after,
                    "read": after, "enter": "ok"}[n]

        with unittest.mock.patch.object(board, "_iterm_disabled", lambda: False), \
             unittest.mock.patch.object(board, "_osa", osa), \
             unittest.mock.patch.object(board, "_claude_ttys", lambda: {"/dev/ttys009": "/x"}), \
             unittest.mock.patch.object(board, "_seat_kind", lambda *a, **k: seat), \
             unittest.mock.patch.object(board, "default_guid", lambda r: "G"):
            return board.iterm_prime(d.name, msg), calls

    def test_a_wrapped_message_still_submits(self):
        got, calls = self._run(self.MSG, self.SCREEN)
        self.assertEqual(got, "ok", "a pane that took the text must get its Return")
        self.assertIn("enter", calls)

    def test_the_old_tail_check_would_have_refused_this(self):
        self.assertNotIn(board._squash(self.MSG)[-40:], board._squash(self.SCREEN))

    def test_a_pane_that_never_took_the_text_is_still_refused(self):
        got, calls = self._run(self.MSG, "some unrelated output scrolled past")
        self.assertEqual(got, "typed")
        self.assertNotIn("enter", calls)


class IgnoreClearsTheDesk(unittest.TestCase):
    """`read` only folds an INFORMATION row. A needs-you item carries no such flag, so
    ticking it left the ask sitting on the desk while a toast claimed otherwise."""

    def test_ignoring_a_needs_you_item_resolves_it(self):
        s = {"entries": []}
        board.add_entry(s, "Prof_Academic", "needs", "decide?", NOW)
        board.set_status(s, "Prof_Academic-1", "resolved", NOW, sum="(ignored — no reply sent)")
        e = board.get_entry(s, "Prof_Academic-1")
        self.assertEqual(e["status"], "resolved")
        self.assertIn("ignored", e["sum"])

    def test_read_alone_would_not_have_cleared_it(self):
        s = {"entries": []}
        board.add_entry(s, "Prof_Academic", "needs", "decide?", NOW)
        board.set_read(s, "Prof_Academic-1", True, NOW)
        self.assertEqual(board.get_entry(s, "Prof_Academic-1")["status"], "open")

    def test_the_page_calls_ignore_not_read(self):
        src = _board_source()
        i = src.index("function ignoreItem(")
        body = src[i:i + 480]
        self.assertIn("post('/ignore'", body)
        self.assertNotIn("post('/read'", body)


class SendFailureIsOnlyARequestFailure(unittest.TestCase):
    """The try wrapped the whole of the post-send handling, so any error after the request
    — a toast, a re-render, a copy — reported "Send failed" for a message the session had
    already received. The most expensive kind of wrong: it tells their to send it again."""

    def test_the_request_has_its_own_catch(self):
        src = _board_source()
        i = src.index("async function sendBasket()")
        seg = src[i:i + 1400]
        self.assertIn("j = await (await postT(`/send`, {}, 45000)).json();", seg)
        # the failure toast must sit in the catch that wraps ONLY the request
        req = seg.index("j = await (await postT(`/send`, {}, 45000)).json();")
        nxt = seg.index("}catch(e){", req)
        self.assertIn("Send failed", seg[nxt:nxt + 500])   # the catch grew a timeout branch

    def test_a_later_error_does_not_claim_failure(self):
        src = _board_source()
        i = src.index("The message went. Anything broken here is display only")
        self.assertIn("Sent.", src[i:i + 240])


class PanelActuallyRuns(unittest.TestCase):
    """A parse cannot catch a temporal dead zone, and neither can a top-level run: a TDZ
    fires only when the function reading the binding is CALLED. `drawComposer` read `ta`
    three lines before `const ta` and blanked the entire board — the parse passed, the
    top-level run passed, and the page was white. This harness calls the draw functions."""

    def test_the_panel_script_runs_and_its_draw_functions_can_be_called(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not available")
        here = os.path.dirname(os.path.abspath(__file__))
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
            f.write(board.PAGE)
            page = f.name
        self.addCleanup(os.unlink, page)
        r = subprocess.run([node, os.path.join(here, "panel_smoke.js"), page],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, (r.stdout or "") + (r.stderr or ""))
        self.assertIn("panel smoke: OK", r.stdout)


class HerOwnRingtones(unittest.TestCase):
    """The arrival sound is played by the SERVER, from ~/.claude/clock-in-sounds, so it
    rings whether or not the tab is open — and rings ONCE. A page-side chime beside it
    would double every arrival they are looking at."""

    def test_a_supplied_file_is_found_by_kind(self):
        with tempfile.TemporaryDirectory() as d:
            with unittest.mock.patch.object(board, "SOUND_DIR", d):
                self.assertIsNone(board.sound_for("needs"))
                open(os.path.join(d, "needs.m4a"), "wb").write(b"x")
                self.assertTrue(board.sound_for("needs").endswith("needs.m4a"))
                open(os.path.join(d, "info.mp3"), "wb").write(b"x")
                self.assertTrue(board.sound_for("info").endswith("info.mp3"))

    def test_no_file_means_no_custom_sound_not_a_crash(self):
        with tempfile.TemporaryDirectory() as d:
            with unittest.mock.patch.object(board, "SOUND_DIR", d):
                self.assertIsNone(board.sound_for("needs"))
                self.assertFalse(board.play_sound("needs"))

    def test_the_banner_drops_its_system_sound_when_hers_played(self):
        # Otherwise an arrival rings twice, in two different voices.
        src = _board_source()
        i = src.index("def notify_entry(")
        seg = src[i:i + 2800]
        self.assertIn("own = play_sound(kind)", seg)
        self.assertIn("if not own:", seg)

    def test_the_page_no_longer_rings(self):
        src = _board_source()
        i = src.index("function ring(kind){")
        self.assertIn("if(true) return;", src[i:i + 400])


class AMessageWearsItsCreationTime(unittest.TestCase):
    """A message's time is when it was WRITTEN. `updated` moves on any later touch — a read
    tick, a resolve, a batch sweep — so two messages written an hour apart both read 22:46
    because one pass had touched them both."""

    def test_the_clock_and_the_day_divider_read_created(self):
        src = _board_source()
        i = src.index("function msgRow(e, T){")
        self.assertIn("clockOf(e.created || tsOf(e))", src[i:i + 2600])
        # The thread interleaves the Boss's own messages with the items, so each node carries the
        # time it happened and the divider reads THAT — for an item it is still `created`.
        j = src.index("const stream = rows.map(")
        self.assertIn("at: e.created || tsOf(e)", src[j:j + 220])
        self.assertIn("const L = dayLabel(n.at);", src[j:j + 420])

    def test_her_own_message_is_dated_when_she_sent_it(self):
        src = _board_source()
        i = src.index("function outBub(e, title, text, at){")
        seg = src[i:i + 600]
        self.assertIn("clockOf(at)", seg)
        self.assertIn("data-ts='${esc(at||'')}'", seg, "or retick cannot keep it honest")
        # Legacy entries carry no send log; their reply is dated by the update that WAS the
        # reply, which is the best the record has.
        j = src.index("const said = mine.length")
        self.assertIn("outBub(e, title, e.sum, e.updated)", src[j:j + 260])


class BannersReachTheScreen(unittest.TestCase):
    """terminal-notifier posts under its own bundle, which macOS never registers in
    Notification Centre — so every banner it sent was ACCEPTED (exit 0) and silently
    dropped. Hours of arrivals produced nothing while the code reported success. Sending as
    an application the system already trusts fixes it; `-appIcon` still carries our mark."""

    def _args(self, kind="needs"):
        seen = {}
        with tempfile.TemporaryDirectory() as d:
            with unittest.mock.patch.object(board, "_iterm_disabled", lambda: False), \
                 unittest.mock.patch.object(board, "NOTIFIER", __file__), \
                 unittest.mock.patch.object(board, "play_sound", lambda k: False), \
                 unittest.mock.patch.object(board.subprocess, "Popen",
                                            lambda a, **k: seen.setdefault("a", a)):
                board.notify_entry(d, {"id": "X-1", "dept": "Frontend",
                                       "kind": "info" if kind == "info" else "needs",
                                       "text": "subject :: detail"}, 1234)
        return seen.get("a", [])

    def test_it_sends_under_the_default_browser_identity(self):
        """With a spoofed sender the click can only ACTIVATE the sender — so the sender
        is the default browser, where the board tab already lives. Script Editor
        remains the fallback when the browser choice cannot be read."""
        a = self._args()
        self.assertIn("-sender", a)
        self.assertEqual(a[a.index("-sender") + 1], board._default_browser())
        self.assertIn("-open", a)          # harmless under the spoof, live if native

    def test_the_browser_lookup_falls_back_to_the_trusted_sender(self):
        with unittest.mock.patch.object(board.os.path, "expanduser",
                                        lambda p: "/nonexistent/ncprefs"):
            self.assertEqual(board._default_browser(), board.NOTIFY_SENDER)

    def test_our_own_icon_still_overrides(self):
        a = self._args()
        if os.path.exists(board.BOARD_ICON):
            self.assertIn("-appIcon", a)

    def test_the_department_is_the_title_and_the_detail_is_the_body(self):
        a = self._args()
        self.assertEqual(a[a.index("-title") + 1], "Frontend · Needs you")
        self.assertEqual(a[a.index("-subtitle") + 1], "subject")
        self.assertEqual(a[a.index("-message") + 1], "detail")
        self.assertEqual(self._args("info")[a.index("-title") + 1], "Frontend")


class TheWatcherCannotGetStuckSeeding(unittest.TestCase):
    """`first = False` sat INSIDE the try, so one failure anywhere in the first pass — a
    half-written store read mid-save is enough — left the watcher permanently seeding. It
    announced nothing ever again, silently, because the except swallowed the reason. Not one
    arrival banner appeared for a day."""

    def test_first_is_cleared_outside_the_try(self):
        src = _board_source()
        i = src.index("def watcher():")
        seg = src[i:i + 3000]
        j = seg.index("except Exception as exc:")
        self.assertIn("first = False", seg[j:], "clearing the seed flag must survive a failure")
        self.assertNotIn("first = False", seg[:j], "it must not sit inside the try")

    def test_a_failure_is_recorded_rather_than_swallowed(self):
        src = _board_source()
        i = src.index("def watcher():")
        seg = src[i:i + 3000]
        self.assertIn("watcher.log", seg)
        self.assertIn("ERROR", seg)


class SendIsOnePress(unittest.TestCase):
    """Pressing Send staged the answer, redrew the tray — complete with its own
    "Send to session" button — and only THEN fired the request. For the seconds the request
    took, the page offered to send what was already being sent. The second press did nothing
    (a guard caught it), so Send read as needing two."""

    def test_the_send_is_claimed_before_the_redraw(self):
        src = _board_source()
        i = src.index("function commitCompose(send){")
        seg = src[i:i + 2600]
        j = seg.index("drawDesk(); drawComposer(true); renderTray();")
        self.assertIn("if(send) sending = true;", seg[:j],
                      "the tray must never render a button for a message already on its way")

    def test_the_tray_button_is_disabled_while_sending(self):
        src = _board_source()
        i = src.index("function renderTray(){")
        self.assertIn("tb.disabled = sending", src[i:i + 400])

    def test_sending_is_declared_once_and_before_its_readers(self):
        src = _board_source()
        decls = re.findall(r"\blet [^;\n]*\bsending\b", src)
        self.assertEqual(len(decls), 1, "one declaration only: %s" % decls)
        self.assertLess(src.index("sending = false;"), src.index("function renderTray(){"),
                        "renderTray reads it, so it must be declared first")


class EveryWriteHasADeadline(unittest.TestCase):
    """`fetch` has no timeout. A request that never resolves leaves the await hanging, so
    the finally never runs, `sending` stays true, and the page sits on "Sending…" forever
    with no way back — a server restarted mid-click is enough. Observed: the browser's
    request never reached the server at all, and the basket was still on disk afterwards."""

    def test_send_carries_an_abort_deadline(self):
        src = _board_source()
        self.assertIn("postT(`/send`, {}, 45000)", src)
        self.assertIn("new AbortController()", src)
        self.assertIn("ac.abort()", src)

    def test_a_timeout_says_so_and_restores_the_page(self):
        src = _board_source()
        i = src.index("postT(`/send`, {}, 45000)")
        seg = src[i:i + 900]
        self.assertIn("AbortError", seg)
        self.assertIn("Send timed out", seg)
        self.assertIn("renderTray()", seg, "the tray must leave the sending state too")

    def test_the_tray_leaves_sending_without_waiting_for_a_poll(self):
        src = _board_source()
        i = src.index("}finally{", src.index("async function sendBasket()"))
        self.assertIn("renderTray()", src[i:i + 320])


class TheSendCannotBeStrandedByARedraw(unittest.TestCase):
    """`sending` was claimed, three redraws ran, and only then was it released and the
    request fired. Anything throwing in those redraws stranded the flag at true AND skipped
    the send — stuck on "Sending…", basket intact, and no request for the deadline to
    rescue. The claim is released in a finally now, and the send fires after it."""

    def test_the_claim_is_released_in_a_finally(self):
        src = _board_source()
        i = src.index("function commitCompose(send){")
        seg = src[i:i + 2400]
        j = seg.index("if(send) sending = true;")
        self.assertIn("finally{", seg[j:j + 420])
        self.assertIn("sending = false;", seg[seg.index("finally{", j):][:120])

    def test_the_request_fires_after_the_redraw_not_inside_it(self):
        src = _board_source()
        i = src.index("function commitCompose(send){")
        seg = src[i:i + 2400]
        f = seg.index("finally{", seg.index("if(send) sending = true;"))
        self.assertIn("if(send) sendBasket();", seg[f:f + 260])

    def test_a_thrown_handler_is_announced(self):
        # A stuck "Sending…" with no request behind it is indistinguishable from a slow one.
        src = _board_source()
        self.assertIn("addEventListener('error'", src)
        i = src.index("addEventListener('error'")
        self.assertIn("Page error", src[i:i + 400])

    def test_the_page_is_never_served_from_cache(self):
        # A version bump reloads the tab; a cached page would reload into the same old
        # version, forever.
        src = _board_source()
        i = src.index('"text/html; charset=utf-8"')
        self.assertIn("no-store", src[max(0, i - 260):i])


class ARestartCannotSwallowTheArrival(unittest.TestCase):
    """`board_add` writes the entry and THEN calls ensure_server, which replaces a stale
    daemon — so the entry that triggered the replacement is already on disk when the new
    watcher seeds, and was filed as "already there". Every plugin update therefore swallowed
    the next arrival, silently. Field case: CEO-531, written 7s after the daemon it
    restarted, never announced."""

    def test_the_seed_pass_still_announces_a_just_written_entry(self):
        src = _board_source()
        i = src.index("def watcher():")
        seg = src[i:i + 2200]
        self.assertIn("timedelta(seconds=30)", seg)
        self.assertIn('arrived = (not first) or (e.get("created") or "") >= fresh', seg)

    def test_an_older_entry_is_still_only_seeded(self):
        # The window must not re-announce a backlog: only what was written around startup.
        import datetime as _dt
        fresh = (_dt.datetime.now() - _dt.timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%S")
        old = (_dt.datetime.now() - _dt.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S")
        now = _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        self.assertFalse(old >= fresh, "a three-hour-old entry must not count as an arrival")
        self.assertTrue(now >= fresh, "one written at startup must")


class AnEditInsideAFolderMovesItsStamp(unittest.TestCase):
    """Every view is memoised on a stamp built from the paths its loader reads, and a
    directory used to contribute its own mtime — which moves only when an entry is
    created, renamed or removed. An edit INSIDE it moved nothing, so the cache never
    expired: three letters were flipped `status: unread` to `read` on disk and the board
    went on showing "3 unread" for an hour, until an unrelated letter arrived and shook
    the folder loose (2026-08-04, a screenshot)."""

    def _mail_project(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, ".claude"))
        os.makedirs(os.path.join(root, "docs", "board", "mail"))
        with open(os.path.join(root, ".claude", "orchestrate.json"), "w", encoding="utf-8") as f:
            json.dump({"active": True, "board": "docs/board", "external": ["Marketing"]}, f)
        self.letter = os.path.join(root, "docs", "board", "mail", "20260804-1150-a.md")
        self._write("unread")
        return root

    def _write(self, status):
        with open(self.letter, "w", encoding="utf-8") as f:
            f.write('---\ntime: "2026-08-04 11:50"\nfrom: Marketing\nto: CEO\n'
                    're: "x"\nstatus: %s\n---\nbody\n' % status)

    def _unread(self, root):
        return board.load_mail(root)["branches"][0]["unread"]

    def test_flipping_a_letter_to_read_in_place_updates_the_lane(self):
        root = self._mail_project()
        self.assertEqual(self._unread(root), 1)
        self._write("read")
        self.assertEqual(self._unread(root), 0,
                         "the lane still claims an unread letter that is read on disk")

    def test_it_moves_back_too(self):
        root = self._mail_project()
        self.assertEqual(self._unread(root), 1)
        self._write("read")
        self._unread(root)
        self._write("unread")
        self.assertEqual(self._unread(root), 1)

    def test_an_arrival_and_a_deletion_still_move_it(self):
        root = self._mail_project()
        self._unread(root)
        second = os.path.join(os.path.dirname(self.letter), "20260804-1200-b.md")
        with open(second, "w", encoding="utf-8") as f:
            f.write('---\ntime: "2026-08-04 12:00"\nfrom: Marketing\nto: CEO\n'
                    're: "y"\nstatus: unread\n---\nb\n')
        self.assertEqual(self._unread(root), 2)
        os.remove(second)
        self.assertEqual(self._unread(root), 1)

    def test_the_stamp_is_the_entries_not_the_folder_clock(self):
        root = self._mail_project()
        mdir = os.path.dirname(self.letter)
        before = board._dirstamp(mdir)
        folder_clock = os.path.getmtime(mdir)
        self._write("read")
        self.assertEqual(os.path.getmtime(mdir), folder_clock,
                         "an in-place edit does not touch the folder — that is the trap")
        self.assertNotEqual(board._dirstamp(mdir), before)

    def test_a_directory_the_loader_opens_is_stamped_by_name(self):
        """_dirstamp reads one level, because every loader here uses os.listdir. A nested
        directory a loader DOES open has to appear in the stamp itself — `<board>/done`
        is read by retired_tasks and would otherwise be invisible."""
        src = _board_source()
        i = src.index("def load_taskboard(root):")
        self.assertIn('os.path.join(bdir, "done")', src[i:i + 1200])


class APaneTitleIsNotAnAnimation(unittest.TestCase):
    """iTerm's session name for a working Claude Code pane IS its status line, and that
    line opens with a braille spinner that advances several times a second. Everything
    downstream treated the name as an identity: the destination label beside the composer
    redrew on every poll, the seat list re-sorted under their hand, and the composer's
    "has anything changed?" check answered yes forever — which rebuilt the box they was
    typing into. The frame is not part of the name."""

    def test_two_frames_of_one_pane_are_one_title(self):
        a = board.pane_title("⠂ Retrieve exact tool call and result")
        b = board.pane_title("⠐ Retrieve exact tool call and result")
        self.assertEqual(a, b)
        self.assertEqual(a, "Retrieve exact tool call and result")

    def test_a_name_with_no_spinner_is_untouched(self):
        for name in ("QA · running tests", "CEO", "fix #1042 — reftype boundary"):
            self.assertEqual(board.pane_title(name), name)

    def test_a_name_that_is_only_spinner_keeps_its_text(self):
        # Stripping to empty would leave the pane with no name at all; there is nothing
        # better to call it than what it says.
        self.assertEqual(board.pane_title("⠿⠿⠿"), "⠿⠿⠿")

    def test_it_survives_a_missing_name(self):
        self.assertEqual(board.pane_title(None), "")
        self.assertEqual(board.pane_title(""), "")

    def test_both_pane_readers_go_through_it(self):
        """One stripped title and one raw one would put the animation back on the board
        by whichever path the caller happened to take."""
        src = _board_source()
        self.assertIn("guid, tty, name = bits[0].strip(), bits[1].strip(), pane_title(bits[2])", src)
        self.assertIn("name = pane_title(head[1]) if len(head) > 1 else \"\"", src)


class ADoneCannotSpeakForHer(unittest.TestCase):
    """The Boss's reply and the raiser's `@BOSS-DONE` note were written to the SAME field,
    and the board renders that field as their words, over "you" and their clock. A session
    that answered their and withdrew its own ask in the same turn therefore deleted what they
    had typed and left its own summary standing in their mouth. Two speakers, two fields."""

    def _answered(self):
        s = {"entries": []}
        e, _ = board.add_entry(s, "CEO", "needs", "flow logic + 准/驳", NOW)
        board.basket_set(s, e["id"], "reply", "I'm not getting it. 为什么一定要指定 collection?", NOW)
        board.board_send_mutate(s, NOW)
        return s, e["id"]

    def test_her_answer_is_recorded_at_send(self):
        s, eid = self._answered()
        e = board.get_entry(s, eid)
        self.assertEqual(e["status"], "resolved")
        self.assertIn("I'm not getting it", e["sum"])

    def test_a_done_afterwards_leaves_her_words_alone(self):
        s, eid = self._answered()
        board.set_status(s, eid, "resolved", NOW, outcome="answered below — your instinct is correct")
        e = board.get_entry(s, eid)
        self.assertIn("I'm not getting it", e["sum"], "their reply was overwritten by a DONE")
        self.assertIn("answered below", e["outcome"])

    def test_a_done_on_an_unanswered_ask_is_the_whole_story(self):
        s = {"entries": []}
        e, _ = board.add_entry(s, "CEO", "needs", "withdrawn ask", NOW)
        board.set_status(s, e["id"], "resolved", NOW, outcome="withdrawn — fixed it myself")
        got = board.get_entry(s, e["id"])
        self.assertEqual(got["status"], "resolved")
        self.assertIsNone(got.get("sum"), "nothing may be attributed to them; they never replied")
        self.assertIn("withdrawn", got["outcome"])

    def test_the_dept_addressed_done_writes_the_outcome_too(self):
        """`@BOSS-DONE[<dept>]` reaches the dept's one remaining OPEN ask, and must not
        reach back into an answered one to relabel their reply."""
        s = {"entries": []}
        answered, _ = board.add_entry(s, "QA", "needs", "postgres or sqlite?", NOW)
        still_open, _ = board.add_entry(s, "QA", "needs", "where do logs go?", NOW)
        board.basket_set(s, answered["id"], "reply", "use SQLite", NOW)
        board.board_send_mutate(s, NOW)
        got, opens = board.resolve_by_dept(s, "QA", NOW, outcome="closing it out")
        self.assertEqual(got["id"], still_open["id"])
        self.assertEqual(board.get_entry(s, still_open["id"])["outcome"], "closing it out")
        first = board.get_entry(s, answered["id"])
        self.assertEqual(first["sum"], "use SQLite")
        self.assertIsNone(first.get("outcome"))

    def test_ignoring_is_her_own_act_and_stays_in_her_field(self):
        """Ignore is their decision not to reply, so it belongs on their side, not the
        raiser's — it is the one non-typed thing that is still theirs."""
        src = _board_source()
        i = src.index('elif path == "/ignore"')
        self.assertIn('sum="(ignored — no reply sent)"', src[i:i + 900])

    def test_the_panel_never_prints_the_outcome_as_hers(self):
        page = board.PAGE
        self.assertIn("const closed = e.outcome ?", page)
        i = page.index("const mine = (SENT||[]).filter")
        self.assertNotIn("e.outcome", page[i:page.index("const closed")],
                         "their bubbles must read only what they sent, and the Boss's own field")


class AMessageWithNoSubjectIsNotAnAsk(unittest.TestCase):
    """A conversation opened, a plain question written, and it went out as
    `CEO-553 asks: <the question>` — hung on an unrelated card raised the night
    before, which it also marked read on the way past. The composer bound any unbound
    message to "the conversation's newest live item", so a message about nothing became a
    question about whatever happened to be at the bottom of the thread."""

    def test_a_free_message_carries_no_item_id(self):
        s = {"entries": []}
        board.add_entry(s, "CEO", "info", "an unrelated update from last night", NOW)
        board.basket_set(s, "free:CEO", "msg", "这个是什么？", NOW)
        rec = board.board_send_mutate(s, NOW)
        self.assertEqual(rec["msg"], "[Boss Board] 这个是什么？")
        self.assertNotIn("CEO-1", rec["msg"])

    def test_it_resolves_and_reads_nothing(self):
        s = {"entries": []}
        e, _ = board.add_entry(s, "CEO", "info", "an unrelated update", NOW)
        board.basket_set(s, "free:CEO", "msg", "unrelated question", NOW)
        board.board_send_mutate(s, NOW)
        got = board.get_entry(s, e["id"])
        self.assertEqual(got["status"], "open", "a free message closed someone else's card")
        self.assertNotEqual(got.get("read"), True, "and marked it read on the way past")

    def test_it_routes_by_conversation(self):
        s = {"entries": []}
        board.basket_set(s, "free:Backend-IO", "msg", "a question for the desk", NOW)
        rec = board.board_send_mutate(s, NOW)
        self.assertEqual([g["src"] for g in rec["groups"]], ["dept:Backend-IO#"])

    def test_it_rides_along_with_real_answers_to_the_same_seat(self):
        s = {"entries": []}
        e, _ = board.add_entry(s, "CEO", "needs", "pick one", NOW)
        board.basket_set(s, e["id"], "reply", "B", NOW)
        board.basket_set(s, "free:CEO", "msg", "and separately: 这个是什么？", NOW)
        rec = board.board_send_mutate(s, NOW)
        self.assertIn("CEO-1 → B", rec["msg"])
        self.assertIn("· 和分开", rec["msg"].replace("and separately:", "和分开"))
        self.assertEqual(board.get_entry(s, e["id"])["sum"], "B")

    def test_the_composer_no_longer_hunts_for_an_anchor(self):
        page = board.PAGE
        self.assertIn("id = 'free:' + CONVO; kind = 'msg';", page)
        self.assertNotIn("Nothing open in this conversation to attach a message to", page)

    def test_the_ceo_conversation_resolves_to_her_own_seat(self):
        """The CEO session registers no agent name, so a roster lookup finds nothing and
        a message to that conversation reported "no live seat" and went nowhere."""
        with unittest.mock.patch.object(board, "default_guid", return_value="GUID-CEO"):
            self.assertEqual(board.dept_guid("/nope", "CEO"), ("GUID-CEO", ""))
        with unittest.mock.patch.object(board, "default_guid", return_value=None):
            guid, why = board.dept_guid("/nope", "CEO")
            self.assertIsNone(guid)
            self.assertIn("CEO", why)


class TheEchoIsWaitedForNotSampled(unittest.TestCase):
    """The typing script slept a fixed 0.22s and read the screen exactly once. A long
    message full of CJK re-wraps the input box, and a TUI that had not finished painting
    inside that window read as "not echoed", so the text sat in their box unsent and they
    pressed Return themselves (2026-08-05). Waiting is also faster in the ordinary case: it
    returns the moment the text appears rather than always paying the delay."""

    LOOK = "/dev/ttys009\n✳ pane\nbefore-only"

    def _run(self, msg, screens, seat="ceo"):
        """`screens` is what each successive READ returns — the paint arriving late."""
        d = tempfile.TemporaryDirectory(); self.addCleanup(d.cleanup)
        board.capture_iterm_target(d.name, "w:G", {"cwd": "/x", "session_id": "s"})
        calls, reads = [], list(screens)

        def osa(script, *a, **k):
            n = ("lookup" if script in (board.ITERM_LOOKUP_APPLESCRIPT,
                                        board.ITERM_PROBE_APPLESCRIPT) else
                 "type" if script is board.ITERM_TYPE_APPLESCRIPT else
                 "read" if script is board.ITERM_READ_APPLESCRIPT else "enter")
            calls.append(n)
            if n == "lookup":
                return self.LOOK
            if n == "type":
                return self.LOOK + "\nnothing painted yet"
            if n == "read":
                return reads.pop(0) if reads else "still nothing"
            return "ok"

        with unittest.mock.patch.object(board, "_iterm_disabled", lambda: False), \
             unittest.mock.patch.object(board, "_osa", osa), \
             unittest.mock.patch.object(board, "time", unittest.mock.Mock(sleep=lambda s: None,
                                                                          time=time.time)), \
             unittest.mock.patch.object(board, "_claude_ttys", lambda: {"/dev/ttys009": "/x"}), \
             unittest.mock.patch.object(board, "_seat_kind", lambda *a, **k: seat), \
             unittest.mock.patch.object(board, "default_guid", lambda r: "G"):
            return board.iterm_prime(d.name, msg), calls

    def test_a_late_paint_is_still_submitted(self):
        msg = "[Boss Board] CEO-553 → 哎我的妈，你就直接举个例子告诉我这行为是啥行不行？"
        got, calls = self._run(msg, ["not yet", "not yet", "❯ " + msg])
        self.assertEqual(got, "ok", "the pane took the text and we walked away from it")
        self.assertEqual(calls.count("read"), 3, "it must stop reading once it sees it")
        self.assertIn("enter", calls)

    def test_a_pane_that_never_paints_it_is_still_refused(self):
        got, calls = self._run("[Boss Board] ship it", ["nope", "nope", "nope", "nope"])
        self.assertEqual(got, "typed")
        self.assertNotIn("enter", calls, "a blind Return is a sentence run as a command")

    def test_an_unreadable_pane_stops_the_wait_rather_than_spinning(self):
        d = tempfile.TemporaryDirectory(); self.addCleanup(d.cleanup)
        board.capture_iterm_target(d.name, "w:G", {"cwd": "/x", "session_id": "s"})
        calls = []

        def osa(script, *a, **k):
            n = ("lookup" if script in (board.ITERM_LOOKUP_APPLESCRIPT,
                                        board.ITERM_PROBE_APPLESCRIPT) else
                 "type" if script is board.ITERM_TYPE_APPLESCRIPT else
                 "read" if script is board.ITERM_READ_APPLESCRIPT else "enter")
            calls.append(n)
            return {"lookup": self.LOOK, "type": self.LOOK + "\nnothing",
                    "read": None, "enter": "ok"}[n]

        with unittest.mock.patch.object(board, "_iterm_disabled", lambda: False), \
             unittest.mock.patch.object(board, "_osa", osa), \
             unittest.mock.patch.object(board, "time", unittest.mock.Mock(sleep=lambda s: None,
                                                                          time=time.time)), \
             unittest.mock.patch.object(board, "_claude_ttys", lambda: {"/dev/ttys009": "/x"}), \
             unittest.mock.patch.object(board, "_seat_kind", lambda *a, **k: "ceo"), \
             unittest.mock.patch.object(board, "default_guid", lambda r: "G"):
            got = board.iterm_prime(d.name, "[Boss Board] ship it")
        self.assertEqual(got, "typed")
        self.assertEqual(calls.count("read"), 1)
        self.assertNotIn("enter", calls)

    def test_a_dropped_return_is_tried_once_more(self):
        """Everything above proves the text is in their box, so one failed keystroke is all
        that stands between a delivered answer and one they have to press Enter on."""
        d = tempfile.TemporaryDirectory(); self.addCleanup(d.cleanup)
        board.capture_iterm_target(d.name, "w:G", {"cwd": "/x", "session_id": "s"})
        msg, calls, enters = "[Boss Board] ship it", [], []

        def osa(script, *a, **k):
            n = ("lookup" if script in (board.ITERM_LOOKUP_APPLESCRIPT,
                                        board.ITERM_PROBE_APPLESCRIPT) else
                 "type" if script is board.ITERM_TYPE_APPLESCRIPT else
                 "read" if script is board.ITERM_READ_APPLESCRIPT else "enter")
            calls.append(n)
            if n == "enter":
                enters.append(1)
                return None if len(enters) == 1 else "ok"      # first keystroke is lost
            return {"lookup": self.LOOK, "type": self.LOOK + "\n❯ " + msg, "read": ""}[n]

        with unittest.mock.patch.object(board, "_iterm_disabled", lambda: False), \
             unittest.mock.patch.object(board, "_osa", osa), \
             unittest.mock.patch.object(board, "_claude_ttys", lambda: {"/dev/ttys009": "/x"}), \
             unittest.mock.patch.object(board, "_seat_kind", lambda *a, **k: "ceo"), \
             unittest.mock.patch.object(board, "default_guid", lambda r: "G"):
            self.assertEqual(board.iterm_prime(d.name, msg), "ok")
        self.assertEqual(calls.count("enter"), 2)


class HerSideOfTheConversationIsKept(unittest.TestCase):
    """A reply was recorded (as the item's `sum`) and nothing else was. So an ask and a
    free message reached the session and left no trace on the board — they wrote them, they
    went, and the thread had nothing between the item and the answer it produced."""

    def test_every_kind_is_logged_with_where_it_went(self):
        s = {"entries": []}
        a, _ = board.add_entry(s, "Backend-IO", "needs", "pick one", NOW)
        b, _ = board.add_entry(s, "Backend-IO", "info", "an update", NOW)
        board.basket_set(s, a["id"], "reply", "B", NOW)
        board.basket_set(s, b["id"], "ask", "what does that mean?", NOW)
        board.basket_set(s, "free:Backend-IO", "msg", "unrelated question", NOW)
        board.board_send_mutate(s, NOW)
        got = [(x["kind"], x["id"], x["dept"], x["text"]) for x in s["sent"]]
        self.assertIn(("reply", a["id"], "Backend-IO", "B"), got)
        self.assertIn(("ask", b["id"], "Backend-IO", "what does that mean?"), got)
        self.assertIn(("msg", "", "Backend-IO", "unrelated question"), got)

    def test_the_log_is_appended_never_replaced(self):
        s = {"entries": []}
        e, _ = board.add_entry(s, "CEO", "info", "an update", NOW)
        for t in ("first", "second", "third"):
            board.basket_set(s, e["id"], "ask", t, NOW)
            board.board_send_mutate(s, NOW)
        self.assertEqual([x["text"] for x in s["sent"]], ["first", "second", "third"])

    def test_it_is_capped_at_the_tail(self):
        s = {"entries": [], "sent": [{"id": "", "dept": "CEO", "kind": "msg",
                                      "text": "old %d" % i, "at": NOW}
                                     for i in range(board.SENT_TAIL + 5)]}
        board.basket_set(s, "free:CEO", "msg", "newest", NOW)
        board.board_send_mutate(s, NOW)
        self.assertEqual(len(s["sent"]), board.SENT_TAIL)
        self.assertEqual(s["sent"][-1]["text"], "newest")

    def test_an_ask_still_leaves_the_item_open(self):
        s = {"entries": []}
        e, _ = board.add_entry(s, "CEO", "needs", "pick one", NOW)
        board.basket_set(s, e["id"], "ask", "what does that mean?", NOW)
        board.board_send_mutate(s, NOW)
        self.assertEqual(board.get_entry(s, e["id"])["status"], "open")
        self.assertEqual(s["sent"][0]["kind"], "ask")

    def test_the_page_redraws_on_a_send_that_changes_no_entry(self):
        """An ask moves nothing on its item, so without `sent` in the redraw signature the
        thread never rebuilt and the question stayed invisible until something else moved."""
        src = _board_source()
        i = src.index("const raw = JSON.stringify(")
        self.assertIn("s.sent", src[i:i + 90])
