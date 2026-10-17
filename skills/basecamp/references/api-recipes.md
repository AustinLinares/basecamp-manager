# API recipes

Base URL: `https://3.basecampapi.com/<account_id>`. Every request carries
`-H "Authorization: Bearer $T"` and `-H "User-Agent: <user_agent>"` (Basecamp answers 400 without a
User-Agent). Writes also carry `-H "Content-Type: application/json"`. The paths below are the flat,
canonical routes; `/buckets/<project_id>/...` in front of them also works.

Checked against the official docs (github.com/basecamp/bc3-api) on 2026-10-17, Basecamp 5 API.

## Reads (always allowed)

| What | Call | Useful jq |
|---|---|---|
| Who am I, which accounts | `GET https://3.basecampapi.com/authorization.json` | `.accounts[] \| select(.product=="bc3")`, `.expires_at` |
| My person id in the account | `GET /my/profile.json` | `.id` |
| Projects and their boards | `GET /projects.json` | `.[] \| {id, name, boards: [.dock[] \| select(.name=="kanban_board")]}` |
| A card table and its columns | `GET /card_tables/<card_table_id>.json` | `.lists[] \| {id, title, cards_count}` |
| Cards in a column | `GET /card_tables/lists/<column_id>/cards.json` (paginated) | `.[] \| {id, title, assignees: [.assignees[].name]}` |
| A card | `GET /card_tables/cards/<card_id>.json` | `{title, content, column: .parent.title, assignees, steps, comments_count}` |
| A step | `GET /card_tables/steps/<step_id>.json` | `.parent.id` is the card |
| Comments of a card | `GET /recordings/<card_id>/comments.json` (paginated) | `.[] \| {creator: .creator.name, created_at, content}` |
| People in the account | `GET /people.json` | `.[] \| {id, name}` |
| An attached image | `GET /blobs/<uuid>/download/<file>` with `curl -sL -o <file>` | open it with Read |

Paginated lists send a `Link: <...>; rel="next"` header; add `-D -` to see it and keep reading until
there is none.

## Writes (allowlist; anything else is denied by the guard)

| What | Call | Body | Answer |
|---|---|---|---|
| Create a card | `POST /card_tables/lists/<column_id>/cards.json` | `{"title": "...", "content": "<p>html</p>", "due_on": "YYYY-MM-DD", "notify": false}` (only `title` required) | 201 + card |
| Update a card | `PUT /card_tables/cards/<card_id>.json` | any of `title`, `content`, `due_on`, `assignee_ids` (partial: what you omit stays) | 200 + card |
| Claim a card | `PUT /card_tables/cards/<card_id>.json` | exactly `{"assignee_ids": [<person_id>]}` | 200 |
| Move a card | `POST /card_tables/cards/<card_id>/moves.json` | `{"column_id": <id>, "position": 1}` (`position` optional, 1-based) | 204 |
| Create a step | `POST /card_tables/cards/<card_id>/steps.json` | `{"title": "..."}` | 201 |
| Update a step | `PUT /card_tables/steps/<step_id>.json` | `{"title": "..."}` | 200 |
| Complete / reopen a step | `PUT /card_tables/steps/<step_id>/completions.json` | `{"completion": "on"}` or `"off"` | 200 |
| Reorder a step | `POST /card_tables/cards/<card_id>/positions.json` | `{"source_id": <step_id>, "position": 1}` | 204 |
| Comment | `POST /recordings/<card_id>/comments.json` | `{"content": "<p>html</p>"}` | 201 |

Notes:

- Creating a card does **not** accept `assignee_ids`. Create, add steps, then assign with `PUT`.
- `"assignee_ids": []` removes every assignee. `"due_on": null` clears the due date.
- A 429 means rate limited: wait the `Retry-After` seconds and retry once.
- A 401 means the token expired (two weeks): the user refreshes it in their own terminal.

## Examples

Read a card with its steps:

```bash
T=$(cat ~/.config/basecamp-manager/token); curl -s -H "Authorization: Bearer $T" -H "User-Agent: basecamp-manager (you@example.com)" \
  "https://3.basecampapi.com/1234567/card_tables/cards/111.json" | jq '{title, column: .parent.title, assignees: [.assignees[].name], steps: [.steps[] | {id, title, completed}]}'
```

Create a card from a body file written with the Write tool:

```bash
jq -e . /path/to/scratchpad/card.json >/dev/null && T=$(cat ~/.config/basecamp-manager/token); curl -s -X POST \
  -H "Authorization: Bearer $T" -H "User-Agent: basecamp-manager (you@example.com)" -H "Content-Type: application/json" \
  -d @/path/to/scratchpad/card.json "https://3.basecampapi.com/1234567/card_tables/lists/333/cards.json" | jq '{id, title, app_url}'
```

Complete a step:

```bash
T=$(cat ~/.config/basecamp-manager/token); curl -s -X PUT -H "Authorization: Bearer $T" -H "User-Agent: basecamp-manager (you@example.com)" \
  -H "Content-Type: application/json" -d '{"completion":"on"}' "https://3.basecampapi.com/1234567/card_tables/steps/555/completions.json" | jq '{title, completed}'
```
