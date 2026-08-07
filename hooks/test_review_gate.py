"""Tests for pretool_review_gate.py — root resolution (esp. the worktree-invariant
git anchor) and the completion gate itself. Run: python3 hooks/test_review_gate.py"""
import os, sys, json, shutil, tempfile, subprocess, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pretool_review_gate as gate

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pretool_review_gate.py")
GIT = shutil.which("git")


def _run_gate(cwd, tool_name="TaskUpdate", status="completed", task_id="3"):
    """Invoke the hook as the harness would; return its exit code."""
    payload = {"cwd": cwd, "tool_name": tool_name,
               "tool_input": {"taskId": task_id, "status": status}}
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                       text=True, capture_output=True)
    return p.returncode


def _write(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _marker(root, active=True):
    _write(os.path.join(root, ".claude", "orchestrate.json"),
           json.dumps({"active": active}))


class WalkFallback(unittest.TestCase):
    def test_walk_finds_marker_from_subdir(self):
        with tempfile.TemporaryDirectory() as d:
            _marker(d)
            sub = os.path.join(d, "a", "b")
            os.makedirs(sub)
            self.assertEqual(os.path.realpath(gate._walk_root(sub)), os.path.realpath(d))

    def test_walk_returns_none_when_no_marker(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(gate._walk_root(d))


@unittest.skipIf(not GIT, "git not available")
class GitRootResolution(unittest.TestCase):
    def _init_repo(self, d):
        subprocess.run([GIT, "init", "-q", d], check=True)
        _write(os.path.join(d, "README"), "x")
        subprocess.run([GIT, "-C", d, "add", "README"], check=True)
        subprocess.run([GIT, "-C", d, "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "init"], check=True)

    def test_main_tree_resolves_to_itself(self):
        with tempfile.TemporaryDirectory() as d:
            d = os.path.realpath(d)
            self._init_repo(d)
            _marker(d)
            self.assertEqual(os.path.realpath(gate.project_root(d)), d)

    def test_worktree_resolves_to_main(self):
        """Dept in a nested worktree, marker only in main → resolve to main."""
        with tempfile.TemporaryDirectory() as d:
            d = os.path.realpath(d)
            self._init_repo(d)
            _marker(d)  # marker lives ONLY in the main tree (untracked, like real runtime state)
            wt = os.path.join(d, ".claude", "worktrees", "wt1")
            subprocess.run([GIT, "-C", d, "worktree", "add", "-q", "-b", "wt1", wt], check=True)
            self.assertEqual(os.path.realpath(gate.project_root(wt)), d)

    def test_worktree_with_shadow_marker_still_resolves_to_main(self):
        """The money test: a shadowing marker inside the worktree would fool the
        plain walk, but git's common-dir anchor still resolves to the main tree."""
        with tempfile.TemporaryDirectory() as d:
            d = os.path.realpath(d)
            self._init_repo(d)
            _marker(d)
            wt = os.path.join(d, ".claude", "worktrees", "wt1")
            subprocess.run([GIT, "-C", d, "worktree", "add", "-q", "-b", "wt1", wt], check=True)
            _marker(wt)  # shadow — as if orchestrate.json were git-tracked
            self.assertEqual(os.path.realpath(gate._walk_root(wt)), os.path.realpath(wt))  # walk is fooled
            self.assertEqual(os.path.realpath(gate.project_root(wt)), d)                   # git is not


class CompletionGate(unittest.TestCase):
    def test_blocks_when_no_pass(self):
        with tempfile.TemporaryDirectory() as d:
            _marker(d)
            self.assertEqual(_run_gate(d, task_id="3"), 2)

    def test_allows_with_pass(self):
        with tempfile.TemporaryDirectory() as d:
            _marker(d)
            _write(os.path.join(d, "docs", "reviews", "3.pass"), "ok")
            self.assertEqual(_run_gate(d, task_id="3"), 0)

    def test_allows_when_inactive(self):
        with tempfile.TemporaryDirectory() as d:
            _marker(d, active=False)
            self.assertEqual(_run_gate(d, task_id="3"), 0)

    def test_allows_when_no_marker(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run_gate(d, task_id="3"), 0)

    def test_ignores_non_completed_transition(self):
        with tempfile.TemporaryDirectory() as d:
            _marker(d)
            self.assertEqual(_run_gate(d, status="in_progress", task_id="3"), 0)

    def test_ignores_non_taskupdate(self):
        with tempfile.TemporaryDirectory() as d:
            _marker(d)
            self.assertEqual(_run_gate(d, tool_name="Edit", task_id="3"), 0)


@unittest.skipIf(not GIT, "git not available")
class RecycledIdCannotWaveWorkThrough(unittest.TestCase):
    """The dangerous half of the 2026-08-05 collision: it was reported as noise in the
    stall alarm, but the same rule is what this gate asks, and here it OPENED the gate.

    Card #500 has never been reviewed. It holds platform task 7, and task 7 belonged to
    another card weeks ago — whose `.pass` is still on disk, naming a commit still sitting
    on master. Evidence held, evidence outranked the clock, and an unreviewed card could
    be marked completed. The clock exists precisely to catch a borrowed id."""

    def _repo(self, d):
        """A base commit and then the reviewed one — a ROOT commit has no parent and no
        patch-id, which would make the fixture pass for the wrong reason."""
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        subprocess.run([GIT, "init", "-q", d], check=True)
        for name, body in (("README", "base\n"), ("work.txt", "the other card's change\n")):
            _write(os.path.join(d, name), body)
            subprocess.run([GIT, "-C", d, "add", "-A"], check=True, env=env)
            subprocess.run([GIT, "-C", d, "commit", "-qm", "c-" + name], check=True, env=env)
        return subprocess.run([GIT, "-C", d, "rev-parse", "HEAD"], capture_output=True,
                              text=True, env=env).stdout.strip()

    def test_an_old_pass_on_a_borrowed_task_id_still_blocks(self):
        import time
        from datetime import datetime, timedelta
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "..", "skills", "orchestrate", "scripts"))
        import board
        with tempfile.TemporaryDirectory() as d:
            d = os.path.realpath(d)
            sha = self._repo(d)
            _marker(d)
            _write(os.path.join(d, "docs", "board", "500-THING.md"),
                   '---\nid: 500\nname: THING\ndept: Frontend\nstatus: todo\n'
                   'since: "%s"\ntask_id: 7\n---\n\nbody\n'
                   % datetime.now().strftime("%Y-%m-%d %H:%M"))
            p = os.path.join(d, "docs", "reviews", "Ops.7.1.pass")
            _write(p, "PASS\nsha: %s\npatch-id: %s\n" % (sha, board.patch_id_of(d, sha)))
            old = time.time() - 200 * 3600
            os.utime(p, (old, old))
            self.assertEqual(_run_gate(d, task_id="7"), 2)

    def test_the_same_marker_on_the_cards_OWN_number_still_passes(self):
        """The control: change nothing but which id matched. A durable `#NNN` is the
        card's permanent identity, so evidence is answering the only open question and
        the rescue stands — otherwise this fix would just be the clock bug again."""
        import time
        from datetime import datetime
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "..", "skills", "orchestrate", "scripts"))
        import board
        with tempfile.TemporaryDirectory() as d:
            d = os.path.realpath(d)
            sha = self._repo(d)
            _marker(d)
            _write(os.path.join(d, "docs", "board", "500-THING.md"),
                   '---\nid: 500\nname: THING\ndept: Frontend\nstatus: review\n'
                   'since: "%s"\ntask_id: 7\n---\n\nbody\n'
                   % datetime.now().strftime("%Y-%m-%d %H:%M"))
            p = os.path.join(d, "docs", "reviews", "Ops.500.1.pass")
            _write(p, "PASS\nsha: %s\npatch-id: %s\n" % (sha, board.patch_id_of(d, sha)))
            old = time.time() - 200 * 3600
            os.utime(p, (old, old))
            self.assertEqual(_run_gate(d, task_id="7"), 0)


if __name__ == "__main__":
    unittest.main()
