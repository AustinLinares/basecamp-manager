#!/usr/bin/env python3
"""SessionStart hook: keeps the `bcm` launcher pointing at the installed plugin version, renews the
Basecamp token when it is about to expire (plugin option auto_refresh, on by default) and, if it
cannot, tells Claude. Silent otherwise; never prints or logs a secret."""
import importlib.util
import json
import os
import sys
import time

WARN_DAYS = 3
REFRESH_TIMEOUT = 4          # seconds; SessionStart's own limit is 10
RETRY_AFTER = 30 * 60        # after a failed refresh, do not try (and wait) again for this long


def home_dir():
    return os.path.expanduser(os.environ.get("BASECAMP_MANAGER_HOME") or "~/.config/basecamp-manager")


def write_launcher(home):
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bcm.py")
    content = f'#!/bin/sh\nexec "{sys.executable}" -I "{script}" "$@"\n'
    launcher = os.path.join(home, "bcm")
    try:
        with open(launcher) as handle:
            if handle.read() == content:
                return
    except OSError:
        pass
    os.makedirs(home, mode=0o700, exist_ok=True)
    with open(launcher, "w") as handle:
        handle.write(content)
    os.chmod(launcher, 0o700)


def days_left(home):
    try:
        with open(os.path.join(home, "token-info.json")) as handle:
            return (float(json.load(handle)["expires_at"]) - time.time()) / 86400
    except (OSError, ValueError, KeyError, TypeError):
        return None


def auto_refresh_enabled():
    raw = os.environ.get("CLAUDE_PLUGIN_OPTION_AUTO_REFRESH")
    if raw is None or raw.strip() == "":
        return True
    return raw.strip().lower() in ("1", "true", "yes", "on")


def load_bcm():
    spec = importlib.util.spec_from_file_location(
        "basecamp_bcm", os.path.join(os.path.dirname(os.path.abspath(__file__)), "bcm.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def try_refresh(home):
    """Renews the token with bcm's own refresh logic when it is inside the warning window. Returns True
    when it renewed. Never raises and never prints; the failure marker holds only a timestamp."""
    marker = os.path.join(home, "refresh-failed")
    try:
        days = days_left(home)
        if days is None or days > WARN_DAYS or not auto_refresh_enabled():
            return False
        try:
            if time.time() - os.path.getmtime(marker) < RETRY_AFTER:
                return False
        except OSError:
            pass
        bcm = load_bcm()
        try:
            bcm.refresh_token(timeout=REFRESH_TIMEOUT)
        except Exception:
            with open(marker, "w") as handle:
                handle.write(str(int(time.time())))
            return False
        try:
            os.remove(marker)
        except OSError:
            pass
        return True
    except Exception:
        return False


def expiry_note(home):
    days = days_left(home)
    if days is None:
        return None
    if days > WARN_DAYS:
        return None
    when = "has expired" if days <= 0 else f"expires in {days:.1f} days"
    return (f"basecamp-manager: the Basecamp access token {when}. If the user works with Basecamp in this "
            f"session, offer to run `{os.path.join(home, 'bcm')} refresh` (it prints no secret).")


def main():
    home = home_dir()
    try:
        write_launcher(home)
    except OSError:
        pass
    try_refresh(home)
    note = expiry_note(home)
    if note:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": note}}))


if __name__ == "__main__":
    main()
