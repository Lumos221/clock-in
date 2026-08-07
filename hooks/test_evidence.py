"""Tests for patch-id review evidence — a verdict bound to the change it judged
rather than to a clock. Run: python3 hooks/test_evidence.py"""
import os, sys, time, shutil, tempfile, subprocess, unittest
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
import board

GIT = shutil.which("git")


def _run(d, *a, **kw):
    return subprocess.run([GIT, "-C", d] + list(a), capture_output=True, text=True,
                          env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"),
                          **kw).stdout.strip()


def _commit(d, name, body):
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        f.write(body)
    _run(d, "add", name)
    _run(d, "commit", "-qm", "c-" + name)
    return _run(d, "rev-parse", "HEAD")


def _marker(root, name, text, hours_ago=0):
    p = os.path.join(root, "docs", "reviews", name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    if hours_ago:
        t = time.time() - hours_ago * 3600
        os.utime(p, (t, t))
    return p


@unittest.skipIf(not GIT, "git not available")
class Evidence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.d = os.path.realpath(self.tmp)
        subprocess.run([GIT, "init", "-q", self.d], check=True)
        _commit(self.d, "README", "base\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_marker_evidence_reads_the_recorded_lines(self):
        p = _marker(self.d, "Ops.5.1.pass",
                    "PASS\nsha: abc1234\npatch-id: deadbeef1234\nreasons: fine\n")
        ev = board.marker_evidence(p)
        self.assertEqual(ev["sha"], "abc1234")
        self.assertEqual(ev["patch-id"], "deadbeef1234")

    def test_a_marker_with_no_evidence_reads_as_empty(self):
        p = _marker(self.d, "Ops.5.1.pass", "PASS — looks good\n")
        self.assertEqual(board.marker_evidence(p), {})

    def test_patch_id_is_computed_for_a_real_commit(self):
        sha = _commit(self.d, "a.txt", "hello\n")
        self.assertRegex(board.patch_id_of(self.d, sha), r"^[0-9a-f]{40}$")

    def test_patch_id_survives_a_rebase(self):
        """The whole point: the same change carried onto a new base keeps its identity,
        so a review of it stays valid through the rebase."""
        base = _run(self.d, "rev-parse", "HEAD")
        _run(self.d, "checkout", "-q", "-b", "feature")
        sha = _commit(self.d, "feature.txt", "work\n")
        before = board.patch_id_of(self.d, sha)
        _run(self.d, "checkout", "-q", "master") if _run(self.d, "branch", "--list", "master") \
            else _run(self.d, "checkout", "-q", "main")
        _commit(self.d, "other.txt", "unrelated\n")
        _run(self.d, "checkout", "-q", "feature")
        _run(self.d, "rebase", "-q", _run(self.d, "rev-parse", "HEAD~0") and "master")
        after = board.patch_id_of(self.d, _run(self.d, "rev-parse", "HEAD"))
        self.assertEqual(before, after)

    def test_evidence_holds_when_the_reviewed_commit_is_untouched(self):
        sha = _commit(self.d, "a.txt", "hello\n")
        ev = {"sha": sha, "patch-id": board.patch_id_of(self.d, sha)}
        self.assertIs(board.evidence_holds(self.d, ev), True)

    def test_evidence_holds_after_the_commit_is_rewritten(self):
        """Rebased, so the recorded sha is gone — but the change is still in the tree."""
        sha = _commit(self.d, "a.txt", "hello\n")
        pid = board.patch_id_of(self.d, sha)
        _run(self.d, "commit", "-q", "--amend", "-m", "reworded")
        ev = {"sha": sha, "patch-id": pid}
        self.assertIs(board.evidence_holds(self.d, ev), True)

    def test_evidence_fails_when_the_reviewed_change_is_not_in_the_repo(self):
        """Genuinely absent: the sha does not resolve AND the patch-id is nowhere."""
        _commit(self.d, "a.txt", "hello\n")
        ev = {"sha": "0" * 12, "patch-id": "0" * 40}
        self.assertIs(board.evidence_holds(self.d, ev), False)

    def test_a_pair_that_contradicts_itself_is_NO_evidence_not_absence(self):
        """The sha resolves and its patch-id is not the one recorded beside it. That is a
        marker whose evidence proves nothing — NOT a change that is gone, and answering
        the two the same way refused a finished card forever while reporting a stale
        clock, which sent the office hunting a bug that did not exist.

        It also cannot be read as absence without claiming to know WHICH field is wrong,
        and it does not: the reviewer transcribes both by hand, so the sha is as likely
        the slip as the patch-id. None = no usable evidence; the clock rule governs, the
        same fallback every marker written before this format already relies on."""
        sha = _commit(self.d, "a.txt", "hello\n")
        ev = {"sha": sha, "patch-id": "0" * 40}
        self.assertIsNone(board.evidence_holds(self.d, ev))

    def test_no_evidence_returns_none_so_the_caller_falls_back(self):
        """Every marker written before this format exists is in this state, so the
        fallback is the common path, not the exception."""
        self.assertIsNone(board.evidence_holds(self.d, {}))
        self.assertIsNone(board.evidence_holds(self.d, {"sha": "abc1234"}))


@unittest.skipIf(not GIT, "git not available")
class VerdictPrefersEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.d = os.path.realpath(self.tmp)
        subprocess.run([GIT, "init", "-q", self.d], check=True)
        _commit(self.d, "README", "base\n")
        self.sha = _commit(self.d, "work.txt", "the reviewed change\n")
        self.pid = board.patch_id_of(self.d, self.sha)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _stamp(self, hours_ago):
        return (datetime.now() - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M")

    def test_evidence_beats_a_clock_that_moved(self):
        """The field case: a genuine verdict written minutes before the card was edited
        for hygiene. With evidence recorded, the clock stops mattering at all.

        On a DURABLE `#NNN` match — which is where evidence is answering the only open
        question. See the pair below for why the same rescue is refused to a task_id."""
        _marker(self.d, "Ops.7.1.pass", "PASS\nsha: %s\npatch-id: %s\n" % (self.sha, self.pid),
                hours_ago=200)
        marks = board._review_markers(self.d)
        self.assertEqual(board.l2_verdict(marks, "7", "500", self._stamp(0), self.d), "pass")

    def test_evidence_does_NOT_rescue_a_recycled_task_id(self):
        """Six cards at `todo`, never dispatched, with no marker of their own anywhere,
        all reported 待合并 (field, 2026-08-05: ids 117/120/121/129/16/29). Their platform
        ids had belonged to other cards weeks earlier, those cards' reviews are still on
        disk, and the commits they name are still on master — so the evidence held, and
        held is all the rule asked for.

        Evidence answers FRESHNESS ("is the reviewed change still on offer"). A task_id
        match is a guess at IDENTITY, and the clock is what validates the guess; letting
        the freshness answer override it deleted the identity test. A guessed identity
        must clear the clock too."""
        _marker(self.d, "Ops.7.1.pass", "PASS\nsha: %s\npatch-id: %s\n" % (self.sha, self.pid),
                hours_ago=200)
        marks = board._review_markers(self.d)
        self.assertEqual(board.l2_verdict(marks, "500", "7", self._stamp(0), self.d), "")

    def test_a_task_id_match_still_survives_the_churn_it_was_written_for(self):
        """What the rescue was FOR: `since` re-stamps on every status edit, so a genuine
        verdict reads minutes older than the card it just judged. The recycle tolerance
        already absorbs that, and the two populations separate cleanly — the collisions
        are days out, the churn is minutes."""
        _marker(self.d, "Ops.7.1.pass", "PASS\nsha: %s\npatch-id: %s\n" % (self.sha, self.pid))
        marks = board._review_markers(self.d)
        self.assertEqual(board.l2_verdict(marks, "500", "7", self._stamp(0), self.d), "pass")

    def test_without_evidence_the_clock_rule_still_governs(self):
        _marker(self.d, "Ops.7.1.pass", "PASS — no evidence recorded\n", hours_ago=200)
        marks = board._review_markers(self.d)
        self.assertEqual(board.l2_verdict(marks, "500", "7", self._stamp(0), self.d), "")

    def test_evidence_naming_a_change_the_repo_does_not_have_refuses(self):
        """Stronger than the clock rule: a verdict about a change that is not on offer
        judges nothing here, however fresh its file is. Absent means BOTH halves miss —
        the sha does not resolve and the patch-id is nowhere."""
        _marker(self.d, "Ops.7.1.pass",
                "PASS\nsha: %s\npatch-id: %s\n" % ("0" * 12, "0" * 40))
        marks = board._review_markers(self.d)
        self.assertEqual(board.l2_verdict(marks, "500", "7", self._stamp(0), self.d), "")

    def test_a_self_contradicting_pair_falls_back_to_the_clock(self):
        """A fresh marker with an inconsistent pair still passes — it is the clock's call
        now, and the clock says this verdict is about this leg. An OLD one still fails,
        so the fallback is the ordinary rule and not an escape hatch."""
        _marker(self.d, "Ops.7.1.pass", "PASS\nsha: %s\npatch-id: %s\n" % (self.sha, "0" * 40))
        marks = board._review_markers(self.d)
        self.assertEqual(board.l2_verdict(marks, "500", "7", self._stamp(0), self.d), "pass")
        _marker(self.d, "Ops.7.1.pass", "PASS\nsha: %s\npatch-id: %s\n" % (self.sha, "0" * 40),
                hours_ago=200)
        marks = board._review_markers(self.d)
        self.assertEqual(board.l2_verdict(marks, "500", "7", self._stamp(0), self.d), "")

    def test_no_root_means_no_git_and_the_clock_rule_applies(self):
        _marker(self.d, "Ops.7.1.pass", "PASS\nsha: %s\npatch-id: %s\n" % (self.sha, self.pid),
                hours_ago=200)
        marks = board._review_markers(self.d)
        self.assertEqual(board.l2_verdict(marks, "500", "7", self._stamp(0)), "")


if __name__ == "__main__":
    unittest.main(verbosity=1)
