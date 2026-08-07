"""Tests for cardlib.py — the per-card board store: frontmatter round-trips,
durable-id minting, lazy migration off a legacy TaskBoard.md, digest surgery.
Run: python3 hooks/test_cardlib.py"""
import os, re, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cardlib

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The card's fields are defined in exactly one file. If a second one starts naming levels
# again, add it here — two definitions is the shape the P3 bug came in.
PRIORITY_DOCS = ("skills/orchestrate/reference/task-widget.md",)

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


class CanonicalStatus(unittest.TestCase):
    def test_first_keyword_wins(self):
        self.assertEqual(cardlib.canonical_status("review — waiting on the Auditor"), "review")
        self.assertEqual(cardlib.canonical_status("blocked on #3 · #7"), "blocked")
        self.assertEqual(cardlib.canonical_status("doing"), "doing")

    def test_ship_and_start_speak_synonyms(self):
        self.assertEqual(cardlib.canonical_status(
            "MERGED 07-20 — L2 PASS Frontend.check760.1.pass, FF ce66fd02"), "done")
        self.assertEqual(cardlib.canonical_status("COMPLETE — all three legs landed"), "done")
        self.assertEqual(cardlib.canonical_status("active — Boss ordered the rewrite"), "doing")
        self.assertEqual(cardlib.canonical_status("parked — after the bug lane"), "todo")
        self.assertEqual(cardlib.canonical_status("pending L2 pass"), "todo")  # appearance order

    def test_unset_left_alone_and_unknown_prose_is_todo(self):
        self.assertIsNone(cardlib.canonical_status(""))
        self.assertIsNone(cardlib.canonical_status("—"))
        self.assertIsNone(cardlib.canonical_status("<CEO fills>"))
        self.assertEqual(cardlib.canonical_status("boss said hold"), "todo")


class Canonicalise(unittest.TestCase):
    def test_essay_collapses_and_note_keeps_original(self):
        """Status IS translated, because leaving prose there has a cost of its own —
        the digest finds no keyword and misfiles the card. Priority has no such cost,
        so the untranslatable half is left standing (see FieldFaults)."""
        with tempfile.TemporaryDirectory() as d:
            cardlib.new_card(d, "X", status="MERGED 07-20 — L2 PASS a.1.pass",
                             priority="high", body="dept prose stays.\n")
            traces = cardlib.canonicalise(d, stamp="2026-07-20")
            self.assertEqual(len(traces), 1)
            card = cardlib.load(d)[0]
            self.assertEqual(card["status"], "done")
            self.assertEqual(card["priority"], "high")
            self.assertIn("dept prose stays.", card["_body"])
            self.assertIn("状态注 2026-07-20", card["_body"])
            self.assertIn('status was "MERGED 07-20 — L2 PASS a.1.pass"', card["_body"])

    def test_P3_is_a_level_the_doctrine_hands_out_and_must_survive(self):
        """The dispatch rule says P0-urgent · P1-critical · P2-important · P3-nice-to-have.
        The sweep allowed P0–P2, so a CEO writing exactly what it was told to write had it
        erased hours later, silently — nine cards on one live board, one of them a level the
        Boss had ruled by name and written into the card's own title."""
        with tempfile.TemporaryDirectory() as d:
            cardlib.new_card(d, "X", status="todo", priority="P3")
            self.assertEqual(cardlib.canonicalise(d), [])
            self.assertEqual(cardlib.load(d)[0]["priority"], "P3")

    def test_a_level_with_its_reason_attached_keeps_the_level(self):
        """`P0 (process-debt closure — …)` is a card marked P0 by someone who also wrote
        down why. Wiping the whole field for the parenthesis DEMOTED it to unset, which is
        the one outcome nobody intended. The prose still moves to the note, because the
        panel matches the field exactly and would not read a level with a tail."""
        with tempfile.TemporaryDirectory() as d:
            cardlib.new_card(d, "X", status="todo",
                             priority="P0 (process-debt closure — the recurring family)")
            self.assertEqual(len(cardlib.canonicalise(d, stamp="2026-08-06")), 1)
            card = cardlib.load(d)[0]
            self.assertEqual(card["priority"], "P0")
            self.assertIn("process-debt closure", card["_body"])
            self.assertEqual(cardlib.canonicalise(d), [])       # and it settles there

    def test_the_docs_and_the_sweep_name_exactly_the_same_levels(self):
        """The whole bug was a disagreement between a rule written for a reader and a
        regex written for the sweep: the doctrine handed out four levels, the sweep
        accepted three, and the gap was invisible until a card lost a level hours after
        it was set. Neither side can move alone now."""
        named = set()
        for rel in PRIORITY_DOCS:
            with open(os.path.join(REPO, rel), encoding="utf-8") as f:
                named |= set(re.findall(r"\bP([0-9])\b", f.read()))
        accepted = {n for n in "0123456789" if cardlib.PRIORITY_RE.match("P" + n)}
        self.assertEqual(named, accepted)

    def test_an_invented_level_is_left_alone_for_its_author(self):
        """`low` is what gets written when nothing named the vocabulary and nothing
        checked. It carries no order, so no level can be recovered from it — and that is
        precisely why the sweep must not touch it. Clearing it was this code deciding the
        card was meant to be unprioritised, which it has no way to know: `low` says the
        opposite of `—`, and the same rule demoted a card whose level merely carried its
        reason. It is reported instead, to the one desk that can say what was meant."""
        with tempfile.TemporaryDirectory() as d:
            cardlib.new_card(d, "X", status="todo", priority="low")
            self.assertEqual(cardlib.canonicalise(d), [])
            self.assertEqual(cardlib.load(d)[0]["priority"], "low")

    def test_idempotent_no_rewrite_churn(self):
        with tempfile.TemporaryDirectory() as d:
            cardlib.new_card(d, "X", status="doing", priority="P1")
            self.assertEqual(cardlib.canonicalise(d), [])
            cardlib.new_card(d, "Y", status="active — go")
            self.assertEqual(len(cardlib.canonicalise(d)), 1)
            self.assertEqual(cardlib.canonicalise(d), [])  # second pass finds canon


class FieldFaults(unittest.TestCase):
    """Report, don't repair. The sweep runs at session start and turn end, so what it
    found used to be a rewrite in a session that had already ended, with the evidence in
    a log file nothing opens."""

    def test_it_names_the_card_the_field_and_the_value(self):
        with tempfile.TemporaryDirectory() as d:
            cardlib.new_card(d, "X", status="todo", priority="low")
            self.assertEqual(cardlib.field_faults(d), [(1, "priority", "low")])

    def test_a_legal_level_and_an_empty_one_are_not_faults(self):
        with tempfile.TemporaryDirectory() as d:
            for n, pr in (("A", "P0"), ("B", "P3"), ("C", ""), ("D", "P1 (queued)")):
                cardlib.new_card(d, n, status="todo", priority=pr)
            self.assertEqual(cardlib.field_faults(d), [])

    def test_a_finished_card_is_not_worth_anyone_going_back_for(self):
        with tempfile.TemporaryDirectory() as d:
            cardlib.new_card(d, "X", status="done", priority="low")
            self.assertEqual(cardlib.field_faults(d), [])


class DedupeIds(unittest.TestCase):
    def _forge(self, d, cid, name, **fields):
        """A hand-written collision: same id, different slug — the path new_card's
        O_EXCL can't guard."""
        meta = {"id": cid, "name": name}
        meta.update(fields)
        path = os.path.join(d, "%d-%s.md" % (cid, cardlib.slugify(name)))
        with open(path, "w", encoding="utf-8") as f:
            f.write(cardlib.render_card(meta))
        return path

    def test_younger_holder_renumbered_with_note(self):
        with tempfile.TemporaryDirectory() as d:
            elder = cardlib.new_card(d, "ELDER", status="doing")
            younger = self._forge(d, 1, "YOUNGER", status="todo")
            os.utime(elder["_path"], (os.path.getmtime(younger) - 10,) * 2)
            traces = cardlib.dedupe_ids(d, stamp="2026-07-20")
            self.assertEqual(len(traces), 1)
            cards = cardlib.load(d)
            self.assertEqual([c["id"] for c in cards], [1, 2])
            self.assertEqual(cards[0]["name"], "ELDER")  # eldest keeps the number
            moved = cards[1]
            self.assertEqual(moved["name"], "YOUNGER")
            self.assertTrue(os.path.basename(moved["_path"]).startswith("2-"))
            self.assertIn("编号注 2026-07-20", moved["_body"])
            self.assertFalse(os.path.exists(younger))
            self.assertEqual(cardlib.dedupe_ids(d), [])  # idempotent

    def test_done_numbers_count_and_next_free_is_global(self):
        with tempfile.TemporaryDirectory() as d:
            done = os.path.join(d, "done")
            os.makedirs(done)
            self._forge(done, 5, "SHIPPED-EARLIER", status="done")
            a = cardlib.new_card(d, "FIRST", status="doing")   # mints 6
            younger = self._forge(d, 6, "SECOND", status="todo")
            os.utime(a["_path"], (os.path.getmtime(younger) - 10,) * 2)
            cardlib.dedupe_ids(d)
            ids = sorted(c["id"] for c in cardlib.load(d)) + \
                [c["id"] for c in cardlib.load(d, "done")]
            self.assertEqual(sorted(ids), [5, 6, 7])

    def test_done_holder_keeps_number_over_elder_active(self):
        # retirement rewrites the file, so a done card's mtime lies about its age;
        # its number is frozen in BACKLOG history — the active twin must move
        # (the 07-20 #190 DIFF-vs-ghost incident)
        with tempfile.TemporaryDirectory() as d:
            done = os.path.join(d, "done")
            os.makedirs(done)
            shipped = self._forge(done, 3, "SHIPPED", status="done")
            ghost = self._forge(d, 3, "GHOST", status="todo")
            os.utime(ghost, (os.path.getmtime(shipped) - 100,) * 2)  # ghost born first
            cardlib.dedupe_ids(d)
            self.assertEqual(cardlib.load(d, "done")[0]["id"], 3)
            self.assertEqual(cardlib.load(d)[0]["id"], 4)


class SinceStamp(unittest.TestCase):
    """`since` = when a card entered its CURRENT status, so the panel can say
    "22h in 审查" instead of "22h since this file was last written" — the file clock
    is reset by any touch (a hygiene sweep, a digest regen) and answered the wrong
    question entirely."""

    def _card(self, d, cid, **fields):
        return cardlib.new_card(d, "T%d" % cid, want_id=cid, **fields)

    def test_new_card_is_born_stamped(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._card(d, 1)
            self.assertRegex(c["since"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")

    def test_status_change_through_the_write_path_restamps(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._card(d, 1)
            cardlib.set_fields(c, since="2026-07-01T09:00", status="todo")
            cardlib.set_fields(c, status="review")           # a real transition
            self.assertNotEqual(c["since"], "2026-07-01T09:00")
            born = c["since"]
            cardlib.set_fields(c, priority="P0")             # not a transition
            self.assertEqual(c["since"], born)

    def test_sweep_catches_a_hand_edit_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            st = os.path.join(d, "since-state.json")
            c = self._card(d, 1)
            cardlib.stamp_since(d, st)                       # first sight: records status
            self.assertEqual(cardlib.stamp_since(d, st), [])  # nothing changed
            # a dept edits its own card file directly — no hook involved
            txt = open(c["_path"], encoding="utf-8").read().replace("status: todo", "status: doing")
            open(c["_path"], "w", encoding="utf-8").write(txt)
            traces = cardlib.stamp_since(d, st, now="2026-07-25T12:00")
            self.assertEqual(len(traces), 1)
            self.assertEqual(cardlib.load(d)[0]["since"], "2026-07-25T12:00")
            self.assertEqual(cardlib.stamp_since(d, st), [])  # settled again

    def test_legacy_card_backfills_from_its_file_clock_not_from_now(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._card(d, 1)
            cardlib.set_fields(c, since="")                  # a card from before the field
            old = 1750000000                                 # 2025-06-15-ish
            os.utime(c["_path"], (old, old))
            cardlib.stamp_since(d, os.path.join(d, "s.json"), now="2026-07-25T12:00")
            self.assertTrue(cardlib.load(d)[0]["since"].startswith("2025-"))


class RetirementSurrendersThePlatformId(unittest.TestCase):
    """Platform ids are small integers the platform restarts every session, so a
    retired card that keeps one still answers to an id the platform will hand out
    again. Months of those make every id-keyed path ambiguous: find_task returns
    whichever holder it reached first, so a completion stamps the wrong card and a
    review marker written for a long-dead card attaches to whatever wears its number
    today. Field state when found: ~100 duplicated ids in one store, 14 shared between
    a LIVE card and a retired one."""

    def test_retire_clears_task_id(self):
        with tempfile.TemporaryDirectory() as d:
            c = cardlib.new_card(d, "a card", want_id=7, task_id="115")
            self.assertEqual(cardlib.clean(c.get("task_id")), "115")
            cardlib.retire(c, d, "done", status="done", shipped="2026-08-05")
            done = cardlib.load(d, "done")
            self.assertEqual(len(done), 1)
            self.assertEqual(cardlib.clean(done[0].get("task_id", "")), "")
            self.assertEqual(done[0]["id"], 7)          # the DURABLE id is untouched
            self.assertEqual(done[0].get("status"), "done")

    def test_an_explicit_task_id_on_the_call_still_wins(self):
        """setdefault, not an override — a caller that means to record one can."""
        with tempfile.TemporaryDirectory() as d:
            c = cardlib.new_card(d, "b card", want_id=8, task_id="9")
            cardlib.retire(c, d, "archive", status="cancelled", task_id="9")
            self.assertEqual(cardlib.clean(cardlib.load(d, "archive")[0]["task_id"]), "9")

    def test_find_task_is_ambiguous_when_two_cards_wear_one_id(self):
        """The failure this prevents, stated as a test: with a retired holder left in
        place, a lookup for the id can reach the wrong card."""
        with tempfile.TemporaryDirectory() as d:
            old = cardlib.new_card(d, "old card", want_id=411, task_id="115")
            cardlib.retire(old, d, "done", status="done", task_id="115")   # the old way
            new = cardlib.new_card(d, "new card", want_id=1068, task_id="115")
            both = cardlib.load(d) + cardlib.load(d, "done")
            self.assertEqual(len([c for c in both
                                  if cardlib.clean(c.get("task_id", "")) == "115"]), 2)
            self.assertIsNotNone(cardlib.find_task(both, "115"))   # returns ONE of them


if __name__ == "__main__":
    unittest.main()
