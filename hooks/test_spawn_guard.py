"""Tests for pretool_spawn_guard.py (spawn-collision guard) and the lingering-pane
sentinel in session_start.py. Both read the team config / task store under
CLAUDE_CONFIG_DIR, so tests point that env at a temp dir.
Run: python3 hooks/test_spawn_guard.py"""
import os, sys, json, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pretool_spawn_guard as guard
import session_start as ss

SID = "aaaa1111-2222-3333-4444-555566667777"


def _team(cfg_root, members, lead_sid=SID):
    d = os.path.join(cfg_root, "teams", "session-%s" % lead_sid[:8])
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "config.json"), "w") as f:
        json.dump({"name": "session-%s" % lead_sid[:8], "leadSessionId": lead_sid,
                   "members": members}, f)


def _task(cfg_root, tid, owner, status, lead_sid=SID):
    d = os.path.join(cfg_root, "tasks", "session-%s" % lead_sid[:8])
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "%s.json" % tid), "w") as f:
        json.dump({"id": str(tid), "subject": "t", "owner": owner, "status": status}, f)


def _member(name, active=True, agent_type=None):
    return {"name": name, "agentType": agent_type or name.rstrip("-2"),
            "isActive": active}


def _proj(d):
    os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
    with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
        f.write('{"active":true}')


class SpawnGuard(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.get("CLAUDE_CONFIG_DIR")
        self.cfg = tempfile.mkdtemp()
        os.environ["CLAUDE_CONFIG_DIR"] = self.cfg

    def tearDown(self):
        if self._env is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = self._env

    def test_live_same_base_collides(self):
        _team(self.cfg, [_member("RnD", active=True)])
        cfg = guard.team_config(SID)
        self.assertEqual(guard.live_collision(cfg, "RnD"), "RnD")

    def test_explicit_suffix_is_a_deliberate_lane(self):
        # Boss's rule 2026-07-19: a second instance of the same dept, explicitly
        # suffixed, on file-disjoint cards = elastic capacity — passes
        _team(self.cfg, [_member("RnD", active=True)])
        cfg = guard.team_config(SID)
        self.assertIsNone(guard.live_collision(cfg, "RnD-2"))
        # but an EXACT name collision always blocks (harness would mint -3)
        _team(self.cfg, [_member("RnD", active=True),
                         _member("RnD-2", active=False, agent_type="RnD")])
        cfg = guard.team_config(SID)
        self.assertEqual(guard.live_collision(cfg, "RnD-2"), "RnD-2")
        self.assertIsNone(guard.live_collision(cfg, "RnD-3"))         # next lane fine

    def test_suffixed_live_member_blocks_base_request(self):
        _team(self.cfg, [_member("RnD-2", active=True, agent_type="RnD")])
        cfg = guard.team_config(SID)
        self.assertEqual(guard.live_collision(cfg, "RnD"), "RnD-2")

    def test_idle_member_still_collides(self):
        # isActive is a BUSY-flag, not liveness (field-proven 2026-07-19: responsive
        # Registrar at isActive:false) — an idle live member must still block, else
        # every between-turns respawn mints a -2 suffix
        _team(self.cfg, [_member("RnD", active=False)])
        cfg = guard.team_config(SID)
        self.assertEqual(guard.live_collision(cfg, "RnD"), "RnD")

    def test_other_dept_no_collision(self):
        _team(self.cfg, [_member("QA", active=True)])
        cfg = guard.team_config(SID)
        self.assertIsNone(guard.live_collision(cfg, "RnD"))

    def test_wrong_lead_sid_or_missing_config_is_none(self):
        self.assertIsNone(guard.team_config(SID))                    # no config at all
        _team(self.cfg, [_member("RnD")], lead_sid=SID)
        other = SID.replace("aaaa", "bbbb")
        self.assertIsNone(guard.team_config(other))                  # not this lead
        # dir matches by 8-hex but leadSessionId differs → not the lead → None
        _team(self.cfg, [_member("RnD")], lead_sid=SID)
        cfgpath = os.path.join(self.cfg, "teams", "session-%s" % SID[:8], "config.json")
        c = json.load(open(cfgpath)); c["leadSessionId"] = other
        json.dump(c, open(cfgpath, "w"))
        self.assertIsNone(guard.team_config(SID))


class TierGuard(unittest.TestCase):
    """0.9.18 brain-regime tier guard: a Fable-CEO session blocks NAMED teammate
    spawns that carry no model: param; any explicit tier passes; parity sessions
    and one-shots are untouched. Session model comes from the transcript tail."""

    def setUp(self):
        self._env = os.environ.get("CLAUDE_CONFIG_DIR")
        self.cfg = tempfile.mkdtemp()
        os.environ["CLAUDE_CONFIG_DIR"] = self.cfg

    def tearDown(self):
        if self._env is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = self._env

    def _transcript(self, d, model):
        p = os.path.join(d, "t.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n")
            f.write(json.dumps({"type": "assistant",
                                "message": {"model": model, "content": []}}) + "\n")
        return p

    def _run(self, d, model, tool_input):
        import subprocess
        hook = os.path.join(HERE, "pretool_spawn_guard.py")
        payload = {"cwd": d, "session_id": SID, "tool_name": "Agent",
                   "transcript_path": self._transcript(d, model),
                   "tool_input": tool_input}
        env = dict(os.environ)
        r = subprocess.run([sys.executable, hook], input=json.dumps(payload),
                           text=True, capture_output=True, env=env, timeout=20)
        return r.returncode, r.stderr

    def test_fable_named_spawn_without_model_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [])
            code, err = self._run(d, "claude-fable-5",
                                  {"name": "RnD", "subagent_type": "RnD"})
            self.assertEqual(code, 2)
            self.assertIn("EXPLICIT tier", err)
            self.assertIn("designated", err)   # Boss-designated tiers named as first-class

    def test_fires_before_the_team_config_exists(self):
        # the 0.9.26 ordering fix: the team config is born by the FIRST teammate
        # spawn, so the 上岗 batch escaped a guard that sat behind it (field ×3)
        with tempfile.TemporaryDirectory() as d:
            _proj(d)  # NOTE: no _team() — no config on disk at all
            code, err = self._run(d, "claude-fable-5",
                                  {"name": "RnD", "subagent_type": "RnD"})
            self.assertEqual(code, 2)
            self.assertIn("tier guard", err)

    def test_named_reviewer_spawn_blocked(self):
        # field case 2026-07-19: L1-151 / L2-145-146-final sat on the members
        # roster — the CEO had been naming its Auditor invocations into teammates
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            for st in ("clock-in:Auditor", "Auditor", "clock-in:Inspector"):
                code, err = self._run(d, "claude-opus-4-8",
                                      {"name": "L2-151-final", "subagent_type": st})
                self.assertEqual(code, 2, st)
                self.assertIn("ONE-SHOT", err)
            # unnamed reviewer passes untouched (the actual contract)
            code, _ = self._run(d, "claude-fable-5", {"subagent_type": "clock-in:Auditor"})
            self.assertEqual(code, 0)

    def test_plugin_agent_pin_covers_registrar_respawn(self):
        # field false-positive 2026-07-19: the Registrar is plugin-scope (its
        # haiku pin lives in the PLUGIN's agents/ dir, not the project's) — a
        # param-less respawn must pass on that pin
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            code, err = self._run(d, "claude-fable-5",
                                  {"name": "Registrar",
                                   "subagent_type": "clock-in:Registrar"})
            self.assertEqual(code, 0, err)

    def test_brief_model_pin_makes_omission_benign(self):
        # template default `model: sonnet` (0.9.26): the frontmatter tier applies,
        # so a param-less spawn is exactly the Boss's default — no block
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            os.makedirs(os.path.join(d, ".claude", "agents"), exist_ok=True)
            with open(os.path.join(d, ".claude", "agents", "RnD.md"), "w") as f:
                f.write("---\nname: RnD\ndescription: x\nmodel: sonnet\n---\nbody\n")
            code, _ = self._run(d, "claude-fable-5",
                                {"name": "RnD", "subagent_type": "RnD"})
            self.assertEqual(code, 0)
            code, _ = self._run(d, "claude-fable-5",     # suffixed lane reads base brief
                                {"name": "RnD-2", "subagent_type": "RnD"})
            self.assertEqual(code, 0)

    def test_fable_spawn_with_any_explicit_tier_passes(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [])
            for tier in ("sonnet", "fable", "opus", "haiku"):
                code, _ = self._run(d, "claude-fable-5",
                                    {"name": "Mkt", "subagent_type": "Mkt", "model": tier})
                self.assertEqual(code, 0, tier)

    def test_parity_session_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [])
            code, _ = self._run(d, "claude-opus-4-8",
                                {"name": "RnD", "subagent_type": "RnD"})
            self.assertEqual(code, 0)

    def test_one_shot_untouched_even_on_fable(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [])
            code, _ = self._run(d, "claude-fable-5", {"subagent_type": "clock-in:Auditor"})
            self.assertEqual(code, 0)

    def test_session_model_reads_last_stamp(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps({"message": {"model": "claude-opus-4-8"}}) + "\n")
                f.write(json.dumps({"message": {"model": "claude-fable-5"}}) + "\n")
            self.assertEqual(guard.session_model(p), "claude-fable-5")
            self.assertEqual(guard.session_model(os.path.join(d, "missing.jsonl")), "")


class PaneSentinel(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.get("CLAUDE_CONFIG_DIR")
        self.cfg = tempfile.mkdtemp()
        os.environ["CLAUDE_CONFIG_DIR"] = self.cfg

    def tearDown(self):
        if self._env is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = self._env

    def _flags(self, d):
        return ss.pane_flags(d, {"session_id": SID})

    def test_orphan_pane_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("QA", active=True)])
            _task(self.cfg, 1, "RnD", "in_progress")                 # QA owns nothing
            flags = self._flags(d)
            self.assertEqual(len(flags), 1)
            self.assertIn("QA", flags[0])

    def test_owner_of_open_task_is_clean(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("QA", active=True)])
            _task(self.cfg, 1, "QA", "in_progress")
            self.assertEqual(self._flags(d), [])

    def test_suffixed_owner_matches_base_member(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("QA-2", active=True, agent_type="QA")])
            _task(self.cfg, 1, "QA", "in_progress")
            self.assertEqual(self._flags(d), [])

    def test_registrar_and_lead_exempt_idle_dept_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [{"name": "team-lead", "isActive": True},
                             _member("Registrar-2", active=True, agent_type="Registrar"),
                             _member("RnD", active=False)])
            _task(self.cfg, 1, "Nobody", "completed")
            flags = self._flags(d)
            # isActive:false = idle, NOT gone — the idle taskless dept is exactly
            # the lingering pane this sentinel exists to catch (2026-07-19 fix:
            # the old isActive check skipped it, so the sentinel never fired)
            self.assertEqual(len(flags), 1)
            self.assertIn("RnD", flags[0])
            self.assertNotIn("Registrar", flags[0])

    def test_boss_in_pane_exempt(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("QA", active=True)])
            os.makedirs(os.path.join(self.cfg, "tasks", "session-%s" % SID[:8]),
                        exist_ok=True)
            with open(os.path.join(d, ".claude", "boss-in-pane.json"), "w") as f:
                json.dump({"QA": "2026-07-15T00:00:00Z"}, f)
            self.assertEqual(self._flags(d), [])

    def test_no_task_store_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("QA", active=True)])            # no tasks dir
            self.assertEqual(self._flags(d), [])


class ExternalLane(unittest.TestCase):
    """0.9.29 分公司: an external dept runs as its own branch session — an in-team
    spawn under its name (bare or suffixed) double-dispatches the lane; block it
    regardless of model params, before any team config exists."""

    def _run(self, d, tool_input):
        import subprocess
        hook = os.path.join(HERE, "pretool_spawn_guard.py")
        payload = {"cwd": d, "session_id": SID, "tool_name": "Agent",
                   "tool_input": tool_input}
        r = subprocess.run([sys.executable, hook], input=json.dumps(payload),
                           text=True, capture_output=True, timeout=20)
        return r.returncode, r.stderr

    def _proj_ext(self, d):
        os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
        with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
            f.write('{"active":true,"roster":["RnD","Marketing"],"external":["Marketing"]}')

    def test_external_dept_spawn_blocked_even_with_model(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj_ext(d)
            for name in ("Marketing", "Marketing-2"):
                code, err = self._run(d, {"name": name, "subagent_type": "Marketing",
                                          "model": "sonnet"})
                self.assertEqual(code, 2, name)
                self.assertIn("分公司", err)

    def test_internal_dept_and_one_shot_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj_ext(d)
            code, _ = self._run(d, {"name": "RnD", "subagent_type": "RnD",
                                    "model": "sonnet"})
            self.assertEqual(code, 0)
            code, _ = self._run(d, {"subagent_type": "Marketing"})  # one-shot: no name
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
