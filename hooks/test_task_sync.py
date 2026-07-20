"""Tests for posttool_task_sync.py over the per-card store (0.9.28) — TaskCreate
births the card (durable #NNN minted at birth) or fills a hand-written one,
TaskUpdate mirrors the coarse lifecycle, multi-id prose task_ids match nobody,
and a legacy single-file board migrates lazily on the first actionable event.
Run: python3 hooks/test_task_sync.py"""
import os, sys, json, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hooklib, cardlib
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


def _digest(d):
    return open(os.path.join(d, "docs", "TaskBoard.md"), encoding="utf-8").read()


def _cards(d, sub=""):
    return cardlib.load(os.path.join(d, "docs", "board"), sub)


class Helpers(unittest.TestCase):
    """hooklib's single-file surgery still backs the migration-era paths."""
    def test_span_exact_id_only(self):
        self.assertIsNotNone(hooklib.tb_card_span(TASKBOARD, "3"))
        self.assertIsNone(hooklib.tb_card_span(TASKBOARD, "7"))   # multi-id card
        self.assertIsNone(hooklib.tb_card_span(TASKBOARD, "30"))  # no prefix match

    def test_set_field_inserts_when_missing(self):
        text = "## Active\n\n### X · thing\n- **task_id:** 9\n- **status:** todo\n"
        out = hooklib.tb_set_field(text, "9", "dept", "RnD")
        self.assertIn("- **dept:** RnD\n- **task_id:** 9", out)


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
    def test_card_born_with_task_id_and_minted_number(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            ts.run(_payload(d, "TaskCreate",
                            {"subject": "wire the API", "description": "spec line one\nlong tail",
                             "owner": "RnD"},
                            {"id": "9"}))
            born = [c for c in _cards(d) if c["name"] == "wire the API"]
            self.assertEqual(len(born), 1)
            self.assertEqual(born[0]["id"], 4)  # migrated cards took 1-3
            self.assertEqual(born[0]["task_id"], "9")
            self.assertEqual(born[0]["dept"], "RnD")
            self.assertEqual(born[0]["what"], "spec line one")
            text = _digest(d)
            self.assertIn("### #4 · wire the API", text)
            self.assertIn("- **task_id:** 9", text)
            self.assertNotIn("long tail", text)

    def test_hand_written_card_gets_filled_not_duplicated(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            ts.run(_payload(d, "TaskCreate",
                            {"subject": "hand-written, unregistered"}, {"id": "9"}))
            hits = [c for c in _cards(d) if c["name"] == "hand-written, unregistered"]
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]["task_id"], "9")
            self.assertEqual(_digest(d).count("hand-written, unregistered"), 1)

    def test_numbered_subject_births_number_faced_card(self):
        # 0.9.26 field case: the subject's durable #NNN becomes the card's id (the
        # coral-pill face), platform id in task_id; the replayed event dedups
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            for _ in range(2):
                ts.run(_payload(d, "TaskCreate",
                                {"subject": "#151 REDEEM-BUTTON-RED — redeem modal fix"},
                                {"id": "46"}))
            hits = [c for c in _cards(d) if c["id"] == 151]
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]["name"], "REDEEM-BUTTON-RED — redeem modal fix")
            self.assertEqual(hits[0]["task_id"], "46")
            self.assertEqual(_digest(d).count("### #151 · REDEEM-BUTTON-RED — redeem modal fix"), 1)

    def test_card_number_fills_hand_card(self):
        # the refcheck field norm: hand card '#130 · NAME — detail', CREATE subject
        # '#130 NAME — other detail' — the leading number alone must bridge them
        board_md = TASKBOARD.replace(
            "### TASK-003 · hand-written, unregistered",
            "### #130 · REDEEM-MODAL-CHROME — X close missing (REPEAT report)")
        with tempfile.TemporaryDirectory() as d:
            _proj(d, taskboard=board_md)
            ts.run(_payload(d, "TaskCreate",
                            {"subject": "#130 REDEEM-MODAL-CHROME — X close + action row"},
                            {"id": "15"}))
            card = [c for c in _cards(d) if c["id"] == 130][0]
            self.assertEqual(card["task_id"], "15")
            self.assertEqual(len([c for c in _cards(d) if "REDEEM" in c["name"]]), 1)

    def test_normalised_name_fills_hand_card(self):
        board_md = TASKBOARD.replace(
            "### TASK-003 · hand-written, unregistered",
            "### #90 · LEGAL-EINVOICE — feasibility")
        with tempfile.TemporaryDirectory() as d:
            _proj(d, taskboard=board_md)
            ts.run(_payload(d, "TaskCreate",
                            {"subject": "LEGAL-EINVOICE   —  feasibility"}, {"id": "15"}))
            card = [c for c in _cards(d) if c["id"] == 90][0]
            self.assertEqual(card["task_id"], "15")
            self.assertEqual(len([c for c in _cards(d) if "LEGAL" in c["name"]]), 1)

    def test_registered_card_never_refilled_by_number(self):
        # a card already holding a task_id is not a fill candidate even on number
        # match — the CREATE births a fresh card whose name keeps the whole subject
        board_md = TASKBOARD.replace(
            "### TASK-003 · hand-written, unregistered\n- **dept:** QA\n- **task_id:** —",
            "### #130 · already registered\n- **dept:** QA\n- **task_id:** 4")
        with tempfile.TemporaryDirectory() as d:
            _proj(d, taskboard=board_md)
            ts.run(_payload(d, "TaskCreate", {"subject": "#130 something else"}, {"id": "15"}))
            old = [c for c in _cards(d) if c["id"] == 130][0]
            self.assertEqual(old["task_id"], "4")  # untouched
            born = [c for c in _cards(d) if c["task_id"] == "15"][0]
            self.assertEqual(born["name"], "#130 something else")
            self.assertNotEqual(born["id"], 130)

    def test_duplicated_card_number_refuses_fill_and_birth(self):
        # two cards wearing #7 (concurrent minting) — filling would guess, birthing
        # would cascade (the 07-20 refcheck ghost-#190 incident): CREATE refuses
        with tempfile.TemporaryDirectory() as d:
            _proj(d, taskboard=None)
            bdir = os.path.join(d, "docs", "board")
            os.makedirs(bdir)
            for name in ("ALPHA — first claimant", "BETA — second claimant"):
                path = os.path.join(bdir, "7-%s.md" % cardlib.slugify(name))
                with open(path, "w", encoding="utf-8") as f:
                    f.write(cardlib.render_card({"id": 7, "name": name, "task_id": "—",
                                                 "status": "todo"}))
            ts.run(_payload(d, "TaskCreate", {"subject": "#7 · ALPHA — reworded detail"},
                            {"id": "15"}))
            cards = _cards(d)
            self.assertEqual(len(cards), 2)  # nothing born
            self.assertTrue(all(cardlib.clean(c.get("task_id", "")) == "" for c in cards))
            log = open(os.path.join(d, ".claude", "marker-misses.log"), encoding="utf-8").read()
            self.assertIn("worn by 2 cards", log)

    def test_recycled_id_detaches_stale_card(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            ts.run(_payload(d, "TaskCreate", {"subject": "brand new thing"}, {"id": "3"}))
            stale = [c for c in _cards(d) if c["name"] == "login form"][0]
            self.assertEqual(stale["task_id"], "—")  # kept, just detached
            born = [c for c in _cards(d) if c["name"] == "brand new thing"][0]
            self.assertEqual(born["task_id"], "3")
            misses = open(os.path.join(d, ".claude", "marker-misses.log")).read()
            self.assertIn("recycled", misses)

    def test_duplicate_event_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            for _ in range(2):
                ts.run(_payload(d, "TaskCreate", {"subject": "wire the API"}, {"id": "9"}))
            self.assertEqual(len([c for c in _cards(d) if c["name"] == "wire the API"]), 1)
            self.assertEqual(_digest(d).count("### #4 · wire the API"), 1)

    def test_no_board_file_creates_store_and_digest(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d, taskboard=None)
            ts.run(_payload(d, "TaskCreate", {"subject": "first task"}, {"id": "1"}))
            self.assertEqual(_cards(d)[0]["name"], "first task")
            self.assertEqual(_cards(d)[0]["id"], 1)
            text = _digest(d)
            self.assertIn("## Active", text)
            self.assertIn("### #1 · first task", text)

    def test_no_id_in_response_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            ts.run(_payload(d, "TaskCreate", {"subject": "x"}, "done"))
            self.assertEqual(_digest(d), TASKBOARD)  # not even migrated


class ExternalLane(unittest.TestCase):
    """0.9.29 分公司: external cards never join the platform lifecycle — a CREATE
    targeting one (by number or name) is refused with a trace, not filled, and
    never birthed as a duplicate."""

    def _proj_ext(self, d):
        board_md = TASKBOARD.replace(
            "### TASK-003 · hand-written, unregistered\n- **dept:** QA",
            "### #141 · MARKETING-LAUNCH — listing copy\n- **dept:** Marketing")
        os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
        with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
            f.write('{"active":true,"external":["Marketing"]}')
        os.makedirs(os.path.join(d, "docs"), exist_ok=True)
        with open(os.path.join(d, "docs", "TaskBoard.md"), "w", encoding="utf-8") as f:
            f.write(board_md)

    def test_create_targeting_external_card_refused_with_trace(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj_ext(d)
            ts.run(_payload(d, "TaskCreate",
                            {"subject": "#141 MARKETING-LAUNCH — listing copy"}, {"id": "9"}))
            card = [c for c in _cards(d) if c["id"] == 141][0]
            self.assertEqual(card["task_id"], "—")            # never registered
            self.assertIsNone(cardlib.find_task(_cards(d), "9"))  # no duplicate born
            misses = open(os.path.join(d, ".claude", "marker-misses.log")).read()
            self.assertIn("分公司", misses)

    def test_internal_cards_unaffected_by_external_flag(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj_ext(d)
            ts.run(_payload(d, "TaskCreate", {"subject": "wire the API"}, {"id": "9"}))
            self.assertIsNotNone(cardlib.find_task(_cards(d), "9"))


class Update(unittest.TestCase):
    def _migrated(self, d):
        _proj(d)
        cardlib.ensure_store(os.path.join(d), {"taskboard": "docs/TaskBoard.md"})

    def test_in_progress_mirrors_doing(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            ts.run(_payload(d, "TaskUpdate", {"taskId": "3", "status": "in_progress"}))
            card = cardlib.find_task(_cards(d), "3")
            self.assertEqual(card["status"], "doing")
            self.assertIn("- **status:** doing", _digest(d))

    def test_pending_mirrors_todo_and_same_status_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            ts.run(_payload(d, "TaskUpdate", {"taskId": "3", "status": "pending"}))
            card = cardlib.find_task(_cards(d), "3")
            self.assertEqual(card["status"], "todo")
            before = os.path.getmtime(card["_path"])
            ts.run(_payload(d, "TaskUpdate", {"taskId": "3", "status": "pending"}))
            self.assertEqual(os.path.getmtime(card["_path"]), before)  # no rewrite churn

    def test_multi_id_card_never_touched(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            ts.run(_payload(d, "TaskUpdate", {"taskId": "7", "status": "in_progress"}))
            card = [c for c in _cards(d) if c["name"] == "shared design chain"][0]
            self.assertEqual(card["task_id"], "6 规格 · 7 build")
            self.assertEqual(card["status"], "doing")

    def test_completed_left_to_backlog_hook(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            ts.run(_payload(d, "TaskUpdate", {"taskId": "3", "status": "completed"}))
            self.assertEqual(_digest(d), TASKBOARD)  # untouched, not even migrated

    def test_retire_statuses_archive_card(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            ts.run(_payload(d, "TaskUpdate", {"taskId": "3", "status": "deleted"}))
            self.assertIsNone(cardlib.find_task(_cards(d), "3"))
            arch = _cards(d, "archive")
            self.assertEqual(arch[0]["name"], "login form")
            self.assertNotIn("login form", _digest(d))

    def test_owner_fills_empty_dept_only(self):
        with tempfile.TemporaryDirectory() as d:
            board_txt = TASKBOARD.replace("- **dept:** RnD", "- **dept:** —")
            _proj(d, taskboard=board_txt)
            ts.run(_payload(d, "TaskUpdate", {"taskId": "3", "owner": "Frontend"}))
            self.assertEqual(cardlib.find_task(_cards(d), "3")["dept"], "Frontend")
        with tempfile.TemporaryDirectory() as d:
            _proj(d)  # dept already RnD — owner must not stomp it
            ts.run(_payload(d, "TaskUpdate", {"taskId": "3", "owner": "Frontend"}))
            self.assertEqual(cardlib.find_task(_cards(d), "3")["dept"], "RnD")


class Gating(unittest.TestCase):
    def test_inactive_and_unmarked_projects_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
                f.write('{"active":false}')
            ts.run(_payload(d, "TaskCreate", {"subject": "x"}, {"id": "9"}))
            self.assertEqual(_digest(d), TASKBOARD)
            self.assertFalse(os.path.isdir(os.path.join(d, "docs", "board")))
        with tempfile.TemporaryDirectory() as d:  # no marker at all
            ts.run(_payload(d, "TaskCreate", {"subject": "x"}, {"id": "9"}))
            self.assertFalse(os.path.exists(os.path.join(d, "docs", "TaskBoard.md")))

    def test_other_tools_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            ts.run(_payload(d, "Edit", {"file_path": "x"}, {}))
            self.assertEqual(_digest(d), TASKBOARD)


if __name__ == "__main__":
    unittest.main()
