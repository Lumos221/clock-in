"""Tests for posttool_backlog_log.py — the completion logger and the 审查-pass
retirement that keeps the review gate honest across sessions.
Run: python3 hooks/test_backlog_log.py"""
import os, sys, json, tempfile, subprocess, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import posttool_backlog_log as bl

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posttool_backlog_log.py")

TASKBOARD = """# demo · TaskBoard

## Active

### TASK-001 · login form
- **dept:** RnD
- **task_id:** 3
- **status:** review

## Recently shipped
<!-- SHIPPED:START -->
<!-- SHIPPED:END -->
"""


def _proj(d):
    os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
    with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
        f.write('{"active":true}')


def _run_hook(root, task_id="3", status="completed"):
    payload = {"cwd": root, "tool_name": "TaskUpdate",
               "tool_input": {"taskId": task_id, "status": status}}
    subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                   text=True, capture_output=True, timeout=20)


class CardFor(unittest.TestCase):
    def test_finds_dept_name_and_label_by_task_id(self):
        self.assertEqual(bl.card_for(TASKBOARD, "3"), ("RnD", "login form", "TASK-001"))

    def test_hash_number_heading_label(self):
        board = TASKBOARD.replace("TASK-001 · login form", "#139 · INVITE-PDF-REORG — rework")
        self.assertEqual(bl.card_for(board, "3"),
                         ("RnD", "INVITE-PDF-REORG — rework", "#139"))

    def test_no_prefix_match_on_ids(self):
        self.assertEqual(bl.card_for(TASKBOARD.replace("task_id:** 3", "task_id:** 30"), "3"),
                         (None, None, None))


class ConsumePass(unittest.TestCase):
    def test_pass_is_archived_on_completion(self):
        with tempfile.TemporaryDirectory() as d:
            rev = os.path.join(d, "docs", "reviews")
            os.makedirs(rev)
            open(os.path.join(rev, "3.pass"), "w").write("ok")
            dst = bl.consume_pass(d, "3")
            self.assertFalse(os.path.exists(os.path.join(rev, "3.pass")))
            self.assertEqual(dst, os.path.join(rev, "archive", "3.pass"))

    def test_collision_suffixes_never_clobbers(self):
        with tempfile.TemporaryDirectory() as d:
            rev = os.path.join(d, "docs", "reviews")
            os.makedirs(os.path.join(rev, "archive"))
            open(os.path.join(rev, "archive", "3.pass"), "w").write("gen1")
            open(os.path.join(rev, "3.pass"), "w").write("gen2")
            dst = bl.consume_pass(d, "3")
            self.assertEqual(open(os.path.join(rev, "archive", "3.pass")).read(), "gen1")
            self.assertNotEqual(dst, os.path.join(rev, "archive", "3.pass"))

    def test_missing_pass_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(bl.consume_pass(d, "3"))

    def test_fails_and_sentinels_swept_with_the_pass(self):
        """The whole review trail retires with the task — a later task recycling the
        id must not inherit its bounce count or its tally sentinels."""
        with tempfile.TemporaryDirectory() as d:
            rev = os.path.join(d, "docs", "reviews")
            os.makedirs(os.path.join(rev, ".tally"))
            open(os.path.join(rev, "3.pass"), "w").write("ok")
            open(os.path.join(rev, "RnD.3.1.fail"), "w").close()
            open(os.path.join(rev, "RnD.3.2.fail"), "w").close()
            open(os.path.join(rev, "RnD.30.1.fail"), "w").close()   # different task
            open(os.path.join(rev, "plan.3.refute"), "w").close()   # L1 — not task 3's
            open(os.path.join(rev, ".tally", "rnd.3.diagnose"), "w").close()
            bl.consume_pass(d, "3")
            self.assertFalse(os.path.exists(os.path.join(rev, "RnD.3.1.fail")))
            self.assertTrue(os.path.exists(os.path.join(rev, "archive", "RnD.3.2.fail")))
            self.assertTrue(os.path.exists(os.path.join(rev, "RnD.30.1.fail")))  # untouched
            self.assertTrue(os.path.exists(os.path.join(rev, "plan.3.refute")))  # untouched
            self.assertFalse(os.path.exists(os.path.join(rev, ".tally", "rnd.3.diagnose")))


class RecentlyShipped(unittest.TestCase):
    def _board(self, d, text=TASKBOARD):
        os.makedirs(os.path.join(d, "docs"), exist_ok=True)
        p = os.path.join(d, "docs", "TaskBoard.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_inserts_newest_first_and_trims_to_keep(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._board(d)
            for i in range(1, 8):
                self.assertTrue(bl.update_shipped(p, "- line %d" % i, keep=5))
            text = open(p, encoding="utf-8").read()
            block = text.split(bl.SHIPPED_START)[1].split(bl.SHIPPED_END)[0]
            lines = [l for l in block.splitlines() if l.strip()]
            self.assertEqual(lines[0], "- line 7")     # newest on top
            self.assertEqual(len(lines), 5)            # trimmed
            self.assertNotIn("- line 1", block)
            self.assertIn("### TASK-001", text)        # rest of the board untouched

    def test_board_without_markers_is_left_alone(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._board(d, "# old board, hand-curated\n## Recently shipped\n- old line\n")
            before = open(p, encoding="utf-8").read()
            self.assertFalse(bl.update_shipped(p, "- new"))
            self.assertEqual(open(p, encoding="utf-8").read(), before)


class EndToEnd(unittest.TestCase):
    def test_completion_matching_no_card_logs_a_miss(self):
        # task_id never filled at CREATE → nothing to retire; the drift must leave
        # a trace instead of hiding (refcheck field case)
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            os.makedirs(os.path.join(d, "docs"), exist_ok=True)
            with open(os.path.join(d, "docs", "TaskBoard.md"), "w") as f:
                f.write(TASKBOARD)
            _run_hook(d, task_id="99")
            misses = open(os.path.join(d, ".claude", "marker-misses.log"),
                          encoding="utf-8").read()
            self.assertIn("completion #99 matched no card", misses)
            board = open(os.path.join(d, "docs", "TaskBoard.md"), encoding="utf-8").read()
            self.assertIn("### TASK-001", board)  # nothing wrongly retired

    def test_hash_headed_card_ships_with_project_number(self):
        # Boss's ask (0.9.24): the durable #NNN rides the shipped line + BACKLOG
        # task cell — the platform id alone is unreferenceable next session
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            os.makedirs(os.path.join(d, "docs", "reviews"))
            board = TASKBOARD.replace("TASK-001 · login form", "#139 · INVITE-PDF-REORG")
            with open(os.path.join(d, "docs", "TaskBoard.md"), "w") as f:
                f.write(board)
            open(os.path.join(d, "docs", "reviews", "3.pass"), "w").write("ok")
            _run_hook(d)
            tb = open(os.path.join(d, "docs", "TaskBoard.md"), encoding="utf-8").read()
            self.assertIn("· #139 · #3 · RnD · INVITE-PDF-REORG ·", tb)
            backlog = open(os.path.join(d, "docs", "BACKLOG.md"), encoding="utf-8").read()
            self.assertIn("| #139 INVITE-PDF-REORG |", backlog)

    def test_completion_appends_backlog_row_and_retires_pass(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            os.makedirs(os.path.join(d, "docs", "reviews"))
            with open(os.path.join(d, "docs", "TaskBoard.md"), "w") as f:
                f.write(TASKBOARD)
            open(os.path.join(d, "docs", "reviews", "3.pass"), "w").write("ok")
            _run_hook(d)
            backlog = open(os.path.join(d, "docs", "BACKLOG.md"), encoding="utf-8").read()
            self.assertIn("| 3 | RnD | login form | done |", backlog)
            self.assertFalse(os.path.exists(os.path.join(d, "docs", "reviews", "3.pass")))
            self.assertTrue(os.path.exists(os.path.join(d, "docs", "reviews", "archive", "3.pass")))
            board = open(os.path.join(d, "docs", "TaskBoard.md"), encoding="utf-8").read()
            self.assertIn("· #3 · RnD · login form ·", board)   # shipped line hook-written
            self.assertNotIn("### TASK-001", board)             # card retired from Active

    def test_completion_leaves_multi_id_cards_alone(self):
        """A shared card ("task_id:** 6 规格 · 7 build") must survive one of its ids
        completing — surgery on a half-understood card would destroy the others."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            os.makedirs(os.path.join(d, "docs", "reviews"))
            shared = TASKBOARD.replace("task_id:** 3", "task_id:** 3 spec · 7 build")
            with open(os.path.join(d, "docs", "TaskBoard.md"), "w") as f:
                f.write(shared)
            open(os.path.join(d, "docs", "reviews", "3.pass"), "w").write("ok")
            _run_hook(d)
            board = open(os.path.join(d, "docs", "TaskBoard.md"), encoding="utf-8").read()
            self.assertIn("### TASK-001", board)  # card kept

    def test_non_completed_and_inactive_are_noops(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _run_hook(d, status="in_progress")
            self.assertFalse(os.path.exists(os.path.join(d, "docs", "BACKLOG.md")))
        with tempfile.TemporaryDirectory() as d:  # no marker at all
            _run_hook(d)
            self.assertFalse(os.path.exists(os.path.join(d, "docs", "BACKLOG.md")))


if __name__ == "__main__":
    unittest.main()
