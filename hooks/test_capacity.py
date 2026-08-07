"""Tests for stop_capacity.py — the mid-session capacity sentinel (lead Stop):
idle desks vs pending cards, prose-designated-unassigned detection, missing
Registrar with ASSIGNed queues, once-per-signature cap.
Run: python3 hooks/test_capacity.py"""
import os, sys, json, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stop_capacity as cap

SID = "aaaa1111-2222-3333-4444-555566667777"


def _team(cfg_root, members, lead_sid=SID):
    d = os.path.join(cfg_root, "teams", "session-%s" % lead_sid[:8])
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "config.json"), "w") as f:
        json.dump({"leadSessionId": lead_sid, "members": members}, f)


def _task(cfg_root, tid, owner, status, blocked_by=None, lead_sid=SID):
    d = os.path.join(cfg_root, "tasks", "session-%s" % lead_sid[:8])
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "%s.json" % tid), "w") as f:
        json.dump({"id": str(tid), "subject": "t%s" % tid, "owner": owner,
                   "status": status, "blockedBy": blocked_by or []}, f)


def _member(name, active=False):
    # active=False by default on purpose: isActive is a busy-flag, and idle
    # members are the sentinel's whole subject
    return {"name": name, "agentType": name, "isActive": active}


def _proj(d, taskboard=None):
    os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
    with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
        f.write('{"active":true}')
    if taskboard:
        os.makedirs(os.path.join(d, "docs"), exist_ok=True)
        with open(os.path.join(d, "docs", "TaskBoard.md"), "w", encoding="utf-8") as f:
            f.write(taskboard)


def _data(d, sid=SID):
    return {"hook_event_name": "Stop", "cwd": d, "session_id": sid,
            "transcript_path": ""}


class Capacity(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.get("CLAUDE_CONFIG_DIR")
        self.cfg = tempfile.mkdtemp()
        os.environ["CLAUDE_CONFIG_DIR"] = self.cfg

    def tearDown(self):
        if self._env is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = self._env

    def test_idle_desk_with_pending_cards_nudges_once(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Backend-IO"), _member("Backend-Engine")])
            _task(self.cfg, 30, None, "pending")
            ret = cap.run(_data(d), None)
            self.assertIn("idle desk", ret or "")
            self.assertIn("Backend-IO", ret)
            self.assertIsNone(cap.run(_data(d), None))          # same state → capped
            _task(self.cfg, 31, None, "pending")
            self.assertIsNone(cap.run(_data(d), None))          # ANOTHER pending card is
            #   the same complaint about the same idle desks, not a new one. Hashing the
            #   whole pending list made every unrelated birth or completion anywhere on
            #   the board replay the identical alarm.
            _team(self.cfg, [_member("Backend-IO"), _member("Backend-Engine"),
                             _member("Frontend")])              # a NEW idle desk re-arms
            self.assertTrue(cap.run(_data(d), None))

    def test_busy_desks_are_silent(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Backend-IO")])
            _task(self.cfg, 30, "Backend-IO", "in_progress")
            self.assertIsNone(cap.run(_data(d), None))

    def test_suffixed_member_with_exact_owner_is_busy(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Backend-IO-2")])
            _task(self.cfg, 30, "Backend-IO-2", "in_progress")
            self.assertIsNone(cap.run(_data(d), None))

    def test_idle_second_lane_flagged_while_base_busy(self):
        # lanes are deliberate — each earns its OWN idle judgement;
        # a busy Frontend must not hide an idle Frontend-2
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Frontend"), _member("Frontend-2")])
            _task(self.cfg, 30, "Frontend", "in_progress")
            ret = cap.run(_data(d), None)
            self.assertIn("Frontend-2", ret or "")
            self.assertNotIn("idle desk(s) Frontend,", ret or "")

    def test_idle_desk_nothing_pending_prescribes_release(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Backend-Engine")])
            _task(self.cfg, 30, "Backend-Engine", "completed")
            ret = cap.run(_data(d), None)
            self.assertIn("release", ret or "")

    def test_blocked_pending_does_not_count_as_ready(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("QA")])
            _task(self.cfg, 30, None, "in_progress")
            _task(self.cfg, 31, None, "pending", blocked_by=[30])
            ret = cap.run(_data(d), None)
            self.assertIn("nothing pending", ret or "")          # release path, not assign

    def test_prose_designated_unassigned_flagged(self):
        board = ("# b\n\n## Active\n\n### #115 · PERF\n- **dept:** Frontend (lead)\n"
                 "- **task_id:** 33\n- **status:** todo\n")
        with tempfile.TemporaryDirectory() as d:
            _proj(d, taskboard=board)
            _team(self.cfg, [_member("Frontend")])
            _task(self.cfg, 33, None, "pending")
            ret = cap.run(_data(d), None)
            self.assertIn("#115 (widget 33)", ret or "")   # the number THE BOSS'S board speaks
            self.assertIn("ASSIGN", ret)

    def test_branch_office_session_is_never_the_ceo_team(self):
        """A 分公司 runs its OWN session in a worktree, and root is pierced to the main
        checkout — so without this gate it judged the CEO's board and was handed the
        CEO's team. An external dept's pane got the CEO's assign-these-cards order verbatim
        (2026-07-26)."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Frontend")])
            _task(self.cfg, 30, None, "pending")
            self.assertTrue(cap.run(_data(d), None))         # the CEO gets the nudge
            wt = os.path.join(d, ".claude", "worktrees", "Marketing")
            os.makedirs(os.path.join(wt, ".claude"), exist_ok=True)
            with open(os.path.join(wt, ".claude", "office.json"), "w") as f:
                json.dump({"office": "Marketing"}, f)
            self.assertIsNone(cap.run(_data(wt), None))      # the branch never does

    def test_seat_that_closed_three_cards_is_flagged_for_retirement(self):
        """One card per seat. Queue-pull and re-tasking
        route around the spawn-time rule, so the closed-card count is what actually
        catches accumulation however it happened. The point is QUALITY, not tokens: a
        seat carrying several cards' abandoned approaches re-proposes them."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Frontend")])
            for i, tid in enumerate((10, 11, 12)):
                _task(self.cfg, tid, "Frontend", "completed")
            ret = cap.run(_data(d), None) or ""
            self.assertIn("closed 3 cards", ret)
            self.assertIn("<Dept>-<NNN>", ret)

    def test_two_closed_cards_is_not_yet_accumulation(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Frontend")])
            _task(self.cfg, 10, "Frontend", "completed")
            _task(self.cfg, 11, "Frontend", "completed")
            self.assertNotIn("closed", cap.run(_data(d), None) or "")

    def test_a_busy_fat_seat_is_flagged_as_last_card_not_retired_mid_task(self):
        """This test used to assert the buggy half: 'flagged only BETWEEN cards' read as
        politeness but was a mute button — a queue-fed seat never HAS a between-cards
        moment, so the one pattern the counter existed for was the one it never spoke
        about (a seat with 4 closed + 2 in progress, silent).
        The spirit survives: a working seat is never told to retire NOW — it is told
        the card in hand is its LAST and the queue must stop feeding it."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Frontend")])
            for tid in (10, 11, 12):
                _task(self.cfg, tid, "Frontend", "completed")
            _task(self.cfg, 13, "Frontend", "in_progress")
            ret = cap.run(_data(d), None) or ""
            self.assertIn("STILL hold work", ret)
            self.assertIn("LAST", ret)
            self.assertNotIn("hold none", ret)                   # not the retire-now text

    def test_a_fat_idle_seat_is_never_also_offered_new_work(self):
        """Before the split, a fat seat that went idle beside pending cards drew BOTH
        messages — 'ASSIGN to the idle desk' and 'retire it' — a contradiction the CEO
        resolved by feeding it, which is the accumulation loop again."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Frontend")])
            for tid in (10, 11, 12):
                _task(self.cfg, tid, "Frontend", "completed")
            _task(self.cfg, 20, None, "pending")
            ret = cap.run(_data(d), None) or ""
            self.assertIn("hold none", ret)                      # retire message fires
            self.assertNotIn("idle desk", ret)                   # assign message must not

    def test_fat_seat_going_idle_rearms_the_nudge(self):
        """busy-fat and idle-fat are different complaints (stop feeding it vs retire it
        now) — the state moving between them must speak again, not hide in one sig."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Frontend")])
            for tid in (10, 11, 12):
                _task(self.cfg, tid, "Frontend", "completed")
            _task(self.cfg, 13, "Frontend", "in_progress")
            self.assertIn("STILL hold work", cap.run(_data(d), None) or "")
            self.assertIsNone(cap.run(_data(d), None))           # same state → capped
            _task(self.cfg, 13, "Frontend", "completed")         # the held card lands
            ret = cap.run(_data(d), None) or ""
            self.assertIn("hold none", ret)

    def test_seat_cards_max_is_configurable(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
                f.write('{"active":true,"seat_cards_max":2}')
            _team(self.cfg, [_member("Frontend")])
            _task(self.cfg, 10, "Frontend", "completed")
            _task(self.cfg, 11, "Frontend", "completed")
            self.assertIn("closed 2 cards", cap.run(_data(d), None) or "")

    def test_recorded_hold_is_not_a_stall(self):
        """A card carrying `blocked_on` has already been answered by the CEO in
        writing. Re-raising it inverts the discipline the sentinel exists to enforce,
        and no reply can clear it because nothing is wrong — it fired twice on five
        such cards on a live board (2026-07-26) with no way to ever satisfy it."""
        board = ("# b\n\n## Active\n\n### #198 · CONVERT\n- **dept:** Frontend\n"
                 "- **task_id:** 12\n- **status:** todo\n"
                 "- **blocked_on:** CEO dispatch sequencing\n")
        with tempfile.TemporaryDirectory() as d:
            _proj(d, taskboard=board)
            _team(self.cfg, [_member("Frontend")])
            _task(self.cfg, 12, None, "pending")
            ret = cap.run(_data(d), None) or ""
            self.assertNotIn("prose is invisible", ret)

    def test_placeholder_blocked_on_still_counts_as_free(self):
        board = ("# b\n\n## Active\n\n### #199 · X\n- **dept:** Frontend\n"
                 "- **task_id:** 13\n- **status:** todo\n- **blocked_on:** —\n")
        with tempfile.TemporaryDirectory() as d:
            _proj(d, taskboard=board)
            _team(self.cfg, [_member("Frontend")])
            _task(self.cfg, 13, None, "pending")
            self.assertIn("prose is invisible", cap.run(_data(d), None) or "")

    def test_multi_dept_card_is_a_split_not_an_assign(self):
        """ASSIGN takes exactly one owner, so "Engine (types) + IO (render)" is a card
        still to be split. Telling their to ASSIGN it is an instruction nobody can obey."""
        board = ("# b\n\n## Active\n\n### #268 · FIELD-MODEL\n"
                 "- **dept:** Backend-Engine (types) + Backend-IO (parse) — CEO specs it\n"
                 "- **task_id:** 36\n- **status:** todo\n")
        with tempfile.TemporaryDirectory() as d:
            _proj(d, taskboard=board)
            _team(self.cfg, [_member("Backend-Engine"), _member("Backend-IO")])
            _task(self.cfg, 36, None, "pending")
            ret = cap.run(_data(d), None) or ""
            self.assertNotIn("prose is invisible", ret)

    def test_second_lane_of_one_dept_is_still_one_owner(self):
        """Frontend and Frontend-2 are two live handles of ONE base dept — a card whose
        prose names 'Frontend' is still a single assignment target."""
        board = ("# b\n\n## Active\n\n### #115 · PERF\n- **dept:** Frontend (lead)\n"
                 "- **task_id:** 33\n- **status:** todo\n")
        with tempfile.TemporaryDirectory() as d:
            _proj(d, taskboard=board)
            _team(self.cfg, [_member("Frontend"), _member("Frontend-2")])
            _task(self.cfg, 33, None, "pending")
            self.assertIn("prose is invisible", cap.run(_data(d), None) or "")

    def test_queue_deeper_than_the_seat_can_close_is_flagged(self):
        """Field case 2026-08-07: five cards ASSIGNed onto one seat with the closed
        counter at zero — silent, because (e) watches the past and nothing watched the
        queue. The seat retires at seat_cards_max closed, and its successor cannot CLAIM
        the dead handle's cards, so the tail is a re-ASSIGN debt being written now."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Backend-IO-998"), _member("Registrar")])
            _task(self.cfg, 3, "Backend-IO-998", "in_progress")
            for tid in (4, 5, 6, 7):
                _task(self.cfg, tid, "Backend-IO-998", "pending")
            ret = cap.run(_data(d), None)
            self.assertIn("queue too deep", ret or "")
            self.assertIn("Backend-IO-998 holds 5 open / can close 3 more", ret)

    def test_queue_within_the_seats_room_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Backend-IO-998"), _member("Registrar")])
            _task(self.cfg, 3, "Backend-IO-998", "in_progress")
            for tid in (4, 5):
                _task(self.cfg, tid, "Backend-IO-998", "pending")
            self.assertIsNone(cap.run(_data(d), None))

    def test_a_fat_seat_with_a_queue_is_one_alarm_not_two(self):
        """(e) already gives a fat seat its order; (g) repeating it teaches the reader
        to skim both alarms."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("QA-5"), _member("Registrar")])
            for tid in (30, 31, 32):
                _task(self.cfg, tid, "QA-5", "completed")
            _task(self.cfg, 33, "QA-5", "in_progress")
            _task(self.cfg, 34, "QA-5", "pending")
            ret = cap.run(_data(d), None)
            self.assertIn("LAST", ret or "")
            self.assertNotIn("queue too deep", ret or "")

    def test_assigned_queue_without_registrar_flags_respawn(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Ops")])
            _task(self.cfg, 30, "Ops", "pending")
            _task(self.cfg, 31, "Ops", "in_progress")           # Ops busy, not idle
            ret = cap.run(_data(d), None)
            self.assertIn("Registrar", ret or "")

    def test_live_registrar_silences_the_respawn_flag(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Ops"), _member("Registrar")])
            _task(self.cfg, 30, "Ops", "pending")
            _task(self.cfg, 31, "Ops", "in_progress")
            self.assertIsNone(cap.run(_data(d), None))

    def test_boss_in_pane_dept_never_idle(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            with open(os.path.join(d, ".claude", "boss-in-pane.json"), "w") as f:
                json.dump({"Frontend": True}, f)
            _team(self.cfg, [_member("Frontend")])
            _task(self.cfg, 30, None, "pending")
            ret = cap.run(_data(d), None)
            # Frontend muted; the pending card alone raises no idle flag
            self.assertIsNone(ret)

    def test_teammate_session_and_unarmed_project_silent(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("QA")], lead_sid=SID)
            _task(self.cfg, 30, None, "pending")
            other = SID.replace("aaaa", "bbbb")
            self.assertIsNone(cap.run(_data(d, sid=other), None))   # not the lead
        with tempfile.TemporaryDirectory() as d:                     # no marker at all
            self.assertIsNone(cap.run(_data(d), None))

    def test_widget_gated_no_task_store_silent(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("QA")])
            self.assertIsNone(cap.run(_data(d), None))

    def test_registrar_alone_never_idle_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Registrar")])
            _task(self.cfg, 30, None, "pending")
            self.assertIsNone(cap.run(_data(d), None))


if __name__ == "__main__":
    unittest.main(verbosity=1)


class StrandedWork(unittest.TestCase):
    """The sweep asked which desks had no card. It never asked which cards had no desk.

    A seat that dies or is released while holding an in_progress card leaves that card
    saying someone is on it, forever: it is not pending, so the idle-desk rule never
    offers it to anyone, and its owner is not in members[], so no idle judgement is made
    about it either. Field case 2026-08-04: a pane closed at 16:01 and its card sat
    in_progress behind the dead seat for three hours while the sentinel reported a
    healthy team, because every live desk happened to be busy."""

    def setUp(self):
        self._env = os.environ.get("CLAUDE_CONFIG_DIR")
        self.cfg = tempfile.mkdtemp()
        os.environ["CLAUDE_CONFIG_DIR"] = self.cfg

    def tearDown(self):
        if self._env is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = self._env

    def test_a_card_held_by_a_seat_that_left_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Frontend-1040")])
            _task(self.cfg, 87, "Frontend-1040", "in_progress")   # live seat, fine
            _task(self.cfg, 89, "Ops-1042", "in_progress")        # its pane is gone
            ret = cap.run(_data(d), None) or ""
            self.assertIn("no longer on the team", ret)
            self.assertIn("Ops-1042", ret)
            self.assertNotIn("Frontend-1040", ret)

    def test_it_speaks_even_when_every_live_desk_is_busy(self):
        """The exact shape that hid it: nothing is idle, so the old sweep saw health."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Frontend-1040"), _member("Backend-Engine-1043")])
            _task(self.cfg, 87, "Frontend-1040", "in_progress")
            _task(self.cfg, 90, "Backend-Engine-1043", "in_progress")
            _task(self.cfg, 89, "Ops-1042", "in_progress")
            ret = cap.run(_data(d), None) or ""
            self.assertIn("Ops-1042", ret)
            self.assertNotIn("idle desk", ret)

    def test_it_names_the_durable_card_number_when_the_board_has_one(self):
        """A nudge naming only the widget id names nothing they can look up."""
        tb = ("# b\n\n## Active\n\n### #1042 · /api/verify boundary\n"
              "- **dept:** Ops\n- **task_id:** 89\n- **status:** doing\n")
        with tempfile.TemporaryDirectory() as d:
            _proj(d, taskboard=tb)
            _team(self.cfg, [_member("Frontend-1040")])
            _task(self.cfg, 87, "Frontend-1040", "in_progress")   # keep a desk busy
            _task(self.cfg, 89, "Ops-1042", "in_progress")
            self.assertIn("#1042 (Ops-1042)", cap.run(_data(d), None) or "")

    def test_a_completed_or_pending_card_is_not_stranded(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Frontend-1040")])
            _task(self.cfg, 87, "Frontend-1040", "in_progress")
            _task(self.cfg, 88, "Ops-1042", "completed")
            _task(self.cfg, 89, "Ops-1042", "pending")   # unowned queue work, not stranded
            ret = cap.run(_data(d), None) or ""
            self.assertNotIn("no longer on the team", ret)

    def test_a_branch_office_handle_is_not_stranded(self):
        """A 分公司 runs its own session and never appears in members[]; its cards are
        not abandoned, they are simply not on this team's lifecycle."""
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
            with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
                f.write('{"active":true,"external":["Marketing"]}')
            _team(self.cfg, [_member("Frontend-1040")])
            _task(self.cfg, 87, "Frontend-1040", "in_progress")
            _task(self.cfg, 91, "Marketing-7", "in_progress")
            ret = cap.run(_data(d), None) or ""
            self.assertNotIn("no longer on the team", ret)

    def test_one_nudge_per_state_and_a_new_stranding_re_arms(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Frontend-1040")])
            _task(self.cfg, 87, "Frontend-1040", "in_progress")
            _task(self.cfg, 89, "Ops-1042", "in_progress")
            self.assertTrue(cap.run(_data(d), None))
            self.assertIsNone(cap.run(_data(d), None), "same complaint must stay silent")
            _task(self.cfg, 92, "Prof_Academic-1038", "in_progress")   # another seat gone
            self.assertTrue(cap.run(_data(d), None), "a new stranding is a new complaint")

    def test_re_assigning_it_to_a_live_desk_clears_it(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Frontend-1040")])
            _task(self.cfg, 87, "Frontend-1040", "in_progress")
            _task(self.cfg, 89, "Ops-1042", "in_progress")
            self.assertTrue(cap.run(_data(d), None))
            _task(self.cfg, 89, "Frontend-1040", "in_progress")   # handed to a live seat
            self.assertIsNone(cap.run(_data(d), None))
