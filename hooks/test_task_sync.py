"""Tests for posttool_task_sync.py + the hooklib TaskBoard-surgery helpers —
TaskCreate births the card, TaskUpdate mirrors the coarse lifecycle, ambiguous
(multi-id / prose) cards are never touched.
Run: python3 hooks/test_task_sync.py"""
import os, sys, json, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hooklib
import posttool_task_sync as ts

TASKBOARD = """# demo · TaskBoard

## Active

### TASK-001 · login form
- **dept:** RnD
- **task_id:** 3
- **status:** review — waiting on the Auditor
- **what:** build it

### TASK-002 · shared design chain
- **dept:** Spec_Designer
- **task_id:** 6 规格 · 7 build
- **status:** doing

### TASK-003 · hand-written, unregistered
- **dept:** QA
- **task_id:** —
- **status:** todo

## Recently shipped
<!-- SHIPPED:START -->
<!-- SHIPPED:END -->
"""


def _proj(d, taskboard=TASKBOARD):
    os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
    with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
        f.write('{"active":true}')
    if taskboard is not None:
        os.makedirs(os.path.join(d, "docs"), exist_ok=True)
        with open(os.path.join(d, "docs", "TaskBoard.md"), "w", encoding="utf-8") as f:
            f.write(taskboard)


def _payload(root, tool, ti, resp=None):
    return {"cwd": root, "tool_name": tool, "tool_input": ti, "tool_response": resp}


def _board(d):
    return open(os.path.join(d, "docs", "TaskBoard.md"), encoding="utf-8").read()


class Helpers(unittest.TestCase):
    def test_span_exact_id_only(self):
        self.assertIsNotNone(hooklib.tb_card_span(TASKBOARD, "3"))
        self.assertIsNone(hooklib.tb_card_span(TASKBOARD, "7"))   # multi-id card
        self.assertIsNone(hooklib.tb_card_span(TASKBOARD, "30"))  # no prefix match

    def test_remove_card_removes_only_that_block(self):
        out = hooklib.tb_remove_card(TASKBOARD, "3")
        self.assertNotIn("login form", out)
        self.assertIn("shared design chain", out)
        self.assertIn("Recently shipped", out)

    def test_set_field_inserts_when_missing(self):
        text = "## Active\n\n### X · thing\n- **task_id:** 9\n- **status:** todo\n"
        out = hooklib.tb_set_field(text, "9", "dept", "RnD")
        self.assertIn("- **dept:** RnD\n- **task_id:** 9", out)

    def test_append_card_lands_inside_active(self):
        out = hooklib.tb_append_card(TASKBOARD, "### #9 · new one\n- **task_id:** 9")
        active = out.split("## Recently shipped")[0]
        self.assertIn("### #9 · new one", active)

    def test_append_card_creates_active_when_absent(self):
        out = hooklib.tb_append_card("", "### #9 · new one\n- **task_id:** 9")
        self.assertTrue(out.startswith("## Active"))
        self.assertIn("### #9 · new one", out)


class ExtractId(unittest.TestCase):
    def test_dict_shapes(self):
        self.assertEqual(ts.extract_id({"id": 7}), "7")
        self.assertEqual(ts.extract_id({"taskId": "12"}), "12")
        self.assertEqual(ts.extract_id({"task": {"id": "4"}}), "4")

    def test_string_and_content_shapes(self):
        self.assertEqual(ts.extract_id("Created task #7"), "7")
        self.assertEqual(ts.extract_id({"content": [{"type": "text", "text": "task 5 created"}]}), "5")
        self.assertIsNone(ts.extract_id("no id here"))


class Create(unittest.TestCase):
    def test_card_born_with_task_id(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            ts.run(_payload(d, "TaskCreate",
                            {"subject": "wire the API", "description": "spec line one\nlong tail",
                             "owner": "RnD"},
                            {"id": "9"}))
            text = _board(d)
            self.assertIn("### #9 · wire the API", text)
            self.assertIn("- **task_id:** 9", text)
            self.assertIn("- **dept:** RnD", text)
            self.assertIn("- **what:** spec line one", text)
            self.assertNotIn("long tail", text)
            active = text.split("## Recently shipped")[0]
            self.assertIn("### #9", active)  # born inside Active, not after shipped

    def test_hand_written_card_gets_filled_not_duplicated(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            ts.run(_payload(d, "TaskCreate",
                            {"subject": "hand-written, unregistered"}, {"id": "9"}))
            text = _board(d)
            self.assertEqual(text.count("hand-written, unregistered"), 1)
            self.assertIn("- **task_id:** 9", text)
            self.assertNotIn("### #9 ·", text)

    def test_numbered_subject_births_project_headed_card(self):
        # 0.9.26 field case: no hand card exists — a CREATE whose subject leads
        # with the durable #NNN must put THAT in the heading slot (the coral-pill
        # face), with the platform id in task_id; and the replayed event dedups
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            for _ in range(2):
                ts.run(_payload(d, "TaskCreate",
                                {"subject": "#151 REDEEM-BUTTON-RED — redeem modal fix"},
                                {"id": "46"}))
            text = _board(d)
            self.assertEqual(text.count("### #151 · REDEEM-BUTTON-RED — redeem modal fix"), 1)
            self.assertIn("- **task_id:** 46", text)
            self.assertNotIn("### #46", text)

    def test_card_number_fills_hand_card(self):
        # the refcheck field norm: heading '### #130 · NAME — detail', CREATE subject
        # '#130 NAME — other detail' — the leading number alone must bridge them
        board_md = TASKBOARD.replace(
            "### TASK-003 · hand-written, unregistered",
            "### #130 · REDEEM-MODAL-CHROME — X close missing (REPEAT report)")
        with tempfile.TemporaryDirectory() as d:
            _proj(d, taskboard=board_md)
            ts.run(_payload(d, "TaskCreate",
                            {"subject": "#130 REDEEM-MODAL-CHROME — X close + action row"},
                            {"id": "15"}))
            text = _board(d)
            self.assertIn("- **task_id:** 15", text)
            self.assertEqual(text.count("REDEEM-MODAL-CHROME"), 1)  # filled, no dup

    def test_card_number_ambiguity_appends(self):
        # two unregistered cards headed #7 → never guess, append a fresh card
        board_md = TASKBOARD.replace(
            "### TASK-003 · hand-written, unregistered",
            "### #7 · first seven\n- **task_id:** —\n\n### #7 · second seven")
        with tempfile.TemporaryDirectory() as d:
            _proj(d, taskboard=board_md)
            ts.run(_payload(d, "TaskCreate", {"subject": "#7 refit the thing"}, {"id": "15"}))
            text = _board(d)
            self.assertIn("### #15 · #7 refit the thing", text)  # appended, neither filled
            self.assertNotIn("- **task_id:** 15\n\n### #7", text)

    def test_normalised_name_fills_hand_card(self):
        board_md = TASKBOARD.replace(
            "### TASK-003 · hand-written, unregistered",
            "### #90 · LEGAL-EINVOICE — feasibility")
        with tempfile.TemporaryDirectory() as d:
            _proj(d, taskboard=board_md)
            ts.run(_payload(d, "TaskCreate",
                            {"subject": "LEGAL-EINVOICE   —  feasibility"}, {"id": "15"}))
            text = _board(d)
            self.assertIn("- **task_id:** 15", text)
            self.assertEqual(text.count("LEGAL-EINVOICE"), 1)

    def test_registered_card_never_refilled_by_number(self):
        # a card already holding a task_id is not a fill candidate even on number match
        board_md = TASKBOARD.replace(
            "### TASK-003 · hand-written, unregistered\n- **dept:** QA\n- **task_id:** —",
            "### #130 · already registered\n- **dept:** QA\n- **task_id:** 4")
        with tempfile.TemporaryDirectory() as d:
            _proj(d, taskboard=board_md)
            ts.run(_payload(d, "TaskCreate", {"subject": "#130 something else"}, {"id": "15"}))
            text = _board(d)
            self.assertIn("- **task_id:** 4", text)          # untouched
            self.assertIn("### #15 · #130 something else", text)  # appended instead

    def test_recycled_id_detaches_stale_card(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            ts.run(_payload(d, "TaskCreate", {"subject": "brand new thing"}, {"id": "3"}))
            text = _board(d)
            self.assertIn("### #3 · brand new thing", text)
            # the stale login-form card no longer claims id 3
            span = hooklib.tb_card_span(text, "3")
            self.assertIn("brand new thing", text[span[0]:span[1]])
            self.assertIn("login form", text)  # old card kept, just detached
            misses = open(os.path.join(d, ".claude", "marker-misses.log")).read()
            self.assertIn("recycled", misses)

    def test_duplicate_event_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            for _ in range(2):
                ts.run(_payload(d, "TaskCreate", {"subject": "wire the API"}, {"id": "9"}))
            self.assertEqual(_board(d).count("### #9 · wire the API"), 1)

    def test_no_board_file_creates_one(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d, taskboard=None)
            ts.run(_payload(d, "TaskCreate", {"subject": "first task"}, {"id": "1"}))
            text = _board(d)
            self.assertIn("## Active", text)
            self.assertIn("### #1 · first task", text)

    def test_no_id_in_response_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            ts.run(_payload(d, "TaskCreate", {"subject": "x"}, "done"))
            self.assertEqual(_board(d), TASKBOARD)


class Update(unittest.TestCase):
    def test_in_progress_mirrors_doing(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            ts.run(_payload(d, "TaskUpdate", {"taskId": "3", "status": "in_progress"}))
            span = hooklib.tb_card_span(_board(d), "3")
            self.assertIn("- **status:** doing", _board(d)[span[0]:span[1]])

    def test_pending_mirrors_todo_and_same_status_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            ts.run(_payload(d, "TaskUpdate", {"taskId": "3", "status": "pending"}))
            before = _board(d)
            self.assertIn("- **status:** todo", before)
            ts.run(_payload(d, "TaskUpdate", {"taskId": "3", "status": "pending"}))
            self.assertEqual(_board(d), before)  # idempotent, no rewrite churn

    def test_multi_id_card_never_touched(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            ts.run(_payload(d, "TaskUpdate", {"taskId": "7", "status": "in_progress"}))
            self.assertEqual(_board(d), TASKBOARD)

    def test_completed_left_to_backlog_hook(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            ts.run(_payload(d, "TaskUpdate", {"taskId": "3", "status": "completed"}))
            self.assertEqual(_board(d), TASKBOARD)

    def test_retire_statuses_remove_card(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            ts.run(_payload(d, "TaskUpdate", {"taskId": "3", "status": "deleted"}))
            text = _board(d)
            self.assertNotIn("login form", text)
            self.assertIn("shared design chain", text)

    def test_owner_fills_empty_dept_only(self):
        with tempfile.TemporaryDirectory() as d:
            board_txt = TASKBOARD.replace("- **dept:** RnD", "- **dept:** —")
            _proj(d, taskboard=board_txt)
            ts.run(_payload(d, "TaskUpdate", {"taskId": "3", "owner": "Frontend"}))
            span = hooklib.tb_card_span(_board(d), "3")
            self.assertIn("- **dept:** Frontend", _board(d)[span[0]:span[1]])
        with tempfile.TemporaryDirectory() as d:
            _proj(d)  # dept already RnD — owner must not stomp it
            ts.run(_payload(d, "TaskUpdate", {"taskId": "3", "owner": "Frontend"}))
            self.assertIn("- **dept:** RnD", _board(d))


class Gating(unittest.TestCase):
    def test_inactive_and_unmarked_projects_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
                f.write('{"active":false}')
            ts.run(_payload(d, "TaskCreate", {"subject": "x"}, {"id": "9"}))
            self.assertEqual(_board(d), TASKBOARD)
        with tempfile.TemporaryDirectory() as d:  # no marker at all
            ts.run(_payload(d, "TaskCreate", {"subject": "x"}, {"id": "9"}))
            self.assertFalse(os.path.exists(os.path.join(d, "docs", "TaskBoard.md")))

    def test_other_tools_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            ts.run(_payload(d, "Edit", {"file_path": "x"}, {}))
            self.assertEqual(_board(d), TASKBOARD)


if __name__ == "__main__":
    unittest.main()
