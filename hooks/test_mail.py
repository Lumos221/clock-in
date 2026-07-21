"""Tests for stop_mail.py — the 分公司 mail-lane nudge: unread mail addressed to
this office nudges once per unread-set; identity from .claude/office.json (absent
→ CEO, with aliases); other offices' mail never nudges here.
Run: python3 hooks/test_mail.py"""
import os, sys, json, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stop_mail as sm

MAIL = """---
from: Marketing
to: %s
re: "#141"
status: %s
---

Listing copy draft is up — need the feature list confirmed.
"""


def _proj(d):
    os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
    with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
        f.write('{"active":true,"external":["Marketing"]}')
    md = os.path.join(d, "docs", "board", "mail")
    os.makedirs(md)
    return md


def _mail(md, fn, to="CEO", status="unread"):
    with open(os.path.join(md, fn), "w", encoding="utf-8") as f:
        f.write(MAIL % (to, status))


class MailNudge(unittest.TestCase):
    def test_unread_ceo_mail_nudges_once_per_set(self):
        with tempfile.TemporaryDirectory() as d:
            md = _proj(d)
            _mail(md, "20260720-1010-marketing-launch.md")
            out = sm.run({"cwd": d, "hook_event_name": "Stop"}, None)
            self.assertIn("1 unread for CEO", out)
            self.assertIn("Marketing", out)
            # same set → silent; a NEW mail re-arms
            self.assertIsNone(sm.run({"cwd": d, "hook_event_name": "Stop"}, None))
            _mail(md, "20260720-1130-marketing-more.md")
            self.assertIn("2 unread", sm.run({"cwd": d, "hook_event_name": "Stop"}, None))

    def test_read_flip_disarms(self):
        with tempfile.TemporaryDirectory() as d:
            md = _proj(d)
            _mail(md, "a.md")
            self.assertIsNotNone(sm.run({"cwd": d, "hook_event_name": "Stop"}, None))
            _mail(md, "a.md", status="read")
            self.assertIsNone(sm.run({"cwd": d, "hook_event_name": "Stop"}, None))

    def test_branch_office_sees_only_its_mail(self):
        with tempfile.TemporaryDirectory() as d:
            md = _proj(d)
            with open(os.path.join(d, ".claude", "office.json"), "w") as f:
                f.write('{"office": "Marketing"}')
            _mail(md, "for-ceo.md", to="Boss")           # CEO alias — not Marketing's
            self.assertIsNone(sm.run({"cwd": d, "hook_event_name": "Stop"}, None))
            _mail(md, "for-mkt.md", to="Marketing")
            out = sm.run({"cwd": d, "hook_event_name": "Stop"}, None)
            self.assertIn("for Marketing", out)
            self.assertIn("for-mkt.md", out)
            self.assertNotIn("for-ceo.md", out)

    def test_dead_letter_nags_the_postmaster_only(self):
        # field case 2026-07-20: a dept report file-dropped without frontmatter sat
        # invisible — empty columns in Bases, no nudge ever. The CEO office now
        # hears about it; branch offices don't (not their mailroom).
        with tempfile.TemporaryDirectory() as d:
            md = _proj(d)
            with open(os.path.join(md, "20260720-Frontend-172-leg1-report.md"), "w") as f:
                f.write("# raw report, no frontmatter\n")
            out = sm.run({"cwd": d, "hook_event_name": "Stop"}, None)
            self.assertIn("DEAD letter", out)
            self.assertIn("Frontend-172-leg1-report", out)
            # same state → silent; fixing the letter disarms
            self.assertIsNone(sm.run({"cwd": d, "hook_event_name": "Stop"}, None))
        with tempfile.TemporaryDirectory() as d:
            md = _proj(d)
            with open(os.path.join(d, ".claude", "office.json"), "w") as f:
                f.write('{"office": "Marketing"}')
            with open(os.path.join(md, "dead.md"), "w") as f:
                f.write("# no frontmatter\n")
            self.assertIsNone(sm.run({"cwd": d, "hook_event_name": "Stop"}, None))

    def test_inactive_or_no_mail_dir_silent(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".claude"))
            with open(os.path.join(d, ".claude", "orchestrate.json"), "w") as f:
                f.write('{"active":true}')
            self.assertIsNone(sm.run({"cwd": d, "hook_event_name": "Stop"}, None))


class BackfillTime(unittest.TestCase):
    """0.9.43: senders drifted off writing time: within a day — the sweep fills it
    from the filename stamp (or the file clock when the name lacks HHMM)."""

    def test_filename_stamp_wins_and_value_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            md = _proj(d)
            _mail(md, "20260721-1335-Marketing-208v11.md")
            with open(os.path.join(md, "20260720-1845-CEO-ack.md"), "w", encoding="utf-8") as f:
                f.write('---\nfrom: CEO\nto: Marketing\ntime: "2026-07-20 18:45"\nstatus: read\n---\nx\n')
            n = sm.backfill_time(md)
            self.assertEqual(n, 1)
            import cardlib
            fm = cardlib.frontmatter(open(os.path.join(md, "20260721-1335-Marketing-208v11.md"),
                                          encoding="utf-8").read())
            self.assertEqual(fm["time"], "2026-07-21 13:35")
            fm2 = cardlib.frontmatter(open(os.path.join(md, "20260720-1845-CEO-ack.md"),
                                           encoding="utf-8").read())
            self.assertEqual(fm2["time"], "2026-07-20 18:45")  # sender's value kept
            self.assertEqual(sm.backfill_time(md), 0)  # idempotent

    def test_date_only_filename_uses_file_clock_and_dead_letters_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            md = _proj(d)
            _mail(md, "20260721-CEO-208ack.md")  # the CEO's HHMM-less naming habit
            path = os.path.join(md, "20260721-CEO-208ack.md")
            os.utime(path, (1784600000,) * 2)
            with open(os.path.join(md, "notes.md"), "w", encoding="utf-8") as f:
                f.write("plain markdown, no fence\n")
            sm.backfill_time(md)
            import cardlib
            t = cardlib.frontmatter(open(path, encoding="utf-8").read())["time"]
            self.assertTrue(t.startswith("2026-07-21 "))
            self.assertRegex(t, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
            self.assertEqual(open(os.path.join(md, "notes.md"), encoding="utf-8").read(),
                             "plain markdown, no fence\n")  # dead letter: postmaster's lane


if __name__ == "__main__":
    unittest.main()
