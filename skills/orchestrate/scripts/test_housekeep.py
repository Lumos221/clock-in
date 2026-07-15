"""Tests for housekeep.py — reference-safe archiving of stale visual artefacts,
residue sweep, stamp cadence, prune. Run: python3 skills/orchestrate/scripts/test_housekeep.py"""
import os, sys, json, time, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "hooks"))
import housekeep as hk

NOW = time.time()
OLD = NOW - 30 * 86400
FRESH = NOW - 1 * 86400


def _proj(d, cfg_extra=None, taskboard="# TB\n\n## Active\n\n## Recently shipped\n"):
    os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
    cfg = {"active": True}
    cfg.update(cfg_extra or {})
    with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
        json.dump(cfg, f)
    os.makedirs(os.path.join(d, "docs"), exist_ok=True)
    with open(os.path.join(d, "docs", "TaskBoard.md"), "w", encoding="utf-8") as f:
        f.write(taskboard)


def _file(d, rel, mtime):
    p = os.path.join(d, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write("x" * 100)
    os.utime(p, (mtime, mtime))
    return p


class Archiving(unittest.TestCase):
    def test_stale_archived_fresh_kept_subpath_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _file(d, "docs/mockups/spec-shots/old-mark.png", OLD)
            _file(d, "docs/mockups/fresh-mark.png", FRESH)
            moved = hk.archive(d, hk.load_cfg(d), now=NOW)
            self.assertEqual(len(moved), 1)
            self.assertIn("spec-shots/old-mark.png", moved[0][1])
            self.assertIn("archive/", moved[0][1])
            self.assertTrue(os.path.exists(os.path.join(d, "docs/mockups/fresh-mark.png")))
            self.assertFalse(os.path.exists(os.path.join(d, "docs/mockups/spec-shots/old-mark.png")))

    def test_active_card_reference_protects(self):
        tb = ("# TB\n\n## Active\n\n### #3 · fix\n- see old-mark.png for the spec\n\n"
              "## Recently shipped\n- shipped-mark.png retired\n")
        with tempfile.TemporaryDirectory() as d:
            _proj(d, taskboard=tb)
            _file(d, "docs/mockups/old-mark.png", OLD)       # referenced in Active
            _file(d, "docs/mockups/shipped-mark.png", OLD)   # only in shipped tail
            moved = hk.archive(d, hk.load_cfg(d), now=NOW)
            self.assertEqual([m[0] for m in moved], ["docs/mockups/shipped-mark.png"])
            self.assertTrue(os.path.exists(os.path.join(d, "docs/mockups/old-mark.png")))

    def test_open_board_ask_protects(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _file(d, "docs/mockups/asked.png", OLD)
            with open(os.path.join(d, ".claude", "boss-board.json"), "w") as f:
                json.dump({"entries": [{"status": "open", "text": "eyeball asked.png"}]}, f)
            self.assertEqual(hk.archive(d, hk.load_cfg(d), now=NOW), [])

    def test_no_dir_no_default_scan(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)  # no docs/mockups at all
            self.assertEqual(hk.hk_dirs(d, hk.load_cfg(d)), [])

    def test_configured_dir_and_days(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d, cfg_extra={"housekeeping": [{"path": "art", "days": 2}]})
            _file(d, "art/x.png", NOW - 3 * 86400)
            moved = hk.archive(d, hk.load_cfg(d), now=NOW)
            self.assertEqual(len(moved), 1)

    def test_collision_suffixes(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _file(d, "docs/mockups/a.png", OLD)
            hk.archive(d, hk.load_cfg(d), now=NOW)
            _file(d, "docs/mockups/a.png", OLD)              # same name again
            moved = hk.archive(d, hk.load_cfg(d), now=NOW)
            self.assertTrue(moved[0][1].endswith("a-1.png"))


class StampAndResidue(unittest.TestCase):
    def test_stamp_written_and_aged(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            os.makedirs(os.path.join(d, "docs/mockups"))
            self.assertIsNone(hk.stamp_age_days(d, now=NOW))
            hk.archive(d, hk.load_cfg(d), now=NOW)
            self.assertLess(hk.stamp_age_days(d), 1)

    def test_residue_sweep(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            os.makedirs(os.path.join(d, "docs/mockups"))
            _file(d, ".claude/idle-nudges/old.json", OLD)
            _file(d, ".claude/idle-nudges/fresh.json", FRESH)
            log = os.path.join(d, ".claude", "marker-misses.log")
            with open(log, "w") as f:
                f.write("m" * (hk.LOG_ROTATE_BYTES + 1))
            hk.archive(d, hk.load_cfg(d), now=NOW)
            self.assertFalse(os.path.exists(os.path.join(d, ".claude/idle-nudges/old.json")))
            self.assertTrue(os.path.exists(os.path.join(d, ".claude/idle-nudges/fresh.json")))
            self.assertTrue(os.path.exists(log + ".1"))
            self.assertFalse(os.path.exists(log))


class Prune(unittest.TestCase):
    def test_prune_only_old_archives(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _file(d, "docs/mockups/archive/2026-05/old.png", NOW - 90 * 86400)
            _file(d, "docs/mockups/archive/2026-07/new.png", FRESH)
            _file(d, "docs/mockups/live.png", NOW - 90 * 86400)  # NOT under archive/
            gone = hk.prune(d, hk.load_cfg(d), 60, now=NOW)
            self.assertEqual(gone, ["docs/mockups/archive/2026-05/old.png"])
            self.assertTrue(os.path.exists(os.path.join(d, "docs/mockups/live.png")))


class SessionStartNudge(unittest.TestCase):
    def test_flag_fires_then_clears_after_run(self):
        import session_start as ss
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _file(d, "docs/mockups/old.png", OLD)
            cfg = hk.load_cfg(d)
            self.assertIn("housekeeping due", ss.housekeep_flag(d, cfg) or "")
            hk.archive(d, cfg, now=NOW)
            self.assertIsNone(ss.housekeep_flag(d, cfg))


if __name__ == "__main__":
    unittest.main()
