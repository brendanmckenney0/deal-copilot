"""deal-copilot as a Slack bot (headless ask-as-a-service).

Runs the fused ask pipeline behind Slack Socket Mode — no public URL
needed; the bot connects outbound. This is the headless demo: the same
/ask logic the web UI uses, reachable from where people already work.

Setup:
  1. Create a Slack app at https://api.slack.com/apps
  2. Enable Socket Mode; add scopes: app_mentions:read, chat:write,
     im:read, im:history, commands
  3. Create the /deadlines slash command (see docs/slack-setup.md)
  4. Install the app to your workspace; copy the Bot Token (xoxb-...)
     and App Token (xapp-...)
  5. pip install -r requirements-slack.txt
  6. Build the index first:  PROVIDER=local python scripts/build_index.py
  7. Run:  SLACK_BOT_TOKEN=xoxb-... SLACK_APP_TOKEN=xapp-... \\
             python slack_bot.py

Then DM the bot or @-mention it in a channel:
  @deal-copilot When does the Copperline Fitness lease expire?
  /deadlines
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from entities.store import EntityStore  # noqa: E402
from providers import get_provider, load_state  # noqa: E402
from query.ask import Asker  # noqa: E402

DATA = ROOT / "data"

# ---------------------------------------------------------------- setup ---

BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
APP_TOKEN = os.environ.get("SLACK_APP_TOKEN", "")

if not BOT_TOKEN or not APP_TOKEN:
    sys.exit("Set SLACK_BOT_TOKEN (xoxb-...) and SLACK_APP_TOKEN (xapp-...) "
             "— see the module docstring / docs/slack-setup.md.")

load_state(DATA / "tfidf.json")  # same embedding space as the index
_store = EntityStore(str(DATA / "entities.db"))
_asker = Asker(_store, DATA / "chroma", get_provider())


# ------------------------------------------------------------ formatting ---

def _fmt_table(table: dict | None) -> str:
    if not table or not table.get("rows"):
        return ""
    cols = table["columns"]
    lines = [" | ".join(cols), " | ".join("---" for _ in cols)]
    for row in table["rows"]:
        lines.append(" | ".join(str(row.get(c, "")) for c in cols))
    return "\n```\n" + "\n".join(lines) + "\n```"


def _fmt_citations(cites: list) -> str:
    seen = []
    for c in cites:
        if isinstance(c, dict):
            s = f"{c.get('source', '?')} p.{c.get('page', '?')}"
        else:
            s = str(c)
        if s not in seen:
            seen.append(s)
    return "_Sources: " + ", ".join(seen) + "_" if seen else ""


def format_answer(result: dict) -> str:
    route = result.get("route", "?")
    parts = [f"*[{route}]* {result.get('answer', '').strip()}"]
    table = _fmt_table(result.get("table"))
    if table:
        parts.append(table)
    cites = _fmt_citations(result.get("citations", []))
    if cites:
        parts.append(cites)
    text = "\n\n".join(p for p in parts if p)
    return text[:3900]  # Slack message safety margin


# ----------------------------------------------------------------- ask ---

def handle_question(question: str) -> str:
    question = question.strip()
    if not question:
        return ("Ask me about the portfolio — e.g. `When does the "
                "Copperline Fitness lease expire?` — or try `/deadlines`.")
    try:
        return format_answer(_asker.ask(question))
    except Exception as exc:  # noqa: BLE001 - surface, don't crash
        return f":warning: Something went wrong: `{type(exc).__name__}: {exc}`"


# ----------------------------------------------------------- /deadlines ---

def _parse_date(s: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(s.strip())
    except (ValueError, AttributeError):
        return None


def get_deadlines(today: dt.date | None = None) -> list[str]:
    """Critical-date diary lines, sorted. Pure logic — no Slack needed."""
    today = today or dt.date.today()
    items = []  # (date, label, who, source)
    for rec in _store.get_extractions(doc_type="lease"):
        fields = rec.get("fields", {})
        prop = _store.get_property(rec.get("property_id") or -1) or {}
        pname = prop.get("canonical_name", "?")
        tenant = (fields.get("tenant_name", {}).get("value") or "").strip()
        who = tenant or pname
        for key, label in (("renewal_notice_date", "renewal notice"),
                           ("expiration_date", "lease expiration")):
            f = fields.get(key, {})
            if f.get("status") != "ok":
                continue
            d = _parse_date(str(f["value"]))
            if not d:
                continue
            items.append((d, label, who, rec.get("source_file", "?")))
    items.sort()
    lines = []
    for d, label, who, src in items:
        delta = (d - today).days
        when = (f"in {delta} days" if delta > 0 else
                "today" if delta == 0 else
                f"{-delta} days ago :warning:")
        lines.append(f"• *{d.isoformat()}* ({when}) — {label}: {who} "
                     f"_{src}_")
    return lines


# --------------------------------------------------------------- wiring ---

def build_app():
    """Create the Slack app. Isolated here (not at import) so the pure
    logic above stays testable without Slack tokens or network."""
    from slack_bolt import App

    app = App(token=BOT_TOKEN)

    @app.event("app_mention")
    def on_mention(event, say):
        # strip the "<@BOTID>" mention prefix
        text = event.get("text", "")
        question = " ".join(
            tok for tok in text.split() if not tok.startswith("<@")).strip()
        say(handle_question(question))

    @app.event("message")
    def on_dm(event, say):
        # DMs only — not channel chatter
        if event.get("channel_type") != "im" or event.get("bot_id"):
            return
        say(handle_question(event.get("text", "")))

    @app.command("/deadlines")
    def on_deadlines(ack, respond):
        ack()
        lines = get_deadlines()
        if not lines:
            respond("No critical dates found in the indexed leases.")
            return
        respond("*Critical dates across indexed leases:*\n"
                + "\n".join(lines))

    return app


if __name__ == "__main__":
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    print("deal-copilot Slack bot starting (Socket Mode)...")
    SocketModeHandler(build_app(), APP_TOKEN).start()
