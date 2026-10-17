# Basecamp Manager for Claude Code

*[Leer en español](README.es.md)*

A Claude Code plugin to read and manage **Basecamp card tables** from your terminal, with a **guard
hook** that makes it impossible for the agent to delete anything or touch cards that are not yours,
and a **guided setup** that never asks you to paste a secret into the chat.

Unofficial. Not affiliated with 37signals or Anthropic.

## Why this exists

Basecamp's card tables are not built for working through a long list. Getting back to the board after
opening a card takes extra clicks, and reviewing many cards means opening tab after tab. This project
started as a way to skip all that and let the agent go through the list for you.

With the plugin, Claude can:

- **Triage a column in one pass.** It reads every card (text, comments, images, due dates) and sorts
  them into quick wins, longer tasks, cards with deadlines and bugs. Each card gets an effort estimate
  and, when it is clear enough, a proposed solution. Claude can then take on the easy and medium ones
  right away, splitting the work across subagents.
- **Keep the board current while you work.** Cards come up mid-task: a bug, something left pending.
  Claude creates the card or adds the step as soon as it appears, and marks steps as done as the work
  moves forward, so nobody has to stop to update Basecamp by hand.
- **Brief you in a minute.** "What do I have today?" reads your assignments across projects and
  gives overdue, due today, in progress and in review. Claude also searches before creating a card
  (to avoid duplicates), shows what changed on a card, and summarizes your unread notifications.
- **Attach the evidence.** When a PR opens, Claude comments on the card with the link, what changed,
  how it was verified and what is still pending, with the screenshots or recordings embedded right in
  the comment. The steps tell the team what still needs proof.

All from the terminal, without opening Basecamp.

## What's inside

Giving an agent a Basecamp token is risky by default: the token acts as you, it can move, reassign or
trash anyone's cards, and there is no undo. This plugin bundles three things:

1. **A skill** with tested recipes: read cards with their images and comments, create cards, add and
   complete steps, comment, move between columns, claim unassigned cards.
2. **A guard** (`PreToolUse` hook) that runs before every command: no deletes, writes only to your
   cards, an endpoint allowlist, curl only, and no access to your credentials. It fails closed.
3. **A setup assistant** that discovers your account, person and board ids for you, while the token
   exchange happens in your own terminal.

## Install

In Claude Code, paste **one command at a time** and press Enter after each (pasting both together
makes Claude Code read the second line as an argument of the first):

```
/plugin marketplace add AustinLinares/basecamp-manager
```

```
/plugin install basecamp-manager@basecamp-manager
```

Claude Code asks for the plugin options (you can keep the defaults). Start a new session, then follow
[docs/SETUP.md](docs/SETUP.md): register your OAuth app, run `~/.config/basecamp-manager/bcm login` in
your terminal, and say **"set up Basecamp"** in Claude Code. The guard is active as soon as the plugin
is enabled.

> **Run `bcm login` in a regular terminal** (Terminal, iTerm, your IDE's terminal), **not in the Claude
> chat** and not with the `!` prefix: it asks for your Client Secret, which must never end up in the
> session, and `!` has no keyboard input anyway.

**Let Claude set it up with Claude in Chrome (optional).** If you give Claude the
[Claude in Chrome](https://claude.ai/chrome) extension, say **"set up Basecamp"** and it can fill in
the OAuth app form at Launchpad and discover your account, person and board ids. It never types
credentials: **you** click **Register this app**, copy the Client ID and Client Secret into your
password manager, and run `bcm login` in your terminal so they stay out of the session.

The plugin's command line, always at `~/.config/basecamp-manager/bcm`:

| Command | What it does |
|---|---|
| `bcm login` | Opens the browser, catches the authorization on localhost and saves the token without printing it |
| `bcm refresh` | Renews the access token (every two weeks; Claude reminds you and can run it) |
| `bcm doctor` | Checks tools, permissions, config, token, person id and the guard |

Updates: run `/plugin`, **Marketplaces**, select `basecamp-manager`, and turn on auto-update, or
update by hand with `claude plugin update basecamp-manager@basecamp-manager`.

## Compatibility

| | Version |
|---|---|
| Plugin | **0.4.1** (see [CHANGELOG.md](CHANGELOG.md)) |
| Claude Code | **2.1.295 or later** (needs `onFailure: "block"` so the guard fails closed). Tested on 2.1.301 |
| Basecamp API | Basecamp 5 API (`3.basecampapi.com`), endpoints checked against the [official docs](https://github.com/basecamp/bc3-api) on 2026-10-17 |
| Python | 3.8 or later, standard library only (runs the guard) |
| Tools | `curl`, `jq` |
| OS | Tested on macOS. Linux should work. Windows needs Git Bash or WSL (untested) |

## What the guard enforces

| Rule | Effect |
|---|---|
| Never delete | `DELETE` and trashing are always denied |
| Only your cards | Before each write the guard reads the card and checks you are an assignee |
| Your new cards | A card you created stays editable while unassigned and outside the protected columns |
| Claiming | An unassigned card can be assigned to you in one exact write, if `allow_claim` is on |
| Comments | Create only, on your cards, if `allow_comments` is on |
| Uploads | Only images, videos and PDFs, embedded in your cards, if `allow_uploads` is on |
| Allowlist | Any other write endpoint or method is denied |
| curl only | The Basecamp host may only appear in a command that starts with `curl`, with literal URLs |
| Credentials | Claude cannot print, copy or open your token or OAuth secrets |
| Fail closed | If it cannot verify something, it blocks |

Rules are configurable per person: plugin options in `/plugin` and `guard.protected_columns` in
`~/.config/basecamp-manager/config.json`. Details: [security model](skills/basecamp/references/security-model.md).

## Honest limits

- The guard **cannot know what you asked for**. Rules like "claim only when I ask" are instructions
  to Claude; the guard only restricts the shape of each write.
- It only covers **Claude Code tool calls**. Your token can still do anything your Basecamp user can
  do from any other tool. It is a client-side barrier, not a server permission.
- It inspects command text. It protects the normal path; it is not a sandbox.
- It acts with **your identity**: everything Claude writes appears in Basecamp under your name.

## Where your data lives

```
~/.config/basecamp-manager/
  config.json   ids and rules, no secrets
  token         access token (600)
  oauth.json    refresh token and OAuth app credentials (600), never readable by Claude
  token-info.json  token expiry date only
  bcm           launcher for the plugin's command line, kept current by the plugin
```

`BASECAMP_MANAGER_HOME` overrides the directory. Nothing is stored in this repository.

## Development

```bash
python3 -m unittest discover -s tests     # 92 tests, nothing reaches Basecamp
claude plugin validate .                   # marketplace manifest
claude plugin validate .claude-plugin/plugin.json
claude --plugin-dir .                      # try the plugin without installing it
```

Layout:

```
.claude-plugin/   plugin.json (manifest, options) and marketplace.json
hooks/hooks.json  registers the guard and the session hook
scripts/guard.sh  finds Python and starts the guard
scripts/guard.py  the guard
scripts/bcm.py    login, refresh, doctor
scripts/session_start.py  keeps the bcm launcher current, warns before the token expires
skills/basecamp/  the skill and its references
config/           config.example.json
docs/SETUP.md     setup guide
tests/            guard tests
```

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "Python 3.8 or later was not found" | Without Python the guard blocks only Basecamp access; install Python 3 and restart Claude Code |
| `ERR_CONNECTION_REFUSED` after authorizing | Expected. The `code` is in the address bar |
| The token exchange fails | The `code` expired or was already used. Authorize again |
| HTTP 400 | Missing `User-Agent` |
| HTTP 401 | The token expired. Run `~/.config/basecamp-manager/bcm refresh` |
| Anything else | Run `~/.config/basecamp-manager/bcm doctor` |
| "not configured" | `config.json` lacks `account_id` or `person_id`. Say "set up Basecamp" |
| A legitimate write is blocked | The card is not assigned to you, it is in a protected column, or the endpoint is not on the allowlist |
| A card I assigned to someone else is now read-only | By design. Assign to others last |

## License

[MIT](LICENSE) © 2026 Austin Airton Linares Castillo
