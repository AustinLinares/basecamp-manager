#!/usr/bin/env python3
"""basecamp-manager command line: login, refresh and doctor.

Run it in your own terminal through the launcher the plugin keeps up to date:

    ~/.config/basecamp-manager/bcm login     # OAuth: opens the browser, catches the code, saves the token
    ~/.config/basecamp-manager/bcm refresh   # new access token from the refresh token
    ~/.config/basecamp-manager/bcm doctor    # checks the whole installation

No command ever prints a token or a secret.
"""
import argparse
import getpass
import html
import importlib.util
import json
import os
import secrets
import select
import shutil
import socket
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

LAUNCHPAD = "https://launchpad.37signals.com"
API = "https://3.basecampapi.com"
DEFAULT_REDIRECT = "http://localhost:8765/oauth"
PLUGIN_KEY = "basecamp-manager@basecamp-manager"
LOGIN_TIMEOUT = 300
WARN_DAYS = 3


class Fail(Exception):
    pass


# ----------------------------------------------------------------------------------------- files

def home_dir():
    return os.path.expanduser(os.environ.get("BASECAMP_MANAGER_HOME") or "~/.config/basecamp-manager")


def path(name):
    return os.path.join(home_dir(), name)


def ensure_home():
    os.makedirs(home_dir(), exist_ok=True)
    os.chmod(home_dir(), 0o700)


def write_private(name, text):
    """Writes a file only the user can read, replacing it atomically."""
    ensure_home()
    target = path(name)
    temp = target + ".tmp"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(text)
    os.chmod(temp, 0o600)
    os.replace(temp, target)


def read_json(name, default=None):
    try:
        with open(path(name)) as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default


def save_tokens(response, client_id, client_secret, previous=None):
    oauth = dict(previous or {})
    oauth.update(response)
    oauth.update({"client_id": client_id, "client_secret": client_secret})
    expires_in = int(response.get("expires_in") or 1209600)
    oauth["expires_at"] = int(time.time()) + expires_in
    write_private("oauth.json", json.dumps(oauth, indent=2) + "\n")
    write_private("token", response["access_token"])
    write_private("token-info.json", json.dumps({"expires_at": oauth["expires_at"]}) + "\n")
    return oauth["expires_at"]


def update_config(**values):
    config = read_json("config.json", {}) or {}
    config.update({key: value for key, value in values.items() if value})
    write_private("config.json", json.dumps(config, indent=2) + "\n")
    return config


def days_left(expires_at):
    return (expires_at - time.time()) / 86400


# ------------------------------------------------------------------------------------------ http

def user_agent():
    config = read_json("config.json", {}) or {}
    return config.get("user_agent") or "basecamp-manager setup"


def post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(url, data=data, method="POST", headers={"User-Agent": user_agent()})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read().decode(errors="replace")[:300]
        raise Fail(f"{url} answered {error.code}: {body}")
    except urllib.error.URLError as error:
        raise Fail(f"could not reach {url}: {error.reason}")


def api_get(url, token):
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "User-Agent": user_agent()})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


# ----------------------------------------------------------------------------------------- login

def authorization_url(client_id, redirect_uri, state):
    query = urllib.parse.urlencode({"response_type": "code", "client_id": client_id,
                                    "redirect_uri": redirect_uri, "state": state})
    return f"{LAUNCHPAD}/authorization/new?{query}"


def code_from_url(url, state=None):
    """Extracts the code from a redirect URL (or returns a bare code unchanged)."""
    url = url.strip()
    if "code=" not in url:
        return url
    params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    if "error" in params:
        raise Fail(f"authorization refused: {params['error'][0]}")
    if state and params.get("state", [state])[0] != state:
        raise Fail("the state parameter does not match; start the login again")
    return params["code"][0]


def can_listen(redirect_uri):
    parts = urllib.parse.urlparse(redirect_uri)
    return parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1") and bool(parts.port)


def wait_for_code(redirect_uri, state, timeout=LOGIN_TIMEOUT):
    """Listens on localhost (IPv4 and IPv6) for the single redirect and returns the code."""
    parts = urllib.parse.urlparse(redirect_uri)
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            if url.path != (parts.path or "/"):
                self.send_response(404)
                self.end_headers()
                return
            try:
                result["code"] = code_from_url(f"http://localhost{self.path}", state)
                message = "Basecamp authorized. You can close this tab and go back to your terminal."
            except Fail as error:
                result["error"] = str(error)
                message = f"Authorization failed: {error}"
            body = f"<!doctype html><meta charset=utf-8><title>basecamp-manager</title><p>{html.escape(message)}</p>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, *args):
            pass

    class Server6(HTTPServer):
        address_family = socket.AF_INET6

    servers = []
    for server_class, host in ((HTTPServer, "127.0.0.1"), (Server6, "::1")):
        try:
            servers.append(server_class((host, parts.port), Handler))
        except OSError:
            continue
    if not servers:
        raise Fail(f"port {parts.port} is busy; close what uses it or register another redirect URI")
    deadline = time.time() + timeout
    try:
        while not result and time.time() < deadline:
            ready, _, _ = select.select(servers, [], [], 1)
            for server in ready:
                server.handle_request()
    finally:
        for server in servers:
            server.server_close()
    if "error" in result:
        raise Fail(result["error"])
    if "code" not in result:
        raise Fail("no answer from the browser within 5 minutes; run login again")
    return result["code"]


def ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def cmd_login(args):
    previous = read_json("oauth.json", {}) or {}
    print("basecamp-manager login. Nothing you type here reaches Claude.\n")
    client_id = previous.get("client_id")
    if client_id and ask("Reuse the saved OAuth app? (y/n)", "y").lower().startswith("y"):
        client_secret = previous.get("client_secret")
    else:
        client_id = ask("Client ID")
        client_secret = getpass.getpass("Client Secret (hidden): ").strip()
    if not client_id or not client_secret:
        raise Fail("the Client ID and the Client Secret are both required (see docs/SETUP.md, step 1)")
    redirect_uri = args.redirect_uri or previous.get("redirect_uri") or ask(
        "Redirect URI registered in your app", DEFAULT_REDIRECT)
    config = read_json("config.json", {}) or {}
    if not config.get("user_agent"):
        email = ask("Email for the User-Agent header Basecamp requires")
        if email:
            update_config(user_agent=f"basecamp-manager ({email})")

    state = secrets.token_urlsafe(16)
    url = authorization_url(client_id, redirect_uri, state)
    print("\nOpening your browser to authorize the app. If it does not open, visit:\n" + url + "\n")
    webbrowser.open(url)
    if can_listen(redirect_uri):
        print("Waiting for the browser (up to 5 minutes)...")
        code = wait_for_code(redirect_uri, state)
    else:
        print("This redirect URI has no port, so the browser will show a connection error. That is expected.")
        code = code_from_url(input("Paste the full address from the browser bar: "), state)

    response = post_form(f"{LAUNCHPAD}/authorization/token", {
        "grant_type": "authorization_code", "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": redirect_uri, "code": code})
    if "access_token" not in response:
        raise Fail(f"the token exchange returned no token: {sorted(response)}")
    previous["redirect_uri"] = redirect_uri
    expires_at = save_tokens(response, client_id, client_secret, previous)
    print(f"\nSaved to {home_dir()} (only your user can read it). Token valid for {days_left(expires_at):.0f} days.")
    try:
        identity = api_get(f"{API}/authorization.json", response["access_token"])
        accounts = [account for account in identity.get("accounts", []) if account.get("product") == "bc3"]
        name = " ".join(filter(None, [identity.get("identity", {}).get(k) for k in ("first_name", "last_name")]))
        print(f"Signed in as {name or 'you'}. Basecamp accounts: "
              + (", ".join(f"{a['name']} ({a['id']})" for a in accounts) or "none found"))
    except Exception as error:  # the token is saved; the check is informative
        print(f"Token saved, but the check call failed ({error}). Run: bcm doctor")
    print("\nNext: go back to Claude Code and say \"set up Basecamp\" to pick your board.")


# --------------------------------------------------------------------------------------- refresh

def cmd_refresh(args):
    oauth = read_json("oauth.json")
    if not oauth or not oauth.get("refresh_token"):
        raise Fail("no refresh token saved; run: bcm login")
    response = post_form(f"{LAUNCHPAD}/authorization/token", {
        "grant_type": "refresh_token", "refresh_token": oauth["refresh_token"],
        "client_id": oauth.get("client_id", ""), "client_secret": oauth.get("client_secret", "")})
    if "access_token" not in response:
        raise Fail(f"the refresh returned no token: {sorted(response)}; run: bcm login")
    expires_at = save_tokens(response, oauth.get("client_id"), oauth.get("client_secret"), oauth)
    print(f"Token refreshed. Valid for {days_left(expires_at):.0f} days.")


# ---------------------------------------------------------------------------------------- doctor

def mode_of(target):
    return stat.S_IMODE(os.stat(target).st_mode)


def load_guard():
    spec = importlib.util.spec_from_file_location(
        "basecamp_guard", os.path.join(os.path.dirname(os.path.abspath(__file__)), "guard.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cmd_doctor(args):
    problems = 0

    def report(ok, message, fix=""):
        nonlocal problems
        problems += 0 if ok else 1
        print(("  ok    " if ok else "  FAIL  ") + message + ("" if ok or not fix else f"\n        -> {fix}"))

    print(f"basecamp-manager doctor ({home_dir()})\n")
    report(sys.version_info >= (3, 8), f"Python {sys.version.split()[0]}", "install Python 3.8 or later")
    for tool in ("curl", "jq"):
        report(bool(shutil.which(tool)), f"{tool} installed", f"install {tool}")

    windows = os.name == "nt"
    if os.path.isdir(home_dir()):
        report(windows or mode_of(home_dir()) & 0o077 == 0, "config directory is private (700)",
               f"chmod 700 {home_dir()}")
    else:
        report(False, "config directory exists", "run: bcm login")
    for name in ("token", "oauth.json"):
        if os.path.exists(path(name)):
            report(windows or mode_of(path(name)) & 0o077 == 0, f"{name} is private (600)", f"chmod 600 {path(name)}")
        else:
            report(False, f"{name} exists", "run: bcm login")

    config = read_json("config.json", {}) or {}
    report(bool(config.get("user_agent")), "config.json has user_agent", "run: bcm login")
    for key in ("account_id", "person_id"):
        report(bool(config.get(key)), f"config.json has {key}", 'in Claude Code, say "set up Basecamp"')
    report(bool((config.get("guard") or {}).get("protected_columns")), "config.json has guard.protected_columns",
           'in Claude Code, say "set up Basecamp" (cards in those columns cannot be claimed)')

    info = read_json("token-info.json", {}) or {}
    if info.get("expires_at"):
        left = days_left(info["expires_at"])
        report(left > WARN_DAYS, f"token valid for {left:.1f} more days", "run: bcm refresh")
    token = None
    if os.path.exists(path("token")):
        with open(path("token")) as handle:
            token = handle.read().strip()
    if token:
        try:
            identity = api_get(f"{API}/authorization.json", token)
            report(True, "Basecamp accepts the token")
            if config.get("account_id"):
                ids = [str(a.get("id")) for a in identity.get("accounts", [])]
                report(str(config["account_id"]) in ids, f"token can reach account {config['account_id']}",
                       "check account_id in config.json")
                profile = api_get(f"{API}/{config['account_id']}/my/profile.json", token)
                report(profile.get("id") == config.get("person_id"),
                       f"person_id matches your profile ({profile.get('id')})",
                       "person_id must be the id from /my/profile.json, not the Launchpad identity id")
        except urllib.error.HTTPError as error:
            report(False, f"Basecamp rejected the token ({error.code})", "run: bcm refresh (or bcm login)")
        except Exception as error:
            report(False, f"could not reach Basecamp ({type(error).__name__})", "check your connection")

    try:
        guard = load_guard()
        reason = guard.decide({"tool_name": "Bash", "tool_input": {
            "command": f"curl -X DELETE {API}/{config.get('account_id', 0)}/card_tables/cards/0.json"}})
        report(bool(reason) and "deleting" in reason, "guard denies a simulated delete (nothing is sent)",
               "reinstall the plugin")
    except Exception as error:
        report(False, f"guard loads ({error})", "reinstall the plugin")

    settings = os.path.join(os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude"), "settings.json")
    try:
        with open(settings) as handle:
            enabled = (json.load(handle).get("enabledPlugins") or {}).get(PLUGIN_KEY)
    except (OSError, ValueError):
        enabled = None
    report(enabled is not False, f"plugin {PLUGIN_KEY} is not disabled in {settings}",
           "enable it in /plugin")

    print("\nAll good." if not problems else f"\n{problems} problem(s) found.")
    return 1 if problems else 0


# ------------------------------------------------------------------------------------------ main

def main(argv=None):
    parser = argparse.ArgumentParser(prog="bcm", description="basecamp-manager: login, refresh, doctor")
    commands = parser.add_subparsers(dest="command", required=True)
    login = commands.add_parser("login", help="authorize your OAuth app and save the token")
    login.add_argument("--redirect-uri", help=f"the redirect URI registered in your app (default {DEFAULT_REDIRECT})")
    commands.add_parser("refresh", help="get a new access token with the saved refresh token")
    commands.add_parser("doctor", help="check the installation")
    args = parser.parse_args(argv)
    handler = {"login": cmd_login, "refresh": cmd_refresh, "doctor": cmd_doctor}[args.command]
    try:
        return handler(args) or 0
    except Fail as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ncancelled", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
