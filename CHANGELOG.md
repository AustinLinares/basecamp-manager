# Changelog

All notable changes to this plugin. The format follows [Keep a Changelog](https://keepachangelog.com/)
and the project uses [semantic versioning](https://semver.org/). Each release is tagged `vX.Y.Z` and
bumps `version` in `.claude-plugin/plugin.json`; pushes without a bump do not reach installed copies.

## [Unreleased]

## [0.5.0] - 2026-10-17

### Added

- Multiple boards: config.json may hold `boards` (alias -> board, same shape as `board`) plus
  `default_board`. A config with only `board` works unchanged. Each board may carry its own
  `protected_columns`; the guard protects the union of those and `guard.protected_columns`. A
  `boards` section that is not an object of objects, or a `protected_columns` that is not a list of
  integers, blocks every card write (fail closed). Setup assistant, SKILL.md, `config.example.json`,
  `docs/SETUP.md` and both READMEs explain picking a board by alias and adding one with reads only.
- Automatic token refresh: at session start, when the token has 3 days or fewer left, `session_start.py`
  renews it with the same logic as `bcm refresh` (`refresh_token` in `bcm.py`), with a 4 second network
  timeout, no output of any secret and no failure of the session. If it cannot, the old warning is
  shown, and it is not retried for 30 minutes (marker file `refresh-failed`, timestamp only). New plugin
  option `auto_refresh` (default on).

- 19 new tests (123 in total).

### Changed

- `bcm doctor` accepts protected columns from any board. `post_form` takes an optional timeout.

## [0.4.1] - 2026-10-17

### Changed

- Docs only: `briefing.md` says that search ignores a `type=` parameter (filter with jq) and how
  pagination behaves (a short list comes back whole, `x-total-count` gives the total).

## [0.4.0] - 2026-10-17

### Added

- Briefing, search, activity and notifications (`skills/basecamp/references/briefing.md`), all
  read-only and checked against the live API: `GET /my/assignments.json` (plus `due.json` with a
  scope and `completed.json`), `GET /search.json?q=`, `GET /recordings/<id>/events.json` and
  `GET /my/readings.json`. The skill points to them for "what do I have today?", standups, searching
  before creating a card, "what changed on this card?" and "what did I miss?". No guard change was
  needed: reads already pass.
- 12 tests for the quoted-ampersand rule (104 in total).

### Changed

- The guard no longer splits a command at a `&` that sits inside a closed quote with no expansion, so
  URLs with several query parameters (`?q=a&page=2`) work. Checked live: the API ignores a `type=`
  filter on search, so results are filtered with jq.
  The scan is conservative: a comment, backtick, `$(...)` other than the token read, `${`, `$'` or an
  unclosed quote leaves the command untouched, and every `&` keeps separating commands. A `&` outside
  quotes, a delete after a quoted URL and a quote closed early are still denied.

## [0.3.1] - 2026-10-17

### Changed

- Install docs (both READMEs and `docs/SETUP.md`): the two `/plugin` commands are in separate code
  blocks, because pasting both lines at once made Claude Code take the second line as an argument of
  the first.
- Docs and the setup prompt (`skills/basecamp/references/setup.md`) say that `bcm login` must run in a
  regular terminal, not in the Claude chat and not with the `!` prefix (no keyboard input there, so it
  fails with `EOFError`, and the secret must stay out of the session).
- Docs describe the optional setup with Claude in Chrome: Claude fills in the Launchpad form and
  discovers the ids; the user clicks Register, copies the Client ID and Client Secret and runs
  `bcm login` themselves.

## [0.3.0] - 2026-10-17

### Added

- Evidence uploads: the guard allows `POST /attachments.json?name=<file>` with exactly one
  `--data-binary @<file>` of an image, video or PDF, never from the credentials directory. New plugin
  option `allow_uploads` (on by default). The skill shows how to embed the upload in a comment or a
  card description with `<bc-attachment sgid="...">`. Checked against the live API (201 with
  `attachable_sgid`).
- Triage recipe (`skills/basecamp/references/triage.md`): read a whole column, classify by effort,
  type, due date, owner and blockers, propose solutions, and split quick cards across subagents.
- "Why this exists" section in both READMEs.
- 13 upload tests (92 in total).

## [0.2.0] - 2026-10-17

### Added

- `bcm` command line (`scripts/bcm.py`), reachable at `~/.config/basecamp-manager/bcm`:
  - `bcm login`: asks for the OAuth app credentials (secret hidden), opens the browser, catches the
    authorization on a localhost listener (IPv4 and IPv6, `state` checked), saves the token. With a
    redirect URI without a port it asks for the address bar instead. Saves the `User-Agent` email.
  - `bcm refresh`: renews the access token and keeps the refresh token.
  - `bcm doctor`: checks Python, curl, jq, file permissions, config, token, account, person id, days
    left and that the guard denies a simulated delete.
- SessionStart hook (`scripts/session_start.py`): keeps the `bcm` launcher pointing at the installed
  version and tells Claude when fewer than three days are left on the token.
- `scripts/guard.sh`: starts the guard with the first Python 3.8+ it finds.
- 18 tests for the command line, the session hook and the wrapper (79 in total).

### Changed

- Without Python, the guard now blocks only Basecamp access instead of every tool call.
- Setup guide rewritten around `bcm login`; the recommended redirect URI is
  `http://localhost:8765/oauth`.
- Claude may run `bcm refresh` and `bcm doctor` itself; `bcm login` stays in the user's terminal.

## [0.1.0] - 2026-10-17

### Added

- Plugin manifest with user options: `allow_claim`, `allow_comments`, `own_unassigned_edit_minutes`,
  `card_language`, `use_workflow`.
- Marketplace manifest so the repository installs with `/plugin marketplace add`.
- Guard hook (`scripts/guard.py`): no deletes or trashing, writes only to the user's cards, claim
  exception, create-only comments, endpoint and method allowlist, curl-only access to the API host,
  literal URLs, credential protection for Bash, Read, Edit, Write and Grep, fail-closed behavior.
  Configuration comes from `~/.config/basecamp-manager/config.json` and the plugin options; no ids in
  the code.
- Guard test suite (61 cases, including the 21 cases from the project definition).
- `basecamp` skill with API recipes, pitfalls, optional workflow conventions, security model and a
  setup assistant that discovers the ids with reads only.
- Setup guide (`docs/SETUP.md`) with a token exchange and refresh that never print a secret.
