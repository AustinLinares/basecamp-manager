# Setup guide

This takes about ten minutes, once per person and machine. Your credentials stay on your computer:
nothing here is pasted into the Claude chat, and nothing is committed anywhere.

You will end up with four values:

| Thing | What it is | Where it lives |
|---|---|---|
| `client_id` | The public id of **your own** OAuth app at 37signals. Identifies the app, not you | Your password manager, and `oauth.json` |
| `client_secret` | The app's password. Whoever has it can impersonate your app | Your password manager, and `oauth.json` |
| Access token | What Claude sends to Basecamp. Acts as **you**, lasts **two weeks** | `~/.config/basecamp-manager/token` |
| Refresh token | Gets a new access token without logging in again | `~/.config/basecamp-manager/oauth.json` |

Both files are created with permissions `600` (only your user can read them) in a `700` directory.
The guard hook stops Claude from reading `oauth.json` at all, and from reading the token other than
to send it to Basecamp.

> Claude can walk you through all of this: install the plugin and say "set up Basecamp". It runs the
> discovery for you and tells you when to switch to your own terminal.

## Requirements

- A Basecamp account with access to the board you want to use.
- Claude Code **2.1.295 or later** (`claude --version`).
- `curl`, `jq` and `python3` on your `PATH`. On Windows, use Git Bash or WSL so `python3` resolves.

## 1. Register your OAuth app

1. Open <https://launchpad.37signals.com/integrations> and sign in with your Basecamp login.
2. Click **Register one now** (or **Register another application**).
3. Fill in the form:
   - **Name of your application:** anything, e.g. `My Claude Code`. Basecamp shows it when you
     authorize, and in your list of connected apps.
   - **Your company's name / website:** anything; they are only displayed.
   - **Products:** tick **Basecamp** (shown as Basecamp 5 or 4 depending on the moment; it is the one
     whose API this plugin uses).
   - **Redirect URI:** `http://localhost/oauth`. If the form rejects it, use `https://localhost/oauth`
     and use that same value everywhere below. **Never use someone else's domain:** the authorization
     code would travel to that server.
4. Click **Register this app**. The next page shows your **Client ID** and **Client Secret**. Save
   both in your password manager now.

## 2. Authorize and copy the code

Open this URL in your browser, replacing `YOUR_CLIENT_ID`:

```
https://launchpad.37signals.com/authorization/new?response_type=code&client_id=YOUR_CLIENT_ID&redirect_uri=http%3A%2F%2Flocalhost%2Foauth
```

Click **Yes, I'll allow access**. The browser lands on `http://localhost/oauth?code=...` and shows a
connection error. **That is expected:** nothing listens there. The `code` is in the address bar.
Copy it and do step 3 right away; it expires within minutes and works only once.

## 3. Exchange the code for a token (in your own terminal)

Open a regular terminal, **not** the Claude chat, and paste this block. It asks for the three values
without echoing the secret, never prints a token, and keeps the secret out of your shell history.

```bash
mkdir -p ~/.config/basecamp-manager && chmod 700 ~/.config/basecamp-manager && cd ~/.config/basecamp-manager
umask 077
printf 'client_id: '; read -r CLIENT_ID
printf 'client_secret: '; stty -echo; read -r CLIENT_SECRET; stty echo; echo
printf 'code: '; read -r CODE
curl -s -X POST https://launchpad.37signals.com/authorization/token \
  -d grant_type=authorization_code -d redirect_uri=http://localhost/oauth \
  --data-urlencode "client_id=$CLIENT_ID" --data-urlencode "client_secret=$CLIENT_SECRET" \
  --data-urlencode "code=$CODE" > response.json
if jq -e .access_token response.json >/dev/null; then
  jq --arg id "$CLIENT_ID" --arg secret "$CLIENT_SECRET" '. + {client_id: $id, client_secret: $secret}' response.json > oauth.json
  jq -r .access_token oauth.json > token
  echo "Saved. Token valid for $(( $(jq .expires_in oauth.json) / 86400 )) days."
else
  echo "The exchange failed:"; jq . response.json
fi
rm -f response.json; unset CLIENT_ID CLIENT_SECRET CODE
```

If you used `https://localhost/oauth` in step 1, change `redirect_uri` in the block to match.

## 4. Allow curl to Basecamp in Claude Code

In Claude Code, run `/permissions`, open the **Allow** tab, choose **Add a new rule**, save it at user
level:

```
Bash(curl * https://3.basecampapi.com/*)
```

Without it, Claude Code asks you to approve every read.

## 5. Let Claude discover your ids

Back in Claude Code, say **"set up Basecamp"**. Claude reads (never writes) your accounts, your
person id, your projects and board columns, asks you which columns are **protected** (in progress, in
review, done: cards there cannot be claimed), shows you the resulting `config.json` and writes it to
`~/.config/basecamp-manager/config.json` after you approve. That file has ids only, no secrets.

If you prefer to do it by hand, copy `config/config.example.json` from this repository and fill it in.
Your **person id** comes from `GET /my/profile.json` in your account. It is not the `identity.id` that
Launchpad shows; mixing them up makes the guard reject every write.

## 6. Check it works

Claude finishes setup by reading one card and running a harmless command that mentions the Basecamp
host outside `curl`. The guard must deny it. If it does not, open `/plugin`, make sure
`basecamp-manager` is enabled, and restart Claude Code. **Never test the guard with a real DELETE.**

## Choose your rules

Run `/plugin`, open **Installed**, select **basecamp-manager**, then **Configure options**:

| Option | Default | Effect |
|---|---|---|
| `allow_claim` | on | Claude may assign an unassigned card to you, in one write, when you ask |
| `allow_comments` | on | Claude may post comments on your cards (never edit or delete them) |
| `own_unassigned_edit_minutes` | 0 | How long a card you created stays editable before it has assignees. 0 = no limit |
| `card_language` | auto | Language for card titles, steps and comments. `auto` follows your messages |
| `use_workflow` | off | Follow the optional workflow conventions (see `skills/basecamp/references/workflow.md`) |

The protected columns live in `guard.protected_columns` in `config.json`. The guard itself cannot be
partially disabled; to turn it off you disable the whole plugin.

## Refresh (every two weeks)

When Claude reports a `401`, or before the date Claude gave you at setup, run this in your own
terminal:

```bash
cd ~/.config/basecamp-manager && umask 077
curl -s -X POST https://launchpad.37signals.com/authorization/token -d grant_type=refresh_token \
  --data-urlencode "refresh_token=$(jq -r .refresh_token oauth.json)" \
  --data-urlencode "client_id=$(jq -r .client_id oauth.json)" \
  --data-urlencode "client_secret=$(jq -r .client_secret oauth.json)" > response.json
if jq -e .access_token response.json >/dev/null; then
  jq -s '.[0] * .[1]' oauth.json response.json > oauth.new && mv oauth.new oauth.json
  jq -r .access_token oauth.json > token && echo "Token refreshed."
else
  echo "Refresh failed:"; jq . response.json
fi
rm -f response.json
```

If the refresh token itself stops working, repeat steps 2 and 3.

## If a secret leaks

If a token or the client secret ever ends up in a chat, a commit or a screenshot: open
<https://launchpad.37signals.com/integrations>, open your app and revoke or regenerate its secret
(or remove the app's access from your account), then redo steps 1 to 3.
