"""Tests for the unmarked-trailing-ask nudge in stop_boss_board.py.
Run: python3 hooks/test_boss_board_ask.py"""
import os, sys, json, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "skills", "orchestrate", "scripts"))
import stop_boss_board as sb
import stop_boss_board as sbb
import hooklib
import board


def _m(raises=(), infos=()):
    return {"raises": list(raises), "infos": list(infos), "dones": [], "misses": []}


class TrailingAskText(unittest.TestCase):
    def test_final_question_line_is_the_ask(self):
        self.assertEqual(sb._trailing_ask_text("did work\nShip it on Friday?"),
                         "Ship it on Friday?")

    def test_full_width_question_mark_counts(self):
        self.assertEqual(sb._trailing_ask_text("干活\n周五发布吗？"), "周五发布吗？")

    def test_needs_you_trailer_counts_even_ending_in_a_full_stop(self):
        """The reply-shape habit: an ask that never wears a question mark."""
        self.assertIn("Needs you", sb._trailing_ask_text("report\n---Needs you: pick a font."))

    def test_a_nil_trailer_is_not_an_ask(self):
        self.assertEqual(sb._trailing_ask_text("report\nNeeds you: nothing."), "")

    def test_prose_with_no_trailer_is_not_an_ask(self):
        self.assertEqual(sb._trailing_ask_text("merged and shipped."), "")


class Covered(unittest.TestCase):
    """The gate is 'is THIS question the thing you registered', not 'did you register
    anything' — the difference is the whole bug."""

    def test_a_marker_restating_the_question_covers_it(self):
        q = "Should the annual toggle default on or off?"
        self.assertTrue(sb._covered(q, _m(raises=[("CEO", "12",
                                                   "Annual toggle: default on or default off")])))

    def test_an_unrelated_marker_does_not_cover_it(self):
        """The field case: a turn raised its L2 escalations and left a panel-render
        question in prose, so the board looked complete and the question died."""
        q = ("Should clicking a style also switch the page itself to that style, "
             "or only produce the file?")
        self.assertFalse(sb._covered(q, _m(raises=[
            ("Prof_Academic", "407", "task 407 已连续 3 次 L2 封驳 — Boss decision"),
            ("Legal", "96", "task 96 已连续 3 次 L2 封驳 — Boss decision")])))

    def test_an_info_marker_can_cover_it_too(self):
        q = "Is the deploy green?"
        self.assertTrue(sb._covered(q, _m(infos=[("CEO", "", "deploy green on prod")])))

    def test_chinese_overlap_is_measured_not_missed(self):
        """Word-splitting alone scores every Chinese ask as sharing nothing."""
        q = "速查卡的版式要不要改成两面制？"
        self.assertTrue(sb._covered(q, _m(raises=[("Marketing", "", "速查卡版式改两面制,请定")])))
        self.assertFalse(sb._covered(q, _m(raises=[("Legal", "96", "红线条款需要你裁定")])))

    def test_a_bare_closer_never_second_guesses_a_turn_that_registered(self):
        """One word is too little to judge against a marker; a turn that registered
        something has earned the benefit of the doubt."""
        self.assertTrue(sb._covered("anything?", _m(raises=[("CEO", "1", "something else")])))

    def test_a_turn_that_registered_nothing_keeps_the_original_nudge(self):
        """No marker at all is the case the nudge has always caught, short question or not."""
        self.assertFalse(sb._covered("Ready?", _m()))

    def test_no_markers_at_all_leaves_a_real_question_uncovered(self):
        self.assertFalse(sb._covered("Should we drop the Vancouver style for now?", _m()))


class Regression(unittest.TestCase):
    def test_the_old_blanket_immunity_is_gone(self):
        """Before: any raise returned early and the trailing ask was never examined."""
        with open(sb.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn('if markers["raises"] or markers.get("infos"):\n        return', src)

    def test_the_nudge_teaches_point_do_not_repeat(self):
        """The hook is the ONLY channel into a session that already loaded its doctrine,
        so the new rule has to travel in the nudge text itself."""
        with open(sb.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("point, do not", src.lower().replace("**", ""))




class BranchOffice(unittest.TestCase):
    """The nudge is a CEO-team piece and must not fire inside a 分公司.

    A branch runs as its own session against a handful of desks, with the Boss working
    inside it directly — so the register the nudge defends is the conversation they are
    already reading. Firing there interrupted a turn to demand a board marker for a
    question they had just been asked to them face."""

    def _office(self, d, name="Marketing", extra=None):
        wt = os.path.join(d, ".claude", "worktrees", name)
        os.makedirs(os.path.join(wt, ".claude"), exist_ok=True)
        os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
        open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active": true}')
        cfg = {"office": name}
        cfg.update(extra or {})
        with open(os.path.join(wt, ".claude", "office.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return wt

    def test_a_branch_office_is_opted_out_by_default(self):
        with tempfile.TemporaryDirectory() as d:
            wt = self._office(d)
            self.assertFalse(sbb._office_wants_nudge(wt))

    def test_a_branch_can_opt_back_in(self):
        with tempfile.TemporaryDirectory() as d:
            wt = self._office(d, extra={"board_nudge": True})
            self.assertTrue(sbb._office_wants_nudge(wt))

    def test_the_ceo_checkout_is_never_treated_as_an_office(self):
        """The main checkout carries no office file, so the CEO keeps the nudge."""
        with tempfile.TemporaryDirectory() as d:
            self._office(d)
            self.assertFalse(sbb._office_wants_nudge(d))
            self.assertEqual(hooklib.local_office(d), "")

    def test_the_opt_out_reads_from_a_subdirectory_of_the_branch(self):
        with tempfile.TemporaryDirectory() as d:
            wt = self._office(d)
            sub = os.path.join(wt, "docs", "营销")
            os.makedirs(sub)
            self.assertEqual(hooklib.local_office(sub), "Marketing")
            self.assertFalse(sbb._office_wants_nudge(sub))


class MarkerTaskIds(unittest.TestCase):
    """A CJK task name broke the marker outright.

    The task segment was ASCII-only, so a task named in Chinese matched nothing,
    landed in marker-misses.log and nowhere else. The ask the model had just been NUDGED
    into registering therefore still never reached the board — worse than the silence
    the nudge exists to prevent."""

    def test_a_cjk_task_name_registers(self):
        r = board.parse_markers("@BOSS[Marketing#任务名]: 等你下一句 :: 详情")
        self.assertEqual(r["misses"], [])
        self.assertEqual(r["raises"], [("Marketing", "任务名", "等你下一句 :: 详情")])

    def test_an_ascii_task_id_still_works(self):
        self.assertEqual(board.parse_markers("@BOSS[Ops#104]: x")["raises"],
                         [("Ops", "104", "x")])

    def test_a_taskless_marker_still_works(self):
        self.assertEqual(board.parse_markers("@BOSS[Ops]: x")["raises"],
                         [("Ops", None, "x")])

    def test_info_markers_take_a_cjk_task_too(self):
        self.assertEqual(board.parse_markers("@BOSS-INFO[Marketing#评测]: 事实")["infos"],
                         [("Marketing", "评测", "事实")])

    def test_a_malformed_marker_is_still_recorded_as_a_miss(self):
        """Widening the class must not swallow genuinely broken markers."""
        self.assertEqual(board.parse_markers("@BOSS Marketing: no brackets")["misses"],
                         ["@BOSS Marketing: no brackets"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
