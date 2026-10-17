# Optional workflow conventions

Only when the plugin option `use_workflow` is on. These came from one team; adjust them through the
`workflow` section of config.json (title prefixes, the PR line) and ask the user when unsure.

1. **One card per task**, assigned to the user and in the in-progress column while it is worked on.
   If `workflow.title_prefixes` exists, start the title with one of them (`[Backend] Fix the export`).
2. **Steps** are one line each, without assignee or due date: one per batch of work, plus review and
   PR when it helps. Mark each one as it is done.
3. **Deferred decisions** become a small card in the triage column (`board.columns.triage`),
   unassigned, with steps and a line on where the decision came from.
4. **When a PR opens:** append the PR line (`workflow.pr_line`, default `PR: <link>`) to the card
   description, keeping the existing content (see pitfalls); post a comment with the PR link, what it
   does, how it was verified, links to screenshots and anything pending; mark the finished steps; move
   the card to the in-review column.
5. **Cards born from another card** link it in the description (its `app_url`).
6. **Show before writing**, as always, unless the user already gave the exact content.
