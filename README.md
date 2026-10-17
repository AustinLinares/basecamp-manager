# Basecamp Manager for Claude Code

*[Leer en español](README.es.md)*

A Claude Code plugin to read and manage **Basecamp card tables** from your terminal, with a **guard
hook** that makes it impossible for the agent to delete anything or touch cards that are not yours,
and a **guided setup** that never asks you to paste a secret into the chat.

Unofficial. Not affiliated with 37signals or Anthropic.

## Why

Giving an agent a Basecamp token is risky by default: the token acts as you, it can move, reassign or
trash anyone's cards, and there is no undo. This plugin bundles three things:

1. **A skill** with tested recipes: read cards with their images and comments, create cards, add and
   complete steps, comment, move between columns, claim unassigned cards.
2. **A guard** (`PreToolUse` hook) that runs before every command: no deletes, writes only to your
   cards, an endpoint allowlist, curl only, and no access to your credentials. It fails closed.
3. **A setup assistant** that discovers your account, person and board ids for you, while the token
   exchange happens in your own terminal.

## Install

In Claude Code:

```
/plugin marketplace add AustinLinares/basecamp-manager
/plugin install basecamp-manager@basecamp-manager
```

Claude Code asks for the plugin options (you can keep the defaults), then say **"set up Basecamp"**
and follow [docs/SETUP.md](docs/SETUP.md). The guard is active as soon as the plugin is enabled.

Updates: run `/plugin`, **Marketplaces**, select `basecamp-manager`, and turn on auto-update, or
update by hand with `claude plugin update basecamp-manager@basecamp-manager`.

## Compatibility

| | Version |
|---|---|
| Plugin | **0.1.0** (see [CHANGELOG.md](CHANGELOG.md)) |
| Claude Code | **2.1.295 or later** (needs `onFailure: "block"` so the guard fails closed). Tested on 2.1.301 |
| Basecamp API | Basecamp 5 API (`3.basecampapi.com`), endpoints checked against the [official docs](https://github.com/basecamp/bc3-api) on 2026-10-17 |
| Python | 3.8 or later, standard library only (runs the guard) |
| Tools | `curl`, `jq` |
| OS | Tested on macOS. Linux should work. Windows needs Git Bash or WSL with `python3` on the `PATH` (untested) |

## What the guard enforces

| Rule | Effect |
|---|---|
| Never delete | `DELETE` and trashing are always denied |
| Only your cards | Before each write the guard reads the card and checks you are an assignee |
| Your new cards | A card you created stays editable while unassigned and outside the protected columns |
| Claiming | An unassigned card can be assigned to you in one exact write, if `allow_claim` is on |
| Comments | Create only, on your cards, if `allow_comments` is on |
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
```

`BASECAMP_MANAGER_HOME` overrides the directory. Nothing is stored in this repository.

## Development

```bash
python3 -m unittest discover -s tests     # guard tests, nothing reaches Basecamp
claude plugin validate .                   # marketplace manifest
claude plugin validate .claude-plugin/plugin.json
claude --plugin-dir .                      # try the plugin without installing it
```

Layout:

```
.claude-plugin/   plugin.json (manifest, options) and marketplace.json
hooks/hooks.json  registers the guard
scripts/guard.py  the guard
skills/basecamp/  the skill and its references
config/           config.example.json
docs/SETUP.md     setup guide
tests/            guard tests
```

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Every tool call is blocked with a hook error | The guard could not start, usually because `python3` is not on the `PATH`. Install Python 3 or disable the plugin |
| `ERR_CONNECTION_REFUSED` after authorizing | Expected. The `code` is in the address bar |
| The token exchange fails | The `code` expired or was already used. Authorize again |
| HTTP 400 | Missing `User-Agent` |
| HTTP 401 | The token expired. See "Refresh" in [docs/SETUP.md](docs/SETUP.md) |
| "not configured" | `config.json` lacks `account_id` or `person_id`. Say "set up Basecamp" |
| A legitimate write is blocked | The card is not assigned to you, it is in a protected column, or the endpoint is not on the allowlist |
| A card I assigned to someone else is now read-only | By design. Assign to others last |

## License

[MIT](LICENSE) © 2026 Austin Airton Linares Castillo
