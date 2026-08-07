"""Tests for stop_stale_stage.findings — the stall alarm.
It had none, and was wrong in the field in two independent ways on 2026-07-27.
Run: python3 hooks/test_stale_stage.py"""
import os, sys, time, tempfile, unittest
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
import stop_stale_stage as ss
import board


def _stamp(hours_ago):
    return (datetime.now() - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M")


def _card(root, num, status="doing", dept="Frontend", since_h=48, task_id=""):
    d = os.path.join(root, "docs", "board")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "%s-THING.md" % num)
    with open(p, "w", encoding="utf-8") as f:
        f.write('---\nid: %s\nname: THING\ndept: %s\nstatus: %s\nsince: "%s"\n'
                'task_id: %s\n---\n\nbody\n' % (num, dept, status, _stamp(since_h), task_id))
    return p


def _marker(root, name, hours_ago):
    d = os.path.join(root, "docs", "reviews")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write("ok")
    t = time.time() - hours_ago * 3600
    os.utime(p, (t, t))
    return p


def _kinds(rows):
    return {r[1]: r[0] for r in rows}


class MergeQueue(unittest.TestCase):
    """The count the Boss reads. It said 35 where the board confirmed 9."""

    def test_a_pass_written_during_this_stage_is_awaiting_merge(self):
        with tempfile.TemporaryDirectory() as d:
            _card(d, "400", status="doing", since_h=48)
            _marker(d, "Frontend.400.1.pass", hours_ago=2)
            self.assertEqual(_kinds(ss.findings(d, set(), 24)).get("400"), "待合并")

    def test_a_pass_predating_the_stage_is_not_a_verdict_on_this_leg(self):
        """The recycled-id collision: platform ids restart, so an old marker attaches to
        whatever card holds that number now. The board rejected these from 0.9.61; this
        alarm had no date test at all and counted every one."""
        with tempfile.TemporaryDirectory() as d:
            _card(d, "400", status="doing", since_h=2, task_id="49")
            _marker(d, "Frontend.49.1.pass", hours_ago=200)
            self.assertNotEqual(_kinds(ss.findings(d, set(), 24)).get("400"), "待合并")

    def test_a_durable_card_number_is_trusted_without_a_clock(self):
        with tempfile.TemporaryDirectory() as d:
            p = _card(d, "400", status="doing", since_h=2)
            open(p, "w", encoding="utf-8").write(
                "---\nid: 400\nname: T\ndept: Frontend\nstatus: doing\n---\n\nb\n")
            _marker(d, "Frontend.400.1.pass", hours_ago=200)
            self.assertEqual(_kinds(ss.findings(d, set(), 24)).get("400"), "待合并")

    def test_a_task_id_is_not_trusted_without_a_clock(self):
        """A card number is permanent; a platform id is recycled, so with nothing to check
        it against it proves nothing."""
        with tempfile.TemporaryDirectory() as d:
            p = _card(d, "400")
            open(p, "w", encoding="utf-8").write(
                "---\nid: 400\nname: T\ndept: Frontend\nstatus: doing\ntask_id: 49\n---\n\nb\n")
            _marker(d, "Frontend.49.1.pass", hours_ago=200)
            self.assertNotEqual(_kinds(ss.findings(d, set(), 24)).get("400"), "待合并")

    def test_the_note_does_not_assume_the_merge_is_still_owed(self):
        """Much of the queue is work already on master whose card was never completed, so
        the owed action is often completion alone."""
        with tempfile.TemporaryDirectory() as d:
            _card(d, "400", since_h=48)
            _marker(d, "Frontend.400.1.pass", hours_ago=2)
            note = [r[4] for r in ss.findings(d, set(), 24) if r[1] == "400"][0]
            self.assertIn("not landed", note)     # the CONDITION, not its phrasing
            self.assertIn("complete the card", note)


class NotEveryFileIsACard(unittest.TestCase):
    def test_a_numbered_document_in_the_board_folder_is_not_a_card(self):
        """A plan of record and a schema proposal live there too. With no frontmatter they
        parsed as cards with no status and no clock, so a durable-id match went unchecked
        and they sat in the alarm as awaiting-merge permanently."""
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "docs", "board"), exist_ok=True)
            with open(os.path.join(d, "docs", "board", "198-plan-of-record.md"), "w",
                      encoding="utf-8") as f:
                f.write("# Plan of record\n\nprose, no frontmatter\n")
            _marker(d, "Frontend.198.1.pass", hours_ago=200)
            self.assertEqual(ss.findings(d, set(), 24), [])


class OtherStates(unittest.TestCase):
    def test_review_with_no_marker_is_never_submitted(self):
        with tempfile.TemporaryDirectory() as d:
            _card(d, "300", status="review", since_h=48)
            self.assertEqual(_kinds(ss.findings(d, set(), 24)).get("300"), "未送审")

    def test_a_live_seat_is_a_working_queue_not_a_stall(self):
        with tempfile.TemporaryDirectory() as d:
            _card(d, "301", status="todo", dept="Frontend-384", since_h=48)
            self.assertEqual(ss.findings(d, {"frontend"}, 24), [])

    def test_a_dead_seat_past_the_dial_is_a_stall(self):
        with tempfile.TemporaryDirectory() as d:
            _card(d, "302", status="todo", dept="Frontend-384", since_h=48)
            self.assertEqual(_kinds(ss.findings(d, {"ops"}, 24)).get("302"), "派工")

    def test_an_unresolvable_roster_withholds_liveness_findings(self):
        """None ≠ empty set: treating unknown as nobody-alive is how a resolution bug
        becomes a wall of false alarms."""
        with tempfile.TemporaryDirectory() as d:
            _card(d, "303", status="todo", dept="Frontend-384", since_h=48)
            self.assertEqual(ss.findings(d, None, 24), [])

    def test_done_cards_are_not_stalled(self):
        with tempfile.TemporaryDirectory() as d:
            _card(d, "304", status="done", since_h=999)
            _marker(d, "Frontend.304.1.pass", hours_ago=1)
            self.assertEqual(ss.findings(d, set(), 24), [])


class ParityWithTheBoard(unittest.TestCase):
    def test_the_alarm_and_the_panel_read_the_evidence_identically(self):
        """The test that would have caught it: one rule, two readers, and only one of them
        had the date fix."""
        with tempfile.TemporaryDirectory() as d:
            _card(d, "400", status="doing", since_h=2, task_id="49")   # stale marker
            _card(d, "401", status="doing", since_h=48, task_id="50")  # fresh marker
            _marker(d, "Frontend.49.1.pass", hours_ago=200)
            _marker(d, "Frontend.50.1.pass", hours_ago=1)
            marks = board._review_markers(d)
            for num, tid, since_h in (("400", "49", 2), ("401", "50", 48)):
                mine = _kinds(ss.findings(d, set(), 24)).get(num)
                theirs = board.l2_verdict(marks, num, tid, _stamp(since_h))
                self.assertEqual(mine == "待合并", theirs == "pass", num)


if __name__ == "__main__":
    unittest.main(verbosity=1)
