#!/usr/bin/env python3
"""Tests for stop_dead_letters.py — messages addressed to a handle nobody staffs.

A mailbox is a file named for the EXACT handle. Address `Frontend` when the live seat is
`Frontend-1096` and the message is written to `Frontend.json`, where nothing reads it and
nothing expires it — while the send returns a receipt, so the sender believes it landed.
Field state when this shipped: 52 such messages in one live team, 13 of them to a bare
handle whose seat was sitting right there.
Run: python3 hooks/test_dead_letters.py"""
import os, sys, json, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stop_dead_letters as dl

SID = "aaaa1111-2222-3333-4444-555566667777"


def _team(cfg_root, members, boxes):
    d = os.path.join(cfg_root, "teams", "session-%s" % SID[:8])
    os.makedirs(os.path.join(d, "inboxes"), exist_ok=True)
    json.dump({"leadSessionId": SID, "members": [{"name": m} for m in members]},
              open(os.path.join(d, "config.json"), "w"))
    for who, n in boxes.items():
        json.dump([{"from": "team-lead", "text": "x"} for _ in range(n)],
                  open(os.path.join(d, "inboxes", "%s.json" % who), "w"))


class DeadLetters(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.get("CLAUDE_CONFIG_DIR")
        self.cfg = tempfile.mkdtemp()
        os.environ["CLAUDE_CONFIG_DIR"] = self.cfg

    def tearDown(self):
        if self._env is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = self._env

    def _find(self):
        return {w: (n, mis) for w, n, _, mis in dl.dead_letters(SID)}

    def test_a_bare_handle_with_a_live_suffixed_seat_is_the_urgent_case(self):
        """The sender dropped the suffix. The seat is right there and never got its card."""
        _team(self.cfg, ["team-lead", "Frontend-1096"], {"Frontend": 5, "Frontend-1096": 2})
        got = self._find()
        self.assertEqual(got["Frontend"], (5, True))
        self.assertNotIn("Frontend-1096", got)          # a staffed box is not a dead letter

    def test_a_different_retired_seat_is_NOT_a_misaddress(self):
        """`Backend-IO-1025` sharing a base with the live `Backend-IO-1049` says nothing —
        it is a seat that retired, not a dropped suffix. Calling it a mis-address sends
        the CEO looking for a mistake it did not make."""
        _team(self.cfg, ["team-lead", "Backend-IO-1049"], {"Backend-IO-1025": 2})
        self.assertEqual(self._find()["Backend-IO-1025"], (2, False))

    def test_an_empty_box_is_not_a_dead_letter(self):
        _team(self.cfg, ["team-lead", "QA-7"], {"QA": 0, "Gone": 0})
        self.assertEqual(self._find(), {})

    def test_an_empty_roster_proves_nothing_and_reports_nothing(self):
        """No members[] is not 'every message is undeliverable' — it is 'we cannot tell'.
        Reading absence as proof is how a sweep destroys a whole board in one pass."""
        _team(self.cfg, [], {"Frontend": 9})
        self.assertEqual(dl.dead_letters(SID), [])

    def test_urgent_ones_sort_first(self):
        _team(self.cfg, ["team-lead", "Ops-3"],
              {"Ops": 1, "Legacy-9": 40})
        order = [w for w, _, _, _ in dl.dead_letters(SID)]
        self.assertEqual(order[0], "Ops")               # 1 msg, but it is live and waiting

    def test_it_is_silent_off_an_active_project_and_for_a_non_lead(self):
        with tempfile.TemporaryDirectory() as d:
            _team(self.cfg, ["team-lead", "Frontend-1"], {"Frontend": 3})
            self.assertIsNone(dl.run({"hook_event_name": "Stop", "cwd": d,
                                      "session_id": SID, "transcript_path": ""}))
            os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":false}')
            self.assertIsNone(dl.run({"hook_event_name": "Stop", "cwd": d,
                                      "session_id": SID, "transcript_path": ""}))


if __name__ == "__main__":
    unittest.main(verbosity=0)
