"""Tests for session_start.py — the CEO-mode injection and the token-free bloat
sentinel (SoT over-cap · essay-cards · unregistered cards).
Run: python3 hooks/test_session_start.py"""
import os, sys, json, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session_start as ss

LEAN_SOT = "# demo · SoT\n\nGoal: ship v1\nNow: a · b · c\n"
LEAN_CARD = "### TASK-001 · login form\n- **task_id:** 3\n- **status:** doing\n"


def _proj(d, sot=LEAN_SOT, cards=LEAN_CARD):
    os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
    with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
        f.write('{"active":true}')
    os.makedirs(os.path.join(d, "docs"), exist_ok=True)
    with open(os.path.join(d, "docs", "SoT.md"), "w", encoding="utf-8") as f:
        f.write(sot)
    with open(os.path.join(d, "docs", "TaskBoard.md"), "w", encoding="utf-8") as f:
        f.write("# demo · TaskBoard\n\n## Active\n\n%s\n## Recently shipped\n" % cards)


def _ctx(d):
    cfg = json.load(open(os.path.join(d, ".claude", "orchestrate.json")))
    return ss.context_for(d, cfg)


class BloatSentinel(unittest.TestCase):
    def test_lean_project_gets_no_flags(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            out = _ctx(d)
            self.assertIn("CEO orchestration mode", out)
            self.assertIn("ship v1", out)          # SoT injected
            self.assertNotIn("⚠", out)             # zero flags when clean

    def test_overgrown_sot_flagged_every_session(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d, sot="# SoT\n" + "a line of standing detail\n" * 40)
            out = _ctx(d)
            self.assertIn("over its ~15-line hard cap", out)
            self.assertIn("DECISIONS.md", out)

    def test_essay_card_flagged_by_label(self):
        with tempfile.TemporaryDirectory() as d:
            essay = ("### TASK-002 · shipped-journal card\n- **task_id:** 4\n"
                     "- **status:** doing — " + "phase notes · " * 120 + "\n")
            _proj(d, cards=LEAN_CARD + "\n" + essay)
            out = _ctx(d)
            self.assertIn("a card is a pointer, not a journal", out)
            self.assertIn("TASK-002", out)
            self.assertNotIn("TASK-001", out.split("pointer")[1])  # lean card not named

    def test_unregistered_card_flag_still_present(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d, cards="### TASK-009 · hand thing\n- **task_id:** —\n- **status:** todo\n")
            out = _ctx(d)
            self.assertIn("carry no platform task_id", out)
            self.assertIn("TASK-009", out)


class Gating(unittest.TestCase):
    def test_inactive_marker_silent(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
                f.write('{"active":false}')
            payload = {"cwd": d}
            import subprocess
            hook = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_start.py")
            r = subprocess.run([sys.executable, hook], input=json.dumps(payload),
                               text=True, capture_output=True, timeout=20)
            self.assertEqual(r.stdout, "")


if __name__ == "__main__":
    unittest.main()
