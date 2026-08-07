"""Tests for mcp/boss_channel.py — the founder's board as an MCP destination.
Run: python3 mcp/test_boss_channel.py"""
import os, sys, json, tempfile, subprocess, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "skills", "orchestrate", "scripts"))
import boss_channel as bc
import board

SERVER = os.path.join(HERE, "boss_channel.py")


def _project(d, active=True):
    os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
    with open(os.path.join(d, ".claude", "orchestrate.json"), "w", encoding="utf-8") as f:
        json.dump({"active": active, "roster": ["Frontend"]}, f)
    return d


def _call(cwd, name, **args):
    """Drive the tool the way the harness does, in-process, with the panel suppressed."""
    board._SKIP_SERVER = True
    old = os.getcwd()
    try:
        os.chdir(cwd)
        return bc.HANDLERS[name](args)
    finally:
        os.chdir(old)


class Validation(unittest.TestCase):
    """The schema IS the noise filter: prose cannot be checked, a tool call can."""

    def test_kind_must_come_from_the_closed_set(self):
        f, err = bc.validate({"dept": "Frontend", "kind": "fyi", "ask": "x"})
        self.assertIsNone(f)
        self.assertIn("decision", err)
        self.assertIn("blocker", err)

    def test_error_teaches_the_shape_rather_than_saying_invalid(self):
        _, err = bc.validate({"dept": "Frontend", "kind": "decision", "ask": "a" * 300})
        self.assertIn("300", err)
        self.assertIn("detail", err)          # tells the caller where the text belongs

    def test_dept_is_required(self):
        _, err = bc.validate({"kind": "info", "ask": "x"})
        self.assertIn("dept is required", err)

    def test_ask_is_required(self):
        _, err = bc.validate({"dept": "CEO", "kind": "info", "ask": "   "})
        self.assertIn("ask is required", err)

    def test_multiline_ask_is_folded_not_rejected(self):
        """A board is scanned in a list, so an ask is one line — but folding is kinder
        than a rejection the caller has to guess its way out of."""
        f, err = bc.validate({"dept": "CEO", "kind": "info", "ask": "one\n  two\tthree"})
        self.assertIsNone(err)
        self.assertEqual(f["ask"], "one two three")

    def test_detail_that_only_repeats_the_ask_is_refused(self):
        _, err = bc.validate({"dept": "CEO", "kind": "decision", "ask": "ship it?",
                              "detail": "ship it?"})
        self.assertIn("repeats the ask", err)

    def test_overlong_detail_is_refused_and_points_at_a_file(self):
        _, err = bc.validate({"dept": "CEO", "kind": "decision", "ask": "ship it?",
                              "detail": "x" * 2000})
        self.assertIn("file", err)

    def test_card_hash_is_stripped(self):
        f, _ = bc.validate({"dept": "CEO", "kind": "decision", "ask": "ship?", "card": "#387"})
        self.assertEqual(f["card"], "387")


class Posting(unittest.TestCase):
    def test_post_lands_on_the_board_and_returns_a_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            err, text = _call(d, "message", dept="Frontend", kind="decision",
                              ask="Annual toggle default-on or default-off?")
            self.assertFalse(err)
            self.assertIn("Posted", text)
            self.assertIn("1 open", text)
            rows = board.board_list(d)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["kind"], "decision")

    def test_receipt_tells_the_caller_not_to_repeat_the_content(self):
        """The whole point is that the terminal stops carrying what the board carries."""
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _, text = _call(d, "message", dept="CEO", kind="info", ask="Deploy is green.")
            self.assertIn("point at it", text)

    def test_detail_is_folded_into_the_entry(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _call(d, "message", dept="CEO", kind="decision", ask="Ship?", detail="Costs £30.")
            self.assertIn("Costs £30.", board.board_list(d)[0]["text"])

    def test_duplicate_post_says_so_instead_of_stacking(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _call(d, "message", dept="CEO", kind="decision", ask="Ship?")
            err, text = _call(d, "message", dept="CEO", kind="decision", ask="Ship?")
            self.assertFalse(err)
            self.assertIn("Already open", text)
            self.assertEqual(len(board.board_list(d)), 1)

    def test_info_and_decision_file_to_different_desk_sections(self):
        """The refined kinds must still land where the existing panel expects them."""
        self.assertEqual(board._desk_section({"kind": "decision", "status": "open"}), "1 Needs you")
        self.assertEqual(board._desk_section({"kind": "blocker", "status": "open"}), "1 Needs you")
        self.assertEqual(board._desk_section({"kind": "signoff", "status": "open"}), "1 Needs you")
        self.assertEqual(board._desk_section({"kind": "info", "status": "open"}), "3 Information")

    def test_off_a_board_project_it_explains_rather_than_failing_silently(self):
        with tempfile.TemporaryDirectory() as d:
            err, text = _call(d, "message", dept="CEO", kind="info", ask="x")
            self.assertTrue(err)
            self.assertIn("orchestrate.json", text)

    def test_inactive_project_is_a_closed_board(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d, active=False)
            err, text = _call(d, "message", dept="CEO", kind="info", ask="x")
            self.assertTrue(err)
            self.assertIn("not active", text)


class Resolving(unittest.TestCase):
    def test_resolve_records_the_outcome(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _call(d, "message", dept="CEO", kind="decision", ask="Ship?")
            eid = board.board_list(d)[0]["id"]
            err, text = _call(d, "resolve", id=eid, outcome="Shipped default-off.")
            self.assertFalse(err)
            self.assertEqual(board.board_list(d)[0]["status"], "resolved")
            # The closing note is the RAISER's, so it lands in `outcome`. `sum` is the
            # Boss's own reply and a resolve must never write into their field.
            self.assertEqual(board.board_list(d)[0]["outcome"], "Shipped default-off.")
            self.assertNotIn("sum", board.board_list(d)[0])

    def test_resolving_without_an_outcome_is_refused(self):
        """An item closed with no outcome loses the answer the board existed to keep."""
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _call(d, "message", dept="CEO", kind="decision", ask="Ship?")
            err, text = _call(d, "resolve", id=board.board_list(d)[0]["id"])
            self.assertTrue(err)
            self.assertIn("outcome is required", text)

    def test_unknown_id_points_at_list_open(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            err, text = _call(d, "resolve", id="CEO-999", outcome="done")
            self.assertTrue(err)
            self.assertIn("list_open", text)

    def test_list_open_is_empty_when_it_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            err, text = _call(d, "list_open")
            self.assertFalse(err)
            self.assertIn("Nothing open", text)


class Protocol(unittest.TestCase):
    """stdout is the transport: a stray byte corrupts the session."""

    def _drive(self, *msgs, cwd=None):
        p = subprocess.run([sys.executable, SERVER], text=True, capture_output=True,
                           cwd=cwd or ROOT,
                           input="".join(json.dumps(m) + "\n" for m in msgs),
                           env=dict(os.environ, BOSS_BOARD_SKIP_SERVER="1"))
        return [json.loads(l) for l in p.stdout.splitlines() if l.strip()], p

    def test_initialize_echoes_a_supported_protocol_version(self):
        out, _ = self._drive({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                              "params": {"protocolVersion": "2025-03-26"}})
        self.assertEqual(out[0]["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual(out[0]["result"]["serverInfo"]["name"], "boss")

    def test_garbage_protocol_version_falls_back_to_a_known_one(self):
        out, _ = self._drive({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                              "params": {"protocolVersion": "banana"}})
        self.assertEqual(out[0]["result"]["protocolVersion"], bc.PROTOCOL_DEFAULT)

    def test_notifications_are_never_answered(self):
        """A response to a notification is a protocol violation, and id-less frames are
        exactly what an initialized handshake sends."""
        out, _ = self._drive({"jsonrpc": "2.0", "method": "notifications/initialized"},
                             {"jsonrpc": "2.0", "id": 7, "method": "ping"})
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], 7)

    def test_malformed_frame_does_not_kill_the_server(self):
        p = subprocess.run([sys.executable, SERVER], text=True, capture_output=True,
                           input='not json\n{"jsonrpc":"2.0","id":2,"method":"ping"}\n',
                           env=dict(os.environ, BOSS_BOARD_SKIP_SERVER="1"))
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout.strip())["id"], 2)

    def test_tools_list_advertises_the_three_tools_with_schemas(self):
        out, _ = self._drive({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        tools = out[0]["result"]["tools"]
        self.assertEqual({t["name"] for t in tools}, {"message", "resolve", "list_open"})
        for t in tools:
            self.assertEqual(t["inputSchema"]["type"], "object")

    def test_unknown_method_is_a_jsonrpc_error_not_a_crash(self):
        out, _ = self._drive({"jsonrpc": "2.0", "id": 1, "method": "tools/nope"})
        self.assertEqual(out[0]["error"]["code"], -32601)

    def test_unknown_tool_is_a_tool_error_not_a_transport_error(self):
        out, _ = self._drive({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                              "params": {"name": "nope", "arguments": {}}})
        self.assertTrue(out[0]["result"]["isError"])

    def test_a_full_session_posts_and_reads_back(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            out, _ = self._drive(
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                 "params": {"name": "message", "arguments": {
                     "dept": "Frontend", "kind": "blocker", "ask": "Staging key expired."}}},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                 "params": {"name": "list_open", "arguments": {}}}, cwd=d)
            self.assertIn("Posted", out[1]["result"]["content"][0]["text"])
            self.assertIn("Staging key expired.", out[2]["result"]["content"][0]["text"])

    def test_registration_points_at_a_file_that_exists(self):
        with open(os.path.join(ROOT, ".mcp.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        args = cfg["mcpServers"]["boss"]["args"]
        rel = args[0].replace("${CLAUDE_PLUGIN_ROOT}/", "")
        self.assertTrue(os.path.isfile(os.path.join(ROOT, rel)), rel)


if __name__ == "__main__":
    unittest.main(verbosity=1)
