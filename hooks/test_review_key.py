"""Tests for the review-marker key: board.review_key and the completion gate that
reads it. Run: python3 hooks/test_review_key.py"""
import os, sys, json, time, tempfile, subprocess, unittest
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
import board
import pretool_review_gate as gate

GATE = os.path.join(HERE, "pretool_review_gate.py")


def _write(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _project(d, active=True):
    _write(os.path.join(d, ".claude", "orchestrate.json"), json.dumps({"active": active}))
    return d


def _card(d, num, task_id, name="THING"):
    _write(os.path.join(d, "docs", "board", "%s-%s.md" % (num, name)),
           "---\nstatus: review\ndept: Ops\ntask_id: %s\n---\n\nbody\n" % task_id)


def _run_gate(cwd, task_id="3", status="completed"):
    p = subprocess.run([sys.executable, GATE], text=True, capture_output=True,
                       input=json.dumps({"cwd": cwd, "tool_name": "TaskUpdate",
                                         "tool_input": {"taskId": task_id, "status": status}}))
    return p.returncode, p.stderr


class Key(unittest.TestCase):
    """One parser, both shapes. The Auditor's spec asks for `<id>.pass` on a pass but
    `<dept>.<id>.<n>.fail` on a bounce, so the field writes both ways."""

    def test_bare_id(self):
        self.assertEqual(board.review_key("108.pass"), "108")

    def test_legacy_id_with_slug(self):
        self.assertEqual(board.review_key("111-leg2-fe.pass"), "111")

    def test_dept_prefixed_shape(self):
        self.assertEqual(board.review_key("Frontend.115.1.pass"), "115")

    def test_dept_prefixed_with_slug_and_attempt(self):
        self.assertEqual(board.review_key("Ops.409-checkout-price.1.pass"), "409")

    def test_hyphenated_dept_is_not_mistaken_for_the_id(self):
        self.assertEqual(board.review_key("Backend-IO.395-apa-ellipsis.2.pass"), "395")

    def test_the_attempt_count_never_wins(self):
        """The id is the FIRST numeric segment; the trailing one is the attempt."""
        self.assertEqual(board.review_key("Prof_Academic.407.6.pass"), "407")

    def test_a_dept_handle_carrying_digits_is_skipped(self):
        """Task-named seats exist in the field (spacefix352), and the segment must start
        with the number to count."""
        self.assertEqual(board.review_key("spacefix352.409.1.pass"), "409")

    def test_external_card_x_prefix(self):
        self.assertEqual(board.review_key("x387.pass"), "387")

    def test_fail_markers_key_the_same_way(self):
        self.assertEqual(board.review_key("Legal.96.3.fail"), "96")

    def test_archived_never_counts(self):
        self.assertEqual(board.review_key("Ops.412.2.pass.archived"), "")

    def test_a_non_marker_is_not_a_marker(self):
        self.assertEqual(board.review_key("notes.txt"), "")
        self.assertEqual(board.review_key("plan.3.refute"), "")

    def test_non_numeric_key_falls_back_to_the_old_rule(self):
        self.assertEqual(board.review_key("abc.pass"), "abc")


class Gate(unittest.TestCase):
    def test_bare_marker_still_passes_the_gate(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _write(os.path.join(d, "docs", "reviews", "3.pass"), "ok")
            self.assertEqual(_run_gate(d, "3")[0], 0)

    def test_dept_prefixed_marker_now_passes_the_gate(self):
        """The field case: the review happened, the file was on disk, and the gate could
        not see it, so finished work could not be ticked off."""
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _write(os.path.join(d, "docs", "reviews", "Ops.3.1.pass"), "ok")
            self.assertEqual(_run_gate(d, "3")[0], 0)

    def test_a_marker_keyed_on_the_card_number_passes(self):
        """Platform ids restart per session, the card number does not, so a marker is
        legitimately keyed on either — the board has matched both since 0.9.58."""
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _card(d, "409", "77")
            _write(os.path.join(d, "docs", "reviews", "Ops.409-checkout-price.1.pass"), "ok")
            self.assertEqual(_run_gate(d, "77")[0], 0)

    def test_no_marker_at_all_still_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            code, err = _run_gate(d, "3")
            self.assertEqual(code, 2)
            self.assertIn("产出审查", err)

    def test_an_unrelated_marker_does_not_open_the_gate(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _write(os.path.join(d, "docs", "reviews", "Ops.999.1.pass"), "ok")
            self.assertEqual(_run_gate(d, "3")[0], 2)

    def test_an_archived_marker_does_not_open_the_gate(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _write(os.path.join(d, "docs", "reviews", "Ops.3.1.pass.archived"), "ok")
            self.assertEqual(_run_gate(d, "3")[0], 2)

    def test_a_fail_marker_does_not_open_the_gate(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _write(os.path.join(d, "docs", "reviews", "Ops.3.1.fail"), "no")
            self.assertEqual(_run_gate(d, "3")[0], 2)

    def test_the_block_message_tells_the_producer_not_to_forge_it(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            code, err = _run_gate(d, "3")
            # The PROHIBITION, not its wording — the message is edited for length and a
            # test that pins prose either breaks on every trim or gets loosened to pass.
            self.assertIn("do not write it yourself", err.lower())

    def test_the_block_message_names_both_accepted_shapes(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _, err = _run_gate(d, "3")
            self.assertIn("3.pass", err)
            self.assertIn("<dept>", err)

    def test_non_completion_transitions_are_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            self.assertEqual(_run_gate(d, "3", status="in_progress")[0], 0)

    def test_inactive_project_is_not_gated(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d, active=False)
            self.assertEqual(_run_gate(d, "3")[0], 0)


class StaleMarker(unittest.TestCase):
    """A marker must be no older than the card's stage clock: platform ids restart every
    session, so an old `115.pass` attaches to whatever card holds task 115 now."""

    def _setup(self, d, since, marker_age_hours, key="7", task_id="7"):
        _project(d)
        _write(os.path.join(d, "docs", "board", "500-THING.md"),
               '---\nstatus: review\ndept: Ops\ntask_id: %s\nsince: "%s"\n---\n\nb\n'
               % (task_id, since))
        p = os.path.join(d, "docs", "reviews", "Ops.%s.1.pass" % key)
        _write(p, "ok")
        old = time.time() - marker_age_hours * 3600
        os.utime(p, (old, old))
        return d

    def test_a_marker_predating_the_stage_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            entered = datetime.now() - timedelta(hours=2)
            self._setup(d, entered.strftime("%Y-%m-%d %H:%M"), marker_age_hours=72)
            code, err = _run_gate(d, "7")
            self.assertEqual(code, 2)
            self.assertIn("earlier leg", err)

    def test_a_marker_written_during_this_stage_passes(self):
        with tempfile.TemporaryDirectory() as d:
            entered = datetime.now() - timedelta(hours=5)
            self._setup(d, entered.strftime("%Y-%m-%d %H:%M"), marker_age_hours=1)
            self.assertEqual(_run_gate(d, "7")[0], 0)

    def test_the_grace_absorbs_minute_precision(self):
        """`since` is minute-precision, so a marker written seconds earlier is not stale."""
        with tempfile.TemporaryDirectory() as d:
            entered = datetime.now()
            self._setup(d, entered.strftime("%Y-%m-%d %H:%M"),
                        marker_age_hours=board.STAGE_GRACE / 7200.0)
            self.assertEqual(_run_gate(d, "7")[0], 0)

    def test_a_verdict_minutes_older_than_a_hygiene_edit_still_counts(self):
        """The field case that made this tolerance necessary: the review landed at 01:08,
        the CEO recorded `blocked_on` at 01:17, and the nine-minute gap invalidated a real
        verdict. Making the board more accurate must never destroy evidence."""
        with tempfile.TemporaryDirectory() as d:
            entered = datetime.now() - timedelta(minutes=1)
            self._setup(d, entered.strftime("%Y-%m-%d %H:%M"), marker_age_hours=0.25)
            self.assertEqual(_run_gate(d, "7")[0], 0)

    def test_a_collision_from_an_earlier_session_is_still_refused(self):
        """The tolerance separates two populations: same-day hygiene versus a recycled id
        from days ago. It must not soften the test that matters."""
        with tempfile.TemporaryDirectory() as d:
            entered = datetime.now() - timedelta(hours=2)
            self._setup(d, entered.strftime("%Y-%m-%d %H:%M"), marker_age_hours=120)
            self.assertEqual(_run_gate(d, "7")[0], 2)

    def test_the_gate_does_not_re_implement_the_rule(self):
        with open(os.path.join(os.path.dirname(HERE), "hooks/pretool_review_gate.py"),
                  encoding="utf-8") as f:
            src = f.read()
        self.assertIn("board.l2_verdict", src)
        self.assertNotIn("STAGE_GRACE", src)      # the fourth copy, removed

    def test_a_durable_marker_from_an_earlier_leg_is_still_refused(self):
        """A card number is permanent; its freshness is not. A pass from a leg the CEO has
        since re-dispatched is not a verdict on the current one, so the durable path is
        date-checked too — it is only exempt when there is no clock at all."""
        with tempfile.TemporaryDirectory() as d:
            entered = datetime.now() - timedelta(hours=2)
            self._setup(d, entered.strftime("%Y-%m-%d %H:%M"),
                        marker_age_hours=72, key="500")
            self.assertEqual(_run_gate(d, "7")[0], 2)

    def test_a_durable_marker_within_tolerance_passes(self):
        with tempfile.TemporaryDirectory() as d:
            entered = datetime.now() - timedelta(minutes=30)
            self._setup(d, entered.strftime("%Y-%m-%d %H:%M"),
                        marker_age_hours=1, key="500")
            self.assertEqual(_run_gate(d, "7")[0], 0)

    def test_a_durable_id_is_trusted_when_there_is_no_clock(self):
        """Where a recycled task id would be refused, a card number still counts."""
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _write(os.path.join(d, "docs", "board", "500-THING.md"),
                   "---\nstatus: review\ndept: Ops\ntask_id: 7\n---\n\nb\n")
            p = os.path.join(d, "docs", "reviews", "Ops.500.1.pass")
            _write(p, "ok")
            old = time.time() - 400 * 3600
            os.utime(p, (old, old))
            self.assertEqual(_run_gate(d, "7")[0], 0)

    def test_no_clock_allows_rather_than_blocks(self):
        """Deliberate asymmetry with the panel: a missing chip costs nothing, a false
        refusal blocks finished work, and a card-less project has no clock at all."""
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            p = os.path.join(d, "docs", "reviews", "Ops.7.1.pass")
            _write(p, "ok")
            old = time.time() - 400 * 3600
            os.utime(p, (old, old))
            self.assertEqual(_run_gate(d, "7")[0], 0)

    def test_the_gate_and_the_panel_agree_on_the_same_data(self):
        """A gate that disagreed with the panel would show 已过审 on a card it refuses."""
        with tempfile.TemporaryDirectory() as d:
            entered = datetime.now() - timedelta(hours=2)
            self._setup(d, entered.strftime("%Y-%m-%d %H:%M"), marker_age_hours=72)
            tasks = [{"label": "#500", "task_id": "7", "since":
                      entered.strftime("%Y-%m-%d %H:%M")}]
            board._attach_l2(d, tasks)
            self.assertEqual(tasks[0]["l2"], "")          # panel: no chip
            self.assertEqual(_run_gate(d, "7")[0], 2)     # gate: refused


class NoThirdCopy(unittest.TestCase):
    def test_the_readers_share_one_parser(self):
        """One rule implemented three times is three chances to drift, and it already
        drifted: the gate, the board and the stall sentinel each had their own copy."""
        # The stall alarm went further than sharing the parser: it now shares the whole
        # reader AND the date rule, because owning either half separately is what let it
        # report 35 cards awaiting merge where the board confirmed 9.
        for rel, must in (("hooks/stop_stale_stage.py", "board._review_markers"),
                          ("hooks/stop_stale_stage.py", "board.l2_verdict"),
                          ("hooks/pretool_review_gate.py", "board._review_markers")):
            p = os.path.join(os.path.dirname(HERE), rel)
            with open(p, encoding="utf-8") as f:
                src = f.read()
            self.assertIn(must, src, rel)


if __name__ == "__main__":
    unittest.main(verbosity=1)
