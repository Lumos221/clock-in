"""Tests for stop_refute_tally.py — the ledger tally + flag-once surfacing.
Run: python3 hooks/test_refute_tally.py"""
import os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
import board
import stop_refute_tally as tally_mod

board._SKIP_SERVER = True  # never spawn a panel/browser in tests
TH = {"chaos_ceo_refutes": 3, "retune_after_bounces": 3, "fire_after_more_fails": 3}


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()


def _reviews(root):
    return os.path.join(root, "docs", "reviews")


def _hr_items(root):
    return [e for e in board.board_list(root, "人事部") if e["status"] == "open"]


class Tally(unittest.TestCase):
    def test_below_threshold_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            for n in (1, 2):
                _touch(os.path.join(_reviews(d), "plan.%d.refute" % n))
            tally_mod.tally(d, TH)
            self.assertEqual(_hr_items(d), [])

    def test_refute_threshold_flags_once(self):
        with tempfile.TemporaryDirectory() as d:
            for n in (1, 2, 3):
                _touch(os.path.join(_reviews(d), "plan.%d.refute" % n))
            tally_mod.tally(d, TH)
            items = _hr_items(d)
            self.assertEqual(len(items), 1)
            self.assertIn("L1 封驳", items[0]["text"])
            # sentinel created
            self.assertTrue(os.path.exists(os.path.join(_reviews(d), ".tally", "ceo-refute-3")))
            # re-run (even with a 4th refute) does not duplicate
            _touch(os.path.join(_reviews(d), "plan.4.refute"))
            tally_mod.tally(d, TH)
            self.assertEqual(len(_hr_items(d)), 1)

    def test_dept_fails_retune_then_fire(self):
        with tempfile.TemporaryDirectory() as d:
            for n in (1, 2, 3):
                _touch(os.path.join(_reviews(d), "RnD.5.%d.fail" % n))
            tally_mod.tally(d, TH)
            items = _hr_items(d)
            self.assertEqual(len(items), 1)
            self.assertIn("retune", items[0]["text"])
            # climb to the fire threshold (6) → a second, distinct alert
            for n in (4, 5, 6):
                _touch(os.path.join(_reviews(d), "RnD.5.%d.fail" % n))
            tally_mod.tally(d, TH)
            texts = [e["text"] for e in _hr_items(d)]
            self.assertEqual(len(texts), 2)
            self.assertTrue(any("fire" in t for t in texts))

    def test_pass_and_other_files_are_not_counted(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(os.path.join(_reviews(d), "3.pass"))
            _touch(os.path.join(_reviews(d), "RnD.5.1.fail"))
            tally_mod.tally(d, TH)  # 1 fail, 1 pass → below any threshold
            self.assertEqual(_hr_items(d), [])


if __name__ == "__main__":
    unittest.main()
