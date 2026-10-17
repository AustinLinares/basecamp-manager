# Pitfalls learned the hard way

- **Updating `content` wipes the images** unless you send the full HTML back, including every
  `<bc-attachment>` tag. Build the new content from a fresh GET saved to a file:
  `jq '{content: (.content + "<p>PR: https://...</p>")}' card.json > body.json`, send `body.json`,
  then GET again and check that `bc-attachment` is still in `.content`.
- A **partial update** is safe: `PUT` with only `title` keeps content, steps and assignees.
- **Creating a card does not assign it.** Create first, then `PUT` the `assignee_ids`.
- **Assign to someone else last.** From that moment the card is theirs and the guard blocks you.
- **Step ids** come from a GET of the card after creating the steps, not from the POST responses.
  Steps keep creation order; create them in the order they should appear.
- **Quotes and accents** in a JSON body on the command line break easily. Write the body to a file
  with the Write tool, validate it with `jq -e .`, send it with `-d @file`.
- **Uploading attachments** (`/attachments.json`) is not on the allowlist. Link images in a comment.
- **Variables in the URL** (`$BASE/cards/1.json`) are denied: the guard needs the literal URL to know
  what is being written. A variable for the token is fine.
- **The API host only inside curl.** Even an `echo` or a heredoc that mentions the host is denied.
  Write files with the Write tool.
- **Person id vs identity id.** `identity.id` in authorization.json is the Launchpad login, not the
  person inside the account. The guard needs the person id from `/my/profile.json`.
- **Comments notify** every subscriber. Never post drafts or test comments.
- **zsh** treats a bare run of `=` (like `=====`) as an expansion and errors; do not echo separators.
- **Two Done columns.** Boards often have a regular Done column and Basecamp's own closing column.
  Both belong in `guard.protected_columns`.
