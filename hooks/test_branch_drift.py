"""Tests for stop_branch_drift.py — the 分公司 branch-drift sentinel.
Run: python3 hooks/test_branch_drift.py"""
import os, io, sys, json, time, shutil, tempfile, subprocess, unittest, contextlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stop_branch_drift as drift

GIT = shutil.which("git")
HOUR = 3600


def _write(path, text="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _git(cwd, *args, when=None):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    if when is not None:                     # backdate BOTH: %ct reads the committer date
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = "%d +0000" % int(when)
    return subprocess.run([GIT, "-C", cwd] + list(args), check=True, env=env,
                          capture_output=True, text=True).stdout.strip()


def _commit(repo, name, text="x", when=None):
    _write(os.path.join(repo, name), text)
    _git(repo, "add", name)
    _git(repo, "commit", "-qm", "c-" + name, when=when)


def _cfg(root, active=True, **thresholds):
    _write(os.path.join(root, ".claude", "orchestrate.json"),
           json.dumps({"active": active, "external": ["Marketing"],
                       "thresholds": thresholds}))


def _nudge(cwd):
    """(returned_value, stderr_text) — run() is advisory and must always return None."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        ret = drift.run({"cwd": cwd}, None)
    return ret, err.getvalue()


@unittest.skipIf(not GIT, "git not available")
class BranchDrift(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.main = os.path.realpath(self.tmp)
        subprocess.run([GIT, "init", "-q", self.main], check=True)
        _commit(self.main, "README")
        _cfg(self.main)                      # marker in MAIN only (the untracked reality)
        self.ref = _git(self.main, "rev-parse", "--abbrev-ref", "HEAD")
        self.wt = os.path.join(self.main, ".claude", "worktrees", "Marketing")
        _git(self.main, "worktree", "add", "-q", "-b", "branch/Marketing", self.wt)
        _write(os.path.join(self.wt, ".claude", "office.json"),
               json.dumps({"office": "Marketing"}))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- gating -----------------------------------------------------------------
    def test_main_office_never_hears_it(self):
        """No office.json = the CEO. Its own drain duty is the branch's, not theirs."""
        self.assertEqual(_nudge(self.main), (None, ""))

    def test_branch_office_outside_a_worktree_is_silent(self):
        """An office running in the main checkout has no branch to drift from."""
        _write(os.path.join(self.main, ".claude", "office.json"),
               json.dumps({"office": "Marketing"}))
        self.assertEqual(_nudge(self.main)[1], "")

    def test_inactive_project_is_silent(self):
        _cfg(self.main, active=False)
        _commit(self.wt, "old.md", when=time.time() - 80 * HOUR)
        self.assertEqual(_nudge(self.wt)[1], "")

    def test_fresh_worktree_is_silent(self):
        self.assertEqual(_nudge(self.wt), (None, ""))

    # ---- 未合并 (held work) -------------------------------------------------------
    def test_commit_held_past_the_dial_is_flagged(self):
        _commit(self.wt, "a.md", when=time.time() - 50 * HOUR)
        ret, err = _nudge(self.wt)
        self.assertIsNone(ret)               # advisory: never blocks the turn
        self.assertIn("未合并", err)
        self.assertIn("1 commit held", err)
        self.assertIn("50h", err)
        self.assertIn("branch/Marketing", err)
        self.assertIn(self.ref, err)

    def test_fresh_commit_is_not_flagged(self):
        _commit(self.wt, "a.md")
        self.assertEqual(_nudge(self.wt)[1], "")

    def test_age_is_the_oldest_held_commit_not_the_newest(self):
        """A branch that keeps committing must not look fresh: the strand is the OLDEST
        commit still unmerged, which is what left the signed correction on the branch."""
        _commit(self.wt, "a.md", when=time.time() - 60 * HOUR)
        _commit(self.wt, "b.md")             # now
        ret, err = _nudge(self.wt)
        self.assertIn("2 commits held", err)
        self.assertIn("60h", err)

    def test_behind_only_never_reports_held_work(self):
        """Guards the rev-list orientation: `A...HEAD` left-counts BEHIND and right-counts
        AHEAD. Swapped, a fully drained branch reports as the worst offender."""
        _commit(self.main, "m1.md", when=time.time() - 90 * HOUR)
        ret, err = _nudge(self.wt)
        self.assertNotIn("未合并", err)

    # ---- 落后 (stale shared state) ------------------------------------------------
    def test_behind_past_the_dial_is_flagged(self):
        for i in range(10):
            _commit(self.main, "m%d.md" % i)
        ret, err = _nudge(self.wt)
        self.assertIn("落后", err)
        self.assertIn("10 commits behind", err)
        self.assertIn("card store", err)     # says WHY behind matters, not just that it is

    def test_slightly_behind_is_normal_and_silent(self):
        _commit(self.main, "m1.md")
        self.assertEqual(_nudge(self.wt)[1], "")

    def test_behind_dial_is_configurable(self):
        _cfg(self.main, branch_behind_commits=1)
        _commit(self.main, "m1.md")
        self.assertIn("落后", _nudge(self.wt)[1])

    # ---- 未提交 (edits that exist nowhere else) -----------------------------------
    def test_stale_uncommitted_tracked_file_is_flagged(self):
        """An external dept's brief write-back sat uncommitted in the worktree for four days
        while the office read the un-written-back copy at main."""
        p = os.path.join(self.wt, "README")
        _write(p, "edited")
        old = time.time() - 96 * HOUR
        os.utime(p, (old, old))
        ret, err = _nudge(self.wt)
        self.assertIn("未提交", err)
        self.assertIn("1 tracked file", err)
        self.assertIn("96h", err)

    def test_untracked_office_state_never_fires(self):
        """The money test for noise: office.json and the nudge-state files are untracked
        by nature and permanent. Counting `??` would nudge every session forever."""
        p = os.path.join(self.wt, ".claude", "office.json")
        old = time.time() - 500 * HOUR
        os.utime(p, (old, old))
        _write(os.path.join(self.wt, ".claude", "mail-nudge-state"), "sig")
        q = os.path.join(self.wt, ".claude", "mail-nudge-state")
        os.utime(q, (old, old))
        self.assertEqual(_nudge(self.wt)[1], "")

    def test_freshly_edited_file_is_silent(self):
        _write(os.path.join(self.wt, "README"), "edited")
        self.assertEqual(_nudge(self.wt)[1], "")

    def test_drain_dial_covers_uncommitted_too(self):
        _cfg(self.main, branch_drain_hours=1)
        p = os.path.join(self.wt, "README")
        _write(p, "edited")
        old = time.time() - 2 * HOUR
        os.utime(p, (old, old))
        self.assertIn("未提交", _nudge(self.wt)[1])

    # ---- one nudge per state ------------------------------------------------------
    def test_same_trigger_set_is_said_once(self):
        _commit(self.wt, "a.md", when=time.time() - 50 * HOUR)
        self.assertIn("未合并", _nudge(self.wt)[1])
        self.assertEqual(_nudge(self.wt)[1], "")          # no nagging every turn

    def test_more_commits_do_not_re_nudge(self):
        """Signature hashes the trigger KINDS, not the counts — keyed on counts every new
        commit would be a fresh 'state' and it would fire every turn (0.9.60's lesson)."""
        _commit(self.wt, "a.md", when=time.time() - 50 * HOUR)
        self.assertIn("未合并", _nudge(self.wt)[1])
        _commit(self.wt, "b.md", when=time.time() - 40 * HOUR)
        self.assertEqual(_nudge(self.wt)[1], "")

    def test_a_new_kind_of_drift_speaks_again(self):
        _commit(self.wt, "a.md", when=time.time() - 50 * HOUR)
        self.assertIn("未合并", _nudge(self.wt)[1])
        for i in range(10):
            _commit(self.main, "m%d.md" % i)
        err = _nudge(self.wt)[1]
        self.assertIn("落后", err)
        self.assertIn("未合并", err)                       # both states, one nudge

    def test_draining_clears_the_memory(self):
        _commit(self.wt, "a.md", when=time.time() - 50 * HOUR)
        self.assertIn("未合并", _nudge(self.wt)[1])
        _git(self.main, "merge", "--no-ff", "-q", "-m", "drain", "branch/Marketing")
        _git(self.wt, "merge", "--ff-only", "-q", self.ref)
        self.assertEqual(_nudge(self.wt)[1], "")          # drained: nothing to say
        _commit(self.wt, "b.md", when=time.time() - 50 * HOUR)
        self.assertIn("未合并", _nudge(self.wt)[1])        # and it speaks for the next one

    # ---- units -------------------------------------------------------------------
    def test_uncommitted_excludes_untracked_counts_tracked(self):
        _write(os.path.join(self.wt, "brand.md"))         # untracked
        _write(os.path.join(self.wt, "README"), "edited")  # tracked, modified
        n, oldest = drift.uncommitted(self.wt)
        self.assertEqual(n, 1)
        self.assertIsNotNone(oldest)

    def test_cjk_path_keeps_its_clock(self):
        """git octal-escapes non-ASCII paths by default, so the clock resolved to None and
        the trigger silently never fired — on an org whose paths are nearly all CJK."""
        _commit(self.wt, "文章2-指南.md")
        p = os.path.join(self.wt, "文章2-指南.md")
        _write(p, "edited")
        old = time.time() - 96 * HOUR
        os.utime(p, (old, old))
        n, oldest = drift.uncommitted(self.wt)
        self.assertEqual(n, 1)
        self.assertIsNotNone(oldest)
        self.assertGreater(oldest, 90)

    def test_deleted_tracked_file_counts_without_a_clock(self):
        os.remove(os.path.join(self.wt, "README"))
        n, _ = drift.uncommitted(self.wt)
        self.assertEqual(n, 1)

    def test_git_failure_is_fail_open(self):
        with tempfile.TemporaryDirectory() as bare:
            self.assertEqual(drift._git(bare, "rev-list", "--count", "HEAD"), "")
            self.assertIsNone(drift._counts(bare, "master"))
            self.assertEqual(drift.findings(bare, "master", 24, 10), [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
