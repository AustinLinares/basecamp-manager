# Changelog

All notable changes to this plugin. The format follows [Keep a Changelog](https://keepachangelog.com/)
and the project uses [semantic versioning](https://semver.org/). Each release is tagged `vX.Y.Z` and
bumps `version` in `.claude-plugin/plugin.json`; pushes without a bump do not reach installed copies.

## [Unreleased]

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
