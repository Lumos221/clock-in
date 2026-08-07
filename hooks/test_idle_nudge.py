"""Tests for stop_idle_nudge.py — the report nudge for dept teammates going idle
with unreported work, plus the boss-in-pane mute and the once-per-report-epoch cap.
Run: python3 hooks/test_idle_nudge.py"""
import os, sys, json, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
import stop_idle_nudge as nudge
import pane


def _line(**kw):
    return json.dumps(kw) + "\n"


def _tool(name, **inp):
    return _line(type="assistant", agentName="RnD", agentSetting="RnD",
                 teamName="session-abc12345",
                 message={"role": "assistant",
                          "content": [{"type": "tool_use", "name": name, "input": inp}]})


def _transcript(d, lines, fname="t.jsonl", identity=True):
    head = _line(type="last-prompt", agentName="RnD", agentSetting="RnD",
                 teamName="session-abc12345") if identity else _line(type="last-prompt")
    p = os.path.join(d, fname)
    with open(p, "w", encoding="utf-8") as f:
        f.write(head + "".join(lines))
    return p


def _proj(d, active=True):
    os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
    with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
        json.dump({"active": active}, f)


def _data(d, tp, event="Stop", session="s1"):
    return {"hook_event_name": event, "transcript_path": tp, "cwd": d,
            "session_id": session}


WORK = _tool("Edit", file_path="src/a.py", old_string="x", new_string="y")
REPORT = _tool("SendMessage", to="team-lead", summary="done", message="Status: done")


class Identity(unittest.TestCase):
    def test_lead_and_plain_sessions_never_nudged(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            plain_work = _line(type="assistant", message={          # NO teammate stamps
                "role": "assistant",
                "content": [{"type": "tool_use", "name": "Edit", "input": {}}]})
            tp = _transcript(d, [plain_work], identity=False)
            self.assertIsNone(nudge.run(_data(d, tp), ""))
            lead = _line(type="last-prompt", agentName="team-lead",
                         teamName="session-abc12345")
            tp2 = os.path.join(d, "lead.jsonl")
            open(tp2, "w").write(lead + WORK)
            self.assertIsNone(nudge.run(_data(d, tp2), ""))

    def test_registrar_never_nudged(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            reg = _line(type="last-prompt", agentName="Registrar-2",
                        agentSetting="Registrar", teamName="session-abc12345")
            tp = os.path.join(d, "r.jsonl")
            open(tp, "w").write(reg + WORK)
            self.assertIsNone(nudge.run(_data(d, tp), ""))

    def test_unarmed_project_silent(self):
        with tempfile.TemporaryDirectory() as d:                 # no marker at all
            tp = _transcript(d, [WORK])
            self.assertIsNone(nudge.run(_data(d, tp), ""))

    def test_inactive_marker_silent(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d, active=False)
            tp = _transcript(d, [WORK])
            self.assertIsNone(nudge.run(_data(d, tp), ""))


class NudgeCondition(unittest.TestCase):
    def test_work_after_report_nudges_once(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            tp = _transcript(d, [REPORT, WORK])
            first = nudge.run(_data(d, tp), "")
            self.assertIn("SendMessage", first or "")
            self.assertIsNone(nudge.run(_data(d, tp), ""))       # capped for this epoch

    def test_readonly_bash_after_report_is_clean(self):
        # Marketing field case 2026-07-18: report → verify HEAD (git log) → idle
        # must NOT draw the unreported-work nudge
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            tp = _transcript(d, [REPORT,
                                 _tool("Bash", command="git log --oneline -3 && git status"),
                                 _tool("Bash", command="cat docs/SoT.md | head -20")])
            self.assertIsNone(nudge.run(_data(d, tp), ""))

    def test_mutating_bash_after_report_nudges(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            tp = _transcript(d, [REPORT, _tool("Bash", command="git commit -am wip")])
            self.assertIn("SendMessage", nudge.run(_data(d, tp), "") or "")

    def test_bash_readonly_classifier(self):
        ro = nudge.bash_readonly
        self.assertTrue(ro("git log --oneline -5"))
        self.assertTrue(ro("git -C /x rev-parse --short HEAD"))
        self.assertTrue(ro("ls -la; grep -rn foo src | wc -l"))
        self.assertFalse(ro("git checkout -b feature"))       # mutating git
        self.assertFalse(ro("git log > out.txt"))             # redirect
        self.assertFalse(ro("python3 build.py"))              # unlisted head
        self.assertFalse(ro("cat a.md && rm b.md"))           # mutator in chain
        self.assertFalse(ro(""))

    def test_report_after_work_is_clean(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            tp = _transcript(d, [WORK, REPORT])
            self.assertIsNone(nudge.run(_data(d, tp), ""))

    def test_no_work_at_all_is_clean(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            tp = _transcript(d, [])
            self.assertIsNone(nudge.run(_data(d, tp), ""))

    def test_new_report_resets_epoch_then_new_work_renudges(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            tp = _transcript(d, [WORK])
            self.assertIsNotNone(nudge.run(_data(d, tp), ""))    # nudge 1 (rep=-1 epoch)
            with open(tp, "a") as f:
                f.write(REPORT + WORK)                           # reported, worked again
            self.assertIsNotNone(nudge.run(_data(d, tp), ""))    # fresh epoch → nudge 2
            self.assertIsNone(nudge.run(_data(d, tp), ""))       # capped again

    def test_pending_boss_ask_suppresses(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            tp = _transcript(d, [WORK])
            self.assertIsNone(nudge.run(_data(d, tp), "@BOSS[RnD#3]: A or B? rec A"))

    def test_subagent_stop_event_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            tp = _transcript(d, [WORK])
            self.assertIsNone(nudge.run(_data(d, tp, event="SubagentStop"), ""))

    def test_stop_hook_active_never_stacks(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            tp = _transcript(d, [WORK])
            data = _data(d, tp)
            data["stop_hook_active"] = True
            self.assertIsNone(nudge.run(data, ""))


class BossInPaneMute(unittest.TestCase):
    def test_marked_dept_is_muted_and_end_rearms(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            tp = _transcript(d, [WORK])
            cwd = os.getcwd()
            os.chdir(d)
            try:
                pane.main(["start", "RnD"])
                self.assertIsNone(nudge.run(_data(d, tp), ""))
                pane.main(["end", "RnD"])
            finally:
                os.chdir(cwd)
            self.assertIsNotNone(nudge.run(_data(d, tp), ""))

    def test_suffixed_spawn_matches_base_handle(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            reg = _line(type="last-prompt", agentName="RnD-2", agentSetting="RnD",
                        teamName="session-abc12345")
            tp = os.path.join(d, "t.jsonl")
            open(tp, "w").write(reg + WORK)
            with open(os.path.join(d, ".claude", "boss-in-pane.json"), "w") as f:
                json.dump({"RnD": "2026-07-15T00:00:00Z"}, f)
            self.assertIsNone(nudge.run(_data(d, tp), ""))


class PaneCli(unittest.TestCase):
    def test_start_status_end_clear(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            cwd = os.getcwd()
            os.chdir(d)
            try:
                self.assertEqual(pane.main(["start", "QA"]), 0)
                self.assertIn("QA", json.load(open(
                    os.path.join(d, ".claude", "boss-in-pane.json"))))
                self.assertEqual(pane.main(["end", "QA"]), 0)
                self.assertFalse(os.path.exists(
                    os.path.join(d, ".claude", "boss-in-pane.json")))
                pane.main(["start", "QA"])
                pane.main(["clear"])
                self.assertFalse(os.path.exists(
                    os.path.join(d, ".claude", "boss-in-pane.json")))
            finally:
                os.chdir(cwd)

    def test_bad_usage(self):
        self.assertEqual(pane.main([]), 1)
        self.assertEqual(pane.main(["bogus"]), 1)


if __name__ == "__main__":
    unittest.main()
