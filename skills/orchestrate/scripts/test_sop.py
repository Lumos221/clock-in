#!/usr/bin/env python3
"""Tests for sop.py — the operating contract each seat is served.

The thing under test is a routing decision made from the process tree, so the tests
pin BOTH directions and the fail-open, because getting it wrong is silent: a one-shot
handed the standing-seat rules will try to claim a queue it has no desk for, and a
teammate denied them will never answer a shutdown request.
Run: python3 skills/orchestrate/scripts/test_sop.py"""
import os, sys, subprocess, unittest, unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sop

BIN = os.path.join(HERE, "..", "..", "..", "bin", "orchestrate-sop")
ADDENDUM_MARK = "Standing seat — the part that only applies"
CORE_MARK = "Operating contract — the core, and it binds every seat"

LEAD = "claude -c"
TEAMMATE = ("/opt/homebrew/Caskroom/claude-code@latest/2.1.219/claude "
            "--agent-id QA-377@session-14e4d4dd --agent-name QA-377 "
            "--team-name session-14e4d4dd --effort xhigh --model sonnet")
SHELL = "/bin/zsh -c -l setopt NO_EXTENDED_GLOB && eval 'orchestrate-sop'"


class Detection(unittest.TestCase):
    def _as(self, chain):
        return unittest.mock.patch.object(sop, "_ancestry", lambda pid, depth=8: chain)

    def test_a_teammate_is_recognised_by_its_own_argv(self):
        """A teammate is its own process and carries --agent-name; a subagent runs
        inside the lead's, which does not. That is the whole signal."""
        with self._as([SHELL, TEAMMATE, "-zsh"]):
            self.assertTrue(sop.is_teammate())

    def test_a_subagent_reads_the_lead_and_is_not_one(self):
        with self._as([SHELL, LEAD, "-zsh"]):
            self.assertFalse(sop.is_teammate())

    def test_the_NEAREST_claude_decides(self):
        """A teammate's shell must not be answered by the lead further up the tree."""
        with self._as([SHELL, TEAMMATE, "-zsh", LEAD]):
            self.assertTrue(sop.is_teammate())

    def test_a_handle_that_merely_contains_the_flag_name_is_not_a_teammate(self):
        with self._as([SHELL, "claude -c --resume agent-name-notes", "-zsh"]):
            self.assertFalse(sop.is_teammate())

    def test_no_claude_ancestor_fails_open_to_core(self):
        """Fail-open to the CORE contract: it is correct for every seat, and the
        addendum is the half that misleads when it does not apply."""
        with self._as(["/bin/zsh", "-zsh", "login -fp genius"]):
            self.assertFalse(sop.is_teammate())
        with self._as([]):
            self.assertFalse(sop.is_teammate())


class Output(unittest.TestCase):
    def _run(self, *args):
        r = subprocess.run([sys.executable, os.path.join(HERE, "sop.py"), *args],
                           capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_core_is_served_to_a_non_teammate_and_carries_no_addendum(self):
        out = self._run()                      # this test process has no --agent-name
        self.assertIn(CORE_MARK, out)
        self.assertNotIn(ADDENDUM_MARK, out)

    def test_full_forces_the_addendum(self):
        out = self._run("--full")
        self.assertIn(CORE_MARK, out)
        self.assertIn(ADDENDUM_MARK, out)

    def test_the_two_halves_do_not_repeat_each_other(self):
        """Each rule lives in exactly one of the two files. A rule in both drifts:
        one copy gets edited and the other quietly contradicts it."""
        full = self._run("--full")
        for once in ("CLAIM id=", "shutdown_response", "to:\"team-lead\"",
                     "While the Boss is with you"):
            self.assertEqual(full.count(once), 1, "%r appears %d times" % (once, full.count(once)))

    def test_a_one_shot_is_not_given_a_way_onto_the_board(self):
        """Raising an ask requires being alive to receive the answer. A one-shot is gone
        by the time they reply, so an ask in its name is one nobody can act on and a
        follow-up nobody can answer — it reports the need and the seat that spawned it
        owns raising it. (The 督察 is the standing exception and carries it in its own
        agent file, not here.)"""
        core = self._run()
        for teammate_only in ("@BOSS[", "@BOSS-INFO[", "mcp__boss__message", "@BOSS-DONE["):
            self.assertNotIn(teammate_only, core, teammate_only)
        self.assertIn("whether you will still be here when they answer", core)
        self.assertIn("@BOSS[", self._run("--full"))

    def test_the_wrapper_resolves_from_its_own_location(self):
        out = subprocess.run([BIN, "--full"], capture_output=True, text=True,
                             timeout=20, cwd="/tmp")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn(ADDENDUM_MARK, out.stdout)


if __name__ == "__main__":
    import unittest.mock
    unittest.main(verbosity=0)
