"""Tests for scripts/bcm.py, scripts/session_start.py and scripts/guard.sh. Nothing reaches the network
except a local listener on 127.0.0.1.

Run: python3 -m unittest discover -s tests
"""
import importlib.util
import json
import os
import shutil
import socket
import stat
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bcm = load("bcm")
session_start = load("session_start")


class HomeTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, "basecamp-manager")
        self.saved = os.environ.get("BASECAMP_MANAGER_HOME")
        os.environ["BASECAMP_MANAGER_HOME"] = self.home
        self.addCleanup(self.restore)

    def restore(self):
        if self.saved is None:
            os.environ.pop("BASECAMP_MANAGER_HOME", None)
        else:
            os.environ["BASECAMP_MANAGER_HOME"] = self.saved

    def mode(self, name):
        return stat.S_IMODE(os.stat(os.path.join(self.home, name)).st_mode)

    def read(self, name):
        with open(os.path.join(self.home, name)) as handle:
            return handle.read()


class TestLoginHelpers(unittest.TestCase):

    def test_authorization_url(self):
        url = bcm.authorization_url("abc", "http://localhost:8765/oauth", "xyz")
        self.assertTrue(url.startswith("https://launchpad.37signals.com/authorization/new?"))
        self.assertIn("client_id=abc", url)
        self.assertIn("redirect_uri=http%3A%2F%2Flocalhost%3A8765%2Foauth", url)
        self.assertIn("state=xyz", url)

    def test_code_from_redirect_url(self):
        self.assertEqual(bcm.code_from_url("http://localhost/oauth?code=c0de&state=s", "s"), "c0de")

    def test_bare_code(self):
        self.assertEqual(bcm.code_from_url("  c0de \n"), "c0de")

    def test_state_mismatch(self):
        with self.assertRaises(bcm.Fail):
            bcm.code_from_url("http://localhost/oauth?code=c0de&state=other", "s")

    def test_refused_authorization(self):
        with self.assertRaises(bcm.Fail):
            bcm.code_from_url("http://localhost/oauth?error=access_denied&code=", "s")

    def test_can_listen(self):
        self.assertTrue(bcm.can_listen("http://localhost:8765/oauth"))
        self.assertFalse(bcm.can_listen("http://localhost/oauth"))
        self.assertFalse(bcm.can_listen("https://localhost:8765/oauth"))
        self.assertFalse(bcm.can_listen("http://example.com:8765/oauth"))

    def test_listener_catches_the_code(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        result = {}
        thread = threading.Thread(target=lambda: result.update(
            code=bcm.wait_for_code(f"http://localhost:{port}/oauth", "s", timeout=10)))
        thread.start()
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/oauth?code=c0de&state=s", timeout=2).read()
                break
            except OSError:
                time.sleep(0.1)
        thread.join(10)
        self.assertEqual(result.get("code"), "c0de")


class TestTokens(HomeTestCase):

    def test_save_tokens_is_private(self):
        bcm.save_tokens({"access_token": "A", "refresh_token": "R", "expires_in": 1209600}, "id", "secret")
        self.assertEqual(self.mode("."), 0o700)
        for name in ("token", "oauth.json", "token-info.json"):
            self.assertEqual(self.mode(name), 0o600, name)
        self.assertEqual(self.read("token"), "A")
        oauth = json.loads(self.read("oauth.json"))
        self.assertEqual((oauth["refresh_token"], oauth["client_secret"]), ("R", "secret"))
        self.assertNotIn("A", self.read("token-info.json").replace("expires_at", ""))

    def test_refresh_keeps_the_refresh_token(self):
        bcm.save_tokens({"access_token": "A", "refresh_token": "R", "expires_in": 10}, "id", "secret")
        sent = {}

        def fake_post(url, fields, timeout=30):
            sent.update(fields)
            return {"access_token": "B", "expires_in": 1209600}

        original, bcm.post_form = bcm.post_form, fake_post
        try:
            bcm.cmd_refresh(None)
        finally:
            bcm.post_form = original
        self.assertEqual(sent["grant_type"], "refresh_token")
        self.assertEqual(sent["refresh_token"], "R")
        self.assertEqual(self.read("token"), "B")
        self.assertEqual(json.loads(self.read("oauth.json"))["refresh_token"], "R")

    def test_refresh_without_login(self):
        with self.assertRaises(bcm.Fail):
            bcm.cmd_refresh(None)

    def test_update_config_merges(self):
        os.makedirs(self.home)
        with open(os.path.join(self.home, "config.json"), "w") as handle:
            json.dump({"account_id": 1}, handle)
        bcm.update_config(user_agent="basecamp-manager (a@b.c)")
        self.assertEqual(json.loads(self.read("config.json")),
                         {"account_id": 1, "user_agent": "basecamp-manager (a@b.c)"})


class TestSessionStart(HomeTestCase):

    def test_launcher_points_at_this_plugin(self):
        session_start.write_launcher(self.home)
        launcher = self.read("bcm")
        self.assertIn(os.path.join(SCRIPTS, "bcm.py"), launcher)
        self.assertTrue(self.mode("bcm") & stat.S_IXUSR)

    def test_no_note_when_token_is_fresh(self):
        os.makedirs(self.home)
        with open(os.path.join(self.home, "token-info.json"), "w") as handle:
            json.dump({"expires_at": time.time() + 10 * 86400}, handle)
        self.assertIsNone(session_start.expiry_note(self.home))

    def test_note_when_token_is_about_to_expire(self):
        os.makedirs(self.home)
        with open(os.path.join(self.home, "token-info.json"), "w") as handle:
            json.dump({"expires_at": time.time() + 86400}, handle)
        self.assertIn("refresh", session_start.expiry_note(self.home))

    def test_no_note_before_login(self):
        self.assertIsNone(session_start.expiry_note(self.home))


class FakeTokenEndpoint:
    """A local stand-in for the Launchpad token endpoint. Records what it receives."""

    def __init__(self, status=200, delay=0):
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                outer.requests.append(self.rfile.read(length).decode())
                if delay:
                    time.sleep(delay)
                body = json.dumps({"access_token": "NEWTOKEN", "expires_in": 1209600}
                                  if status == 200 else {"error": "bad"}).encode()
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body)
                except OSError:
                    pass

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class TestAutoRefresh(HomeTestCase):

    def setUp(self):
        super().setUp()
        self.saved_launchpad = bcm.LAUNCHPAD
        self.addCleanup(setattr, bcm, "LAUNCHPAD", self.saved_launchpad)
        self.saved_option = os.environ.pop("CLAUDE_PLUGIN_OPTION_AUTO_REFRESH", None)
        self.addCleanup(self.restore_option)

    def restore_option(self):
        os.environ.pop("CLAUDE_PLUGIN_OPTION_AUTO_REFRESH", None)
        if self.saved_option is not None:
            os.environ["CLAUDE_PLUGIN_OPTION_AUTO_REFRESH"] = self.saved_option

    def endpoint(self, **kwargs):
        fake = FakeTokenEndpoint(**kwargs)
        self.addCleanup(fake.close)
        bcm.LAUNCHPAD = fake.url
        return fake

    def login(self, days):
        bcm.save_tokens({"access_token": "OLD", "refresh_token": "REFRESH", "expires_in": 100}, "id", "CSECRET")
        with open(os.path.join(self.home, "token-info.json"), "w") as handle:
            json.dump({"expires_at": time.time() + days * 86400}, handle)

    def refresh(self):
        """Runs try_refresh with bcm.py's LAUNCHPAD already pointed at the fake endpoint."""
        original = session_start.load_bcm
        session_start.load_bcm = lambda: bcm
        try:
            return session_start.try_refresh(self.home)
        finally:
            session_start.load_bcm = original

    def test_refreshes_inside_the_window(self):
        fake = self.endpoint()
        self.login(1)
        self.assertTrue(self.refresh())
        self.assertEqual(len(fake.requests), 1)
        self.assertIn("grant_type=refresh_token", fake.requests[0])
        self.assertEqual(self.read("token"), "NEWTOKEN")
        self.assertEqual(json.loads(self.read("oauth.json"))["refresh_token"], "REFRESH")
        self.assertEqual(self.mode("token"), 0o600)
        self.assertIsNone(session_start.expiry_note(self.home))

    def test_expired_token_is_refreshed_too(self):
        self.endpoint()
        self.login(-2)
        self.assertTrue(self.refresh())

    def test_does_nothing_when_fresh(self):
        fake = self.endpoint()
        self.login(10)
        self.assertFalse(self.refresh())
        self.assertEqual(fake.requests, [])

    def test_option_off(self):
        fake = self.endpoint()
        self.login(1)
        os.environ["CLAUDE_PLUGIN_OPTION_AUTO_REFRESH"] = "false"
        self.assertFalse(self.refresh())
        self.assertEqual(fake.requests, [])
        self.assertEqual(self.read("token"), "OLD")
        self.assertIn("refresh", session_start.expiry_note(self.home))

    def test_option_true_refreshes(self):
        self.endpoint()
        self.login(1)
        os.environ["CLAUDE_PLUGIN_OPTION_AUTO_REFRESH"] = "true"
        self.assertTrue(self.refresh())

    def test_rejected_refresh_falls_back_to_warning_and_backs_off(self):
        fake = self.endpoint(status=400)
        self.login(1)
        self.assertFalse(self.refresh())
        self.assertEqual(self.read("token"), "OLD")
        self.assertIn("refresh", session_start.expiry_note(self.home))
        self.assertFalse(self.refresh())
        self.assertEqual(len(fake.requests), 1)  # the second start did not try again

    def test_unreachable_endpoint_does_not_raise(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        bcm.LAUNCHPAD = f"http://127.0.0.1:{port}"
        self.login(1)
        self.assertFalse(self.refresh())
        self.assertEqual(self.read("token"), "OLD")

    def test_slow_endpoint_is_cut_off(self):
        self.endpoint(delay=3)
        self.login(1)
        original = session_start.REFRESH_TIMEOUT
        session_start.REFRESH_TIMEOUT = 0.5
        self.addCleanup(setattr, session_start, "REFRESH_TIMEOUT", original)
        started = time.time()
        self.assertFalse(self.refresh())
        self.assertLess(time.time() - started, 2.5)

    def test_no_login_no_attempt(self):
        fake = self.endpoint()
        self.assertFalse(self.refresh())
        os.makedirs(self.home, exist_ok=True)
        with open(os.path.join(self.home, "token-info.json"), "w") as handle:
            json.dump({"expires_at": time.time() + 86400}, handle)
        self.assertFalse(self.refresh())  # no oauth.json: the failure is swallowed
        self.assertEqual(fake.requests, [])

    def test_script_is_silent_about_secrets(self):
        self.login(1)
        out = subprocess.run(["python3", "-I", os.path.join(SCRIPTS, "session_start.py")],
                             capture_output=True, text=True, timeout=20,
                             env={"BASECAMP_MANAGER_HOME": self.home, "PATH": os.environ["PATH"],
                                  "CLAUDE_PLUGIN_OPTION_AUTO_REFRESH": "false"})
        self.assertEqual(out.returncode, 0)
        for secret in ("OLD", "REFRESH", "CSECRET"):
            self.assertNotIn(secret, out.stdout + out.stderr)
        self.assertIn("expires in", out.stdout)

    def test_manifest_declares_the_option(self):
        with open(os.path.join(ROOT, ".claude-plugin", "plugin.json")) as handle:
            option = json.load(handle)["userConfig"]["auto_refresh"]
        self.assertEqual((option["type"], option["default"]), ("boolean", True))


class TestGuardWrapper(unittest.TestCase):
    """guard.sh with and without a Python on the PATH."""

    def run_wrapper(self, command, path):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        env = {"PATH": path, "BASECAMP_MANAGER_HOME": "/nonexistent"}
        return subprocess.run(["/bin/sh", os.path.join(SCRIPTS, "guard.sh")], input=payload,
                              capture_output=True, text=True, env=env, timeout=20).stdout

    def bare_path(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory)
        for tool in ("cat", "dirname"):
            os.symlink(shutil.which(tool), os.path.join(directory, tool))
        return directory

    def test_runs_the_python_guard(self):
        out = self.run_wrapper("curl -X DELETE https://3.basecampapi.com/1/card_tables/cards/2.json",
                               os.environ["PATH"])
        self.assertIn("deleting is never allowed", out)

    def test_without_python_blocks_basecamp(self):
        out = self.run_wrapper("curl -s https://3.basecampapi.com/1/projects.json", self.bare_path())
        self.assertIn("Python 3.8 or later was not found", out)

    def test_without_python_lets_other_commands_through(self):
        self.assertEqual(self.run_wrapper("git status", self.bare_path()), "")


if __name__ == "__main__":
    unittest.main()
