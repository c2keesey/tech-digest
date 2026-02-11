#!/usr/bin/env python3
"""
Tech Release Digest

Fetches release notes from multiple sources and sends a formatted
morning digest via Telegram. Uses Claude to parse and categorize changes.
"""

import json
import subprocess
import shutil
from pathlib import Path
from typing import Optional
from telegram_toolkit.telegram import TelegramNotifier
import requests

from sources import get_release_data, list_sources, ReleaseData

PROMPT_FILE = Path(__file__).parent / "prompts" / "parse-release.md"
STATE_FILE = Path(__file__).parent / "state.json"

# Default sources to include in digest
DEFAULT_SOURCES = ["claude-code", "cursor", "linear", "pydantic-ai", "granola", "agent-deck"]

# Cap stored versions per source to prevent unbounded growth
MAX_STORED_VERSIONS = 50


def load_state() -> dict:
    """Load version tracking state from disk."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_state(state: dict):
    """Save version tracking state to disk."""
    STATE_FILE.write_text(json.dumps(state, indent=2))


def escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def find_claude_executable() -> Optional[str]:
    """Find the claude CLI executable."""
    paths = [
        shutil.which("claude"),
        "/usr/local/bin/claude",
        f"{subprocess.os.environ.get('HOME', '')}/.local/bin/claude",
    ]
    for path in paths:
        if path and subprocess.os.path.exists(path):
            return path
    return None


def parse_with_claude(content: str, timeout: int = 60) -> Optional[dict]:
    """
    Parse release content using Claude CLI.

    Args:
        content: Raw release/changelog content
        timeout: Max seconds to wait

    Returns:
        Parsed structure or None if failed
    """
    claude_path = find_claude_executable()
    if not claude_path:
        print("Claude CLI not found")
        return None

    if not PROMPT_FILE.exists():
        print(f"Prompt file not found: {PROMPT_FILE}")
        return None

    prompt = PROMPT_FILE.read_text()

    try:
        result = subprocess.run(
            [claude_path, "-p", prompt, "--output-format", "text"],
            input=content,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**subprocess.os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
        )

        if result.returncode != 0:
            print(f"Claude parse failed: {result.stderr}")
            return None

        output = result.stdout.strip()

        # Strip markdown fences if present
        if output.startswith("```"):
            lines = output.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            output = "\n".join(lines)

        return json.loads(output)

    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON: {e}")
        return None
    except subprocess.TimeoutExpired:
        print(f"Claude parse timed out after {timeout}s")
        return None
    except Exception as e:
        print(f"Claude parse error: {e}")
        return None


def format_source_section(data: ReleaseData, parsed: Optional[dict]) -> str:
    """Format a single source's releases into a Telegram HTML section."""
    lines = [f"▎<b>{escape_html(data.source_name)}</b>"]

    if not parsed:
        lines.append("<i>No recent updates</i>")
        return "\n".join(lines)

    # Summary line
    summary = parsed.get("summary", "")
    if summary:
        lines.append(f"<i>{escape_html(summary)}</i>")

    # Try This (only show if present)
    try_this = parsed.get("try_this", [])
    if try_this:
        lines.append("")
        for item in try_this[:2]:
            lines.append(f"  🎯 {escape_html(item)}")

    # Categories
    category_config = [
        ("New Features", "✨"),
        ("Improvements", "📈"),
        ("Bug Fixes", "🐛"),
        ("Changes", "🔄"),
    ]

    categories = parsed.get("categories", {})

    category_lines = []
    for category, emoji in category_config:
        items = categories.get(category, [])
        if not items:
            continue

        # Summarize bug fixes into a count instead of listing each one
        if category == "Bug Fixes":
            category_lines.append(f"  {emoji} {len(items)} bug fix{'es' if len(items) != 1 else ''}")
            continue

        for change in items:
            if len(change) > 80:
                change = change[:77] + "..."
            category_lines.append(f"  {emoji} {escape_html(change)}")

    if category_lines:
        lines.append("")
        lines.extend(category_lines)

    lines.append(f'\n  <a href="{data.url}">View changelog →</a>')

    return "\n".join(lines)


def generate_digest(sources: list[str] = None, quiet: bool = False) -> tuple[str, dict]:
    """
    Generate digest for multiple sources using version tracking.

    Args:
        sources: List of source keys to include
        quiet: Suppress progress output

    Returns:
        Tuple of (formatted digest string, updated state dict)
    """
    if sources is None:
        sources = DEFAULT_SOURCES

    state = load_state()
    new_state = {k: dict(v) for k, v in state.items()}  # deep-ish copy

    lines = [
        "☀️ <b>Tech Morning Digest</b>",
    ]

    sections = []

    for source_key in sources:
        if not quiet:
            print(f"Fetching {source_key}...")

        source_state = state.get(source_key, {})
        seen_versions = set(source_state.get("seen_versions", []))
        last_hash = source_state.get("content_hash", "")

        data = get_release_data(source_key, seen_versions=seen_versions)

        if not data or not data.content.strip():
            if not quiet:
                print(f"  No new updates for {source_key}")
            continue

        # For web sources, skip if content hasn't changed
        if data.content_hash and data.content_hash == last_hash:
            if not quiet:
                print(f"  No changes for {source_key}")
            continue

        if not quiet:
            print(f"  Parsing with Claude...")

        parsed = parse_with_claude(data.content)
        section = format_source_section(data, parsed)
        sections.append(section)

        # Build updated state for this source
        entry = dict(new_state.get(source_key, {}))
        if data.versions:
            existing = set(entry.get("seen_versions", []))
            existing.update(data.versions)
            # Cap stored versions to prevent unbounded growth
            entry["seen_versions"] = sorted(existing)[-MAX_STORED_VERSIONS:]
        if data.content_hash:
            entry["content_hash"] = data.content_hash
        new_state[source_key] = entry

    if not sections:
        lines.append("No new updates. You're all caught up!")
    else:
        lines.extend(sections)

    digest_text = "\n\n".join(lines) if sections else "\n".join(lines)
    return digest_text, new_state


def send_digest(sources: list[str] = None, quiet: bool = False) -> bool:
    """
    Generate and send digest via Telegram. Saves state on success.

    Args:
        sources: List of source keys
        quiet: Suppress output

    Returns:
        True if successful
    """
    digest, new_state = generate_digest(sources=sources, quiet=quiet)

    if not quiet:
        print("\n--- Digest Preview ---")
        print(digest)
        print("--- End Preview ---\n")

    try:
        notifier = TelegramNotifier()
        api_url = f"https://api.telegram.org/bot{notifier.bot_token}/sendMessage"

        # Split digest into chunks that fit Telegram's 4096 char limit
        # Split on source boundaries (each source starts with ▎)
        header, *source_sections = digest.split("\n\n▎")
        chunks = [header]
        for section in source_sections:
            section = "▎" + section
            # If adding this section would exceed limit, start a new chunk
            if len(chunks[-1]) + len("\n\n") + len(section) > 4000:
                chunks.append(section)
            else:
                chunks[-1] += "\n\n" + section

        for chunk in chunks:
            payload = {
                'chat_id': notifier.chat_id,
                'text': chunk,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True,
                'disable_notification': False
            }
            response = requests.post(api_url, json=payload, timeout=10)
            response.raise_for_status()

        # Only save state after successful send
        save_state(new_state)

        if not quiet:
            print("Digest sent to Telegram!")
        return True

    except requests.RequestException as e:
        print(f"Failed to send: {e}")
        return False
    except ValueError as e:
        print(f"Telegram not configured: {e}")
        return False


def main():
    """CLI entry point."""
    import sys

    preview_only = "--preview" in sys.argv
    sources = None  # Use defaults

    if "--sources" in sys.argv:
        idx = sys.argv.index("--sources")
        if idx + 1 < len(sys.argv):
            sources = sys.argv[idx + 1].split(",")

    if "--list" in sys.argv:
        print("Available sources:")
        for s in list_sources():
            print(f"  {s}")
        return

    if "--reset-state" in sys.argv:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
            print("State reset. Next run will report all recent releases.")
        else:
            print("No state file to reset.")
        return

    if "--show-state" in sys.argv:
        state = load_state()
        if not state:
            print("No state yet. Run a digest first.")
        else:
            print(json.dumps(state, indent=2))
        return

    if "--help" in sys.argv or "-h" in sys.argv:
        print("Tech Digest - Morning release notes summary")
        print()
        print("Usage: claude-digest [OPTIONS]")
        print()
        print("Options:")
        print("  --preview        Show digest without sending to Telegram")
        print("  --sources X,Y,Z  Comma-separated list of sources to include")
        print("  --list           List available sources")
        print("  --show-state     Show current version tracking state")
        print("  --reset-state    Clear tracked versions (next run reports everything)")
        print("  --help, -h       Show this help message")
        print()
        print("Default sources:", ", ".join(DEFAULT_SOURCES))
        return

    if preview_only:
        digest, new_state = generate_digest(sources=sources)
        print(digest)
        # Preview doesn't save state
    else:
        success = send_digest(sources=sources)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
