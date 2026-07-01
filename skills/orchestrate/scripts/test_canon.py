import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import canon

NOW = "2026-07-01"


class TableModel(unittest.TestCase):
    def test_set_creates_row_and_flags_affects(self):
        rows = []
        res = canon.apply_set(rows, "Fin", "pricing-tier", "docs/财务/pricing-tier.md",
                              "a7643d1", ["Marketing"], NOW)
        self.assertEqual(res["action"], "created")
        self.assertIsNone(res["old_file"])
        r = canon.find_row(rows, "pricing-tier")
        self.assertEqual(r["dept"], "Fin")
        self.assertEqual(r["needs_recheck"], ["Marketing"])

    def test_reemit_identical_is_noop(self):
        rows = []
        canon.apply_set(rows, "Fin", "pricing-tier", "f.md", "v1", ["Marketing"], NOW)
        canon.apply_ack(rows, "pricing-tier", "Marketing")          # clear the flag
        res = canon.apply_set(rows, "Fin", "pricing-tier", "f.md", "v1", ["Marketing"], NOW)
        self.assertEqual(res["action"], "unchanged")
        self.assertEqual(canon.find_row(rows, "pricing-tier")["needs_recheck"], [])  # not re-flagged

    def test_real_change_reflags_and_reports_old_file_on_path_change(self):
        rows = []
        canon.apply_set(rows, "Fin", "pricing-tier", "old.md", "v1", ["Marketing"], NOW)
        canon.apply_ack(rows, "pricing-tier", "Marketing")
        res = canon.apply_set(rows, "Fin", "pricing-tier", "new.md", "v2", ["Marketing"], NOW)
        self.assertEqual(res["action"], "changed")
        self.assertEqual(res["old_file"], "old.md")
        self.assertEqual(canon.find_row(rows, "pricing-tier")["needs_recheck"], ["Marketing"])
        self.assertEqual(canon.find_row(rows, "pricing-tier")["file"], "new.md")

    def test_version_change_same_path_is_a_change_no_archive(self):
        rows = []
        canon.apply_set(rows, "Fin", "pricing-tier", "f.md", "v1", [], NOW)
        res = canon.apply_set(rows, "Fin", "pricing-tier", "f.md", "v2", [], NOW)
        self.assertEqual(res["action"], "changed")
        self.assertIsNone(res["old_file"])     # same path -> nothing to archive

    def test_ack_supersede_get_list(self):
        rows = []
        canon.apply_set(rows, "Fin", "pricing-tier", "f.md", "v1", ["Marketing"], NOW)
        canon.apply_set(rows, "Legal", "redline", "r.md", "v1", [], NOW)
        self.assertTrue(canon.apply_ack(rows, "pricing-tier", "Marketing"))
        self.assertFalse(canon.apply_ack(rows, "nope", "X"))
        self.assertEqual(canon.get_file(rows, "redline"), "r.md")
        self.assertEqual([r["topic"] for r in canon.list_rows(rows, "Fin")], ["pricing-tier"])
        gone = canon.apply_supersede(rows, "redline")
        self.assertEqual(gone["file"], "r.md")
        self.assertIsNone(canon.find_row(rows, "redline"))

    def test_save_load_roundtrip_with_unicode_and_lists(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "docs", "CANON.md")
            rows = []
            canon.apply_set(rows, "Fin", "pricing-tier", "docs/财务/pricing-tier.md",
                            "a7643d1", ["Marketing", "Docs"], NOW)
            canon.save_rows(p, rows, "demo")
            back = canon.load_rows(p)
            self.assertEqual(len(back), 1)
            self.assertEqual(back[0]["file"], "docs/财务/pricing-tier.md")
            self.assertEqual(back[0]["affects"], ["Marketing", "Docs"])
            self.assertEqual(back[0]["needs_recheck"], ["Marketing", "Docs"])

    def test_render_shows_needs_recheck_block(self):
        rows = []
        canon.apply_set(rows, "Fin", "pricing-tier", "f.md", "v1", ["Marketing"], NOW)
        out = canon.render(rows, "demo")
        self.assertIn("## ⚠ Needs re-check", out)
        self.assertIn("`pricing-tier` → Marketing", out)
        self.assertIn("| pricing-tier | Fin |", out)


class MarkerParse(unittest.TestCase):
    def test_register_with_affects_and_unicode_path(self):
        out = canon.parse_canon_markers("ok\n@CANON[Fin] pricing-tier → docs/财务/pricing-tier.md (affects: Marketing, Docs)")
        self.assertEqual(out["registers"], [("Fin", "pricing-tier", "docs/财务/pricing-tier.md", ["Marketing", "Docs"])])
        self.assertEqual(out["acks"], [])

    def test_register_without_affects_and_ascii_arrow(self):
        out = canon.parse_canon_markers("@CANON[Legal] redline -> docs/合规/红线法律依据.md")
        self.assertEqual(out["registers"], [("Legal", "redline", "docs/合规/红线法律依据.md", [])])

    def test_ack_marker(self):
        out = canon.parse_canon_markers("done\n@CANON-ACK[Marketing] pricing-tier")
        self.assertEqual(out["acks"], [("Marketing", "pricing-tier")])
        self.assertEqual(out["registers"], [])

    def test_ack_is_not_parsed_as_register(self):
        out = canon.parse_canon_markers("@CANON-ACK[Marketing] pricing-tier")
        self.assertEqual(out["registers"], [])

    def test_no_marker(self):
        self.assertEqual(canon.parse_canon_markers("nothing here"), {"registers": [], "acks": []})


class Commands(unittest.TestCase):
    def _proj(self, d):
        os.makedirs(os.path.join(d, ".claude"))
        open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')

    def test_project_root_finds_marker(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            sub = os.path.join(d, "a"); os.makedirs(sub)
            self.assertEqual(os.path.realpath(canon.project_root(sub)), os.path.realpath(d))

    def test_set_persists_and_get_list(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            canon.cmd_set(d, "Fin", "pricing-tier", "docs/财务/pricing-tier.md", ["Marketing"])
            self.assertEqual(canon.cmd_get(d, "pricing-tier"), "docs/财务/pricing-tier.md")
            self.assertEqual([r["topic"] for r in canon.cmd_list(d, "Fin")], ["pricing-tier"])

    def test_set_repoint_archives_old_file(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            fin = os.path.join(d, "docs", "财务"); os.makedirs(fin)
            old = os.path.join(fin, "old.md"); open(old, "w").write("old")
            new = os.path.join(fin, "pricing-tier.md"); open(new, "w").write("new")
            canon.cmd_set(d, "Fin", "pricing-tier", "docs/财务/old.md", [])
            canon.cmd_set(d, "Fin", "pricing-tier", "docs/财务/pricing-tier.md", ["Marketing"])
            self.assertFalse(os.path.exists(old))                          # moved
            self.assertTrue(os.path.exists(os.path.join(fin, "archive", "old.md")))
            self.assertEqual(canon.cmd_get(d, "pricing-tier"), "docs/财务/pricing-tier.md")

    def test_ack_clears_flag(self):
        with tempfile.TemporaryDirectory() as d:
            self._proj(d)
            canon.cmd_set(d, "Fin", "pricing-tier", "f.md", ["Marketing"])
            self.assertTrue(canon.cmd_ack(d, "pricing-tier", "Marketing"))
            self.assertEqual(canon.cmd_list(d, "Fin")[0]["needs_recheck"], [])


class HookFlow(unittest.TestCase):
    def _run_hook(self, root, text):
        import subprocess, json as _json
        tpath = os.path.join(root, "t.jsonl")
        with open(tpath, "w", encoding="utf-8") as f:
            f.write(_json.dumps({"type": "assistant", "message": {"role": "assistant",
                    "content": [{"type": "text", "text": text}]}}) + "\n")
        hook = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))), "hooks", "stop_canon.py")
        subprocess.run([sys.executable, hook],
                       input=_json.dumps({"transcript_path": tpath, "cwd": root}),
                       text=True, timeout=20)

    def test_register_marker_writes_row(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
            self._run_hook(d, "done\n@CANON[Fin] pricing-tier → docs/财务/pricing-tier.md (affects: Marketing)")
            self.assertEqual(canon.cmd_get(d, "pricing-tier"), "docs/财务/pricing-tier.md")

    def test_ack_marker_clears_flag(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
            self._run_hook(d, "@CANON[Fin] pricing-tier → f.md (affects: Marketing)")
            self._run_hook(d, "@CANON-ACK[Marketing] pricing-tier")
            self.assertEqual(canon.cmd_list(d)[0]["needs_recheck"], [])

    def test_inactive_project_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            self._run_hook(d, "@CANON[Fin] pricing-tier → f.md")
            self.assertFalse(os.path.exists(os.path.join(d, "docs", "CANON.md")))


class DecisionResolve(unittest.TestCase):
    def _write(self, d, body):
        os.makedirs(os.path.join(d, "docs"), exist_ok=True)
        open(os.path.join(d, "docs", "DECISIONS.md"), "w", encoding="utf-8").write(body)

    def test_resolves_tag_strips_date_and_token(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d, "# log\n\n## 2026-06-30 · [monetization-model] Free=credits · Paid=packs\n- Why: x\n")
            date, gist = canon.decision_entry(d, "monetization-model")
            self.assertEqual(date, "2026-06-30")
            self.assertEqual(gist, "Free=credits · Paid=packs")

    def test_topmost_wins_on_date_collision_and_supersede(self):
        with tempfile.TemporaryDirectory() as d:
            # newest on top: a later monetization entry sits above the older one
            self._write(d,
                "## 2026-07-02 · [monetization-model] v2 credits model\n- Why: revised\n\n"
                "## 2026-06-30 · [pricing-tier] unrelated same-ish day\n\n"
                "## 2026-06-30 · [monetization-model] v1 credits model\n")
            date, gist = canon.decision_entry(d, "monetization-model")
            self.assertEqual((date, gist), ("2026-07-02", "v2 credits model"))

    def test_missing_tag_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d, "## 2026-06-30 · [other] thing\n")
            self.assertEqual(canon.decision_entry(d, "monetization-model"), (None, None))

    def test_no_decisions_file_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(canon.decision_entry(d, "x"), (None, None))


class RenderMirror(unittest.TestCase):
    def test_decision_row_gets_mirrored_section(self):
        rows = []
        canon.apply_set(rows, "Fin", "monetization-model", "DECISIONS", "2026-06-30", ["Marketing"], "2026-07-01")
        out = canon.render(rows, "demo", {"monetization-model": "Free=credits · Paid=packs"})
        self.assertIn("## Key decisions (mirrored", out)
        self.assertIn("- `monetization-model` · Fin — Free=credits · Paid=packs → `docs/DECISIONS.md`", out)
        self.assertIn("| monetization-model | Fin | DECISIONS |", out)   # still in the table

    def test_missing_gist_is_fail_visible(self):
        rows = []
        canon.apply_set(rows, "Fin", "monetization-model", "DECISIONS", "—", [], "2026-07-01")
        out = canon.render(rows, "demo", {})
        self.assertIn("(no [monetization-model] entry in DECISIONS.md", out)

    def test_no_decision_rows_no_section(self):
        rows = []
        canon.apply_set(rows, "Fin", "pricing-tier", "docs/财务/pricing-tier.md", "a76", [], "2026-07-01")
        out = canon.render(rows, "demo")
        self.assertNotIn("Key decisions", out)


if __name__ == "__main__":
    unittest.main()
