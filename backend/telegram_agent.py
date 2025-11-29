"""
Telegram agent to poll the AI suspect list and push to a chat.

Usage:
  TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... \
    python backend/telegram_agent.py

Env vars:
  TELEGRAM_BOT_TOKEN       Bot token (do not commit this)
  TELEGRAM_CHAT_ID         Chat/channel id to send messages to
  TELEGRAM_AGENT_ENDPOINT  Defaults to http://localhost:5005/api/ai-agent/top?limit=5
  TELEGRAM_AGENT_INTERVAL  Poll interval seconds (default 60)
"""

import os
import time
import requests
from dotenv import load_dotenv


def fetch_top(endpoint: str):
    resp = requests.get(endpoint, timeout=10)
    resp.raise_for_status()
    return resp.json()


def send_message(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=10,
    )
    resp.raise_for_status()


def format_alert(a: dict) -> str:
    rule = a.get("ruleKey") or a.get("rule") or ""
    summary = a.get("summary") or ""
    sev = a.get("severity") or ""
    return f"• [{sev}] {rule}: {summary}"


def main():
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    endpoint = os.getenv("TELEGRAM_AGENT_ENDPOINT", "http://localhost:5005/api/ai-agent/top?limit=5")
    interval = int(os.getenv("TELEGRAM_AGENT_INTERVAL", "60"))

    if not token or not chat_id:
        print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID before running.")
        return

    print(f"Starting Telegram agent. Polling {endpoint} every {interval}s")
    while True:
        try:
            alerts = fetch_top(endpoint)
            if alerts:
                body = "\n".join(format_alert(a) for a in alerts)
                msg = f"🔍 Search & Destroy (unflagged suspects)\n{body}"
                send_message(token, chat_id, msg)
        except Exception as exc:
            print(f"Agent error: {exc}")
        time.sleep(interval)


if __name__ == "__main__":
    main()
