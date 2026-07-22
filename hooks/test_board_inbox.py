"""Tests for userprompt_board_inbox.py — the Boss Board reply inbox (the reverse
channel's fallback leg). Verifies a pending outbox message injects exactly once and
that the hook stays inert off the CEO/active path."""
import os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
import board
import userprompt_board_inbox as inbox


class InboxHook(unittest.TestCase):
    def _armed_root(self, d, active=True):
        os.makedirs(os.path.join(d, ".claude"))
        open(os.path.join(d, ".claude", "orchestrate.json"), "w").write(
            '{"active":%s}' % ("true" if active else "false"))

    def test_pending_message_injects_once_then_silent(self):
        board._SKIP_SERVER = True
        os.environ["BOARD_SKIP_ITERM"] = "1"    # force the fallback path (outbox pending)
        try:
            with tempfile.TemporaryDirectory() as d:
                self._armed_root(d)
                board.board_add(d, "QA", "needs", "Postgres or SQLite?")
                board._locked_mutate(d, lambda s: board.basket_set(
                    s, "QA-1", "reply", "use SQLite", board._now()))
                board.board_send(d)             # iTerm2 skipped -> message sits pending
                data = {"hook_event_name": "UserPromptSubmit", "cwd": d}
                out = inbox.run(data)
                self.assertIsNotNone(out)
                self.assertIn("QA-1", out)
                self.assertIn("SQLite", out)
                self.assertIsNone(inbox.run(data))   # delivered -> no double injection
        finally:
            os.environ.pop("BOARD_SKIP_ITERM", None)

    def test_inert_without_active_project(self):
        with tempfile.TemporaryDirectory() as d:
            self._armed_root(d, active=False)
            self.assertIsNone(inbox.run({"hook_event_name": "UserPromptSubmit", "cwd": d}))

    def test_wrong_event_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            self._armed_root(d)
            self.assertIsNone(inbox.run({"hook_event_name": "Stop", "cwd": d}))


if __name__ == "__main__":
    unittest.main()
