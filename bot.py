#!/usr/bin/env python3
"""
Telegram Bot Listener for Tech Digest

Listens for messages from an authorized Telegram chat and routes them
to a headless Claude Code session that can modify the tech-digest repo.
"""

import json
import os
import subprocess
import sys
import time
from functools import partial
from pathlib import Path

# Ensure print output is unbuffered for systemd log visibility
print = partial(print, flush=True)

from telegram_toolkit.telegram import TelegramNotifier

REPO_DIR = Path(__file__).parent
OFFSET_FILE = REPO_DIR / ".bot_offset"
SESSION_FILE = REPO_DIR / ".bot_session"
POLL_TIMEOUT = 30
CLAUDE_TIMEOUT = 300
MAX_MSG_LEN = 3900
BACKOFF_BASE = 2
BACKOFF_MAX = 60

CONTEXT_PREFIX = (
    "You are working in the tech-digest repository. "
    "This repo generates daily tech release digests and sends them via Telegram. "
    "Key files: sources.py (release sources config), digest.py (digest generation), "
    "prompts/parse-release.md (Claude parsing prompt). "
    "Make the requested change. Keep your response concise (1-3 sentences)."
)


def find_claude_executable():
    """Find the claude CLI executable."""
    import shutil
    paths = [
        shutil.which("claude"),
        "/usr/local/bin/claude",
        f"{os.environ.get('HOME', '')}/.local/bin/claude",
    ]
    for path in paths:
        if path and os.path.exists(path):
            return path
    return None


def load_offset():
    """Load last processed update_id from disk."""
    if OFFSET_FILE.exists():
        try:
            return int(OFFSET_FILE.read_text().strip())
        except (ValueError, OSError):
            pass
    return None


def save_offset(offset):
    """Persist last processed update_id."""
    OFFSET_FILE.write_text(str(offset))


def load_session_id():
    """Load persisted Claude session ID."""
    if SESSION_FILE.exists():
        try:
            sid = SESSION_FILE.read_text().strip()
            print(f"Loaded session: {sid}")
            return sid
        except OSError:
            pass
    print("No existing session")
    return None


def save_session_id(session_id):
    """Persist Claude session ID for conversation continuity."""
    SESSION_FILE.write_text(session_id)
    print(f"Saved session: {session_id}")


def clear_session():
    """Clear the persisted session to start a fresh conversation."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()
    return None


def send_message(bot_token, chat_id, text):
    """Send a message to Telegram, chunking if needed."""
    import requests

    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chunks = []
    while text:
        if len(text) <= MAX_MSG_LEN:
            chunks.append(text)
            break
        # Find a newline to split on near the limit
        split_at = text.rfind("\n", 0, MAX_MSG_LEN)
        if split_at == -1:
            split_at = MAX_MSG_LEN
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")

    for chunk in chunks:
        requests.post(api_url, json={
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": True,
        }, timeout=10)


def get_updates(bot_token, offset):
    """Long-poll for new messages."""
    import requests

    params = {"timeout": POLL_TIMEOUT, "allowed_updates": ["message"]}
    if offset is not None:
        params["offset"] = offset
    resp = requests.get(
        f"https://api.telegram.org/bot{bot_token}/getUpdates",
        params=params,
        timeout=POLL_TIMEOUT + 10,
    )
    resp.raise_for_status()
    return resp.json().get("result", [])


def _build_claude_cmd(claude_path, message_text, session_id=None):
    """Build the claude CLI command list."""
    cmd = [
        claude_path, "-p", message_text,
        "--dangerously-skip-permissions",
        "--output-format", "json",
        "--model", "claude-opus-4-6",
    ]

    if session_id:
        # Resume existing session — system prompt is already in the session
        cmd.extend(["--resume", session_id])
    else:
        # New session — set the system prompt
        cmd.extend(["--system-prompt", CONTEXT_PREFIX])

    return cmd


def _run_claude_once(cmd):
    """Execute a claude CLI command. Returns (data_dict, error_string)."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=CLAUDE_TIMEOUT,
        cwd=str(REPO_DIR),
        env={**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"},
    )
    if result.returncode != 0:
        return None, f"Claude failed (exit {result.returncode}):\n{result.stderr[-500:]}"

    try:
        data = json.loads(result.stdout)
        return data, None
    except json.JSONDecodeError:
        return None, result.stdout.strip()


def run_claude(message_text, session_id=None):
    """Run Claude CLI with the user's message, resuming the session if possible.

    Returns (response_text, session_id).
    """
    claude_path = find_claude_executable()
    if not claude_path:
        return "Error: Claude CLI not found on this machine.", None

    cmd = _build_claude_cmd(claude_path, message_text, session_id)
    print(f"Claude cmd: resume={session_id is not None} session={session_id}")

    try:
        data, error = _run_claude_once(cmd)

        # If resume failed, retry without resume (start fresh session)
        if error and session_id:
            print(f"Resume failed, starting fresh session: {error[:100]}")
            cmd = _build_claude_cmd(claude_path, message_text, session_id=None)
            data, error = _run_claude_once(cmd)

        if error:
            return error, session_id

        new_session_id = data.get("session_id", session_id)
        response_text = data.get("result", "")
        print(f"Claude response OK, session={new_session_id}")
        return response_text, new_session_id

    except subprocess.TimeoutExpired:
        return f"Claude timed out after {CLAUDE_TIMEOUT}s.", session_id
    except Exception as e:
        return f"Claude error: {e}", session_id


def git_changes():
    """Check for uncommitted changes and return diff stat."""
    result = subprocess.run(
        ["git", "diff", "--stat"],
        capture_output=True, text=True, cwd=str(REPO_DIR),
    )
    # Also check untracked files
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=str(REPO_DIR),
    )
    return (result.stdout.strip() + "\n" + status.stdout.strip()).strip()


def git_commit_and_push(user_message):
    """Stage all changes, commit with descriptive message, and push."""
    subprocess.run(["git", "add", "-A"], cwd=str(REPO_DIR), check=True)

    # Build a short commit message from the user request
    short_msg = user_message[:60].replace("\n", " ")
    commit_msg = f"Auto: {short_msg}"

    subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=str(REPO_DIR), check=True,
        capture_output=True, text=True,
    )

    push_result = subprocess.run(
        ["git", "push"],
        cwd=str(REPO_DIR),
        capture_output=True, text=True,
    )
    return push_result.returncode == 0, push_result.stderr.strip()


def handle_message(bot_token, chat_id, message_text):
    """Process a single user message: run Claude, commit changes, report back."""
    # Handle /reset command
    if message_text.strip().lower() == "/reset":
        clear_session()
        send_message(bot_token, chat_id, "Session cleared. Next message starts a fresh conversation.")
        return

    send_message(bot_token, chat_id, "Processing...")

    session_id = load_session_id()
    response, new_session_id = run_claude(message_text, session_id)

    if new_session_id and new_session_id != session_id:
        save_session_id(new_session_id)

    changes = git_changes()
    if changes:
        pushed, push_err = git_commit_and_push(message_text)
        diff_result = subprocess.run(
            ["git", "log", "-1", "--stat", "--format="],
            capture_output=True, text=True, cwd=str(REPO_DIR),
        )
        summary = diff_result.stdout.strip()

        commit_result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            capture_output=True, text=True, cwd=str(REPO_DIR),
        )
        commit_subject = commit_result.stdout.strip()

        reply = response + "\n\n---\n"
        reply += f"Changed: {summary}\n"
        reply += f'Committed: "{commit_subject}"\n'
        if pushed:
            reply += "Pushed to main"
        else:
            reply += f"Push failed: {push_err}"
    else:
        reply = response

    send_message(bot_token, chat_id, reply)


def main():
    print("Starting tech-digest bot...")

    notifier = TelegramNotifier(env_file=str(REPO_DIR / ".env"))
    bot_token = notifier.bot_token
    chat_id = notifier.chat_id

    print(f"Authorized chat_id: {chat_id}")

    offset = load_offset()
    retries = 0

    while True:
        try:
            updates = get_updates(bot_token, offset)
            retries = 0  # Reset on success

            for update in updates:
                update_id = update["update_id"]
                offset = update_id + 1
                save_offset(offset)

                msg = update.get("message", {})
                msg_chat_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "")

                if msg_chat_id != str(chat_id):
                    continue  # Silent rejection

                if not text:
                    continue

                print(f"Received: {text[:80]}")
                try:
                    handle_message(bot_token, chat_id, text)
                except Exception as e:
                    print(f"Error handling message: {e}")
                    send_message(bot_token, chat_id, f"Error: {e}")

        except KeyboardInterrupt:
            print("\nShutting down.")
            sys.exit(0)
        except Exception as e:
            delay = min(BACKOFF_BASE ** (retries + 1), BACKOFF_MAX)
            print(f"Poll error: {e} — retrying in {delay}s")
            time.sleep(delay)
            retries += 1


if __name__ == "__main__":
    main()
