"""Tests for stop_board_digest.py — the turn-end digest freshener: regen only when
a card file outdates the digest (Obsidian / dept / branch-session edits), inert
everywhere else. Run: python3 hooks/test_board_digest.py"""
import os, sys, json, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cardlib
import stop_board_digest as sbd


def _proj(d, active=True):
    os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
    with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
        f.write('{"active":%s}' % ("true" if active else "false"))
    os.makedirs(os.path.join(d, "docs"), exist_ok=True)
    cfg = {"taskboard": "docs/TaskBoard.md"}
    bdir, _ = cardlib.ensure_store(d, cfg)
    return cfg, bdir


def _bump(path, secs=5):
    os.utime(path, (os.path.getmtime(path) + secs,) * 2)


class DigestFreshener(unittest.TestCase):
    def test_out_of_hook_edit_lands_on_digest_at_turn_end(self):
        with tempfile.TemporaryDirectory() as d:
            cfg, bdir = _proj(d)
            card = cardlib.new_card(bdir, "obsidian-edited", task_id="1")
            cardlib.regen_digest(d, cfg)
            cardlib.set_fields(card, status="blocked")  # an Obsidian-style direct edit
            _bump(card["_path"])
            sbd.run({"cwd": d}, None)
            text = open(os.path.join(d, "docs", "TaskBoard.md"), encoding="utf-8").read()
            self.assertIn("- **status:** blocked", text)

    def test_fresh_digest_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            cfg, bdir = _proj(d)
            cardlib.new_card(bdir, "quiet", task_id="1")
            cardlib.regen_digest(d, cfg)
            tb = os.path.join(d, "docs", "TaskBoard.md")
            before = os.path.getmtime(tb)
            sbd.run({"cwd": d}, None)
            self.assertEqual(os.path.getmtime(tb), before)  # no rewrite churn

    def test_turn_end_heals_essay_status_and_dup_ids(self):
        with tempfile.TemporaryDirectory() as d:
            cfg, bdir = _proj(d)
            card = cardlib.new_card(bdir, "ESSAY", task_id="1",
                                    status="MERGED 07-20 — L2 PASS x.1.pass")
            with open(os.path.join(bdir, "1-TWIN.md"), "w", encoding="utf-8") as f:
                f.write(cardlib.render_card({"id": 1, "name": "TWIN", "status": "todo"}))
            _bump(card["_path"], -10)  # ESSAY is the elder — it keeps #1
            sbd.run({"cwd": d}, None)
            cards = cardlib.load(bdir)
            self.assertEqual([c["id"] for c in cards], [1, 2])
            self.assertEqual(cards[0]["status"], "done")
            self.assertIn("状态注", cards[0]["_body"])
            text = open(os.path.join(d, "docs", "TaskBoard.md"), encoding="utf-8").read()
            self.assertIn("- **status:** done", text)  # sweep's writes reach the digest
            self.assertIn("#2 · TWIN", text)
            log = open(os.path.join(d, ".claude", "marker-misses.log"), encoding="utf-8").read()
            self.assertIn("board-hygiene", log)

    def test_inactive_or_storeless_projects_inert(self):
        with tempfile.TemporaryDirectory() as d:
            cfg, bdir = _proj(d, active=False)
            card = cardlib.new_card(bdir, "x", task_id="1")
            _bump(card["_path"])
            sbd.run({"cwd": d}, None)
            self.assertFalse(os.path.exists(os.path.join(d, "docs", "TaskBoard.md")))
        with tempfile.TemporaryDirectory() as d:  # active but no store dir → never migrates
            os.makedirs(os.path.join(d, ".claude"))
            with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
                f.write('{"active":true}')
            sbd.run({"cwd": d}, None)
            self.assertFalse(os.path.isdir(os.path.join(d, "docs", "board")))


if __name__ == "__main__":
    unittest.main()
