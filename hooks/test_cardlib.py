"""Tests for cardlib.py — the per-card board store: frontmatter round-trips,
durable-id minting, lazy migration off a legacy TaskBoard.md, digest surgery.
Run: python3 hooks/test_cardlib.py"""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cardlib

LEGACY = """# demo · TaskBoard

> board notes the digest must keep.

## Active

### #130 · REDEEM-MODAL — X close missing
- **dept:** Frontend
- **task_id:** 3
- **status:** review — waiting on the Auditor
- **blocked_on:** —
- **what:** fix the modal chrome
- **done-when:** X closes it
- **artifacts:** —
dept prose line the card keeps.

### TASK-002 · shared design chain
- **dept:** Spec_Designer
- **task_id:** 6 规格 · 7 build
- **status:** doing
- **what:** two tasks one card

### ~~#7 · SHIPPED old thing~~

## Recently shipped
<!-- SHIPPED:START -->
- 2026-07-19 · #12 · RnD · older ship · abc1234
<!-- SHIPPED:END -->
"""


def _proj(d, board_md=LEGACY):
    os.makedirs(os.path.join(d, "docs"), exist_ok=True)
    if board_md is not None:
        with open(os.path.join(d, "docs", "TaskBoard.md"), "w", encoding="utf-8") as f:
            f.write(board_md)
    return {"taskboard": "docs/TaskBoard.md"}


class RoundTrip(unittest.TestCase):
    def test_quote_unquote_hostile_values(self):
        for v in ('has: colon', '#hash', 'trailing ', '"quoted"', '中书省 · 起草', '—'):
            self.assertEqual(cardlib._unquote(cardlib._quote(v)), v)

    def test_parse_render_preserves_extras_and_body(self):
        text = cardlib.render_card({"id": 5, "name": "x", "status": "todo"},
                                   ["severity: high"], "body [[link]]\n")
        meta, extras, body = cardlib.parse_card(text)
        self.assertEqual(meta["name"], "x")
        self.assertEqual(extras, ["severity: high"])
        self.assertIn("[[link]]", body)
        self.assertEqual(cardlib.parse_card(cardlib.render_card(meta, extras, body)),
                         (meta, extras, body))

    def test_parse_rejects_fenceless(self):
        self.assertIsNone(cardlib.parse_card("# just a note\n"))


class Store(unittest.TestCase):
    def test_priority_field_first_class(self):
        with tempfile.TemporaryDirectory() as d:
            a = cardlib.new_card(d, "urgent", priority="P0")
            b = cardlib.new_card(d, "normal")
            got = {c["name"]: c["priority"] for c in cardlib.load(d)}
            self.assertEqual(got, {"urgent": "P0", "normal": "—"})
            # lexical ordering P0 < P1 < P2 < — holds by construction (Bases + panel
            # sort with no mapping table)
            self.assertTrue("P0" < "P1" < "P2" < "—")

    def test_new_card_mints_next_free_id(self):
        with tempfile.TemporaryDirectory() as d:
            a = cardlib.new_card(d, "first")
            b = cardlib.new_card(d, "second", want_id=7)
            c = cardlib.new_card(d, "third", want_id=7)  # 7 taken → next free
            self.assertEqual([a["id"], b["id"]], [1, 7])
            self.assertEqual(c["id"], 8)
            self.assertEqual([x["id"] for x in cardlib.load(d)], [1, 7, 8])

    def test_done_and_archived_ids_stay_claimed(self):
        with tempfile.TemporaryDirectory() as d:
            a = cardlib.new_card(d, "ship me", want_id=3)
            cardlib.retire(a, d, "done", status="done")
            self.assertTrue(os.path.exists(a["_path"]))
            self.assertEqual(cardlib.load(d), [])
            self.assertEqual(cardlib.load(d, "done")[0]["name"], "ship me")
            self.assertEqual(cardlib.new_card(d, "next")["id"], 4)

    def test_find_task_exact_one_id_only(self):
        with tempfile.TemporaryDirectory() as d:
            cardlib.new_card(d, "a", task_id="3")
            cardlib.new_card(d, "b", task_id="6 规格 · 7 build")
            cards = cardlib.load(d)
            self.assertEqual(cardlib.find_task(cards, "3")["name"], "a")
            self.assertIsNone(cardlib.find_task(cards, "7"))
            self.assertIsNone(cardlib.find_task(cards, "30"))

    def test_set_fields_rewrites_atomically(self):
        with tempfile.TemporaryDirectory() as d:
            a = cardlib.new_card(d, "a", task_id="3")
            cardlib.set_fields(a, status="doing", dept="RnD")
            got = cardlib.load(d)[0]
            self.assertEqual((got["status"], got["dept"]), ("doing", "RnD"))

    def test_non_card_files_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            cardlib.new_card(d, "real")
            for fn in ("Board.base", "notes.md", "9-broken.md"):
                open(os.path.join(d, fn), "w").write("no frontmatter")
            self.assertEqual(len(cardlib.load(d)), 1)


class Migration(unittest.TestCase):
    def test_migrates_legacy_board(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _proj(d)
            bdir, notice = cardlib.ensure_store(d, cfg)
            self.assertIn("migrated", notice)
            cards = cardlib.load(bdir)
            self.assertEqual([c["id"] for c in cards], [130, 131])
            c130 = cards[0]
            self.assertEqual(c130["name"], "REDEEM-MODAL — X close missing")
            self.assertEqual(c130["task_id"], "3")
            self.assertIn("dept prose line", c130["_body"])
            self.assertEqual(cards[1]["task_id"], "6 规格 · 7 build")  # preserved verbatim
            # tombstone went to archive/, wearing its own number
            arch = cardlib.load(bdir, "archive")
            self.assertEqual([c["id"] for c in arch], [7])

    def test_digest_after_migration_keeps_shipped_and_notes(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _proj(d)
            cardlib.ensure_store(d, cfg)
            text = open(os.path.join(d, "docs", "TaskBoard.md"), encoding="utf-8").read()
            self.assertIn("board notes the digest must keep", text)
            self.assertIn("older ship · abc1234", text)
            self.assertIn("### #130 · REDEEM-MODAL — X close missing", text)
            self.assertIn("GENERATED SECTION", text)
            self.assertNotIn("~~#7", text)  # tombstone no longer on the digest

    def test_prestaged_dir_never_blocks_migration(self):
        # a board dir holding only non-card files (Board.base, an Obsidian-created
        # folder) is NOT a live store — the legacy board must still migrate into it
        with tempfile.TemporaryDirectory() as d:
            cfg = _proj(d)
            bdir = os.path.join(d, "docs", "board")
            os.makedirs(bdir)
            open(os.path.join(bdir, "Board.base"), "w").write("views: []\n")
            bdir2, notice = cardlib.ensure_store(d, cfg)
            self.assertIn("migrated", notice)
            self.assertEqual([c["id"] for c in cardlib.load(bdir2)], [130, 131])
            self.assertEqual([c["id"] for c in cardlib.load(bdir2, "archive")], [7])
            self.assertTrue(os.path.exists(os.path.join(bdir, "Board.base")))  # kept

    def test_existing_store_untouched_and_empty_project_ok(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _proj(d)
            bdir, _ = cardlib.ensure_store(d, cfg)
            n = len(os.listdir(bdir))
            bdir2, notice = cardlib.ensure_store(d, cfg)
            self.assertEqual((bdir2, notice), (bdir, None))
            self.assertEqual(len(os.listdir(bdir)), n)
        with tempfile.TemporaryDirectory() as d:
            cfg = _proj(d, board_md=None)
            bdir, notice = cardlib.ensure_store(d, cfg)
            self.assertTrue(os.path.isdir(bdir))
            self.assertIsNone(notice)


class Digest(unittest.TestCase):
    def test_regen_replaces_only_active(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _proj(d)
            bdir, _ = cardlib.ensure_store(d, cfg)
            card = cardlib.find_task(cardlib.load(bdir), "3")
            cardlib.set_fields(card, status="doing")
            cardlib.regen_digest(d, cfg)
            text = open(os.path.join(d, "docs", "TaskBoard.md"), encoding="utf-8").read()
            self.assertIn("- **status:** doing", text)
            self.assertIn("older ship · abc1234", text)
            self.assertIn("# demo · TaskBoard", text)

    def test_regen_without_digest_creates_one(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _proj(d, board_md=None)
            bdir, _ = cardlib.ensure_store(d, cfg)
            cardlib.new_card(bdir, "fresh", task_id="1")
            cardlib.regen_digest(d, cfg)
            text = open(os.path.join(d, "docs", "TaskBoard.md"), encoding="utf-8").read()
            self.assertIn("### #1 · fresh", text)
            self.assertIn("SHIPPED:START", text)

    def test_digest_stale_tracks_card_mtime(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _proj(d)
            bdir, _ = cardlib.ensure_store(d, cfg)
            cardlib.regen_digest(d, cfg)
            self.assertFalse(cardlib.digest_stale(d, cfg))
            card = cardlib.load(bdir)[0]
            cardlib.set_fields(card, status="blocked")
            os.utime(card["_path"], (os.path.getmtime(card["_path"]) + 5,) * 2)
            self.assertTrue(cardlib.digest_stale(d, cfg))


if __name__ == "__main__":
    unittest.main()
