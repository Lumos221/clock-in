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
            _task(self.cfg, 31, None, "pending")                # state moved → re-arms
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
        # lanes are deliberate (Boss's rule) — each earns its OWN idle judgement;
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
            self.assertIn("#33", ret or "")
            self.assertIn("ASSIGN", ret)

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
