# Security model

## What the guard enforces

The guard is a `PreToolUse` hook that runs before every Bash, Read, Edit, Write and Grep call.

| Rule | How |
|---|---|
| Never delete | `DELETE` and any `/status/trashed` or trash path are denied |
| Only your cards | Before each write the guard GETs the card (or the step's card) and checks `assignees` |
| Your unassigned cards | Editable when you are the creator and the card is outside the protected columns (optionally only for N minutes) |
| Claiming | Only `PUT {"assignee_ids":[you]}` with nothing else, on an unassigned card outside the protected columns, if `allow_claim` |
| Comments | Create only, on your cards, if `allow_comments`; edits and deletes are denied |
| Uploads | One image, video or PDF per call, from a file outside the credentials directory, if `allow_uploads`; it appears only where one of your cards embeds it |
| Several boards | Protected columns are the union of `guard.protected_columns` and every board's `protected_columns`; a malformed `boards` section blocks card writes |
| Allowlist | Any write to an endpoint not on the list, or with another method, is denied |
| curl only | A command that mentions the API host must start with `curl`; `echo`, `python`, `bash -c`, `xargs` are denied |
| Separators | Commands are split at `&`, `;`, `|` and newlines and every piece that mentions the host is checked. A `&` inside a closed quote with no expansion is plain text (`?q=a&page=2`); with a comment, backtick, `$(...)`, `${`, `$'` or an unclosed quote nearby, every `&` splits |
| Literal URLs | A write must target exactly one literal URL inside the configured account |
| Credentials | The token is only readable as `$(cat <token>)` feeding a curl to the API host; `oauth.json` is never readable; Read, Edit, Write and Grep on them are denied |
| Fail closed | If a card cannot be verified, the config is broken, or the guard crashes, the action is blocked |

## What it cannot do

- **It cannot know what the user asked.** "Claim only when asked" and "show before writing" are
  instructions to Claude, not checks. The guard only limits the shape of each write.
- **It only sees Claude Code tool calls.** Your own terminal, other clients and other tools are not
  covered. The token can do anything your Basecamp user can do; the guard is a client-side barrier,
  not a server-side permission.
- **It reads command text.** It protects the normal path (`curl` with literal URLs); it is not a
  sandbox.
- **Anyone at the keyboard can turn it off** by disabling the plugin. That is by design: it protects
  you from an agent's mistakes, not from yourself.
