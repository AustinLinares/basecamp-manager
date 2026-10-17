---
name: basecamp
description: Read and manage Basecamp card tables (kanban boards) with curl - read cards with their images and comments, create cards, add and complete steps, comment, move between columns, claim unassigned cards - and set up the Basecamp connection when it is missing. Use whenever the user mentions Basecamp, a Basecamp card, board, column or step, or pastes a basecamp.com link.
---

# Basecamp Manager

You operate the user's Basecamp card tables through the official API with `curl`. The token acts as the
user: everything you write shows up in Basecamp under their name, for their whole team. A guard hook
(`basecamp-manager` plugin) checks every command before it runs. Work with it, never around it.

Files (outside any repository, one set per person):

- Config, no secrets: `~/.config/basecamp-manager/config.json` (see `${CLAUDE_PLUGIN_ROOT}/config/config.example.json`)
- Access token: `~/.config/basecamp-manager/token` (permissions 600). Never print, copy or paste it.
- OAuth secrets: `~/.config/basecamp-manager/oauth.json`. You never open it; the user's own terminal does.

If `BASECAMP_MANAGER_HOME` is set, that directory replaces `~/.config/basecamp-manager`.

## 1. Before anything: is it set up?

Read `~/.config/basecamp-manager/config.json` with the Read tool. If it is missing or lacks
`account_id`, `person_id` or `user_agent`, the token file does not exist, or the user asks to set
up, follow
[references/setup.md](references/setup.md) before doing anything else. Reads work before setup; the
guard blocks every write until `account_id` and `person_id` exist.

## 2. Rules (the guard enforces most of them; you follow all of them)

1. **Never delete**, by any route. Trashing is deleting. Archiving is not on the allowlist either.
2. **Write only to cards assigned to the user.** Everyone else's cards are read-only. A card the user
   created that still has no assignees is editable while it is outside the protected columns.
3. **Claim only on an explicit request in the current message.** Claiming is one write,
   `PUT /card_tables/cards/{id}.json` with exactly `{"assignee_ids":[<person_id>]}`, on an unassigned
   card outside the protected columns. Edit the card in later calls. The guard cannot know whether the
   user asked, so this one is on you.
4. **Show before you write.** Show the exact title, column, assignee, steps or comment and wait for
   approval, unless the user already spelled out that exact content.
5. **Comments are create-only.** They notify everyone subscribed to the card; keep them useful.
6. **Never handle credentials in the chat.** If the user pastes a token or secret, tell them to revoke
   it in Launchpad and generate a new one (see setup).
7. If the guard denies something, read its reason, explain it to the user in their language, and do
   not retry a variant of the same write. Never edit, disable or bypass the hook or its config to get
   a write through; only the user changes the rules (plugin options or `guard` in config.json).

Language: talk to the user in the language they use. Write card text in
`${user_config.card_language}` ("auto" means the language the user writes in).

## 3. How every call looks

The guard only accepts this shape: the command **starts with `curl`**, the URL is a **literal**
`https://3.basecampapi.com/<account_id>/...` (no variables for host or path), and the token is read
with `$(cat <token file>)`, either inline or into a variable that only that `curl` uses.

```bash
T=$(cat ~/.config/basecamp-manager/token); curl -s \
  -H "Authorization: Bearer $T" -H "User-Agent: <user_agent from config>" \
  "https://3.basecampapi.com/<account_id>/card_tables/cards/<id>.json" | jq '{title, column: .parent.title, assignees: [.assignees[].name], steps: [.steps[] | {id, title, completed}]}'
```

- Writes add `-H "Content-Type: application/json"` and `-X PUT` or `-X POST`.
- Long or accented JSON bodies: write the body to a file in the scratchpad with the Write tool, check
  it with `jq -e . <file>`, send it with `-d @<file>`.
- One `curl` per segment. Chain calls with `&&`. Piping a read into `jq` is fine.
- Never write a command that mentions the API host without being that `curl` (no `echo`, heredoc,
  `python`, `bash -c`, `xargs`). Create files with the Write tool instead.
- Use the flat routes (`/card_tables/cards/1.json`). The legacy `/buckets/<project>/...` form also works.

The endpoint table, with bodies and responses, is in [references/api-recipes.md](references/api-recipes.md).
Read [references/pitfalls.md](references/pitfalls.md) before your first update of a card's content.

## 4. Reading a card means reading all of it

Text, steps, comments and attached images. Images often show which screen or component the card is
about. Find `<bc-attachment ... href=".../blobs/<uuid>/download/<file>">` in `.content`, download it
with `curl -sL -o <scratchpad>/<file> "<literal url>"`, and open it with the Read tool. Read comments
with `GET /recordings/<card_id>/comments.json`.

## 5. Common tasks

- **Create a card:** `POST /card_tables/lists/<column_id>/cards.json` with `title` (and `content`).
  It does not take assignees: assign in a second call with `PUT` and `assignee_ids`. Assigning to
  someone else makes the card theirs, so do that **last**, after steps and content.
- **Steps:** create them in order with `POST /card_tables/cards/<id>/steps.json`; take their ids from a
  fresh GET of the card, not from the POST response. Complete with
  `PUT /card_tables/steps/<step_id>/completions.json` and `{"completion":"on"}`.
- **Move:** `POST /card_tables/cards/<id>/moves.json` with `{"column_id": <id>}` (204, no body).
- **Comment:** `POST /recordings/<card_id>/comments.json` with `{"content":"<p>...</p>"}`.
- **Append to the description:** rebuild the content from a GET so attachments survive (pitfalls).

Column ids are in `board.columns` of config.json. To list columns, GET the card table:
`/card_tables/<card_table_id>.json` (`.lists[] | {id, title}`).

If `${user_config.use_workflow}` is `true`, also follow [references/workflow.md](references/workflow.md).

## 6. Token expiry and health

Access tokens last two weeks. A `401` means it expired: run `~/.config/basecamp-manager/bcm refresh`
(it prints no secret), then retry the read. If the refresh fails, the user runs
`~/.config/basecamp-manager/bcm login` in their own terminal; never run `login` yourself, it is
interactive and asks for the secret. When something looks wrong, run
`~/.config/basecamp-manager/bcm doctor` and follow what it reports.

The security model and its honest limits: [references/security-model.md](references/security-model.md).
