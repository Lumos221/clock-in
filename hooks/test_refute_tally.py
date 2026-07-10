"""Tests for stop_refute_tally.py — the per-task circuit breaker + self-arming
sentinels. Run: python3 hooks/test_refute_tally.py"""
import os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
import board
import stop_refute_tally as tally_mod
import posttool_backlog_log as bl

board._SKIP_SERVER = True  # never spawn a panel/browser in tests
TH = {"chaos_ceo_refutes": 3, "bounce_diagnose": 2, "bounce_escalate": 3}


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()


def _reviews(root):
    return os.path.join(root, "docs", "reviews")


def _open_items(root, dept=None):
    return [e for e in board.board_list(root, dept) if e["status"] == "open"]


class L1Refutes(unittest.TestCase):
    def test_below_threshold_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            for n in (1, 2):
                _touch(os.path.join(_reviews(d), "plan.%d.refute" % n))
            tally_mod.tally(d, TH)
            self.assertEqual(_open_items(d), [])

    def test_refute_threshold_flags_once(self):
        with tempfile.TemporaryDirectory() as d:
            for n in (1, 2, 3):
                _touch(os.path.join(_reviews(d), "plan.%d.refute" % n))
            tally_mod.tally(d, TH)
            items = _open_items(d, "督察")
            self.assertEqual(len(items), 1)
            self.assertIn("L1 封驳", items[0]["text"])
            # re-run (even with a 4th refute) does not duplicate
            _touch(os.path.join(_reviews(d), "plan.4.refute"))
            tally_mod.tally(d, TH)
            self.assertEqual(len(_open_items(d, "督察")), 1)

    def test_sentinel_rearms_after_ledger_archive(self):
        """Resolving an escalation archives the refutes (SKILL §2.3); the NEXT
        generation of 3 refutes must flag again — a permanent sentinel went silent."""
        with tempfile.TemporaryDirectory() as d:
            for n in (1, 2, 3):
                _touch(os.path.join(_reviews(d), "plan.%d.refute" % n))
            tally_mod.tally(d, TH)
            e = _open_items(d, "督察")[0]
            board.board_done(d, e["id"])                       # Boss resolves
            for n in (1, 2, 3):                                # ...and archives
                os.remove(os.path.join(_reviews(d), "plan.%d.refute" % n))
            tally_mod.tally(d, TH)                             # count 0 → re-arm
            for n in (5, 6, 7):
                _touch(os.path.join(_reviews(d), "plan.%d.refute" % n))
            tally_mod.tally(d, TH)
            self.assertEqual(len(_open_items(d, "督察")), 1)   # gen-2 flags again


class L2PerTask(unittest.TestCase):
    def test_first_bounce_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(os.path.join(_reviews(d), "RnD.5.1.fail"))
            tally_mod.tally(d, TH)
            self.assertEqual(_open_items(d), [])

    def test_second_bounce_on_one_task_flags_diagnose_once(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(os.path.join(_reviews(d), "RnD.5.1.fail"))
            _touch(os.path.join(_reviews(d), "RnD.5.2.fail"))
            tally_mod.tally(d, TH)
            items = _open_items(d, "RnD")
            self.assertEqual(len(items), 1)
            self.assertIn("督察", items[0]["text"])
            self.assertIn("task 5", items[0]["text"])
            tally_mod.tally(d, TH)                             # no duplicate
            self.assertEqual(len(_open_items(d, "RnD")), 1)

    def test_third_bounce_escalates_to_boss(self):
        with tempfile.TemporaryDirectory() as d:
            for n in (1, 2, 3):
                _touch(os.path.join(_reviews(d), "RnD.5.%d.fail" % n))
            tally_mod.tally(d, TH)
            texts = [e["text"] for e in _open_items(d, "RnD")]
            self.assertTrue(any("Boss decision" in t for t in texts))

    def test_tasks_are_independent(self):
        """One bounce each on two tasks of the same dept is NOT a dept-career count."""
        with tempfile.TemporaryDirectory() as d:
            _touch(os.path.join(_reviews(d), "RnD.5.1.fail"))
            _touch(os.path.join(_reviews(d), "RnD.9.1.fail"))
            tally_mod.tally(d, TH)
            self.assertEqual(_open_items(d), [])

    def test_dept_casing_is_one_bucket(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(os.path.join(_reviews(d), "frontend.8.1.fail"))
            _touch(os.path.join(_reviews(d), "Frontend.8.2.fail"))
            tally_mod.tally(d, TH)
            self.assertEqual(len(_open_items(d)), 1)

    def test_completion_sweep_rearms_a_recycled_task_id(self):
        """Completion archives the task's markers (posttool hook); a LATER task that
        recycles the id must start from zero and be able to flag again."""
        with tempfile.TemporaryDirectory() as d:
            _touch(os.path.join(_reviews(d), "RnD.5.1.fail"))
            _touch(os.path.join(_reviews(d), "RnD.5.2.fail"))
            _touch(os.path.join(_reviews(d), "5.pass"))
            tally_mod.tally(d, TH)
            board.board_done(d, _open_items(d, "RnD")[0]["id"])
            bl.consume_pass(d, "5")                            # task completes
            tally_mod.tally(d, TH)                             # count 0 → re-arm
            _touch(os.path.join(_reviews(d), "RnD.5.1.fail"))  # next session, same id
            tally_mod.tally(d, TH)
            self.assertEqual(_open_items(d), [])               # 1 bounce → silent
            _touch(os.path.join(_reviews(d), "RnD.5.2.fail"))
            tally_mod.tally(d, TH)
            self.assertEqual(len(_open_items(d, "RnD")), 1)    # 2nd → flags again

    def test_alias_handle_is_surfaced_not_silently_bucketed(self):
        """Regression (refcheck, web.40.1.fail): a legacy alias splits one task's
        bounces across buckets — neither reaches the diagnose threshold, the breaker
        never fires. With a roster, the hook must surface the alias itself."""
        with tempfile.TemporaryDirectory() as d:
            _touch(os.path.join(_reviews(d), "web.40.1.fail"))
            _touch(os.path.join(_reviews(d), "Frontend.40.2.fail"))
            tally_mod.tally(d, TH, roster=["Frontend", "QA"])
            items = _open_items(d, "督察")
            self.assertEqual(len(items), 1)
            self.assertIn("'web'", items[0]["text"])
            self.assertIn("alias", items[0]["text"])
            tally_mod.tally(d, TH, roster=["Frontend", "QA"])   # no duplicate
            self.assertEqual(len(_open_items(d, "督察")), 1)

    def test_canonical_handles_and_no_roster_stay_silent(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(os.path.join(_reviews(d), "frontend.8.1.fail"))   # casing ≠ alias
            tally_mod.tally(d, TH, roster=[{"handle": "Frontend"}])
            self.assertEqual(_open_items(d), [])
        with tempfile.TemporaryDirectory() as d:
            _touch(os.path.join(_reviews(d), "web.40.1.fail"))
            tally_mod.tally(d, TH)                # no roster → detector off
            self.assertEqual(_open_items(d), [])

    def test_pass_refute_and_malformed_files_are_not_counted(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(os.path.join(_reviews(d), "3.pass"))
            _touch(os.path.join(_reviews(d), "plan.1.refute"))
            _touch(os.path.join(_reviews(d), "stray.fail"))     # not <dept>.<id>.<n>.fail
            _touch(os.path.join(_reviews(d), "RnD.5.1.fail"))
            tally_mod.tally(d, TH)
            self.assertEqual(_open_items(d), [])


if __name__ == "__main__":
    unittest.main()
