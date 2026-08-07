"""Tests for hooklib.is_lead and the CEO-only Stop pieces that must honour it.
Run: python3 hooks/test_session_role.py"""
import os, io, sys, json, tempfile, unittest, contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
import hooklib, board

board._SKIP_SERVER = True


def _transcript(d, name=None, team=None, fname="t.jsonl"):
    """A teammate's transcript stamps agentName/teamName on every line; the lead's
    carries none."""
    p = os.path.join(d, fname)
    row = {"type": "user", "message": {"role": "user", "content": "hi"}}
    if name:
        row["agentName"] = name
        row["agentSetting"] = "clock-in:%s" % name
    if team:
        row["teamName"] = team
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return p


def _project(d):
    os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
    with open(os.path.join(d, ".claude", "orchestrate.json"), "w", encoding="utf-8") as f:
        json.dump({"active": True}, f)
    return d


class IsLead(unittest.TestCase):
    def test_a_named_teammate_is_not_the_lead(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(hooklib.is_lead(_transcript(d, "Frontend-384", "acme")))

    def test_the_lead_has_no_stamp(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(hooklib.is_lead(_transcript(d)))

    def test_the_literal_team_lead_name_is_the_lead(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(hooklib.is_lead(_transcript(d, "team-lead", "acme")))

    def test_a_missing_transcript_reads_as_lead(self):
        """Unknown must read as LEAD: the lead's transcript is precisely the one with no
        stamp, so treating absence as doubt would silence every sentinel for the one
        session that exists to receive them."""
        self.assertTrue(hooklib.is_lead("/no/such/file.jsonl"))
        self.assertTrue(hooklib.is_lead(""))

    def test_a_branch_office_session_is_not_a_teammate(self):
        """A 分公司 runs its own top-level session, so it carries no stamp and keeps its
        own mail nudge — the gate must not swallow it."""
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(hooklib.is_lead(_transcript(d, None, None)))

    def test_session_agent_returns_the_stamp(self):
        with tempfile.TemporaryDirectory() as d:
            name, setting, team = hooklib.session_agent(_transcript(d, "Ops-405", "acme"))
            self.assertEqual(name, "Ops-405")
            self.assertEqual(team, "acme")
            self.assertTrue(setting.endswith("Ops-405"))


class CeoOnlyPieces(unittest.TestCase):
    """A teammate finishing a turn IS a Stop in its own session, so gating on the event
    excludes nobody. Field case: a dept pane printed the stall report, a merge
    backlog and prompts to respawn agents — none of it the dept's business, and it only
    has to be obeyed once to put a department's hands on master."""

    PIECES = ("stop_capacity", "stop_stale_stage", "stop_task_reconcile",
              "stop_board_pointer", "stop_mail")

    def _silent_for_teammate(self, mod_name):
        mod = __import__(mod_name)
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            # a board item exists, so the piece would have something to say if it ran
            board.board_add(d, "Frontend", "decision", "Ship it?")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                ret = mod.run({"cwd": d, "session_id": "s",
                               "transcript_path": _transcript(d, "Frontend-384", "acme")},
                              "some text?")
            return ret, err.getvalue()

    def test_every_ceo_only_piece_is_silent_in_a_teammate_pane(self):
        for name in self.PIECES:
            with self.subTest(piece=name):
                ret, err = self._silent_for_teammate(name)
                self.assertEqual(err, "", name)
                self.assertIsNone(ret, name)

    def test_the_pointer_still_speaks_for_the_lead(self):
        """The gate must not silence the lead — that is the session it exists for."""
        import stop_board_pointer as bp
        real, bp.notify = bp.notify, lambda *a: True
        try:
            with tempfile.TemporaryDirectory() as d:
                _project(d)
                board.board_add(d, "Frontend", "decision", "Ship it?")
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    bp.run({"cwd": d, "transcript_path": _transcript(d)}, None)
                self.assertIn("on your board", err.getvalue())
        finally:
            bp.notify = real

    def test_a_teammate_never_consumes_the_lead_s_announcement(self):
        """Worse than noise: the pointer's state is shared, so a teammate ending a turn
        first would mark the arrival as announced and the lead would never see it."""
        import stop_board_pointer as bp
        real, bp.notify = bp.notify, lambda *a: True
        try:
            with tempfile.TemporaryDirectory() as d:
                _project(d)
                board.board_add(d, "Frontend", "decision", "Ship it?")
                bp.run({"cwd": d, "transcript_path": _transcript(d, "Frontend-384", "acme",
                                                                 "mate.jsonl")}, None)
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    bp.run({"cwd": d, "transcript_path": _transcript(d)}, None)
                self.assertIn("on your board", err.getvalue())
        finally:
            bp.notify = real


class OneReader(unittest.TestCase):
    def test_the_transcript_reader_lives_in_one_place(self):
        """Their CEO's own condition: not a second helper, or it becomes the third copy of
        the thing being complained about."""
        import stop_idle_nudge
        with open(stop_idle_nudge.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("hooklib.session_agent", src)
        self.assertNotIn('d.get("agentName")', src)   # no second parser here

    def test_the_boss_board_uses_the_shared_predicate(self):
        import stop_boss_board
        with open(stop_boss_board.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("hooklib.is_lead", src)
        self.assertNotIn("import stop_idle_nudge", src)


if __name__ == "__main__":
    unittest.main(verbosity=1)
