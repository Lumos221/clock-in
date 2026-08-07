"""Tests for stop_done_sweep.py — the tool-independent completion recorder. A card whose
own `status` says done must reach BACKLOG + board/done/ even when the task widget never
fired, exactly once, without disturbing live cards."""
import os, sys, json, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
import cardlib
import stop_done_sweep as sweep


class DoneSweep(unittest.TestCase):
    def _proj(self, d):
        os.makedirs(os.path.join(d, ".claude"))
        os.makedirs(os.path.join(d, "docs", "board"))
        cfg = {"active": True, "board": "docs/board", "backlog": "docs/BACKLOG.md",
               "taskboard": "docs/TaskBoard.md"}
        open(os.path.join(d, ".claude", "orchestrate.json"), "w").write(json.dumps(cfg))
        return cfg

    def _card(self, d, name, status, **f):
        return cardlib.new_card(os.path.join(d, "docs", "board"), name, status=status, **f)

    def _backlog(self, d):
        p = os.path.join(d, "docs", "BACKLOG.md")
        return open(p, encoding="utf-8").read() if os.path.exists(p) else ""

    def test_done_card_reaches_backlog_and_retires_without_the_widget(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._proj(d)
            self._card(d, "SHIPPED-THING", "done", dept="Ops")
            self._card(d, "STILL-BUILDING", "doing", dept="Frontend")
            traces = sweep.sweep(d, cfg)
            bl = self._backlog(d)
            self.assertEqual(len(traces), 1)
            self.assertIn("SHIPPED-THING", bl)          # recorded
            self.assertNotIn("STILL-BUILDING", bl)      # live card untouched
            self.assertTrue(os.path.exists(os.path.join(d, "docs", "board", "done", "1-shipped-thing.md")))
            live = [c.get("name") for c in cardlib.load(os.path.join(d, "docs", "board"))]
            self.assertEqual(live, ["STILL-BUILDING"])  # retired out of Active

    def test_is_idempotent_never_double_logs(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._proj(d)
            self._card(d, "ONCE-ONLY", "done", dept="QA")
            sweep.sweep(d, cfg)
            first = self._backlog(d)
            self.assertEqual(sweep.sweep(d, cfg), [])   # nothing left to record
            self.assertEqual(self._backlog(d), first)   # byte-identical, no second row

    def test_skips_a_card_the_widget_path_already_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._proj(d)
            c = self._card(d, "ALREADY-LOGGED", "done", dept="Ops")
            os.makedirs(os.path.join(d, "docs"), exist_ok=True)
            open(os.path.join(d, "docs", "BACKLOG.md"), "w").write(
                "| 2026-07-01 | 9 | Ops | #%d ALREADY-LOGGED | done | abc | — |\n" % c["id"])
            self.assertEqual(sweep.sweep(d, cfg), [])   # row exists -> skip, no duplicate

    def test_note_flags_a_missing_l2_pass(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._proj(d)
            c = self._card(d, "UNREVIEWED", "done", dept="Ops")
            sweep.sweep(d, cfg)
            self.assertIn("no L2 pass on file", self._backlog(d))

    def test_pass_on_file_drops_the_caveat(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._proj(d)
            c = self._card(d, "REVIEWED", "done", dept="Ops")
            os.makedirs(os.path.join(d, "docs", "reviews"), exist_ok=True)
            open(os.path.join(d, "docs", "reviews", "%d.pass" % c["id"]), "w").write("PASS")
            sweep.sweep(d, cfg)
            self.assertIn("REVIEWED", self._backlog(d))
            self.assertNotIn("no L2 pass on file", self._backlog(d))

    def test_cap_limits_work_per_turn(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._proj(d)
            for i in range(5):
                self._card(d, "CARD-%d" % i, "done", dept="Ops")
            self.assertEqual(len(sweep.sweep(d, cfg, cap=2)), 2)   # drains over turns
            self.assertEqual(len(sweep.sweep(d, cfg, cap=2)), 2)
            self.assertEqual(len(sweep.sweep(d, cfg, cap=2)), 1)
            self.assertEqual(sweep.sweep(d, cfg, cap=2), [])

    def test_hook_is_opt_in_per_project(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._proj(d)                      # no "done_sweep" key -> opt-out
            self._card(d, "NOT-YET", "done")
            self.assertIsNone(sweep.run({"hook_event_name": "Stop", "cwd": d}, None))
            self.assertEqual(self._backlog(d), "")   # nothing written without opt-in
            cfg["done_sweep"] = True
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write(json.dumps(cfg))
            sweep.run({"hook_event_name": "Stop", "cwd": d}, None)
            self.assertIn("NOT-YET", self._backlog(d))   # opted in -> recorded

    def test_inert_off_the_stop_path(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            self._card(d, "X", "done")
            self.assertIsNone(sweep.run({"hook_event_name": "SubagentStop", "cwd": d}, None))
            self.assertEqual(self._backlog(d), "")


if __name__ == "__main__":
    unittest.main()
