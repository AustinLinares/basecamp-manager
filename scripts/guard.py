#!/usr/bin/env python3
"""basecamp-manager guard: a Claude Code PreToolUse hook that limits what an agent can do in Basecamp.

Rules (fail-closed for anything it cannot classify):
  * Never delete: DELETE requests and anything that trashes a recording are denied.
  * Writes only touch cards assigned to you (person_id in the config). A card with no assignees that
    you created stays editable while it is outside the protected columns (optionally only for a few
    minutes after creation, see own_unassigned_edit_minutes).
  * Claiming (allow_claim): an unassigned card outside the protected columns accepts exactly one
    write, PUT {"assignee_ids": [you]}, and nothing else. The hook cannot tell whether the user asked
    for it; the skill tells Claude to claim only on an explicit request.
  * Comments (allow_comments) can be created on your cards, never edited or removed.
  * Uploads (allow_uploads): one evidence file (image, video or PDF) per call with
    --data-binary @<file>, never from the credentials directory. An upload shows up nowhere until a
    comment or a description of one of your cards embeds it.
  * Any write to an endpoint that is not on the allowlist is denied.
  * Only curl may talk to the Basecamp API host.
  * The token file may only be read as $(cat <token file>) inside a curl to the API host, or into a
    variable that only such a curl uses. The OAuth secrets file is never readable by the agent.
Reads (GET) pass through.

Boards: config.json holds one "board" or several under "boards" (alias -> board). Protected columns
are the union of guard.protected_columns and every board's protected_columns.

Configuration: <BASECAMP_MANAGER_HOME or ~/.config/basecamp-manager>/config.json, plus the plugin
options exported as CLAUDE_PLUGIN_OPTION_<KEY>. The script contains no ids.
"""
import json
import os
import re
import shlex
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HOST = "3.basecampapi.com"
DEFAULT_USER_AGENT = "basecamp-manager guard (https://github.com/AustinLinares/basecamp-manager)"
DEFAULTS = {"allow_claim": True, "allow_comments": True, "allow_uploads": True, "own_unassigned_edit_minutes": 0}
# Evidence only: screenshots, recordings and PDFs. Anything else on disk stays on disk.
UPLOAD_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".mp4", ".mov", ".webm"}

ID = r"(\d+)"
BUCKET = r"(?:/buckets/\d+)?"
# (method, path pattern, what the write touches). The captured id is a card, a step or a recording.
WRITE_ENDPOINTS = [
    ("POST", re.compile(rf"^{BUCKET}/card_tables/lists/\d+/cards\.json$"), "create"),
    ("PUT", re.compile(rf"^{BUCKET}/card_tables/cards/{ID}\.json$"), "card_update"),
    ("POST", re.compile(rf"^{BUCKET}/card_tables/cards/{ID}/moves\.json$"), "card"),
    ("POST", re.compile(rf"^{BUCKET}/card_tables/cards/{ID}/steps\.json$"), "card"),
    ("POST", re.compile(rf"^{BUCKET}/card_tables/cards/{ID}/positions\.json$"), "card"),
    ("PUT", re.compile(rf"^{BUCKET}/card_tables/steps/{ID}\.json$"), "step"),
    ("PUT", re.compile(rf"^{BUCKET}/card_tables/steps/{ID}/completions\.json$"), "step"),
    ("POST", re.compile(rf"^{BUCKET}/recordings/{ID}/comments\.json$"), "comment"),
    ("POST", re.compile(r"^/attachments\.json$"), "upload"),
]
TRASH = re.compile(r"/status/(?:trashed|deleted)|/trash", re.I)
DATA_FLAGS = ("--data-urlencode", "--data-binary", "--data-ascii", "--data-raw", "--data", "--json", "-d")
SEPARATORS = re.compile(r"\|\||&&|[|;&\n]")
TOKEN_ASSIGNMENT = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)=("?)\$\(TOKEN\)\2\s*$')
FILE_TOOLS = {"Read", "Edit", "Write", "MultiEdit", "NotebookEdit", "Grep"}


class Deny(Exception):
    pass


# ---------------------------------------------------------------------------------------- config

def home_dir():
    return os.path.expanduser(os.environ.get("BASECAMP_MANAGER_HOME") or "~/.config/basecamp-manager")


def load_config():
    path = os.path.join(home_dir(), "config.json")
    try:
        with open(path) as handle:
            config = json.load(handle)
    except FileNotFoundError:
        config = {}
    except ValueError as error:
        raise Deny(f"{path} is not valid JSON ({error}); fix it before using Basecamp")
    guard = dict(DEFAULTS)
    guard.update(config.get("guard") or {})
    for key, default in DEFAULTS.items():
        raw = os.environ.get(f"CLAUDE_PLUGIN_OPTION_{key.upper()}")
        if raw is None or raw == "":
            continue
        if isinstance(default, bool):
            guard[key] = raw.strip().lower() in ("1", "true", "yes", "on")
        else:
            try:
                guard[key] = float(raw)
            except ValueError:
                raise Deny(f"plugin option {key} must be a number, got {raw!r}")
    config["guard"] = guard
    config["token_file"] = os.path.expanduser(config.get("token_file") or os.path.join(home_dir(), "token"))
    config["oauth_file"] = os.path.join(home_dir(), "oauth.json")
    return config


# --------------------------------------------------------------------------------------- secrets

def path_variants(path):
    """The spellings a shell command could use for an absolute path under the home directory."""
    variants = {path}
    home = os.path.expanduser("~")
    if path.startswith(home + os.sep):
        rest = path[len(home) + 1:]
        variants |= {f"~/{rest}", f"$HOME/{rest}", f"${{HOME}}/{rest}", f'"$HOME"/{rest}'}
    return sorted(variants, key=len, reverse=True)


def check_secrets(command, config):
    """Checks how the credential files are used. Returns the command with every allowed token read
    replaced by $(TOKEN), and the shell variables that hold the token."""
    for variant in path_variants(config["oauth_file"]):
        if variant in command:
            raise Deny("the OAuth secrets file is never read by the agent; run the setup scripts in your own terminal")
    token_variants = path_variants(config["token_file"])
    if not any(variant in command for variant in token_variants):
        return command, set()
    stripped = command
    for variant in token_variants:
        for quoted in (variant, f'"{variant}"', f"'{variant}'"):
            stripped = stripped.replace(f"$(cat {quoted})", "$(TOKEN)").replace(f"$(< {quoted})", "$(TOKEN)")
    if any(variant in stripped for variant in token_variants):
        raise Deny("the token file may only be read as $(cat <token file>) to pass it to curl; never print or copy it")
    names = set()
    for segment in SEPARATORS.split(stripped):
        match = TOKEN_ASSIGNMENT.match(segment)
        if match:
            names.add(match.group(1))
    return stripped, names


def uses_any(segment, names):
    return any(re.search(rf"\$\{{?{re.escape(name)}\b", segment) for name in names)


# ---------------------------------------------------------------------------------- basecamp api

def api_get(config, path):
    with open(config["token_file"]) as handle:
        token = handle.read().strip()
    request = urllib.request.Request(
        f"https://{HOST}/{config['account_id']}{path}",
        headers={"Authorization": f"Bearer {token}",
                 "User-Agent": config.get("user_agent") or DEFAULT_USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def fetch(config, path, what):
    try:
        return api_get(config, path)
    except Exception as error:  # fail closed
        raise Deny(f"could not verify {what} ({type(error).__name__}); write blocked")


def column_ids(value, where):
    if value is None:
        return set()
    if not isinstance(value, list) or any(isinstance(i, bool) or not isinstance(i, int) for i in value):
        raise Deny(f"{where} must be a list of column ids; fix config.json (writes are blocked until then)")
    return set(value)


def protected_columns(config):
    """Union of guard.protected_columns and the protected_columns of every board in "boards". A
    "boards" section that is not an object of objects fails closed (Deny)."""
    protected = column_ids((config.get("guard") or {}).get("protected_columns"), "guard.protected_columns")
    boards = config.get("boards")
    if boards is None:
        return protected
    if not isinstance(boards, dict):
        raise Deny("boards in config.json must be an object of boards; fix it (writes are blocked until then)")
    for alias, board in boards.items():
        if not isinstance(board, dict):
            raise Deny(f"boards.{alias} in config.json must be an object; fix it (writes are blocked until then)")
        protected |= column_ids(board.get("protected_columns"), f"boards.{alias}.protected_columns")
    return protected


def card_allowed(config, card_id, kind, claim=False):
    me = config["person_id"]
    guard = config["guard"]
    protected = protected_columns(config)
    card = fetch(config, f"/card_tables/cards/{card_id}.json", f"card {card_id}")
    assignees = [person.get("id") for person in card.get("assignees") or []]
    if me in assignees:
        return
    column = (card.get("parent") or {}).get("id")
    if not assignees and column not in protected:
        if (card.get("creator") or {}).get("id") == me and fresh_enough(card, guard):
            return
        if claim and guard["allow_claim"]:
            return
    who = [person.get("name") or str(person.get("id")) for person in card.get("assignees") or []]
    hint = ""
    if not assignees and guard["allow_claim"] and column not in protected:
        hint = (' To take it, claim it first with a PUT whose body is exactly {"assignee_ids":[<your person id>]}'
                " (only if the user asked), then edit it in a later call.")
    elif not assignees and column in protected:
        hint = " It is in a protected column, so it cannot be claimed."
    raise Deny(f"card {card_id} is not assigned to you (assignees: {', '.join(who) or 'nobody'}); read-only.{hint}")


def fresh_enough(card, guard):
    minutes = float(guard.get("own_unassigned_edit_minutes") or 0)
    if minutes <= 0:
        return True
    try:
        created = datetime.fromisoformat(card["created_at"].replace("Z", "+00:00"))
    except (KeyError, ValueError, AttributeError):
        return False
    return (datetime.now(timezone.utc) - created).total_seconds() <= minutes * 60


# ------------------------------------------------------------------------------------ curl parse

def curl_tokens(segment):
    try:
        return shlex.split(segment)
    except ValueError:
        raise Deny("could not parse this command; write the curl call without unbalanced quotes")


def method_of(tokens):
    method = None
    for index, token in enumerate(tokens):
        if token in ("-X", "--request") and index + 1 < len(tokens):
            method = tokens[index + 1]
        elif token.startswith("--request="):
            method = token.split("=", 1)[1]
        elif token.startswith("-X") and len(token) > 2:
            method = token[2:]
    if method:
        return method.upper()
    if "-G" in tokens or "--get" in tokens:
        return "GET"
    if any(t in ("-T", "--upload-file") or t.startswith("--upload-file=") for t in tokens):
        return "PUT"
    if any(t in ("-F", "--form") or t.startswith(("--form=", "-F")) for t in tokens) or data_bodies(tokens):
        return "POST"
    return "GET"


def data_bodies(tokens):
    bodies = []
    for index, token in enumerate(tokens):
        for flag in DATA_FLAGS:
            if token == flag:
                bodies.append(tokens[index + 1] if index + 1 < len(tokens) else "")
                break
            if flag.startswith("--") and token.startswith(flag + "="):
                bodies.append(token[len(flag) + 1:])
                break
            if flag == "-d" and token.startswith("-d") and not token.startswith("--"):
                bodies.append(token[2:])
                break
    return bodies


def is_claim_body(tokens, me):
    bodies = data_bodies(tokens)
    if len(bodies) != 1 or bodies[0].startswith("@"):
        return False
    try:
        body = json.loads(bodies[0])
    except ValueError:
        return False
    return isinstance(body, dict) and set(body) == {"assignee_ids"} and body["assignee_ids"] == [me]


# -------------------------------------------------------------------------------------- decision

def check_segment(segment, config):
    tokens = curl_tokens(segment)
    if not tokens or os.path.basename(tokens[0]) != "curl":
        raise Deny("the Basecamp API may only be called by a command that starts with curl"
                   " (not echo, scripts, bash -c, xargs or other tools)")
    if any(t in ("-K", "--config", "--next", "-:") or t.startswith("--config=") for t in tokens):
        raise Deny("curl config files and --next are not allowed with the Basecamp API")
    method = method_of(tokens)
    urls = re.findall(rf"https?://{re.escape(HOST)}(/[^\s'\"\\)`]*)", segment)
    if method == "DELETE":
        raise Deny("deleting is never allowed")
    if any(TRASH.search(url) for url in urls):
        raise Deny("trashing counts as deleting and is never allowed")
    if method in ("GET", "HEAD"):
        return
    if not config.get("account_id") or not config.get("person_id"):
        raise Deny("basecamp-manager is not configured (missing account_id or person_id); writes are blocked until setup is done")
    if len(urls) != 1:
        raise Deny("a write must target exactly one literal Basecamp URL; write blocked")
    path = urls[0].split("?")[0].split("#")[0]
    prefix = f"/{config['account_id']}/"
    if not path.startswith(prefix):
        raise Deny(f"writes outside account {config['account_id']} are blocked")
    path = path[len(prefix) - 1:]
    for allowed_method, pattern, kind in WRITE_ENDPOINTS:
        match = pattern.match(path)
        if not match:
            continue
        if method != allowed_method:
            if kind == "comment":
                raise Deny("comments may only be created, never edited or removed")
            raise Deny(f"{method} is not allowed on {path} (only {allowed_method})")
        if kind == "create":
            return
        if kind == "upload":
            return check_upload(tokens, urls[0], config)
        if kind == "card_update":
            claim = is_claim_body(tokens, config["person_id"])
            return card_allowed(config, match.group(1), kind, claim=claim)
        if kind == "card":
            return card_allowed(config, match.group(1), kind)
        if kind == "step":
            step = fetch(config, f"/card_tables/steps/{match.group(1)}.json", f"the card of step {match.group(1)}")
            card_id = (step.get("parent") or {}).get("id")
            if not card_id:
                raise Deny(f"could not find the card of step {match.group(1)}; write blocked")
            return card_allowed(config, card_id, kind)
        if kind == "comment":
            if not config["guard"]["allow_comments"]:
                raise Deny("creating comments is turned off (allow_comments)")
            return card_allowed(config, match.group(1), kind)
    raise Deny(f"{method} {path} is not an allowed write endpoint; ask the user to do it in Basecamp")


def check_upload(tokens, url, config):
    """An upload only stores a file; it shows up nowhere until a comment or a card you own embeds it.
    Still, only evidence files may leave the disk, and never the credentials."""
    if not config["guard"]["allow_uploads"]:
        raise Deny("uploading files is turned off (allow_uploads)")
    sources = [t[len("--data-binary="):] if t.startswith("--data-binary=") else tokens[i + 1]
               for i, t in enumerate(tokens)
               if (t == "--data-binary" and i + 1 < len(tokens)) or t.startswith("--data-binary=")]
    if len(sources) != 1 or len(data_bodies(tokens)) != 1 or not sources[0].startswith("@") or sources[0] == "@-":
        raise Deny("upload exactly one file with --data-binary @<file>")
    source = os.path.realpath(os.path.expanduser(sources[0][1:]))
    if os.path.splitext(source)[1].lower() not in UPLOAD_EXTENSIONS:
        raise Deny("only images, videos and PDFs can be uploaded (" + ", ".join(sorted(UPLOAD_EXTENSIONS)) + ")")
    secrets_dir = os.path.realpath(home_dir())
    if source.startswith(secrets_dir + os.sep):
        raise Deny("files from the basecamp-manager directory are never uploaded")
    query = urllib.parse.parse_qs(urllib.parse.urlparse("https://x" + url).query)
    name = (query.get("name") or [""])[0]
    if os.path.splitext(name)[1].lower() not in UPLOAD_EXTENSIONS:
        raise Deny("the upload needs ?name=<file name> with an image, video or PDF extension")


AMPERSAND = "\x00"


def protect_ampersands(command):
    """Hides the & of a quoted literal (a URL with several query parameters) from the segment
    splitter. Only a & inside a properly closed quote with no expansion in it is hidden, because the
    shell reads it as plain text there. Anything that could put this scan out of step with the shell
    (comments, backticks, $(...) other than the token read, ${, $'...', an unclosed quote) returns the
    command untouched, so those commands keep being split at every & and fail closed."""
    out, i, n = [], 0, len(command)
    while i < n:
        c = command[i]
        if c == "\\":
            out.append(command[i:i + 2])
            i += 2
        elif c in "#`":
            return command
        elif c == "$":
            following = command[i + 1:i + 2]
            if following in ("'", '"', "{") or (following == "(" and not command.startswith("$(TOKEN)", i)):
                return command
            out.append(c)
            i += 1
        elif c == "'":
            end = command.find("'", i + 1)
            if end == -1:
                return command
            out.append(command[i:end + 1].replace("&", AMPERSAND))
            i = end + 1
        elif c == '"':
            j = i + 1
            while j < n and command[j] != '"':
                if command[j] in "`" or command.startswith("$(", j) and not command.startswith("$(TOKEN)", j):
                    return command
                j += 2 if command[j] == "\\" else 1
            if j >= n:
                return command
            span = command[i:j + 1]
            out.append(span if "$" in span else span.replace("&", AMPERSAND))
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def check_bash(command, config):
    command, token_names = check_secrets(command, config)
    if HOST not in command and "$(TOKEN)" not in command:
        return
    for segment in SEPARATORS.split(protect_ampersands(command)):
        segment = segment.replace(AMPERSAND, "&")
        if HOST in segment:
            check_segment(segment, config)
        elif TOKEN_ASSIGNMENT.match(segment):
            continue
        elif "$(TOKEN)" in segment or uses_any(segment, token_names):
            raise Deny("the token may only be sent to a curl with a literal https://3.basecampapi.com/... URL")


def check_file_tool(tool_input, config):
    secrets = [os.path.realpath(config["token_file"]), os.path.realpath(config["oauth_file"])]
    for key in ("file_path", "path", "notebook_path"):
        value = tool_input.get(key)
        if not value:
            continue
        target = os.path.realpath(os.path.expanduser(value))
        for secret in secrets:
            if target == secret or secret.startswith(target.rstrip(os.sep) + os.sep):
                raise Deny("Basecamp credentials are never read or written by the agent")


def decide(payload):
    """Returns None to allow, or the reason to deny."""
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    try:
        config = load_config()
        if tool == "Bash":
            check_bash(tool_input.get("command") or "", config)
        elif tool in FILE_TOOLS:
            check_file_tool(tool_input, config)
    except Deny as reason:
        return str(reason)
    except Exception as error:  # fail closed only when Basecamp is involved
        text = json.dumps(tool_input)
        if HOST in text or "basecamp-manager" in text:
            return f"internal error ({type(error).__name__}: {error}); blocked to be safe"
    return None


def main():
    reason = decide(json.load(sys.stdin))
    if reason:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"Basecamp guard: {reason}",
        }}))


if __name__ == "__main__":
    main()
