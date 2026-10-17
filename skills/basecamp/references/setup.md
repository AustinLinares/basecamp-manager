# Setup assistant (for Claude)

Goal: take the user from nothing to a working connection without any secret passing through the chat.
The human-facing guide with every screen and command is `${CLAUDE_PLUGIN_ROOT}/docs/SETUP.md`; send
the user there for the steps they run themselves. Go step by step, check each one, and skip the steps
that are already done.

## 0. Check what exists

```bash
~/.config/basecamp-manager/bcm doctor
```

The doctor prints what is missing and how to fix it; it never prints a secret. If
`~/.config/basecamp-manager/bcm` does not exist, the session hook has not run yet: use
`python3 -I "${CLAUDE_PLUGIN_ROOT}/scripts/bcm.py" doctor` and tell the user to restart Claude Code
once. Skip every step the doctor reports as ok. Never `cat` the token; the doctor is enough.

## 1. OAuth app and token (the user does this, in their own terminal)

Basecamp's current API has no personal API keys; the user needs an OAuth app of their own. Tell them
to follow `docs/SETUP.md` steps 2 and 3, and summarize:

1. Register an app at `https://launchpad.37signals.com/integrations` with redirect URI
   `http://localhost:8765/oauth`. Keep `client_id` and `client_secret` in a password manager.
2. In **their own terminal** (a regular one: Terminal, iTerm, the IDE's terminal; **not this chat and
   not the `!` prefix**, which has no keyboard input and fails with `EOFError`; and because it asks for
   the secret), run `~/.config/basecamp-manager/bcm login`. If `bcm` does not exist yet, give the
   `python3 -I "${CLAUDE_PLUGIN_ROOT}/scripts/bcm.py" login` form with the expanded path. It opens the browser, catches the authorization on
   localhost, and saves the token without printing it.
3. Come back and say when it is done. Then run the doctor again.

`bcm login` is interactive: never run it yourself. Never ask for the `client_secret`, the `code` or a
token in the chat. If the user pastes one, tell them to regenerate the secret in Launchpad and log in
again, and do not use the pasted value.

**Optional guided mode with Claude in Chrome.** Offer it when the browser tools are available: you open
the Launchpad integrations page (a new tab, since you cannot see the user's open ones) and fill in the
non-secret fields (name, company, website, Basecamp 5, redirect URI). If an app already exists, ask
before registering another and do not open its page (it shows the secret). Tell the user to run
`bcm login` in their terminal afterwards. Limits: you never type
passwords, secrets or tokens; the user clicks "Register" and "Yes, I'll allow access" themselves; if
a login page appears, stop and let the user sign in; never read the `code` from the address bar for
them. You only point and explain.

## 2. Permission rule

So reads are not blocked by the permission prompt every time, ask the user to add this allow rule in
`/permissions` (Allow tab), at user level:

```
Bash(curl * https://3.basecampapi.com/*)
```

## 3. Discover the ids (you do this, with reads)

Use the common call shape from SKILL.md, with the `user_agent` that `bcm login` already saved in
config.json. If it is missing, ask the user for an email and use `basecamp-manager (<email>)`.

1. Accounts: `GET https://3.basecampapi.com/authorization.json` and keep the
   `accounts[] | select(.product == "bc3") | {id, name}`. Ask which one if there are several.
2. The user's **person id** in that account: `GET /<account_id>/my/profile.json` and take `.id`.
   It is **not** `identity.id` from authorization.json; mixing them up breaks the guard.
3. Projects with a card table:
   `GET /<account_id>/projects.json | jq '.[] | {id, name, boards: [.dock[] | select(.name == "kanban_board") | {id, title}]}'`.
   Ask which board.
4. Columns: `GET /<account_id>/card_tables/<card_table_id>.json | jq '.lists[] | {id, title, type, cards_count}'`.

## 4. Write the config

Ask the user to map the columns (triage, todo, in progress, in review, done; any can be missing) and
which columns are **protected**: cards there cannot be claimed, and the user's own unassigned cards
stop being editable there. Suggest in progress, in review and every done or closing column.

Single board: use the `board` key. If the user already has `board` and wants another one, or wants
several from the start, use `boards` (alias -> board, same shape as `board`) plus `default_board`; keep
the existing board as an alias (ask for a short one, e.g. the project name in lowercase). Put each
board's protected columns in its own `protected_columns` (the guard protects the union with
`guard.protected_columns`). Never drop an existing protected column when editing the config.

Build the JSON following `${CLAUDE_PLUGIN_ROOT}/config/config.example.json`, keeping every key the
existing config.json already has (at least `user_agent`), show it, and after the user approves write
it with the Write tool to `~/.config/basecamp-manager/config.json`. It holds no secrets. Leave out
`workflow` unless the user wants the workflow conventions.

### Adding another board later (reads only)

1. Read config.json (Read tool) and note the aliases and the person id.
2. Steps 3.3 and 3.4 above for the new project: list projects, then its columns. Reads only.
3. Ask for an alias and which columns are protected, show the new `boards` entry, and after approval
   write the whole config back (existing keys unchanged).

## 5. Verify

1. Run `~/.config/basecamp-manager/bcm doctor`. Every line should say ok; fix what it reports.
2. A read works: GET one card of the board and show its title.
3. The guard is active in this session: run `echo "https://3.basecampapi.com/guard-check"`. The guard
   must deny it ("may only be called by a command that starts with curl"). If it prints the text
   instead, the plugin is not enabled: tell the user to check `/plugin` and restart Claude Code.
   **Never test the guard with a real DELETE or any real write.**
4. Tell the user how many days the token has left (the doctor prints it) and that
   the session hook renews it by itself when fewer than three days are left (option `auto_refresh`);
   `bcm refresh` does it by hand, and you warn them if the automatic renewal fails.

## 6. Rules the user can change

Tell the user, once, where the rules live:

- Plugin options (`/plugin` > Installed > basecamp-manager > Configure options): `allow_claim`,
  `allow_comments`, `allow_uploads`, `own_unassigned_edit_minutes`, `auto_refresh`, `card_language`, `use_workflow`.
- `guard.protected_columns` (and each board's `protected_columns`) in config.json.

You never change these yourself to get a write through.
