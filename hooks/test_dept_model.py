"""Tests for posttool_dm.py — capturing the CEO's per-session spawn model
override so the Departments view shows the EFFECTIVE model, not just the frontmatter
default."""
import os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
import board
import posttool_dept_model as dm


class DeptModelCapture(unittest.TestCase):
    def _armed(self, d, active=True):
        os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
        open(os.path.join(d, ".claude", "orchestrate.json"), "w").write(
            '{"active":%s}' % ("true" if active else "false"))

    def _models(self, d):
        return board.load_store(board._store_path(d)).get("models", {})

    def test_records_spawn_override_keyed_by_handle(self):
        with tempfile.TemporaryDirectory() as d:
            self._armed(d)
            dm.run({"tool_name": "Agent", "cwd": d,
                    "tool_input": {"name": "RnD-1", "subagent_type": "RnD", "model": "opus"}})
            self.assertEqual(self._models(d).get("RnD", {}).get("model"), "opus")

    def test_no_override_records_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            self._armed(d)
            dm.run({"tool_name": "Agent", "cwd": d,
                    "tool_input": {"name": "RnD-1", "subagent_type": "RnD"}})
            self.assertEqual(self._models(d), {})

    def test_records_nickname_under_seat_handle(self):
        """nickname is a display name, not the handle: the numeric handle stays
        untouched, and the nickname lands in the store's seats map."""
        with tempfile.TemporaryDirectory() as d:
            self._armed(d)
            dm.run({"tool_name": "Agent", "cwd": d,
                    "tool_input": {"name": "RnD-1", "subagent_type": "RnD",
                                   "description": "card #377 · effort=high · nickname: Vera"}})
            s = board.load_store(board._store_path(d)).get("seats", {})
            self.assertEqual(s.get("RnD-1", {}).get("nickname"), "Vera")

    def test_nickname_alone_records_seat_without_model(self):
        with tempfile.TemporaryDirectory() as d:
            self._armed(d)
            dm.run({"tool_name": "Agent", "cwd": d,
                    "tool_input": {"name": "RnD-2", "subagent_type": "RnD",
                                   "prompt": "nickname: Lisa"}})
            s = board.load_store(board._store_path(d)).get("seats", {})
            self.assertEqual(s.get("RnD-2", {}).get("nickname"), "Lisa")
            self.assertEqual(self._models(d), {})

    def test_chinese_nickname_key_is_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            self._armed(d)
            dm.run({"tool_name": "Agent", "cwd": d,
                    "tool_input": {"name": "RnD-3", "subagent_type": "RnD",
                                   "description": "effort=high · 花名: 阿岚"}})
            s = board.load_store(board._store_path(d)).get("seats", {})
            self.assertEqual(s.get("RnD-3", {}).get("nickname"), "阿岚")

    def test_template_separator_is_equals(self):
        """模板统一 `nickname=Lisa`（与 effort= 同款）；`=` 和 `:` 都解析。"""
        with tempfile.TemporaryDirectory() as d:
            self._armed(d)
            dm.run({"tool_name": "Agent", "cwd": d,
                    "tool_input": {"name": "RnD-4", "subagent_type": "RnD",
                                   "description": "card #400 · effort=high · nickname=Lisa"}})
            s = board.load_store(board._store_path(d)).get("seats", {})
            self.assertEqual(s.get("RnD-4", {}).get("nickname"), "Lisa")

    def test_skips_lead_and_standing_agents(self):
        with tempfile.TemporaryDirectory() as d:
            self._armed(d)
            dm.run({"tool_name": "Agent", "cwd": d,
                    "tool_input": {"name": "team-lead", "model": "opus"}})
            dm.run({"tool_name": "Agent", "cwd": d,
                    "tool_input": {"name": "Auditor", "subagent_type": "clock-in:Auditor", "model": "opus"}})
            self.assertEqual(self._models(d), {})

    def test_inert_off_active_project(self):
        with tempfile.TemporaryDirectory() as d:
            self._armed(d, active=False)
            dm.run({"tool_name": "Agent", "cwd": d,
                    "tool_input": {"name": "RnD-1", "subagent_type": "RnD", "model": "opus"}})
            self.assertEqual(self._models(d), {})

    def test_load_roster_prefers_live_over_default(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude", "agents"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
            open(os.path.join(d, ".claude", "agents", "RnD.md"), "w").write("---\nmodel: sonnet\n---\nx")
            board.save_store(board._store_path(d),
                             {"entries": [], "models": {"RnD": {"model": "opus", "ts": board._now()}}})
            r = {x["handle"]: x for x in board.load_roster(d)}
            self.assertEqual(r["RnD"]["model"], "opus")          # effective = the live override
            self.assertEqual(r["RnD"]["default_model"], "sonnet")
            self.assertTrue(r["RnD"]["live"])

    def test_load_roster_carries_nicknames(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude", "agents"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
            open(os.path.join(d, ".claude", "agents", "RnD.md"), "w").write("---\nmodel: sonnet\n---\nx")
            board.save_store(board._store_path(d),
                             {"entries": [], "seats": {
                                 "RnD-1": {"nickname": "Vera", "ts": board._now()},
                                 "RnD-2": {"nickname": "Lisa", "ts": board._now()}}})
            r = {x["handle"]: x for x in board.load_roster(d)}
            self.assertEqual(r["RnD"]["names"], ["Lisa", "Vera"])


@unittest.skip("effort setting suspended: /effort cannot apply until the seat's turn "
               "ends, and a dept's first turn IS its card — the command queued for "
               "20 minutes and had to be cancelled by hand")
class SeatEffortRidesThisHook(unittest.TestCase):
    """The effort setter lives in THIS hook, not one of its own, and that is
    load-bearing: a session snapshots the hook REGISTRY at start but reads the FILE
    behind a registered entry fresh every time. Shipped as a new hook it reached no
    running session, while the guard that refuses an undeclared spawn — an edit to an
    already-registered hook — took effect at once. Every seat came up at the lead's
    level and the CEO had complied with an instruction that did nothing."""

    def setUp(self):
        self.fired = []
        self._real = dm.subprocess
        outer = self

        class _S:
            DEVNULL = None

            @staticmethod
            def Popen(argv, **kw):
                outer.fired.append(argv)

        dm.subprocess = _S

    def tearDown(self):
        dm.subprocess = self._real

    def _proj(self, d, briefs=()):
        os.makedirs(os.path.join(d, ".claude", "agents"), exist_ok=True)
        open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
        for handle, model in briefs:
            open(os.path.join(d, ".claude", "agents", "%s.md" % handle), "w").write(
                "---\nname: %s\nmodel: %s\n---\nbody\n" % (handle, model))

    def _run(self, d, **ti):
        self.fired.clear()
        dm.run({"tool_name": "Agent", "cwd": d, "tool_input": ti})
        return self.fired

    def test_declared_level_reaches_the_setter(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d, [("Frontend", "sonnet")])
            got = self._run(d, name="Frontend-1079", subagent_type="Frontend",
                            description="Leg F web-side seat, effort=medium")
            self.assertEqual(len(got), 1)
            self.assertEqual(got[0][-3:], ["Frontend-1079", "medium", "--wait"])

    def test_it_runs_even_with_no_model_override(self):
        """The model record returns early when the spawn names no model. Effort must
        not sit behind that: most spawns take the brief's pin and would get nothing."""
        with tempfile.TemporaryDirectory() as d:
            self._proj(d, [("QA", "sonnet")])
            self.assertEqual(len(self._run(d, name="QA-1", subagent_type="QA",
                                           description="effort=high")), 1)

    def test_undeclared_and_haiku_and_one_shots_are_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d, [("QA", "sonnet"), ("Desk", "haiku")])
            self.assertEqual(self._run(d, name="QA-1", subagent_type="QA",
                                       description="nothing here"), [])
            # haiku has no effort ladder — the command would be a no-op that still
            # rewrites the machine's global default
            self.assertEqual(self._run(d, name="Desk", subagent_type="Desk",
                                       description="effort=low"), [])
            # a one-shot honours its own frontmatter; nothing to do here
            self.assertEqual(self._run(d, subagent_type="QA", description="effort=low"), [])

    def test_the_reader_matches_the_guard_exactly(self):
        """A spawn the guard accepts must be one this can act on, or the CEO is told it
        declared something that then quietly never happens."""
        import pretool_spawn_guard as g
        for text in ("effort=high", "effort: xhigh", "EFFORT = low", "x effort=medium y",
                     "effort=turbo", "efforting=high", "no mention at all"):
            self.assertEqual(bool(g.EFFORT_RE.search(text)),
                             bool(dm.declared_effort({"description": text})), text)


if __name__ == "__main__":
    unittest.main()
