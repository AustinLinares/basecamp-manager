# Triage a column

Use when the user wants an overview of many cards ("what is in Todo?", "which ones are quick?",
"review the backlog"). Everything here is read-only until the user picks what to work on.

1. **List** the cards of the column: `GET /card_tables/lists/<column_id>/cards.json`, following the
   `Link: rel="next"` pages. Keep `id`, `title`, `due_on`, `assignees`, `comments_count`, `app_url`.
2. **Read each card fully**: content, steps, comments when `comments_count > 0`, and attached images
   (the image often shows which screen the card is about). For long lists, read in parallel with
   subagents, each one handling a batch and returning a short summary per card.
3. **Classify** each card:
   - **Effort:** quick (under an hour), medium (a few hours), long (a day or more), or unclear.
   - **Type:** bug, feature, chore, question.
   - **Due date:** overdue, due this week, later, none.
   - **Owner:** yours, someone else's, unassigned (claimable only if the user asks).
   - **Blockers:** missing information, waiting on someone, depends on another card.
4. **Report** one table, sorted by due date and then by effort, with a one-line reason per card and the
   card link. Then list the quick and medium cards that are clear enough, each with a proposed
   solution in two or three lines (where in the code, what to change, how to verify).
5. **Offer to work** the cards the user picks. For independent quick cards, offer to split them
   across subagents, one card each. Before writing anything on a card (claim, steps, move, comment),
   follow the normal rules: show the content first, and claim only on an explicit request.

Estimates are guesses from the card text; say so, and mark as "unclear" anything you could not judge
without asking someone.
