# Setup guide

About ten minutes, once per person and machine. Your credentials stay on your computer: nothing here
is pasted into the Claude chat, and nothing is committed anywhere.

You will end up with four values:

| Value | What it is | Where it lives |
|---|---|---|
| `client_id` | The public id of **your own** OAuth app at 37signals. Identifies the app, not you | Your password manager, and `oauth.json` |
| `client_secret` | The app's password. Whoever has it can impersonate your app | Your password manager, and `oauth.json` |
| Access token | What Claude sends to Basecamp. Acts as **you**, lasts **two weeks** | `~/.config/basecamp-manager/token` |
| Refresh token | Gets a new access token without logging in again | `~/.config/basecamp-manager/oauth.json` |

Both files are created with permissions `600` (only your user can read them) in a `700` directory.
The guard hook stops Claude from reading `oauth.json` at all, and from reading the token other than
to send it to Basecamp.

> Basecamp's current API has no personal API keys: an OAuth app of your own is the only way in.

## Requirements

- A Basecamp account with access to the board you want to use.
- Claude Code **2.1.295 or later** (`claude --version`).
- `curl`, `jq` and Python **3.8 or later** on your `PATH`. On Windows, use Git Bash or WSL.

## 1. Install the plugin

In Claude Code, paste **one command at a time** and press Enter after each (pasting both together
makes Claude Code read the second line as an argument of the first):

```
/plugin marketplace add AustinLinares/basecamp-manager
```

```
/plugin install basecamp-manager@basecamp-manager
```

or in your terminal: `claude plugin marketplace add AustinLinares/basecamp-manager` and then
`claude plugin install basecamp-manager@basecamp-manager`.

Then **start a new Claude Code session** (or run `/reload-plugins`). On start, the plugin creates the
`bcm` command at `~/.config/basecamp-manager/bcm`, which the next steps use.

## 2. Register your OAuth app

> **Optional: let Claude do this with Claude in Chrome.** With the extension connected, Claude opens
> Launchpad and fills in the form below (name, company, website, product, redirect URI). **You** click
> **Register this app** and copy the Client ID and Client Secret yourself; Claude never types or reads
> them, so they stay out of the session.

1. Open <https://launchpad.37signals.com/integrations> and sign in with your Basecamp login.
2. Click **Register one now** (or **Register another application**).
3. Fill in the form:
   - **Name of your application:** anything, e.g. `My Claude Code`. Basecamp shows it when you
     authorize, and in your list of connected apps.
   - **Your company's name / website:** anything; they are only displayed.
   - **Products:** tick **Basecamp**.
   - **Redirect URI:** `http://localhost:8765/oauth`. With a port, `bcm login` catches the
     authorization by itself. If the form rejects it, use `http://localhost/oauth`; then you paste the
     address from the browser bar instead. **Never use someone else's domain:** the authorization
     code would travel to that server.
4. Click **Register this app**. The next page shows your **Client ID** and **Client Secret**. Save
   both in your password manager now.

## 3. Log in (in your own terminal)

Open a regular terminal (Terminal, iTerm, your IDE's terminal), **not** the Claude chat and not with
the `!` prefix (it has no keyboard input, so `bcm login` fails with `EOFError`), and run:

```bash
~/.config/basecamp-manager/bcm login
```

It asks for the Client ID, the Client Secret (hidden while you type), the redirect URI from step 2,
and an email for the `User-Agent` header Basecamp requires. Then it opens your browser:

1. Click **Yes, I'll allow access**.
2. With `http://localhost:8765/oauth`, the tab says "Basecamp authorized" and the terminal continues
   by itself. macOS may ask whether Python can accept incoming connections: allow it (it only listens
   on your own machine, for one request, for at most five minutes).
3. With `http://localhost/oauth`, the tab shows a connection error. That is expected: copy the full
   address from the bar and paste it in the terminal. The code inside expires within minutes.

`bcm login` saves the token, prints how many days it lasts and which Basecamp accounts it reaches. It
never prints a token or the secret.

## 4. Allow curl to Basecamp in Claude Code

In Claude Code, run `/permissions`, open the **Allow** tab, choose **Add a new rule**, and save it at
user level:

```
Bash(curl * https://3.basecampapi.com/*)
```

Without it, Claude Code asks you to approve every read.

## 5. Let Claude pick your board

Back in Claude Code, say **"set up Basecamp"**. Claude reads (never writes) your accounts, your person
id, your projects and board columns, asks you which columns are **protected** (in progress, in review,
done: cards there cannot be claimed), shows you the resulting `config.json` and writes it to
`~/.config/basecamp-manager/config.json` after you approve. That file has ids only, no secrets.

To do it by hand instead, copy `config/config.example.json` from this repository and fill it in. Your
**person id** comes from `GET /my/profile.json` in your account. It is not the `identity.id` that
Launchpad shows; mixing them up makes the guard reject every write.

### Several boards

To work with more than one board, say "add another board" to Claude (it only reads, then shows you
the change before writing). By hand, replace `board` with `boards`, one entry per alias, and name the
default:

```json
"default_board": "main",
"boards": {
  "main":  {"project_id": 1, "card_table_id": 2, "columns": {"todo": 3, "in_progress": 4, "done": 5},
            "protected_columns": [4, 5]},
  "other": {"project_id": 6, "card_table_id": 7, "columns": {"todo": 8, "done": 9},
            "protected_columns": [9]}
}
```

A config with only `board` keeps working. The guard treats the union of `guard.protected_columns` and
every board's `protected_columns` as protected. If `boards` is malformed, writes are blocked until
you fix it.

## 6. Check it works

```bash
~/.config/basecamp-manager/bcm doctor
```

It checks Python, `curl` and `jq`, file permissions, the config, that Basecamp accepts the token,
that `person_id` matches your profile, the days left on the token, and that the guard denies a
simulated delete. Nothing is written to Basecamp. Claude can run it for you too.

## Choose your rules

Run `/plugin`, open **Installed**, select **basecamp-manager**, then **Configure options**:

| Option | Default | Effect |
|---|---|---|
| `allow_claim` | on | Claude may assign an unassigned card to you, in one write, when you ask |
| `allow_comments` | on | Claude may post comments on your cards (never edit or delete them) |
| `allow_uploads` | on | Claude may upload screenshots, recordings and PDFs to embed them in your cards |
| `own_unassigned_edit_minutes` | 0 | How long a card you created stays editable before it has assignees. 0 = no limit |
| `auto_refresh` | on | At the start of a session, renew the token when 3 days or fewer are left (4 second network limit, no secret printed). If it fails, Claude warns you |
| `card_language` | auto | Language for card titles, steps and comments. `auto` follows your messages |
| `use_workflow` | off | Follow the optional workflow conventions (see `skills/basecamp/references/workflow.md`) |

The protected columns live in `guard.protected_columns` in `config.json`. The guard itself cannot be
partially disabled; to turn it off you disable the whole plugin.

## Refresh (every two weeks)

```bash
~/.config/basecamp-manager/bcm refresh
```

With `auto_refresh` on (the default), the session hook renews the token at the start of a session
when fewer than three days are left, without printing anything. If that fails (offline, revoked
refresh token), Claude warns you instead and can run the refresh itself (it prints no secret). If the refresh token stops working, run `bcm login` again; it
offers to reuse your saved app.

## If a secret leaks

If a token or the client secret ever ends up in a chat, a commit or a screenshot: open
<https://launchpad.37signals.com/integrations>, open your app and regenerate its secret (or remove the
app's access from your account), then run `bcm login` again with the new values.

## Troubleshooting setup

| Symptom | Fix |
|---|---|
| `~/.config/basecamp-manager/bcm: No such file` | Start a Claude Code session once after installing the plugin |
| `port 8765 is busy` | Close what uses it, or register another port in your app and run `bcm login --redirect-uri http://localhost:<port>/oauth` |
| The browser says the redirect URI does not match | The URI you typed in `bcm login` must be exactly the one registered in step 2 |
| `authorization refused` | You clicked "No" or closed the page; run `bcm login` again |
| The exchange answers 400 or `invalid_grant` | The code expired or was already used; run `bcm login` again |
