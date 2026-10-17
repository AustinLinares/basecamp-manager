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

        def fake_post(url, fields):
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
