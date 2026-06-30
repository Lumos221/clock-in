import os, sys, json, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board

NOW = "2026-06-30T12:00:00"


class StoreCore(unittest.TestCase):
    def test_add_creates_dept_prefixed_sequential_ids(self):
        s = {"entries": []}
        e1, c1 = board.add_entry(s, "QA", "needs", "Postgres or SQLite?", NOW)
        e2, c2 = board.add_entry(s, "QA", "needs", "Where do logs go?", NOW)
        e3, c3 = board.add_entry(s, "RnD", "needs", "Bump node?", NOW)
        self.assertEqual((e1["id"], e2["id"], e3["id"]), ("QA-1", "QA-2", "RnD-1"))
        self.assertTrue(c1 and c2 and c3)
        self.assertEqual(e1["status"], "open")
        self.assertEqual(e1["kind"], "needs")

    def test_add_is_idempotent_per_dept_and_normalised_text(self):
        s = {"entries": []}
        e1, c1 = board.add_entry(s, "QA", "needs", "Postgres or SQLite?", NOW)
        e2, c2 = board.add_entry(s, "QA", "needs", "  postgres or  SQLITE? ", NOW)
        self.assertTrue(c1)
        self.assertFalse(c2)              # duplicate -> no new entry
        self.assertEqual(e1["id"], e2["id"])
        self.assertEqual(len(s["entries"]), 1)

    def test_resolved_entry_frees_text_for_a_new_open_one(self):
        s = {"entries": []}
        e1, _ = board.add_entry(s, "QA", "needs", "same ask", NOW)
        board.set_status(s, e1["id"], "resolved", NOW)
        e2, c2 = board.add_entry(s, "QA", "needs", "same ask", NOW)
        self.assertTrue(c2)               # prior was resolved -> not a dup
        self.assertEqual(e2["id"], "QA-2")

    def test_resolve_by_dept_single_vs_ambiguous(self):
        s = {"entries": []}
        board.add_entry(s, "QA", "needs", "a", NOW)
        e, opens = board.resolve_by_dept(s, "QA", NOW)
        self.assertIsNotNone(e)
        self.assertEqual(e["status"], "resolved")
        board.add_entry(s, "RnD", "needs", "b", NOW)
        board.add_entry(s, "RnD", "needs", "c", NOW)
        e2, opens2 = board.resolve_by_dept(s, "RnD", NOW)
        self.assertIsNone(e2)             # two open -> ambiguous
        self.assertEqual(len(opens2), 2)

    def test_get_and_list_filter_by_dept(self):
        s = {"entries": []}
        board.add_entry(s, "QA", "needs", "a", NOW)
        board.add_entry(s, "RnD", "needs", "b", NOW)
        self.assertEqual(board.get_entry(s, "QA-1")["text"], "a")
        self.assertIsNone(board.get_entry(s, "QA-9"))
        self.assertEqual([e["id"] for e in board.list_entries(s, "RnD")], ["RnD-1"])
        self.assertEqual(len(board.list_entries(s)), 2)

    def test_set_status_park_reopen(self):
        s = {"entries": []}
        board.add_entry(s, "Boss", "discuss", "ToS read", NOW)
        self.assertEqual(board.set_status(s, "Boss-1", "parked", NOW)["status"], "parked")
        self.assertEqual(board.set_status(s, "Boss-1", "open", NOW)["status"], "open")
        self.assertIsNone(board.set_status(s, "Boss-9", "open", NOW))

    def test_load_save_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, ".claude", "boss-board.json")
            self.assertEqual(board.load_store(p), {"entries": []})  # missing -> empty
            s = {"entries": []}
            board.add_entry(s, "QA", "needs", "ask", NOW)
            board.save_store(p, s)
            self.assertEqual(board.load_store(p)["entries"][0]["id"], "QA-1")


class MarkerParse(unittest.TestCase):
    def test_raise_marker_extracts_dept_and_one_line_ask(self):
        out = board.parse_markers("blah\n@BOSS[QA]: Postgres or SQLite?\nmore")
        self.assertEqual(out["raises"], [("QA", "Postgres or SQLite?")])
        self.assertEqual(out["dones"], [])

    def test_done_marker_by_dept_and_by_id(self):
        out = board.parse_markers("@BOSS-DONE[QA]\nx\n@BOSS-DONE[RnD-2]")
        self.assertEqual(out["dones"], ["QA", "RnD-2"])
        self.assertEqual(out["raises"], [])

    def test_no_marker_is_empty(self):
        out = board.parse_markers("just a normal message, discuss this later")
        self.assertEqual(out, {"raises": [], "dones": []})

    def test_done_line_is_not_also_a_raise(self):
        out = board.parse_markers("@BOSS-DONE[QA]")
        self.assertEqual(out["raises"], [])
        self.assertEqual(out["dones"], ["QA"])


if __name__ == "__main__":
    unittest.main()
