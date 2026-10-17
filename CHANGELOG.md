# Changelog

All notable changes to this plugin. The format follows [Keep a Changelog](https://keepachangelog.com/)
and the project uses [semantic versioning](https://semver.org/). Each release is tagged `vX.Y.Z` and
bumps `version` in `.claude-plugin/plugin.json`; pushes without a bump do not reach installed copies.

## [Unreleased]

Planned for 0.2.0: setup scripts (local OAuth callback listener, token refresh, `doctor` with token
expiry warning).

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
