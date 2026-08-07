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
        # A second instance of the same dept, explicitly
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
        # isActive is a BUSY-flag, not liveness (responsive
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


class SpawnShape(unittest.TestCase):
    """The shape rules: who may be named (a reviewer or an expert may not — naming
    converts a one-shot into a pane-squatting teammate that loses its brief's
    `effort:`), what a spawn must declare, and the L2 pre-flight on an 审查官 call."""

    def setUp(self):
        self._env = os.environ.get("CLAUDE_CONFIG_DIR")
        self.cfg = tempfile.mkdtemp()
        os.environ["CLAUDE_CONFIG_DIR"] = self.cfg

    def tearDown(self):
        if self._env is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = self._env

    def _run(self, d, tool_input):
        import subprocess
        hook = os.path.join(HERE, "pretool_spawn_guard.py")
        ti = dict(tool_input)
        # Every spawn must declare a level (see the effort check). Fixtures here are
        # about the OTHER rules, so they carry a valid declaration unless they say not.
        ti.setdefault("description", "effort=high")
        payload = {"cwd": d, "session_id": SID, "tool_name": "Agent",
                   "transcript_path": "", "tool_input": ti}
        env = dict(os.environ)
        r = subprocess.run([sys.executable, hook], input=json.dumps(payload),
                           text=True, capture_output=True, env=env, timeout=20)
        return r.returncode, r.stderr

    def test_named_reviewer_spawn_blocked(self):
        # field case 2026-07-19: L1-151 / L2-145-146-final sat on the members
        # roster — the CEO had been naming its Auditor invocations into teammates
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            for st in ("clock-in:Auditor", "Auditor", "clock-in:Inspector"):
                code, err = self._run(d, {"name": "L2-151-final", "subagent_type": st})
                self.assertEqual(code, 2, st)
                self.assertIn("ONE-SHOT", err)
            # unnamed reviewer passes untouched (the actual contract)
            code, _ = self._run(d, {"subagent_type": "clock-in:Auditor", "prompt": "review task_id 7, handle QA"})
            self.assertEqual(code, 0)

    @unittest.skip("effort declaration not required while the setter is unwired")
    def test_effort_must_be_declared_on_every_teammate_spawn(self):
        """A teammate cannot be given a level by the platform — the spawn drops the
        field and hands it the LEAD's — so an omission is an accident nobody can see,
        not a default. It rides the TEXT: `effort` as a parameter is accepted by the
        Agent tool and discarded before any hook sees it (verified against the hook
        payload), so a param would look right and reach nothing."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            code, err = self._run(d, {"name": "RnD-377", "subagent_type": "RnD",
                                   "description": "build it", "prompt": "card #377"})
            self.assertEqual(code, 2)
            self.assertIn("effort not declared", err)
            # a PARAMETER does not count — that is the whole point
            code, err = self._run(d, {"name": "RnD-377", "subagent_type": "RnD",
                                   "description": "build it", "effort": "high"})
            self.assertEqual(code, 2)
            # declared in either field, in any of the spellings, passes
            for ti in ({"description": "effort=high"},
                       {"description": "x", "prompt": "… effort: xhigh …"},
                       {"description": "EFFORT = low"}):
                ti.update({"name": "RnD-377", "subagent_type": "RnD"})
                code, _ = self._run(d, ti)
                self.assertEqual(code, 0, ti)
            # a level that is not a level is not a declaration
            code, err = self._run(d, {"name": "RnD-377", "subagent_type": "RnD",
                                   "description": "effort=turbo"})
            self.assertEqual(code, 2)
            self.assertIn("effort not declared", err)
            # one-shots are untouched: their frontmatter effort: IS honoured
            code, _ = self._run(d, {"subagent_type": "RnD"})
            self.assertEqual(code, 0)

    @unittest.skip("effort declaration not required while the setter is unwired")
    def test_structural_refusals_outrank_the_effort_check(self):
        """A spawn that is structurally wrong must hear that first — asking the CEO to
        add a level to a call it is about to be told to withdraw is two round trips."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            code, err = self._run(d, {"name": "L2-151", "subagent_type": "clock-in:Auditor",
                                   "description": "review it"})
            self.assertEqual(code, 2)
            self.assertIn("ONE-SHOT", err)
            self.assertNotIn("effort not declared", err)

    def _pf(self, d, **ti):
        ti.setdefault("subagent_type", "clock-in:Auditor")
        return self._run(d, ti)

    def test_preflight_refuses_a_review_that_would_bounce_on_sight(self):
        """Roughly half of one project's review rounds were paperwork-shaped — a bounce
        that changed ZERO bytes. The 审查官 already refuses these at STEP 0, but only
        after an opus subagent has been spawned, has read, and has written a `.fail`.
        Same refusals, before the spawn, for free. NO new bar: everything here is
        something the reviewer already bounces."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            # names no task -> the reviewer is told to stop and ask, never to guess an id
            code, err = self._pf(d, prompt="please review my work")
            self.assertEqual(code, 2)
            self.assertIn("names no task", err)
            # names one -> nothing to catch
            code, _ = self._pf(d, prompt="L2 for task_id 118, handle QA")
            self.assertEqual(code, 0)

    def test_preflight_refuses_a_card_whose_named_evidence_is_not_on_disk(self):
        """The reviewer judges the artefact the card NAMES, never prose about it — so a
        missing file is a certain bounce and a mechanical one."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            bd = os.path.join(d, "docs", "board"); os.makedirs(bd)
            open(os.path.join(bd, "7-x.md"), "w").write(
                "---\ntask_id: 99\ndept: QA\n---\nEvidence: docs/reports/absent.md\n")
            code, err = self._pf(d, prompt="L2 for task_id 99, handle QA")
            self.assertEqual(code, 2)
            self.assertIn("absent.md", err)
            os.makedirs(os.path.join(d, "docs", "reports"))
            open(os.path.join(d, "docs", "reports", "absent.md"), "w").write("x")
            code, _ = self._pf(d, prompt="L2 for task_id 99, handle QA")
            self.assertEqual(code, 0)

    def test_preflight_never_judges_a_NAMED_auditor_first(self):
        """A named reviewer is a worse and different mistake — a reviewer squatting a
        pane. It must hear that, not a note about its paperwork."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            code, err = self._run(d, {"name": "L2-7", "subagent_type": "clock-in:Auditor",
                                   "prompt": "please review my work"})
            self.assertEqual(code, 2)
            self.assertIn("ONE-SHOT", err)
            self.assertNotIn("names no task", err)

    def test_preflight_is_inert_off_an_active_project_and_on_other_agents(self):
        with tempfile.TemporaryDirectory() as d:            # no orchestrate.json
            code, _ = self._pf(d, prompt="please review my work")
            self.assertEqual(code, 0)
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            code, _ = self._run(d, {"subagent_type": "clock-in:Inspector", "prompt": "look"})
            self.assertEqual(code, 0)

    def test_named_expert_spawn_blocked(self):
        """An expert named into a teammate holds a pane it has no card for AND loses
        its brief's `effort:` — the teammate spawn path drops that field, so the pin
        the file carries silently becomes the lead's level."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            for st in ("Prof_Academic", "Spec_CompIntel", "clock-in:Prof_Legal"):
                code, err = self._run(d, {"name": "Prof_Academic-962", "subagent_type": st})
                self.assertEqual(code, 2, st)
                self.assertIn("ONE-SHOT", err)
            # unnamed expert passes — that IS the contract
            code, _ = self._run(d, {"subagent_type": "Prof_Academic"})
            self.assertEqual(code, 0)
            # a dept whose handle merely starts with the letters is not an expert
            code, _ = self._run(d, {"name": "Profiler-12", "subagent_type": "Profiler"})
            self.assertEqual(code, 0)


class FableApproval(unittest.TestCase):
    """`fable` is weekly-capped and the cap is shared with everything else the Boss
    runs on it, so the tier is theirs to approve per spawn and never the CEO's to route.
    The guard reads a verbatim marker off the call; a dept the Boss pinned in its brief
    spawns param-less and is never judged here at all."""

    def setUp(self):
        self._env = os.environ.get("CLAUDE_CONFIG_DIR")
        self.cfg = tempfile.mkdtemp()
        os.environ["CLAUDE_CONFIG_DIR"] = self.cfg

    def tearDown(self):
        if self._env is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = self._env

    def _run(self, d, tool_input):
        import subprocess
        ti = dict(tool_input)
        ti.setdefault("description", "effort=high")
        payload = {"cwd": d, "session_id": SID, "tool_name": "Agent",
                   "transcript_path": "", "tool_input": ti}
        r = subprocess.run([sys.executable, os.path.join(HERE, "pretool_spawn_guard.py")],
                           input=json.dumps(payload), text=True, capture_output=True,
                           env=dict(os.environ), timeout=20)
        return r.returncode, r.stderr

    def test_unapproved_fable_teammate_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [])
            code, err = self._run(d, {"name": "RnD-7", "subagent_type": "RnD",
                                      "model": "fable"})
            self.assertEqual(code, 2)
            # The fix must be typeable from the message alone: the ask, the marker,
            # and the fallback to run while they have not answered.
            self.assertIn("@BOSS", err)
            self.assertIn("BOSS-APPROVED-FABLE", err)
            self.assertIn("opus", err)

    def test_a_one_shot_is_judged_too(self):
        """A one-shot can name a tier like anything else, and it is the shape that
        would drain the weekly cap with nobody's name on any bill. The old tier guard
        returned before it ever saw one."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            code, err = self._run(d, {"subagent_type": "clock-in:Inspector",
                                      "model": "fable", "prompt": "复盘 task 7"})
            self.assertEqual(code, 2)
            self.assertIn("BOSS-APPROVED-FABLE", err)

    def test_the_marker_unblocks_it_in_either_field(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [])
            for ti in ({"description": "effort=high · BOSS-APPROVED-FABLE"},
                       {"prompt": "BOSS-APPROVED-FABLE — they said go on the board"}):
                ti.update({"name": "RnD-7", "subagent_type": "RnD", "model": "fable"})
                code, err = self._run(d, ti)
                self.assertEqual(code, 0, err)

    def test_a_paraphrase_is_not_the_marker(self):
        """One spelling on purpose: a marker the CEO can produce by paraphrase is one
        it produces by habit, and this one is meant to cost a round trip."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [])
            for desc in ("effort=high · boss approved fable",
                         "effort=high · BOSS_APPROVED_FABLE",
                         "effort=high · the Boss approved this fable spawn"):
                code, _ = self._run(d, {"name": "RnD-7", "subagent_type": "RnD",
                                        "model": "fable", "description": desc})
                self.assertEqual(code, 2, desc)

    def test_her_brief_pin_never_reaches_the_guard(self):
        """A 部门 they designated `model: fable` spawns with no param, so there is no
        value on the call to judge — their standing word, unchallenged."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [])
            os.makedirs(os.path.join(d, ".claude", "agents"), exist_ok=True)
            with open(os.path.join(d, ".claude", "agents", "Mkt.md"), "w") as f:
                f.write("---\nname: Mkt\ndescription: x\nmodel: fable\n---\nbody\n")
            code, err = self._run(d, {"name": "Mkt-7", "subagent_type": "Mkt"})
            self.assertEqual(code, 0, err)

    def test_every_other_tier_is_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [])
            for tier in ("sonnet", "opus", "haiku"):
                code, err = self._run(d, {"name": "RnD-7", "subagent_type": "RnD",
                                          "model": tier})
                self.assertEqual(code, 0, "%s: %s" % (tier, err))

    def test_inert_off_an_armed_project(self):
        """The rule it enforces is the CEO's; outside an orchestrate project there is
        no CEO, and a plugin that polices unrelated repos gets uninstalled."""
        with tempfile.TemporaryDirectory() as d:      # NOTE: no _proj() marker
            code, err = self._run(d, {"name": "RnD-7", "subagent_type": "RnD",
                                      "model": "fable"})
            self.assertEqual(code, 0, err)


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
        ti = dict(tool_input)
        # Same as the tier-guard runner: these fixtures test OTHER rules, so they
        # satisfy the effort declaration unless the test is about it.
        ti.setdefault("description", "effort=high")
        payload = {"cwd": d, "session_id": SID, "tool_name": "Agent",
                   "tool_input": ti}
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



class SeatPerCard(unittest.TestCase):
    """One card per seat, each seat named for its card.
    Card detection reads only ASSIGNMENT-shaped mentions, taken off three LIVE dispatch
    prompts rather than guessed: "dispatched by the CEO for card #377 (platform task 81)"
    and "read your two cards IN FULL: docs/board/361-…md and docs/board/363-…md"."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, ".claude"), exist_ok=True)
        with open(os.path.join(self.tmp, ".claude", "orchestrate.json"), "w") as f:
            f.write('{"active":true}')

    def _run(self, name, prompt, root, stype=None):
        import subprocess
        hook = os.path.join(HERE, "pretool_spawn_guard.py")
        payload = {"cwd": root, "session_id": "z" * 36, "tool_name": "Agent",
                   "transcript_path": "",
                   # `effort=high` satisfies the effort declaration — these fixtures
                   # are about the one-card-per-seat naming rules, not that check.
                   "tool_input": {"name": name, "subagent_type": stype or name,
                                  "prompt": prompt, "model": "sonnet",
                                  "description": "effort=high"}}
        r = subprocess.run([sys.executable, hook], input=json.dumps(payload),
                           text=True, capture_output=True, timeout=20)
        return r.returncode, r.stderr

    def test_bare_handle_on_a_single_card_dispatch_is_renamed(self):
        rc, err = self._run("Frontend", "dispatched by the CEO for card #377 (task 81)", self.tmp)
        self.assertEqual(rc, 2)
        self.assertIn("Frontend-377", err)

    def test_card_numbered_seat_passes(self):
        rc, _ = self._run("Frontend-377", "dispatched by the CEO for card #377", self.tmp)
        self.assertEqual(rc, 0)

    def test_two_cards_on_one_seat_is_split(self):
        rc, err = self._run(
            "Backend-Engine",
            "read your two cards IN FULL: docs/board/361-GROUP.md (task_id 65) and "
            "docs/board/363-MASSIVE.md (task_id 67)", self.tmp)
        self.assertEqual(rc, 2)
        self.assertIn("one card per seat", err)
        self.assertIn("#361", err)
        self.assertIn("#363", err)

    def test_a_cited_card_is_context_not_an_assignment(self):
        """A live spec names its parent, its grounding doc and the frozen window. Reading
        every #NNN as an assignment would misname the seat, and the CEO would comply."""
        rc, _ = self._run("Frontend", "rework the #364 caveat and mind #368", self.tmp)
        self.assertEqual(rc, 0)

    def test_ad_hoc_task_name_is_prescribed_off_the_DEPT_not_the_name(self):
        """Their CEO already invents task-named seats (`spacefix352`, `iofix338`,
        `ioaudit362`, `fencefix359` all appear as completed-card owners on the live
        board) and they carry the number with no separator, so base() cannot strip it:
        each reads as a dept nobody staffs, finds no agent brief, and never matches a
        card's dept in a liveness check. Prescribing off the NAME would answer
        'spacefix352-352'; the dept comes from subagent_type."""
        rc, err = self._run("spacefix352", "dispatched for card #352", self.tmp,
                            stype="Frontend")
        self.assertEqual(rc, 2)
        self.assertIn("Frontend-352", err)
        self.assertNotIn("spacefix352-352", err)

    def test_suffix_of_a_different_dept_does_not_count_as_named(self):
        """`Backend-IO-2` spawned as subagent_type Frontend is not a Frontend seat named
        for its card — the numeric suffix must sit on the DEPT handle."""
        rc, err = self._run("Backend-IO-2", "dispatched for card #352", self.tmp,
                            stype="Frontend")
        self.assertEqual(rc, 2)
        self.assertIn("Frontend-352", err)

    def test_registrar_is_exempt_because_its_prompt_carries_the_queue(self):
        rc, _ = self._run(
            "Registrar",
            "queue state: Backend-Engine has docs/board/218-A.md and docs/board/212-B.md",
            self.tmp)
        self.assertEqual(rc, 0)


class RoutingTable(unittest.TestCase):
    """The routing table only bound the external-dispatch script; internally it was a
    note the CEO was asked to consult, and a routing rule nobody consults is decoration.
    This binds the ONE case nobody catches: a spawn that names no model, inherits the
    brief's pin, and comes up a tier under what the dept's row says the work needs."""

    def setUp(self):
        self._env = os.environ.get("CLAUDE_CONFIG_DIR")
        self.cfg = tempfile.mkdtemp()
        os.environ["CLAUDE_CONFIG_DIR"] = self.cfg
        self.d = tempfile.mkdtemp()
        _proj(self.d)
        _team(self.cfg, [_member("team-lead")])
        os.makedirs(os.path.join(self.d, ".claude", "agents"), exist_ok=True)
        with open(os.path.join(self.d, ".claude", "agents", "Legal.md"), "w") as f:
            f.write("---\nname: Legal\nmodel: sonnet\neffort: high\n---\n\nbody\n")
        os.makedirs(os.path.join(self.d, "docs", "board"), exist_ok=True)
        with open(os.path.join(self.d, "docs", "board", "routing.json"), "w") as f:
            json.dump({"version": 3, "default": {"model": "sonnet", "effort": "high"},
                       "departments": {"Legal": {
                           "default": {"model": "sonnet", "effort": "medium"},
                           "task_classes": {"judge": {"model": "opus", "effort": "high"}}}}}, f)

    def tearDown(self):
        if self._env is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = self._env

    def _run(self, desc, model=None):
        import subprocess
        ti = {"subagent_type": "Legal", "name": "Legal-9", "description": desc}
        if model:
            ti["model"] = model
        payload = {"cwd": self.d, "session_id": SID, "tool_name": "Agent",
                   "transcript_path": "", "tool_input": ti}
        r = subprocess.run([sys.executable, os.path.join(HERE, "pretool_spawn_guard.py")],
                           input=json.dumps(payload), text=True, capture_output=True,
                           env=dict(os.environ), timeout=20)
        return r.returncode, r.stderr

    def test_the_ordinary_dispatch_is_silent(self):
        """The dept's default row and its brief agree, which is the normal state of a
        table that recruit seeded from the briefs. A guard that fires here is a tax."""
        self.assertEqual(self._run("card #7 · effort=high")[0], 0)

    def test_a_class_that_raises_the_tier_blocks_a_model_less_spawn(self):
        rc, err = self._run("card #7 · class=judge · effort=high")
        self.assertEqual(rc, 2)
        self.assertIn("judge", err)
        self.assertIn("sonnet", err)                # what this spawn would actually get
        self.assertIn("opus", err)                  # what the row says

    def test_it_names_no_value_and_narrates_nothing(self):
        """Two facts and the parameter. Naming a value answers the question this guard
        exists to make somebody ask; narrating that it is not naming one ("whichever you
        name") is the same mistake wearing humility, and costs the reader a line
        mid-dispatch."""
        _, err = self._run("card #7 · class=judge · effort=high")
        for banned in ('model:"opus"', 'model:"sonnet"', "Re-issue with",
                       "whichever", "nothing here can tell"):
            self.assertNotIn(banned, err)
        self.assertIn("Pass `model:`", err)
        self.assertLess(len(err.strip()), 200)

    def test_the_message_carries_ONE_row_not_the_table(self):
        """The reader is mid-dispatch. A guard that prints a config file makes them
        find their own line in it."""
        _, err = self._run("card #7 · class=judge · effort=high")
        self.assertNotIn("Backend", err)
        self.assertNotIn("task_classes", err)
        self.assertLess(len(err), 400)

    def test_an_explicit_model_always_passes(self):
        """Naming a tier IS the decision this guard exists to force. Refusing it too
        would bill the CEO for exercising the judgment the routing rule grants it."""
        self.assertEqual(self._run("card #7 · class=judge · effort=high", "sonnet")[0], 0)

    def test_no_table_and_an_unknown_class_are_both_silent(self):
        """Fail open: the table is the CEO's own note, so a missing file or a typo in
        it must never stop the work."""
        self.assertEqual(self._run("card #7 · class=zzz · effort=high")[0], 0)
        os.remove(os.path.join(self.d, "docs", "board", "routing.json"))
        self.assertEqual(self._run("card #7 · class=judge · effort=high")[0], 0)


if __name__ == "__main__":
    unittest.main()
