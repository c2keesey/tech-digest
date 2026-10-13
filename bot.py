#!/usr/bin/env python3
"""Advisory-only Telegram maintenance bot.

Repository mutation belongs to the isolated, reviewed worker workflow. A bot
turn never runs tools, stages runtime files, commits, pushes, deploys or restarts.
"""

from functools import partial
from pathlib import Path
from types import SimpleNamespace
import time

from claude_runtime import ClaudeFailure, run_claude as invoke_claude
from delivery import DeliveryFailure, send_html
from state_store import StateFailure, atomic_text, runtime_lock
from telegram_toolkit.telegram import TelegramNotifier
import requests

print = partial(print, flush=True)
REPO_DIR = Path(__file__).resolve().parent
OFFSET_FILE = REPO_DIR / ".bot_offset"
POLL_TIMEOUT = 30
CLAUDE_TIMEOUT = 300
BACKOFF_BASE = 2
BACKOFF_MAX = 60
CONTEXT_PREFIX = (
    "You are the advisory maintenance assistant for Tech Digest, a daily release "
    "summary service. You have no tools and no repository mutation authority. "
    "Do not claim to edit, commit, push, send a digest, deploy or restart anything. "
    "Repairs must use the catalogued isolated worker and a reviewed PR targeting main. "
    "Explain the next safe step briefly. Never quote credentials or private identifiers."
)


def load_offset():
    try:
        return int(OFFSET_FILE.read_text().strip())
    except FileNotFoundError:
        return None
    except (ValueError, OSError):
        # Never reset a corrupt cursor and replay old maintenance requests.
        raise StateFailure("bot-offset-unreadable") from None


def save_offset(offset):
    with runtime_lock():
        atomic_text(OFFSET_FILE, str(offset))


def send_message(bot_token, chat_id, text):
    from html import escape
    notifier = SimpleNamespace(bot_token=bot_token, chat_id=chat_id)
    # Escape complete plain-text slices; never split inside an HTML entity.
    for start in range(0, len(text), 500):
        send_html(notifier, escape(text[start:start + 500]))


def get_updates(bot_token, offset):
    params = {"timeout": POLL_TIMEOUT, "allowed_updates": ["message"]}
    if offset is not None:
        params["offset"] = offset
    try:
        response = requests.get(f"https://api.telegram.org/bot{bot_token}/getUpdates",
                                params=params, timeout=POLL_TIMEOUT + 10)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict) or body.get("ok") is not True or not isinstance(body.get("result"), list):
            raise ValueError
        return body["result"]
    except (requests.RequestException, ValueError):
        raise DeliveryFailure("bot-poll-failed") from None


def run_claude(message_text, session_id=None):
    # Existing persisted sessions may have unsafe tools/system prompts. Never
    # resume them; keep their artifacts untouched for the preservation handoff.
    try:
        return invoke_claude(message_text, CONTEXT_PREFIX, CLAUDE_TIMEOUT), True
    except ClaudeFailure as error:
        return f"Maintenance unavailable: {error}. No repository changes were made.", False


def handle_message(bot_token, chat_id, message_text):
    if message_text.strip().lower() == "/reset":
        send_message(bot_token, chat_id, "Bot is advisory-only and does not persist Claude sessions.")
        return
    with runtime_lock():
        response, successful = run_claude(message_text)
        # Only content-free diagnostics enter service logs.
        print("Maintenance advisory completed" if successful else "Maintenance advisory failed")
    send_message(bot_token, chat_id, response)


def main():
    print("Starting advisory-only tech-digest bot")
    try:
        notifier = TelegramNotifier(env_file=str(REPO_DIR / ".env"))
        offset = load_offset()
    except (ValueError, StateFailure, OSError):
        print("Bot configuration/cursor unavailable; preserve artifacts for review")
        return 1
    retries = 0
    while True:
        try:
            for update in get_updates(notifier.bot_token, offset):
                update_id = update["update_id"]
                if type(update_id) is not int:
                    raise ValueError
                # Record receipt before execution: no automatic replay of a turn
                # whose reply or execution was interrupted/ambiguous.
                offset = update_id + 1
                save_offset(offset)
                message = update.get("message", {})
                if str(message.get("chat", {}).get("id", "")) != str(notifier.chat_id):
                    continue
                text = message.get("text")
                if isinstance(text, str) and text:
                    try:
                        handle_message(notifier.bot_token, notifier.chat_id, text)
                    except Exception:
                        # Do not echo a token-bearing request URL or user text.
                        print("Maintenance reply failed; not replaying acknowledged receipt")
            retries = 0
        except KeyboardInterrupt:
            print("Bot stopped")
            return 0
        except Exception:
            delay = min(BACKOFF_BASE ** (retries + 1), BACKOFF_MAX)
            print(f"Bot poll failed; retrying in {delay}s")
            time.sleep(delay)
            retries += 1


if __name__ == "__main__":
    raise SystemExit(main())
