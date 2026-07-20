"""Tests for session_start.py — the CEO-mode injection and the token-free bloat
sentinel (SoT over-cap · essay-cards · unregistered cards · tombstone cards ·
DECISIONS lookup/impl discipline).
Run: python3 hooks/test_session_start.py"""
import os, sys, json, tempfile, unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session_start as ss

LEAN_SOT = "# demo · SoT\n\nGoal: ship v1\nNow: a · b · c\n"
LEAN_CARD = "### TASK-001 · login form\n- **task_id:** 3\n- **status:** doing\n"


def _proj(d, sot=LEAN_SOT, cards=LEAN_CARD, decisions=None, canon=None):
    os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
    with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
        f.write('{"active":true}')
    os.makedirs(os.path.join(d, "docs"), exist_ok=True)
    with open(os.path.join(d, "docs", "SoT.md"), "w", encoding="utf-8") as f:
        f.write(sot)
    with open(os.path.join(d, "docs", "TaskBoard.md"), "w", encoding="utf-8") as f:
        f.write("# demo · TaskBoard\n\n## Active\n\n%s\n## Recently shipped\n" % cards)
    if decisions is not None:
        with open(os.path.join(d, "docs", "DECISIONS.md"), "w", encoding="utf-8") as f:
            f.write(decisions)
    if canon is not None:
        with open(os.path.join(d, "docs", "CANON.md"), "w", encoding="utf-8") as f:
            f.write(canon)


def _ctx(d):
    cfg = json.load(open(os.path.join(d, ".claude", "orchestrate.json")))
    return ss.context_for(d, cfg)


class BloatSentinel(unittest.TestCase):
    def test_lean_project_gets_no_flags(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            out = _ctx(d)
            self.assertIn("CEO orchestration mode", out)
            self.assertIn("ship v1", out)          # SoT injected
            self.assertNotIn("⚠", out)             # zero flags when clean

    def test_overgrown_sot_flagged_every_session(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d, sot="# SoT\n" + "a line of standing detail\n" * 40)
            out = _ctx(d)
            self.assertIn("over its ~15-line hard cap", out)
            self.assertIn("DECISIONS.md", out)

    def test_essay_card_flagged_by_label(self):
        with tempfile.TemporaryDirectory() as d:
            essay = ("### TASK-002 · shipped-journal card\n- **task_id:** 4\n"
                     "- **status:** doing — " + "phase notes · " * 120 + "\n")
            _proj(d, cards=LEAN_CARD + "\n" + essay)
            out = _ctx(d)
            self.assertIn("a card is a pointer, not a journal", out)
            self.assertIn("TASK-002", out)
            self.assertNotIn("TASK-001", out.split("pointer")[1])  # lean card not named

    def test_unregistered_card_flag_still_present(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d, cards="### TASK-009 · hand thing\n- **task_id:** —\n- **status:** todo\n")
            out = _ctx(d)
            self.assertIn("carry no platform task_id", out)
            self.assertIn("TASK-009", out)


TOMB_CARD = "### ~~OLD-X~~ ALL SHIPPED 07-14 (detail = BACKLOG) — card closes.\n"
LIVE_IDLESS = "### TASK-009 · hand thing\n- **task_id:** —\n- **status:** todo\n"


class TombstoneCards(unittest.TestCase):
    """Field case (refcheck): id-less finished cards closed by striking the heading.
    The register-via-TaskCreate advice is wrong for them (it would re-register shipped
    work); the flag must prescribe deletion instead."""

    def test_tombstone_prescribes_delete_not_register(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d, cards=TOMB_CARD)
            out = _ctx(d)
            self.assertIn("tombstone", out)
            self.assertIn("Delete", out)
            self.assertNotIn("carry no platform task_id", out)

    def test_mixed_idless_cards_get_separate_prescriptions(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d, cards=LIVE_IDLESS + "\n" + TOMB_CARD)
            out = _ctx(d)
            self.assertIn("carry no platform task_id", out)   # live one: register
            self.assertIn("TASK-009", out)
            self.assertIn("tombstone", out)                   # dead one: delete
            reg_flag = out.split("carry no platform task_id", 1)[1].split("⚠")[0]
            self.assertNotIn("OLD-X", reg_flag)               # not told to register a tombstone


class ExternalLaneFlags(unittest.TestCase):
    """0.9.29 分公司: an external dept's cards are id-less BY DESIGN — the
    register-via-TaskCreate prescription must skip them."""

    def test_external_idless_card_not_prescribed_registration(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d, cards=("### #141 · MARKETING-LAUNCH\n- **dept:** Marketing\n"
                            "- **task_id:** —\n- **status:** todo\n"))
            with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
                f.write('{"active":true,"external":["Marketing"]}')
            self.assertNotIn("carry no platform task_id", _ctx(d))

    def test_internal_idless_card_still_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d, cards=("### #141 · MARKETING-LAUNCH\n- **dept:** Marketing\n"
                            "- **task_id:** —\n- **status:** todo\n"))
            self.assertIn("carry no platform task_id", _ctx(d))  # no external flag set


class DecisionsSentinel(unittest.TestCase):
    """Token-free lookup/impl discipline over DECISIONS.md — field causes (refcheck):
    tagged rulings without a CANON row make lookups grep-luck; rulings whose impl was
    'queued' in prose but never became a card are silent loss."""

    def test_tagged_decision_without_canon_row_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d, decisions=("# D\n\n## 2026-06-01 · [pricing-model] credits, not tiers\n"
                                "- **Why:** x\n- **Impl:** none-needed\n"),
                  canon="# demo · CANON\n\n| topic | dept |\n| --- | --- |\n")
            out = _ctx(d)
            self.assertIn("CANON row", out)
            self.assertIn("pricing-model", out)

    def test_tagged_decision_with_canon_row_is_clean(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d, decisions=("# D\n\n## 2026-06-01 · [pricing-model] credits, not tiers\n"
                                "- **Why:** x\n- **Impl:** none-needed\n"),
                  canon=("# demo · CANON\n\n| topic | dept |\n| --- | --- |\n"
                         "| pricing-model | RnD |\n"))
            self.assertNotIn("CANON row", _ctx(d))

    def test_recent_entry_missing_impl_flagged(self):
        day = (date.today() - timedelta(days=2)).isoformat()
        with tempfile.TemporaryDirectory() as d:
            _proj(d, decisions="# D\n\n## %s · 留空 on required fields\n- **Why:** x\n" % day)
            out = _ctx(d)
            self.assertIn("**Impl:**", out)
            self.assertIn("留空", out)

    def test_old_entry_missing_impl_not_flagged(self):
        day = (date.today() - timedelta(days=30)).isoformat()
        with tempfile.TemporaryDirectory() as d:
            _proj(d, decisions="# D\n\n## %s · ancient ruling\n- **Why:** x\n" % day)
            self.assertNotIn("**Impl:**", _ctx(d))

    def test_recent_entry_with_impl_is_clean(self):
        day = date.today().isoformat()
        with tempfile.TemporaryDirectory() as d:
            _proj(d, decisions=("# D\n\n## %s · new ruling\n- **Why:** x\n"
                                "- **Impl:** #4\n" % day))
            self.assertNotIn("⚠", _ctx(d).split("ship v1")[1])  # no flags after SoT

    def test_no_decisions_file_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            self.assertNotIn("CANON row", _ctx(d))


class EssayAskSentinel(unittest.TestCase):
    """Field case (refcheck CEO-89, 800+ chars): the Boss reads a 2-line clamp, and
    boss-board.md's decidable-ask rule (question · options · recommendation, 1–2 lines)
    is prose that rots. Flag open essay asks at session start; resolved ones are done."""

    def _add(self, d, text):
        ss.board._SKIP_SERVER = True
        return ss.board.board_add(d, "CEO", "needs", text)

    def test_open_essay_ask_flagged_with_id_and_size(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            e = self._add(d, "eyeball the v5 render — " + "detail · " * 60)
            out = _ctx(d)
            self.assertIn("essay", out)
            self.assertIn(e["id"], out)

    def test_short_and_resolved_asks_are_clean(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            self._add(d, "sign the 3 strings? A keep · B revert — rec A")
            e = self._add(d, "old essay " + "x" * 400)
            ss.board.board_done(d, e["id"])
            self.assertNotIn("essay", _ctx(d))


class SettledQuestionRule(unittest.TestCase):
    def test_search_before_answer_rule_always_injected(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            out = _ctx(d)
            self.assertIn("orchestrate-canon get", out)
            self.assertIn("DECISIONS", out)


def _hook_out(d, transcript_path=None):
    import subprocess
    payload = {"cwd": d}
    if transcript_path:
        payload["transcript_path"] = transcript_path
    hook = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_start.py")
    r = subprocess.run([sys.executable, hook], input=json.dumps(payload),
                       text=True, capture_output=True, timeout=20)
    return r.stdout


def _teammate_transcript(d, name, setting):
    p = os.path.join(d, "%s.jsonl" % name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "last-prompt", "agentName": name,
                            "agentSetting": setting, "teamName": "session-ab12cd34"}) + "\n")
    return p


class Audience(unittest.TestCase):
    """Teammate panes get the slim brief (role line + SoT, no CEO flags); the
    Registrar gets nothing; the lead keeps the full injection (field cause: every
    dept spawn was being told 'You are the CEO' + handed the CEO's chore flags)."""

    def test_dept_gets_slim_brief_without_ceo_flags(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d, sot="# SoT\n" + "a line of standing detail\n" * 40)  # over-cap
            out = _hook_out(d, _teammate_transcript(d, "RnD", "RnD"))
            self.assertIn("teammate RnD", out)
            self.assertIn("a line of standing detail", out)     # SoT still injected
            self.assertIn("orchestrate-canon get", out)         # settled-question rule
            self.assertNotIn("You are the CEO", out)
            self.assertNotIn("⚠", out)                          # CEO chores not relayed

    def test_registrar_gets_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            out = _hook_out(d, _teammate_transcript(d, "Registrar-2", "Registrar"))
            self.assertEqual(out, "")

    def test_lead_still_gets_full_injection(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d, cards="### TASK-009 · hand thing\n- **task_id:** —\n- **status:** todo\n")
            p = os.path.join(d, "lead.jsonl")
            open(p, "w").write(json.dumps({"type": "last-prompt"}) + "\n")
            out = _hook_out(d, p)
            self.assertIn("You are the CEO", out)
            self.assertIn("carry no platform task_id", out)     # flags intact


class StaleIdDetach(unittest.TestCase):
    """Platform ids die with the session; stale ones auto-detach to — at session
    start so the id-less flag takes over (field cause: refcheck CEO journaled
    '#— (session-1 id retired; re-CREATE at dispatch)' into card headings)."""

    SID = "dddd1111-2222-3333-4444-555566667777"

    def setUp(self):
        self._env = os.environ.get("CLAUDE_CONFIG_DIR")
        self.cfg_root = tempfile.mkdtemp()
        os.environ["CLAUDE_CONFIG_DIR"] = self.cfg_root

    def tearDown(self):
        if self._env is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = self._env

    def _store_task(self, tid):
        d = os.path.join(self.cfg_root, "tasks", "session-%s" % self.SID[:8])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "%s.json" % tid), "w") as f:
            json.dump({"id": str(tid), "status": "in_progress"}, f)

    def test_stale_id_detached_live_id_kept(self):
        with tempfile.TemporaryDirectory() as d:
            cards = ("### #7 · dead one\n- **task_id:** 7\n- **status:** todo\n\n"
                     "### #9 · live one\n- **task_id:** 9\n- **status:** doing\n")
            _proj(d, cards=cards)
            self._store_task(9)
            cfg = json.load(open(os.path.join(d, ".claude", "orchestrate.json")))
            n = ss.detach_stale_ids(d, cfg, {"session_id": self.SID})
            self.assertEqual(n, 1)
            text = open(os.path.join(d, "docs", "TaskBoard.md"), encoding="utf-8").read()
            self.assertIn("- **task_id:** —", text)
            self.assertIn("- **task_id:** 9", text)

    def test_detached_card_then_gets_the_idless_flag(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d, cards="### TASK-X · orphan\n- **task_id:** 5\n- **status:** todo\n")
            cfg = json.load(open(os.path.join(d, ".claude", "orchestrate.json")))
            ss.detach_stale_ids(d, cfg, {"session_id": self.SID})
            self.assertIn("carry no platform task_id", ss.context_for(d, cfg))

    def test_no_session_id_or_missing_board_noop(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            cfg = json.load(open(os.path.join(d, ".claude", "orchestrate.json")))
            self.assertEqual(ss.detach_stale_ids(d, cfg, {}), 0)


class StandingShadowSentinel(unittest.TestCase):
    """0.9.16: standing agents ship plugin-scope; a leftover project copy shadows the
    plugin version and pins whatever contract wrote it. The flag prescribes the
    /recruit upgrade pass (diff for drift, then archive)."""

    def test_clean_project_silent(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            self.assertIsNone(ss.standing_shadow_flag(d))

    def test_legacy_copies_flagged_by_name(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            os.makedirs(os.path.join(d, ".claude", "agents"))
            for n in ("Registrar", "Auditor"):
                with open(os.path.join(d, ".claude", "agents", "%s.md" % n), "w") as f:
                    f.write("legacy")
            flag = ss.standing_shadow_flag(d)
            self.assertIn("Auditor", flag)
            self.assertIn("Registrar", flag)
            self.assertIn("/recruit", flag)
            self.assertIn("archive", flag)

    def test_dept_files_do_not_trigger(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            os.makedirs(os.path.join(d, ".claude", "agents"))
            with open(os.path.join(d, ".claude", "agents", "RnD.md"), "w") as f:
                f.write("dept brief")
            self.assertIsNone(ss.standing_shadow_flag(d))


class BriefsStampSentinel(unittest.TestCase):
    """0.9.16: recruit stamps briefs_template_hash at generation; a mismatch against
    the shipped department.md template means briefs predate it. No stamp = silent
    (pre-0.9.16 project — the shadow flag owns that migration)."""

    def _tpl_hash(self):
        import hashlib
        tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                           "skills", "orchestrate", "templates", "department.md")
        return hashlib.sha256(open(tpl, "rb").read()).hexdigest()[:12]

    def test_no_stamp_silent(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            self.assertIsNone(ss.briefs_stamp_flag(d, {"active": True}))

    def test_current_stamp_silent(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            cfg = {"active": True, "briefs_template_hash": self._tpl_hash()}
            self.assertIsNone(ss.briefs_stamp_flag(d, cfg))

    def test_stale_stamp_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            cfg = {"active": True, "briefs_template_hash": "deadbeef0123"}
            flag = ss.briefs_stamp_flag(d, cfg)
            self.assertIn("/recruit", flag)
            self.assertIn("restart", flag)


class RegimeArm(unittest.TestCase):
    """0.9.18: the Fable brain regime arms mechanically from SessionStart's `model`
    field (the prose switch was field-skipped twice). Parity/absent-model → silent."""

    def test_fable_model_arms(self):
        arm = ss.regime_arm({"model": "claude-fable-5"})
        self.assertIn("BRAIN REGIME", arm)
        self.assertIn("brain-regime.md", arm)
        self.assertIn("EXPLICIT model", arm)

    def test_parity_and_absent_model_silent(self):
        self.assertIsNone(ss.regime_arm({"model": "claude-opus-4-8"}))
        self.assertIsNone(ss.regime_arm({"model": "claude-sonnet-5"}))
        self.assertIsNone(ss.regime_arm({}))

    def test_arm_opens_the_lead_injection(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            hook = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_start.py")
            payload = {"cwd": d, "model": "claude-fable-5"}
            r = subprocess.run([sys.executable, hook], input=json.dumps(payload),
                               text=True, capture_output=True, timeout=20)
            self.assertTrue(r.stdout.startswith("🧠 REGIME SWITCH"))
            self.assertIn("CEO orchestration mode", r.stdout)   # normal injection follows
            payload = {"cwd": d, "model": "claude-opus-4-8"}
            r = subprocess.run([sys.executable, hook], input=json.dumps(payload),
                               text=True, capture_output=True, timeout=20)
            self.assertNotIn("REGIME SWITCH", r.stdout)


class Gating(unittest.TestCase):
    def test_inactive_marker_silent(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
                f.write('{"active":false}')
            payload = {"cwd": d}
            import subprocess
            hook = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_start.py")
            r = subprocess.run([sys.executable, hook], input=json.dumps(payload),
                               text=True, capture_output=True, timeout=20)
            self.assertEqual(r.stdout, "")


class BriefsAutopatch(unittest.TestCase):
    """0.9.27 frontmatter auto-migration: missing template fields are ADDED at
    session start (never overwriting a present pin); schema parity advances the
    stamp so the /recruit prescription retires for what the patch cured."""

    OLD_BRIEF = ("---\nname: %s\ndescription: dept\n"
                 "disallowedTools: TaskCreate, TaskUpdate, AskUserQuestion, Workflow, PowerShell\n"
                 "---\n\n# body stays byte-identical\n")

    def _armed(self, d, roster, stamp="deadbeef0000"):
        os.makedirs(os.path.join(d, ".claude", "agents"), exist_ok=True)
        with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
            json.dump({"active": True, "roster": roster,
                       "briefs_template_hash": stamp}, f)

    def _brief(self, d, handle, text):
        with open(os.path.join(d, ".claude", "agents", "%s.md" % handle), "w",
                  encoding="utf-8") as f:
            f.write(text)

    def _read(self, d, handle):
        return open(os.path.join(d, ".claude", "agents", "%s.md" % handle),
                    encoding="utf-8").read()

    def _cfg(self, d):
        return json.load(open(os.path.join(d, ".claude", "orchestrate.json"),
                              encoding="utf-8"))

    def test_missing_model_added_and_stamp_advanced(self):
        with tempfile.TemporaryDirectory() as d:
            self._armed(d, ["RnD", "QA"])
            for h in ("RnD", "QA"):
                self._brief(d, h, self.OLD_BRIEF % h)
            cfg = self._cfg(d)
            lines = ss.briefs_autopatch(d, cfg)
            self.assertEqual(len(lines), 1)
            self.assertIn("RnD (+model)", lines[0])
            self.assertNotIn("comments", lines[0])
            for h in ("RnD", "QA"):
                text = self._read(d, h)
                self.assertIn("model: sonnet\n", text)
                self.assertIn("# body stays byte-identical", text)
                self.assertTrue(text.startswith("---\nname: %s\n" % h))
            # parity → stamp advanced on disk → the /recruit flag stays silent
            cur = self._cfg(d)
            self.assertNotEqual(cur["briefs_template_hash"], "deadbeef0000")
            self.assertIsNone(ss.briefs_stamp_flag(d, cur))

    def test_present_pin_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            self._armed(d, ["Marketing"])
            self._brief(d, "Marketing", self.OLD_BRIEF % "Marketing"
                        .replace("---\n\n", ""))  # no-op guard for template drift
            self._brief(d, "Marketing",
                        "---\nname: Marketing\ndescription: d\n"
                        "disallowedTools: TaskCreate\nmodel: fable\n---\nbody\n")
            lines = ss.briefs_autopatch(d, self._cfg(d))
            self.assertEqual(lines, [])                      # nothing missing
            self.assertIn("model: fable", self._read(d, "Marketing"))

    def test_legacy_tools_allowlist_blocks_denylist_add_and_parity(self):
        with tempfile.TemporaryDirectory() as d:
            self._armed(d, ["Ops"])
            self._brief(d, "Ops", "---\nname: Ops\ndescription: d\n"
                                  "tools: Read, Edit, Bash\n---\nbody\n")
            cfg = self._cfg(d)
            lines = ss.briefs_autopatch(d, cfg)
            text = self._read(d, "Ops")
            self.assertIn("model: sonnet", text)             # model still added
            self.assertNotIn("disallowedTools", text)        # hand allowlist respected
            self.assertIn("tools: Read, Edit, Bash", text)
            self.assertEqual(self._cfg(d)["briefs_template_hash"], "deadbeef0000")
            self.assertTrue(lines)                           # notice names the patch

    def test_inline_comments_purged_from_field_lines(self):
        # the 0.9.18 bug class, found live in every refcheck brief (0.9.17-era
        # generation): the loader parses comment words as values
        with tempfile.TemporaryDirectory() as d:
            self._armed(d, ["Marketing"])
            self._brief(d, "Marketing",
                        "---\nname: Marketing\ndescription: d # keep this one\n"
                        "disallowedTools: TaskCreate, PowerShell  # denylist, not allowlist\n"
                        "model: fable  # Boss pin 2026-07-17\n---\nbody # not frontmatter\n")
            lines = ss.briefs_autopatch(d, self._cfg(d))
            text = self._read(d, "Marketing")
            self.assertIn("disallowedTools: TaskCreate, PowerShell\n", text)
            self.assertIn("model: fable\n", text)                  # pin kept, comment gone
            self.assertIn("description: d # keep this one", text)  # non-field lines untouched
            self.assertIn("body # not frontmatter", text)
            self.assertIn("comments purged", lines[0])

    def test_clean_briefs_are_untouched_and_silent(self):
        with tempfile.TemporaryDirectory() as d:
            self._armed(d, ["RnD"])
            full = self.OLD_BRIEF % "RnD"
            full = full.replace("---\n\n#", "model: sonnet\n---\n\n#")
            self._brief(d, "RnD", full)
            before = self._read(d, "RnD")
            self.assertEqual(ss.briefs_autopatch(d, self._cfg(d)), [])
            self.assertEqual(self._read(d, "RnD"), before)

    def test_empty_roster_or_missing_files_noop(self):
        with tempfile.TemporaryDirectory() as d:
            self._armed(d, [])
            self.assertEqual(ss.briefs_autopatch(d, self._cfg(d)), [])
        with tempfile.TemporaryDirectory() as d:
            self._armed(d, ["Ghost"])                        # roster entry, no file
            self.assertEqual(ss.briefs_autopatch(d, self._cfg(d)), [])


if __name__ == "__main__":
    unittest.main()
