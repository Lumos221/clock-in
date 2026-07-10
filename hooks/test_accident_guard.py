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

    def test_dotnext_whitelist(self):
        for cmd in ("rm -rf .next", "rm -rf ./.next", "rm -rf web/.next", "rm -Rf .next/"):
            self.assertFalse(self.blocked(cmd), cmd)
        for cmd in ("rm -rf .next src", "rm -rf .nextish", "rm -rf src && rm -rf .next"):
            self.assertTrue(self.blocked(cmd), cmd)
        # whitelist holds per segment: every rm -rf in a compound must be .next
        self.assertFalse(self.blocked("rm -rf .next && npm run dev"))


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
