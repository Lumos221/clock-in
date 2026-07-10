"""Tests for hooklib.py — the shared hook helpers, esp. the replay-protection
semantics of last_assistant_text. Run: python3 hooks/test_hooklib.py"""
import os, sys, json, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hooklib


def _write_transcript(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def _assistant(blocks):
    return {"type": "assistant", "message": {"role": "assistant", "content": blocks}}


class LastAssistantText(unittest.TestCase):
    def test_reads_last_assistant_text(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.jsonl")
            _write_transcript(p, [
                _assistant([{"type": "text", "text": "old turn @BOSS[QA]: stale ask"}]),
                {"type": "user", "message": {"role": "user", "content": "answer"}},
                _assistant([{"type": "text", "text": "final message"}]),
            ])
            self.assertEqual(hooklib.last_assistant_text(p), "final message")

    def test_textless_final_message_does_not_replay_an_older_turn(self):
        # Regression: walking back past a text-less final assistant entry used to
        # re-apply markers from an earlier, already-processed message (e.g. re-raising
        # a @BOSS ask the Boss had already resolved).
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.jsonl")
            _write_transcript(p, [
                _assistant([{"type": "text", "text": "@BOSS[QA]: stale ask"}]),
                _assistant([{"type": "tool_use", "id": "x", "name": "Bash", "input": {}}]),
            ])
            self.assertEqual(hooklib.last_assistant_text(p), "")

    def test_string_content_and_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.jsonl")
            _write_transcript(p, [{"type": "assistant",
                                   "message": {"role": "assistant", "content": "plain string"}}])
            self.assertEqual(hooklib.last_assistant_text(p), "plain string")
            self.assertEqual(hooklib.last_assistant_text(os.path.join(d, "nope.jsonl")), "")


class FindRoot(unittest.TestCase):
    def test_walks_up_to_marker(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write("{}")
            sub = os.path.join(d, "a", "b"); os.makedirs(sub)
            self.assertEqual(os.path.realpath(hooklib.find_root(sub)), os.path.realpath(d))

    def test_none_without_marker(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(hooklib.find_root(d))


class MissLog(unittest.TestCase):
    def test_appends_and_never_raises(self):
        with tempfile.TemporaryDirectory() as d:
            hooklib.log_marker_misses(d, "canon", ["@CANON[Fin] broken line"])
            log = os.path.join(d, ".claude", "marker-misses.log")
            self.assertIn("broken line", open(log, encoding="utf-8").read())
            hooklib.log_marker_misses(d, "canon", [])          # empty → no-op
            hooklib.log_marker_misses("/nonexistent/x", "c", ["y"])  # unwritable → silent


if __name__ == "__main__":
    unittest.main()
