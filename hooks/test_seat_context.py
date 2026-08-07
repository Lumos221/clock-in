"""Tests for stop_seat_context.py — the CEO-side seat-context gauge (lead Stop):
teammate transcript resolution by agentName stamp, real usage from the last
assistant `usage` fields, warn/high thresholds of the model window, one nudge
per seat per threshold with silent downgrade (respawn reset).
Run: python3 hooks/test_seat_context.py"""
import os, sys, json, time, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hooklib
import stop_seat_context as sc

SID = "aaaa1111-2222-3333-4444-555566667777"


def _team(cfg_root, members, lead_sid=SID):
    d = os.path.join(cfg_root, "teams", "session-%s" % lead_sid[:8])
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "config.json"), "w") as f:
        json.dump({"leadSessionId": lead_sid, "members": members}, f)


def _member(name, cwd, joined_ms=0):
    return {"name": name, "agentId": "%s@session-%s" % (name, SID[:8]),
            "agentType": name.rsplit("-", 1)[0], "cwd": cwd,
            "joinedAt": joined_ms, "isActive": False}


def _proj(d, extra=None):
    os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
    cfg = {"active": True}
    cfg.update(extra or {})
    with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
        json.dump(cfg, f)


def _transcript(cwd, agent_name, tokens, model="claude-sonnet-5", fname=None):
    """A teammate transcript: agentName stamped on every line (platform behaviour),
    last assistant entry carrying the usage that /context would report."""
    tdir = hooklib.transcripts_dir(cwd)
    os.makedirs(tdir, exist_ok=True)
    path = os.path.join(tdir, fname or ("%s.jsonl" % agent_name.lower()))
    stamp = {"agentName": agent_name, "agentSetting": agent_name, "teamName": "tm"}
    lines = [dict(stamp, type="user", message={"role": "user", "content": "go"}),
             dict(stamp, type="assistant",
                  message={"role": "assistant", "model": model,
                           "usage": {"input_tokens": tokens - 1000,
                                     "cache_read_input_tokens": 600,
                                     "cache_creation_input_tokens": 400}})]
    with open(path, "w", encoding="utf-8") as f:
        for ln in lines:
            f.write(json.dumps(ln) + "\n")
    return path


def _data(d, sid=SID, transcript=""):
    return {"hook_event_name": "Stop", "cwd": d, "session_id": sid,
            "transcript_path": transcript}


class SeatContext(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.get("CLAUDE_CONFIG_DIR")
        self.cfg = tempfile.mkdtemp()
        os.environ["CLAUDE_CONFIG_DIR"] = self.cfg

    def tearDown(self):
        if self._env is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = self._env

    def test_under_threshold_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Frontend-7", d)])
            _transcript(d, "Frontend-7", 300_000)              # 30% of 1M
            self.assertIsNone(sc.run(_data(d), None))

    def test_warn_crossing_nudges_once_then_high_rearms(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Frontend-7", d)])
            _transcript(d, "Frontend-7", 550_000)              # 55% → warn
            ret = sc.run(_data(d), None) or ""
            self.assertIn("Frontend-7 at 55%", ret)
            self.assertIn("fresh seat", ret)
            self.assertIsNone(sc.run(_data(d), None))            # same bucket → capped
            _transcript(d, "Frontend-7", 720_000)              # 72% → high re-arms
            ret = sc.run(_data(d), None) or ""
            self.assertIn("rotate at the CURRENT card's boundary", ret)
            self.assertIn("docs/handover-Frontend-7.md", ret)
            self.assertIsNone(sc.run(_data(d), None))

    def test_respawned_seat_resets_and_earns_future_nudges(self):
        """Same handle, fresh transcript: the record follows the decrease silently,
        so the fresh seat's own climb speaks again instead of being muted by the
        predecessor's bucket."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Backend-Engine-12", d)])
            _transcript(d, "Backend-Engine-12", 750_000)
            self.assertIn("rotate", sc.run(_data(d), None) or "")
            _transcript(d, "Backend-Engine-12", 80_000)         # fresh seat, 8%
            self.assertIsNone(sc.run(_data(d), None))            # downgrade is silent
            _transcript(d, "Backend-Engine-12", 560_000)        # climbs again
            self.assertIn("Backend-Engine-12 at 56%", sc.run(_data(d), None) or "")

    def test_haiku_window_is_200k(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Docs-9", d)])
            _transcript(d, "Docs-9", 120_000, model="claude-haiku-4-5")
            ret = sc.run(_data(d), None) or ""
            self.assertIn("Docs-9 at 60%", ret)
            self.assertIn("120k/200k", ret)

    def test_context_windows_override_wins(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d, extra={"context_windows": {"claude-sonnet": 200_000}})
            _team(self.cfg, [_member("QA-7", d)])
            _transcript(d, "QA-7", 120_000)                      # 60% of overridden 200k
            self.assertIn("QA-7 at 60%", sc.run(_data(d), None) or "")

    def test_registrar_is_exempt(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Registrar", d)])
            _transcript(d, "Registrar", 190_000, model="claude-haiku-4-5")
            self.assertIsNone(sc.run(_data(d), None))

    def test_transcript_older_than_joinedat_is_ignored(self):
        """A dead predecessor's transcript must not gauge the seat that replaced it."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            now_ms = int(time.time() * 1000)
            _team(self.cfg, [_member("Ops-9", d, joined_ms=now_ms)])
            old = _transcript(d, "Ops-9", 800_000, fname="old.jsonl")
            two_hours_ago = time.time() - 7200
            os.utime(old, (two_hours_ago, two_hours_ago))
            self.assertIsNone(sc.run(_data(d), None))

    def test_teammate_session_is_silent(self):
        """The gauge is CEO-facing: a teammate's own Stop must not print it."""
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Frontend-7", d)])
            own = _transcript(d, "Frontend-7", 750_000)
            self.assertIsNone(sc.run(_data(d, transcript=own), None))

    def test_branch_office_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Frontend-7", d)])
            _transcript(d, "Frontend-7", 750_000)
            wt = os.path.join(d, "wt")
            os.makedirs(os.path.join(wt, ".claude"), exist_ok=True)
            with open(os.path.join(wt, ".claude", "office.json"), "w") as f:
                json.dump({"office": "Marketing"}, f)
            self.assertIsNone(sc.run(_data(wt), None))

    def test_inactive_orchestrate_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
            with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
                f.write('{"active":false}')
            _team(self.cfg, [_member("Frontend-7", d)])
            _transcript(d, "Frontend-7", 750_000)
            self.assertIsNone(sc.run(_data(d), None))

    def test_two_seats_cross_in_one_turn_high_leads(self):
        with tempfile.TemporaryDirectory() as d:
            _proj(d)
            _team(self.cfg, [_member("Frontend-7", d), _member("Ops-9", d)])
            _transcript(d, "Frontend-7", 550_000)
            _transcript(d, "Ops-9", 730_000)
            ret = sc.run(_data(d), None) or ""
            self.assertLess(ret.index("Ops-9"), ret.index("Frontend-7"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
