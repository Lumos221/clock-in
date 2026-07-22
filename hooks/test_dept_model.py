"""Tests for posttool_dept_model.py — capturing the CEO's per-session spawn model
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


if __name__ == "__main__":
    unittest.main()
