"""Tests for pretool_accident_guard.py — the irreversible-op backstop.
Run: python3 hooks/test_accident_guard.py"""
import os, sys, json, tempfile, subprocess, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pretool_accident_guard as guard

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pretool_accident_guard.py")


class RmDetection(unittest.TestCase):
    def blocked(self, cmd):
        return guard.guard_verdict(cmd) is not None

    def test_combined_separate_long_and_uppercase_flags_all_block(self):
        for cmd in ("rm -rf /tmp/x", "rm -fr x", "rm -Rf x", "rm -r -f x",
                    "rm --recursive --force x", "sudo rm -rf /", "rm -rf -- x"):
            self.assertTrue(self.blocked(cmd), cmd)

    def test_non_destructive_rm_allowed(self):
        # recursive-without-force (prompts, interruptible) and plain removes stay allowed
        for cmd in ("rm x.txt", "rm -f *.pyc", "rm -r somedir", "npm rm some-package", "echo hello"):
            self.assertFalse(self.blocked(cmd), cmd)

    def test_the_whitelist_is_one_path_not_a_name(self):
        """0.9.140 (Boss): narrowed to the single path `web/.next`. The old list keyed on
        NAMES (`.next|node_modules|.cache`) behind a `[\\w./@+-]+/` wildcard, so it
        exempted every directory anywhere that happened to wear one of those names —
        including a `node_modules` nobody meant to touch and a `.cache` some tool had
        started putting authored files in. A name-keyed exemption cannot tell those apart;
        a path-keyed one exempts exactly one place."""
        for cmd in ("rm -rf web/.next", "rm -rf ./web/.next", "rm -Rf web/.next/",
                    "rm -r -f web/.next", "rm -rf web/.next && npm run dev"):
            self.assertFalse(self.blocked(cmd), cmd)
        for cmd in ("rm -rf .next",              # the bare name is no longer enough
                    "rm -rf node_modules", "rm -rf .cache",
                    "rm -rf apps/web/.next",     # same name, different place
                    "rm -rf ../web/.next", "rm -rf ~/web/.next",
                    "rm -rf web/.next/../../src",
                    "rm -rf web/.nextish",
                    "rm -rf web/.next src",      # one bad target poisons the segment
                    "rm -rf src && rm -rf web/.next"):
            self.assertTrue(self.blocked(cmd), cmd)


class OtherPatterns(unittest.TestCase):
    def blocked(self, cmd):
        return guard.guard_verdict(cmd) is not None

    def test_sql_drop_is_caught_regardless_of_case(self):
        self.assertTrue(self.blocked('psql -c "DROP TABLE users;"'))
        self.assertTrue(self.blocked("drop database prod"))

    def test_git_push_force_short_and_long(self):
        self.assertTrue(self.blocked("git push -f origin main"))
        self.assertTrue(self.blocked("git push origin main --force"))
        self.assertTrue(self.blocked("git push --force-with-lease"))  # still rewrites history
        self.assertFalse(self.blocked("git push origin feature-f"))   # branch name, not a flag
        self.assertFalse(self.blocked("git push"))

    def test_git_reset_and_clean(self):
        self.assertTrue(self.blocked("git reset --hard origin/main"))
        self.assertTrue(self.blocked("git clean -xfd"))
        self.assertFalse(self.blocked("git reset --soft HEAD~1"))


class EndToEnd(unittest.TestCase):
    def _run(self, root, cmd):
        payload = {"cwd": root, "tool_name": "Bash", "tool_input": {"command": cmd}}
        p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                           text=True, capture_output=True)
        return p.returncode

    def test_blocks_only_inside_active_project(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._run(d, "rm -rf /tmp/x"), 0)  # no marker → allow
            os.makedirs(os.path.join(d, ".claude"))
            open(os.path.join(d, ".claude", "orchestrate.json"), "w").write('{"active":true}')
            self.assertEqual(self._run(d, "rm -rf /tmp/x"), 2)  # active → block
            self.assertEqual(self._run(d, "ls -la"), 0)         # benign → allow


if __name__ == "__main__":
    unittest.main()
