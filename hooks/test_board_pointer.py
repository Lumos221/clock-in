"""Tests for stop_board_pointer.py — the board announcing itself.
Run: python3 hooks/test_board_pointer.py"""
import os, io, sys, json, time, tempfile, unittest, contextlib
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
import stop_board_pointer as bp
import board

board._SKIP_SERVER = True


def _project(d, active=True):
    os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
    with open(os.path.join(d, ".claude", "orchestrate.json"), "w", encoding="utf-8") as f:
        json.dump({"active": active}, f)
    return d


def _post(d, dept="CEO", kind="decision", text="Ship it?"):
    return board.board_add(d, dept, kind, text)


def _age(d, eid, hours):
    """Backdate an entry's creation, the way a board nobody clears actually looks."""
    p = board._store_path(d)
    store = board.load_store(p)
    for e in store["entries"]:
        if e["id"] == eid:
            e["created"] = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")
    board.save_store(p, store)


class Pointer(unittest.TestCase):
    def setUp(self):
        # A real banner during a test run would spam the desktop; capture instead.
        self.banners = []
        self._real = bp.notify
        bp.notify = lambda title, body: self.banners.append((title, body)) or True

    def tearDown(self):
        bp.notify = self._real

    def _run(self, d):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ret = bp.run({"cwd": d}, None)
        return ret, err.getvalue()

    # ---- gating ----------------------------------------------------------------
    def test_off_a_board_project_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._run(d), (None, ""))

    def test_inactive_project_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d, active=False)
            _post(d)
            self.assertEqual(self._run(d)[1], "")

    def test_empty_board_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            self.assertEqual(self._run(d)[1], "")

    def test_info_only_board_needs_nothing_so_says_nothing(self):
        """Information is not a queue. Counting it would inflate every number the Boss reads."""
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _post(d, kind="info", text="Deploy is green.")
            self.assertEqual(self._run(d)[1], "")

    def test_notices_and_inspector_file_as_information(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            board.board_notice(d, "CEO", "ambiguous DONE")
            _post(d, dept="Inspector", kind="decision", text="复盘 verdict")
            needs, info = bp.waiting(d)
            self.assertEqual(needs, [])
            self.assertEqual(len(info), 2)

    # ---- the line --------------------------------------------------------------
    def test_it_points_and_never_carries_the_content(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _post(d, text="Annual toggle default-on or default-off?")
            ret, err = self._run(d)
            self.assertIsNone(ret)                       # advisory: never blocks the turn
            self.assertIn("1 on your board", err)
            self.assertNotIn("Annual toggle", err)       # the terminal carries no content

    def test_the_line_breaks_down_by_kind(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _post(d, kind="decision", text="Ship?")
            _post(d, kind="blocker", text="Staging key expired.")
            err = self._run(d)[1]
            self.assertIn("2 on your board", err)
            self.assertIn("blocker 1", err)
            self.assertIn("decision 1", err)

    def test_it_reports_the_oldest_age(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            e = _post(d)
            _age(d, e["id"], 30)
            self.assertIn("oldest 30h", self._run(d)[1])

    def test_info_count_rides_along_when_there_is_any(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _post(d)
            _post(d, kind="info", text="FYI deploy green")
            self.assertIn("1 info", self._run(d)[1])

    # ---- one announcement per change -------------------------------------------
    def test_the_same_board_is_announced_once(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _post(d)
            self.assertIn("board", self._run(d)[1])
            self.assertEqual(self._run(d)[1], "")        # no nagging every turn

    def test_a_new_arrival_speaks_again(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _post(d, text="Ship?")
            self._run(d)
            _post(d, text="Rename the plan?")
            self.assertIn("2 on your board", self._run(d)[1])

    def test_a_board_nobody_clears_re_speaks_as_it_ages(self):
        """Silence-until-changed would let a forgotten board stay forgotten forever."""
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            e = _post(d)
            self.assertIn("board", self._run(d)[1])
            _age(d, e["id"], bp.AGE_BUCKET_HOURS + 1)
            self.assertIn("oldest", self._run(d)[1])

    def test_clearing_the_board_resets_it(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            e = _post(d)
            self._run(d)
            board.board_done(d, e["id"], "done")
            self.assertEqual(self._run(d)[1], "")
            _post(d, text="Something new?")
            self.assertIn("1 on your board", self._run(d)[1])

    # ---- the banner ------------------------------------------------------------
    def test_arrival_fires_one_banner_carrying_the_first_ask(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _post(d, text="Ship the pricing page? :: costs a day")
            self._run(d)
            self.assertEqual(len(self.banners), 1)
            title, body = self.banners[0]
            self.assertIn("1 on your board", title)
            self.assertIn("Ship the pricing page?", body)
            self.assertNotIn("costs a day", body)        # the ask, not the detail

    def test_a_batch_of_arrivals_is_one_banner(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _post(d, text="One?")
            _post(d, text="Two?")
            _post(d, text="Three?")
            self._run(d)
            self.assertEqual(len(self.banners), 1)
            self.assertIn("+2 more", self.banners[0][1])

    def test_ageing_re_speaks_the_line_but_never_re_banners(self):
        """A banner saying 'still 2 waiting' is nagging; the terminal line is not."""
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            e = _post(d)
            self._run(d)
            self.assertEqual(len(self.banners), 1)
            _age(d, e["id"], bp.AGE_BUCKET_HOURS + 1)
            self.assertIn("oldest", self._run(d)[1])
            self.assertEqual(len(self.banners), 1)       # no second banner

    def test_notify_is_time_boxed_and_swallows_failure(self):
        """A notification is never worth a hung or crashed turn end."""
        self.assertLessEqual(bp.NOTIFY_TIMEOUT, 5)
        real_run = bp.subprocess.run
        bp.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(OSError("no osascript"))
        try:
            self.assertFalse(self._real("t", "b"))
        finally:
            bp.subprocess.run = real_run

    # ---- shared state ----------------------------------------------------------
    def test_two_sessions_on_one_board_announce_an_arrival_once(self):
        """Sessions sitting at different depths resolve the same root, so the memory of
        what has already been announced is shared and an arrival is never double-called."""
        with tempfile.TemporaryDirectory() as d:
            d = os.path.realpath(d)
            _project(d)
            _post(d)
            self.assertIn("board", self._run(d)[1])
            sub = os.path.join(d, "sub", "deep")
            os.makedirs(sub)
            self.assertEqual(self._run(sub)[1], "")
            self.assertEqual(len(self.banners), 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
