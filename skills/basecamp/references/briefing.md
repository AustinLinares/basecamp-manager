# Briefing, search, activity and notifications

Everything here is read-only. Use it for "what do I have today?", "is there already a card about X?",
"what changed on this card?" and "what did I miss?". Endpoints were checked against a live account
on 2026-10-17. Paths are relative to `https://3.basecampapi.com/<account_id>`.

## What do I have? (`GET /my/assignments.json`)

Returns `{priorities: [...], non_priorities: [...]}`, every item of the user across all projects
(cards, steps, to-dos). Each item has `id`, `type` (`card`, `step`, ...), `content` (the title),
`due_on`, `completed`, `assignees`, `comments_count`, `bucket.name` (the project), `parent.title`
(for a card: `Card Table: <column>`) and `app_url`.

```bash
T=$(cat ~/.config/basecamp-manager/token); curl -s -H "Authorization: Bearer $T" -H "User-Agent: <user_agent>" \
  "https://3.basecampapi.com/<account_id>/my/assignments.json" | jq '[.priorities[], .non_priorities[]] | map(select(.type=="card" and .completed==false and (.parent.title | endswith(": Done") | not))) | group_by(.parent.title) | map({column: .[0].parent.title, cards: map({id, title: .content, due_on})})'
```

- A card in a regular "Done" column still has `completed: false`; filter on the column title, as above.
- Due dates: `GET /my/assignments/due.json?scope=<scope>` with `overdue`, `due_today`, `due_tomorrow`,
  `due_later_this_week`, `due_next_week` or `due_later`. Done work: `GET /my/assignments/completed.json`.
- Present it as a short briefing: overdue first, then due today, then what is in progress or in
  review, then the rest by column. Offer to open any card in full (SKILL.md section 4).

## Search (`GET /search.json?q=<text>`)

Use it before creating a card, to avoid a duplicate. Returns recordings of every type: cards
(`Kanban::Card`), steps (`Kanban::Step`), comments, messages, documents. A card's `parent.title` is its
column; a step's is its card.

```bash
T=$(cat ~/.config/basecamp-manager/token); curl -s -H "Authorization: Bearer $T" -H "User-Agent: <user_agent>" \
  "https://3.basecampapi.com/<account_id>/search.json?q=mediciones" | jq '[.[] | {id, type, title: (.title // .content), parent: .parent.title, project: .bucket.name}]'
```

- URL-encode the text (`%20` for a space). Filter by type with jq (`select(.type=="Kanban::Card")`).
- A URL with several query parameters needs `&` inside the quoted URL. The guard accepts that only
  for a closed quote with no `$(...)`, backtick or `${` in it; otherwise it treats `&` as a command
  separator and denies the call. If it denies, drop the extra parameter and filter with jq.
- Paginated: follow `Link: rel="next"` (add `-D -` to see it).

## What changed? (`GET /recordings/<id>/events.json`)

The activity log of one recording (a card, a comment). Each event has `created_at`, `creator.name`,
`action` (`created`, `assignment_changed`, `completed`, `uncompleted`, `content_changed`,
`position_changed`, ...) and `details` (for example `added_person_ids`, `notified_recipient_ids`).
Person ids resolve with `GET /people.json`.

```bash
T=$(cat ~/.config/basecamp-manager/token); curl -s -H "Authorization: Bearer $T" -H "User-Agent: <user_agent>" \
  "https://3.basecampapi.com/<account_id>/recordings/<card_id>/events.json" | jq '[.[] | {at: .created_at, who: .creator.name, action, details}]'
```

- For a standup ("what moved this week?"): read `/my/assignments.json`, then the events of each
  card of the user and keep the ones since the last working day. Say what moved, not the raw log.

## What did I miss? (`GET /my/readings.json`)

The user's notifications: `unreads`, `reads`, `memories` and `bubble_ups`. Each entry has `section`
(`inbox`, ...), `type` (`Bulletin`, `Kanban::Card`, `Comment`, ...), `title`, `bucket_name` (the
project), `creator.name`, `unread_at`, `content_excerpt` and `app_url`. Reading this does not mark
anything as read.

```bash
T=$(cat ~/.config/basecamp-manager/token); curl -s -H "Authorization: Bearer $T" -H "User-Agent: <user_agent>" \
  "https://3.basecampapi.com/<account_id>/my/readings.json" | jq '[.unreads[] | select(.creator.id != "bulletins") | {type, title, project: .bucket_name, from: .creator.name, at: .unread_at, url: .app_url}]'
```

- Skip Basecamp's own announcements (`type == "Bulletin"`) unless the user asks.
- Group by project, newest first, and say which ones mention or comment on the user's cards. To
  answer one, read the card (SKILL.md section 4) and propose the comment; never post unasked.
