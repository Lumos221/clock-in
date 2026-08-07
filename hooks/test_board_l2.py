"""Tests for board.py's L2 marker attachment — the DATE check that stops a recycled
platform task id from pinning someone else's verdict on a card.
Run: python3 hooks/test_board_l2.py"""
import os, sys, time, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
import board


def _marker(root, name, when=None):
    d = os.path.join(root, "docs", "reviews")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write("verdict\n")
    if when is not None:
        os.utime(p, (when, when))
    return p


def _card(label, task_id, since, status="todo"):
    return {"label": label, "task_id": task_id, "since": since, "status": status}


DAY = 86400.0


class MarkerFreshness(unittest.TestCase):
    """Platform ids restart every session, so `49.pass` written in one session attaches
    to whatever card holds task_id 49 in the next one. On a live board 2026-07-26 that
    was EVERY L2 chip on the board: four cards wearing 已过审 from markers 5 to 8 days
    older than the stage they were sitting in — which is why a "passed" card still drew
    at 派工."""

    def test_marker_older_than_the_stage_clock_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            _marker(d, "49.pass", when=time.time() - 6 * DAY)
            t = [_card("#314", "49", _stamp(time.time() - 2 * DAY))]
            board._attach_l2(d, t)
            self.assertEqual(t[0]["l2"], "")

    def test_marker_newer_than_the_stage_clock_counts(self):
        with tempfile.TemporaryDirectory() as d:
            _marker(d, "49.pass", when=time.time() - 3600)
            t = [_card("#314", "49", _stamp(time.time() - 2 * DAY))]
            board._attach_l2(d, t)
            self.assertEqual(t[0]["l2"], "pass")

    def test_durable_number_match_is_date_checked_too(self):
        """A stale pass on the right card is still stale: it belongs to an earlier leg
        the CEO has since re-dispatched, and the current leg has not been reviewed."""
        with tempfile.TemporaryDirectory() as d:
            _marker(d, "314.pass", when=time.time() - 6 * DAY)
            t = [_card("#314", "", _stamp(time.time() - 1 * DAY))]
            board._attach_l2(d, t)
            self.assertEqual(t[0]["l2"], "")

    def test_no_stage_clock_trusts_the_durable_id_and_refuses_the_task_id(self):
        with tempfile.TemporaryDirectory() as d:
            _marker(d, "314.pass", when=time.time() - 6 * DAY)
            _marker(d, "49.fail", when=time.time() - 6 * DAY)
            durable = [_card("#314", "", "")]
            recycled = [_card("#999", "49", "")]
            board._attach_l2(d, durable)
            board._attach_l2(d, recycled)
            self.assertEqual(durable[0]["l2"], "pass")   # #NNN is permanent identity
            self.assertEqual(recycled[0]["l2"], "")      # task_id is not — refuse

    def test_minute_precision_stamp_does_not_reject_a_same_minute_pass(self):
        """`since` is minute-precision, so a pass written seconds later can read as
        microscopically older. The grace absorbs that; it does not soften the real test."""
        with tempfile.TemporaryDirectory() as d:
            now = time.time()
            _marker(d, "49.pass", when=now - 30)
            t = [_card("#314", "49", _stamp(now))]
            board._attach_l2(d, t)
            self.assertEqual(t[0]["l2"], "pass")

    def test_archived_marker_never_counts(self):
        with tempfile.TemporaryDirectory() as d:
            _marker(d, "49.pass.archived", when=time.time())
            t = [_card("#314", "49", _stamp(time.time() - DAY))]
            board._attach_l2(d, t)
            self.assertEqual(t[0]["l2"], "")

    def test_newest_marker_of_a_key_is_the_one_dated(self):
        with tempfile.TemporaryDirectory() as d:
            _marker(d, "49-leg1.pass", when=time.time() - 9 * DAY)
            _marker(d, "49-leg2.pass", when=time.time() - 60)
            t = [_card("#314", "49", _stamp(time.time() - DAY))]
            board._attach_l2(d, t)
            self.assertEqual(t[0]["l2"], "pass")

    def test_no_reviews_dir_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            t = [_card("#314", "49", _stamp(time.time()))]
            board._attach_l2(d, t)
            self.assertEqual(t[0]["l2"], "")


def _stamp(ts):
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M")


if __name__ == "__main__":
    unittest.main()
