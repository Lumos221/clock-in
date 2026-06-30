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


if __name__ == "__main__":
    unittest.main()
