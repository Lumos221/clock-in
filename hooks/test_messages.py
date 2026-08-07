"""Length budget for everything a hook says out loud. Run: python3 hooks/test_messages.py

**A hook message is an order, not a lesson.** It is injected into a live turn, so every
sentence is paid for in the reader's context at the moment it is least welcome. Shape:

    <icon> <LABEL>: <what is true, with the exact ids/paths/handles>. <what to do>.

Then a prohibition, and ONLY where the wrong fix is tempting (`do not write the marker
yourself`). Nothing else. Not why the check exists, not the field report that motivated
it, not "this fires once" — that belongs in the docstring, where the person who maintains
it reads, and it was three quarters of the text before this file existed.

The budget is the enforcement. Prose grows back one clause at a time and no reviewer ever
objects to a single clause.
"""
import ast, os, glob, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
FLOOR = 140          # below this a literal is a fragment, not a message
CAP = 400            # no single message may exceed this
TOTAL = 9500         # ratchet: the sweep landed at 9017


def messages():
    """[(file, lineno, text)] — every non-docstring string literal long enough to be
    something a hook says. Implicit concatenation is one Constant after parsing, so a
    message split across source lines is measured whole."""
    out = []
    for p in sorted(glob.glob(os.path.join(HERE, "*.py"))):
        b = os.path.basename(p)
        if b.startswith("test_"):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except Exception:
            continue
        docs = {ast.get_docstring(n, clean=False)
                for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef, ast.Module))}
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) \
                    and len(n.value) > FLOOR and n.value not in docs:
                out.append((b, n.lineno, n.value))
    return out


class MessageBudget(unittest.TestCase):
    def test_no_single_message_runs_past_the_cap(self):
        over = ["%s:%d %d chars — %s…" % (b, l, len(t), t[:60].replace("\n", " "))
                for b, l, t in messages() if len(t) > CAP]
        self.assertEqual(over, [], "\n" + "\n".join(over))

    def test_the_total_does_not_creep_back(self):
        """Per-message caps alone lose to a new message every week. The total is what
        makes adding one a decision instead of an afterthought."""
        tot = sum(len(t) for _, _, t in messages())
        self.assertLessEqual(tot, TOTAL, "hook message text is %d chars, budget %d — "
                                         "trim an existing one or justify raising the "
                                         "ratchet" % (tot, TOTAL))

    def test_the_scan_actually_finds_the_messages(self):
        """A budget that matches nothing passes forever."""
        found = messages()
        self.assertGreater(len(found), 20)
        files = {b for b, _, _ in found}
        for expected in ("pretool_review_gate.py", "stop_capacity.py", "session_start.py"):
            self.assertIn(expected, files)


if __name__ == "__main__":
    unittest.main(verbosity=1)
