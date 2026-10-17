# Setup assistant (for Claude)

Goal: take the user from nothing to a working connection without any secret passing through the chat.
The human-facing guide with every screen and command is `${CLAUDE_PLUGIN_ROOT}/docs/SETUP.md`; send
the user there for the steps they run themselves. Go step by step, check each one, and skip the steps
that are already done.

## 0. Check what exists

```bash
command -v curl jq python3; ls -l ~/.config/basecamp-manager/ 2>/dev/null
```

- `curl`, `jq` and `python3` are required. On Windows, `python3` must resolve (Git Bash or WSL);
  if only `py` or `python` exists, tell the user the guard cannot run and point them to the
  troubleshooting section of the README.
- `token` present and `600`: skip to step 3. Never `cat` it; `ls -l` is enough.
- `config.json` complete (`account_id`, `person_id`, `user_agent`, `guard.protected_columns`): skip to step 5.

## 1. OAuth app and token (the user does this, in their own terminal)

Tell the user to follow `docs/SETUP.md` sections 1 to 3. Summarize what they will do:

1. Register an app at `https://launchpad.37signals.com/integrations` with redirect URI
   `http://localhost/oauth`. Keep `client_id` and `client_secret` in a password manager.
2. Open the authorization URL, approve, and copy the `code` from the address bar (the browser shows a
   connection error; that is expected).
3. Run the token exchange **in their own terminal**, which writes `oauth.json` and `token` without
   printing them.

Never ask for the `client_secret`, the `code` or a token in the chat. If the user pastes one, tell
them to revoke the app's access in Launchpad and start over, and do not use the pasted value.

**Optional guided mode with Claude in Chrome.** If the user wants it and the browser tools are
available, you can open the Launchpad integrations page and explain each field. Limits: you never type
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

Use the common call shape from SKILL.md. Before the config exists, use a provisional User-Agent such
as `basecamp-manager setup (<user's email>)`; ask the user which email to use, since Basecamp asks for
a contact in the User-Agent.

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

Build the JSON following `${CLAUDE_PLUGIN_ROOT}/config/config.example.json`, show it, and after the
user approves write it with the Write tool to `~/.config/basecamp-manager/config.json`. It holds no
secrets. Leave out `workflow` unless the user wants the workflow conventions.

## 5. Verify

1. A read works: GET one card of the board and show its title.
2. The guard is active: run `echo "https://3.basecampapi.com/guard-check"`. The guard must deny it
   ("may only be called by a command that starts with curl"). If it prints the text instead, the
   plugin is not enabled: tell the user to check `/plugin` and restart Claude Code. **Never test the
   guard with a real DELETE or any real write.**
3. Token expiry: `GET https://3.basecampapi.com/authorization.json | jq .expires_at`. Tell the user
   the date and that the refresh is in `docs/SETUP.md`, section "Refresh".

## 6. Rules the user can change

Tell the user, once, where the rules live:

- Plugin options (`/plugin` > Installed > basecamp-manager > Configure options): `allow_claim`,
  `allow_comments`, `own_unassigned_edit_minutes`, `card_language`, `use_workflow`.
- `guard.protected_columns` in config.json.

You never change these yourself to get a write through.
