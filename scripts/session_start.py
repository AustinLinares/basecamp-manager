#!/usr/bin/env python3
"""SessionStart hook: keeps the `bcm` launcher pointing at the installed plugin version, and tells
Claude when the Basecamp token is about to expire. Silent otherwise; never reads a secret."""
import json
import os
import sys
import time

WARN_DAYS = 3


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


def expiry_note(home):
    try:
        with open(os.path.join(home, "token-info.json")) as handle:
            expires_at = json.load(handle)["expires_at"]
    except (OSError, ValueError, KeyError):
        return None
    days = (expires_at - time.time()) / 86400
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
    note = expiry_note(home)
    if note:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": note}}))


if __name__ == "__main__":
    main()
