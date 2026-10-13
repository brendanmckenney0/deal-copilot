# Testing deal-copilot headlessly through Slack

The Slack bot is the headless demo: the same fused ask pipeline as the
web UI, reachable from Slack via Socket Mode (no public URL needed —
the bot connects outbound to Slack).

## 1. Create the Slack app (one time, ~5 minutes)

1. Go to **https://api.slack.com/apps** → *Create New App* → *From
   scratch*. Name it `deal-copilot`, pick your workspace.
2. **Enable Socket Mode**: *Settings → Socket Mode* → toggle on.
   Create an **App-Level Token** named `socket`, add the
   `connections:write` scope, copy the token — it starts with
   `xapp-`. This is `SLACK_APP_TOKEN`.
3. **Add bot scopes**: *Features → OAuth & Permissions → Scopes →
   Bot Token Scopes*, add:
   - `app_mentions:read`
   - `chat:write`
   - `im:read`
   - `im:history`
   - `commands`
4. **Subscribe to events**: *Features → Event Subscriptions* →
   toggle on, then *Subscribe to bot events* → add
   `app_mention` and `message.im`.
5. **Create the slash command**: *Features → Slash Commands* →
   *Create New Command*: command `/deadlines`, short description
   `Upcoming lease critical dates`. (With Socket Mode the request
   URL is not needed.)
6. **Install the app**: *Settings → Install App* → *Install to
   Workspace* → allow. Copy the **Bot User OAuth Token** — it
   starts with `xoxb-`. This is `SLACK_BOT_TOKEN`.

## 2. Install and run the bot

```bash
cd deal-copilot
source .venv/bin/activate
pip install -r requirements-slack.txt
PROVIDER=local python scripts/build_index.py   # (re)build the demo index
SLACK_BOT_TOKEN="xoxb-..." SLACK_APP_TOKEN="xapp-..." python slack_bot.py
```

**Success:** `deal-copilot Slack bot starting (Socket Mode)...` with
no errors. Leave it running.

> Tokens are secrets: keep them in your shell session (or a password
> manager), never commit them.

## 3. Talk to it

- **DM the bot** (find `deal-copilot` in Slack's Apps section):
  `When does the Copperline Fitness lease expire?`
- **@-mention it** in any channel it's invited to:
  `@deal-copilot Compare base rent across leases`
- **`/deadlines`** — the critical-date diary: every renewal notice
  and expiration across indexed leases, sorted with days-until.

**What good looks like:** the reply starts with a route badge like
`[structured]`, gives the answer, and ends with `_Sources: ..._`
citations — the same pipeline as the web UI, no browser involved.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Set SLACK_BOT_TOKEN ...` on startup | Export both tokens in the same shell session |
| Bot doesn't respond to DMs | Check the app is installed to the workspace and the bot is in your Apps list |
| `@deal-copilot` ignored in a channel | Invite the bot to the channel first (`/invite @deal-copilot`) |
| `/deadlines` says "command not found" | Re-check step 1.5 — the slash command must be created in the app config |
| Answers say "I don't know" for everything | Rebuild the index (step 2) — the bot reads the same `data/` the server uses |
