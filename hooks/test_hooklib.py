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


class StoreKeyResolution(unittest.TestCase):
    """The platform files teams/ and tasks/ under `session-<8hex>` of whatever id the
    session carried when the store was BORN, and that key does not track the running
    session_id. Field case: the hook payload said 49310ed7 while the whole
    roster and 79 live tasks sat under e103ac6e, which silently disarmed every hook
    that keyed on the current id. Resolution therefore anchors on the lead's cwd."""

    BORN = "e103ac6e-aaaa-bbbb-cccc-dddddddddddd"
    NOW = "49310ed7-1111-2222-3333-444444444444"

    def setUp(self):
        self._env = os.environ.get("CLAUDE_CONFIG_DIR")
        self.cfg = tempfile.mkdtemp()
        os.environ["CLAUDE_CONFIG_DIR"] = self.cfg

    def tearDown(self):
        if self._env is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = self._env

    def _team(self, sid, cwd, members=None):
        d = os.path.join(self.cfg, "teams", "session-%s" % sid[:8])
        os.makedirs(d, exist_ok=True)
        mem = [{"name": "team-lead", "cwd": cwd}] + list(members or [])
        with open(os.path.join(d, "config.json"), "w") as f:
            json.dump({"leadSessionId": sid, "members": mem}, f)
        return d

    def _task(self, sid, tid):
        d = os.path.join(self.cfg, "tasks", "session-%s" % sid[:8])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "%s.json" % tid), "w") as f:
            json.dump({"id": str(tid), "status": "pending"}, f)
        return d

    def test_fast_path_current_id_owns_the_store(self):
        with tempfile.TemporaryDirectory() as p:
            self._team(self.NOW, p)
            self.assertEqual(hooklib.team_key(self.NOW, p), self.NOW[:8])

    def test_resumed_id_resolves_through_the_cwd_anchor(self):
        with tempfile.TemporaryDirectory() as p:
            self._team(self.BORN, p)
            self.assertEqual(hooklib.team_key(self.NOW, p), self.BORN[:8])
            cfg = hooklib.team_config(self.NOW, p)
            self.assertEqual(cfg["leadSessionId"], self.BORN)

    def test_another_projects_team_is_never_borrowed(self):
        with tempfile.TemporaryDirectory() as mine, tempfile.TemporaryDirectory() as other:
            self._team(self.BORN, other)
            self.assertIsNone(hooklib.team_key(self.NOW, mine))
            self.assertIsNone(hooklib.team_config(self.NOW, mine))

    def test_without_a_root_there_is_no_guessing(self):
        with tempfile.TemporaryDirectory() as p:
            self._team(self.BORN, p)
            self.assertIsNone(hooklib.team_key(self.NOW))

    def test_newest_team_wins_when_a_project_led_several(self):
        with tempfile.TemporaryDirectory() as p:
            old = self._team("11111111-x", p)
            new = self._team(self.BORN, p)
            os.utime(os.path.join(old, "config.json"), (1, 1))
            os.utime(os.path.join(new, "config.json"), (9_000_000, 9_000_000))
            self.assertEqual(hooklib.team_key(self.NOW, p), self.BORN[:8])

    def test_tasks_dir_prefers_the_store_that_actually_holds_tasks(self):
        with tempfile.TemporaryDirectory() as p:
            self._team(self.BORN, p)
            os.makedirs(os.path.join(self.cfg, "tasks", "session-%s" % self.NOW[:8]))
            self._task(self.BORN, 73)
            self.assertEqual(hooklib.tasks_dir(self.NOW, p),
                             os.path.join(self.cfg, "tasks", "session-%s" % self.BORN[:8]))

    def test_tasks_dir_falls_back_to_the_raw_id_for_a_teamless_lead(self):
        with tempfile.TemporaryDirectory() as p:
            self._task(self.NOW, 1)
            self.assertEqual(hooklib.tasks_dir(self.NOW, p),
                             os.path.join(self.cfg, "tasks", "session-%s" % self.NOW[:8]))


    def test_a_worktree_under_the_project_is_not_the_lead(self):
        """These lookups ARE the lead-only guarantee the id-equality check used to carry.
        A branch office and a dept worktree both live under the project root, so anything
        looser than exact cwd equality hands them the CEO's team and task store — 0.9.59
        did exactly that and the capacity sentinel started ordering the Marketing branch
        to assign the CEO's cards."""
        with tempfile.TemporaryDirectory() as p:
            self._team(self.BORN, p)
            wt = os.path.join(p, ".claude", "worktrees", "Marketing")
            os.makedirs(wt, exist_ok=True)
            self.assertEqual(hooklib.team_key(self.NOW, p), self.BORN[:8])
            self.assertIsNone(hooklib.team_key(self.NOW, wt))

    def test_local_office_names_the_branch_and_leaves_the_ceo_blank(self):
        with tempfile.TemporaryDirectory() as p:
            os.makedirs(os.path.join(p, ".claude"), exist_ok=True)
            with open(os.path.join(p, ".claude", "orchestrate.json"), "w") as f:
                f.write('{"active":true}')
            wt = os.path.join(p, ".claude", "worktrees", "Marketing")
            os.makedirs(os.path.join(wt, ".claude"), exist_ok=True)
            with open(os.path.join(wt, ".claude", "office.json"), "w") as f:
                json.dump({"office": "Marketing"}, f)
            self.assertEqual(hooklib.local_office(p), "")
            self.assertEqual(hooklib.local_office(wt), "Marketing")
            # a subdirectory of the branch still resolves to the branch
            sub = os.path.join(wt, "src")
            os.makedirs(sub, exist_ok=True)
            self.assertEqual(hooklib.local_office(sub), "Marketing")


if __name__ == "__main__":
    unittest.main()
