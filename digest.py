#!/usr/bin/env python3
"""
Claude Code Release Digest

Fetches Claude Code release notes from GitHub and sends a formatted
morning digest via Telegram.
"""

import re
import requests
from datetime import datetime, timedelta
from typing import Optional
from telegram_toolkit.telegram import TelegramNotifier

# Optional enrichment import
try:
    from enrich import enrich_digest
    ENRICHMENT_AVAILABLE = True
except ImportError:
    ENRICHMENT_AVAILABLE = False


GITHUB_RELEASES_URL = "https://api.github.com/repos/anthropics/claude-code/releases"

# Category patterns for sorting changes (checked in order, first match wins)
# Using tuples of (category, patterns) to maintain order
def escape_markdown(text: str) -> str:
    """Escape Telegram markdown special characters."""
    # Escape underscores, asterisks, brackets, backticks
    for char in ['_', '*', '[', ']', '`']:
        text = text.replace(char, '\\' + char)
    return text


CATEGORY_RULES = [
    # Bug fixes first - these often contain other keywords like "add" or "improve"
    ("Bug Fixes", [r"^fix", r"\bfixed\b", r"\bfix\b", r"\bresolve", r"\bpatch\b"]),
    # IDE-specific changes
    ("IDE & Editor", [r"\[vscode\]", r"\[ide\]", r"\bvscode\b", r"\bvim\b", r"\bneovim\b", r"\bjetbrains\b"]),
    # Performance
    ("Performance", [r"\bperformance\b", r"\bfaster\b", r"\bspeed\b", r"\bmemory\b", r"\boptimiz"]),
    # New features - things that are added
    ("New Features", [r"^added?\b", r"^new\b", r"\bintroduce", r"^enabled?\b", r"^implement"]),
    # Improvements - enhancements to existing features
    ("Improvements", [r"^improved?\b", r"^enhanced?\b", r"^updated?\b", r"^better\b", r"^refactor"]),
    # Documentation
    ("Documentation", [r"\bdoc\b", r"\breadme\b", r"\bguide\b", r"\btutorial\b"]),
    # Changes (behavioral changes)
    ("Changes", [r"^changed?\b"]),
]


def fetch_releases(days: int = 7, limit: int = 10) -> list[dict]:
    """
    Fetch recent Claude Code releases from GitHub.

    Args:
        days: Only include releases from the last N days
        limit: Maximum number of releases to fetch

    Returns:
        List of release dictionaries
    """
    try:
        response = requests.get(
            GITHUB_RELEASES_URL,
            params={"per_page": limit},
            headers={"Accept": "application/vnd.github+json"},
            timeout=30
        )
        response.raise_for_status()
        releases = response.json()

        # Filter to recent releases
        cutoff = datetime.now() - timedelta(days=days)
        recent = []
        for release in releases:
            published = datetime.fromisoformat(release["published_at"].replace("Z", "+00:00"))
            if published.replace(tzinfo=None) > cutoff:
                recent.append(release)

        return recent
    except requests.RequestException as e:
        print(f"Failed to fetch releases: {e}")
        return []


def parse_changes(body: str) -> list[str]:
    """
    Extract individual changes from release body.

    Args:
        body: Markdown body of release notes

    Returns:
        List of change descriptions
    """
    if not body:
        return []

    changes = []
    lines = body.split("\n")

    for line in lines:
        # Match bullet points (-, *, or numbered)
        line = line.strip()
        if re.match(r'^[-*]|\d+\.', line):
            # Clean up the line
            change = re.sub(r'^[-*]\s*|\d+\.\s*', '', line).strip()
            if change and len(change) > 5:  # Skip empty or too short
                changes.append(change)

    return changes


def categorize_change(change: str) -> str:
    """
    Categorize a change based on regex patterns.

    Args:
        change: Change description

    Returns:
        Category name
    """
    change_lower = change.lower()

    for category, patterns in CATEGORY_RULES:
        for pattern in patterns:
            if re.search(pattern, change_lower):
                return category

    return "Other Changes"


def categorize_changes(changes: list[str]) -> dict[str, list[str]]:
    """
    Sort changes into categories.

    Args:
        changes: List of change descriptions

    Returns:
        Dictionary of category -> list of changes
    """
    categorized = {}

    for change in changes:
        category = categorize_change(change)
        if category not in categorized:
            categorized[category] = []
        categorized[category].append(change)

    return categorized


def identify_try_this(changes: list[str]) -> list[str]:
    """
    Identify features worth trying out.

    Args:
        changes: List of change descriptions

    Returns:
        List of notable features to try
    """
    # Look for actionable user-facing features
    try_patterns = [
        r"\bshortcut\b",
        r"\bcommand\b",
        r"\bsetting\b",
        r"\bmode\b",
        r"\bautocomplete\b",
        r"\bnavigation\b",
        r"ctrl\+",
        r"cmd\+",
    ]

    # Things to skip - internal, IDE-specific, or not actionable
    skip_patterns = [
        r"^fix",
        r"\binternal\b",
        r"\brefactor",
        r"\btypo\b",
        r"\[sdk\]",
        r"\[ide\]",
        r"\bdeprecation\b",
    ]

    notable = []
    for change in changes:
        change_lower = change.lower()

        # Skip excluded items
        if any(re.search(p, change_lower) for p in skip_patterns):
            continue

        # Must start with "Added" or "Changed" to be actionable
        if not re.match(r"^(added?|changed?)\b", change_lower):
            continue

        # Prefer items with try-worthy keywords
        if any(re.search(p, change_lower) for p in try_patterns):
            notable.insert(0, change)  # Prioritize
        else:
            notable.append(change)

    # Return top 3, truncating long items
    result = []
    for item in notable[:3]:
        if len(item) > 80:
            item = item[:77] + "..."
        result.append(item)
    return result


def generate_summary(releases: list[dict], all_changes: list[str]) -> str:
    """
    Generate a top-line summary.

    Args:
        releases: List of releases
        all_changes: All changes across releases

    Returns:
        Summary string
    """
    if not releases:
        return "No new Claude Code releases this week."

    versions = [r["tag_name"] for r in releases]
    if len(versions) == 1:
        version_text = f"version {versions[0]}"
    else:
        version_text = f"versions {versions[-1]} → {versions[0]}"

    return f"Claude Code {version_text} • {len(all_changes)} changes"


def format_digest(releases: list[dict], enrichment: str = "") -> str:
    """
    Format releases into a readable Telegram digest.

    Args:
        releases: List of release dictionaries
        enrichment: Optional community context section

    Returns:
        Formatted digest string
    """
    if not releases:
        return "☀️ *Claude Code Morning Digest*\n\nNo new releases in the past week. You're all caught up!"

    # Collect all changes
    all_changes = []
    for release in releases:
        changes = parse_changes(release.get("body", ""))
        all_changes.extend(changes)

    # Generate components
    summary = generate_summary(releases, all_changes)
    categorized = categorize_changes(all_changes)
    try_this = identify_try_this(all_changes)

    # Build the digest
    lines = [
        "☀️ *Claude Code Morning Digest*",
        "",
        f"📌 {summary}",
        "",
    ]

    # Try This section (if any notable features)
    if try_this:
        lines.append("🎯 *Try This*")
        for item in try_this:
            lines.append(f"  → {escape_markdown(item)}")
        lines.append("")

    # Category order for display
    category_order = [
        "New Features",
        "Improvements",
        "IDE & Editor",
        "Performance",
        "Bug Fixes",
        "Changes",
        "Documentation",
        "Other Changes",
    ]

    emoji_map = {
        "New Features": "✨",
        "Bug Fixes": "🐛",
        "Improvements": "📈",
        "IDE & Editor": "🖥️",
        "Performance": "⚡",
        "Documentation": "📚",
        "Changes": "🔄",
        "Other Changes": "📝",
    }

    # Categorized changes (limit per category for readability)
    max_per_category = 8

    for category in category_order:
        if category in categorized:
            emoji = emoji_map.get(category, "•")
            items = categorized[category]
            shown = items[:max_per_category]
            hidden = len(items) - len(shown)

            lines.append(f"{emoji} *{category}*")
            for change in shown:
                # Truncate long changes
                if len(change) > 100:
                    change = change[:97] + "..."
                lines.append(f"  • {escape_markdown(change)}")
            if hidden > 0:
                lines.append(f"  _...and {hidden} more_")
            lines.append("")

    # Community context (if enrichment enabled)
    if enrichment:
        lines.append(enrichment.rstrip())

    # Footer
    latest = releases[0]
    lines.append(f"[View on GitHub]({latest['html_url']})")

    return "\n".join(lines)


def send_digest(days: int = 7, quiet: bool = False, enrich: bool = False) -> bool:
    """
    Fetch releases and send digest via Telegram.

    Args:
        days: Look back N days for releases
        quiet: Suppress preview output
        enrich: Enable web context enrichment via Claude

    Returns:
        True if successful
    """
    if not quiet:
        print(f"Fetching Claude Code releases from the last {days} days...")

    releases = fetch_releases(days=days)

    if not quiet:
        print(f"Found {len(releases)} release(s)")

    # Optional enrichment
    enrichment = ""
    if enrich and releases and ENRICHMENT_AVAILABLE:
        versions = [r["tag_name"] for r in releases[:3]]
        enrichment = enrich_digest(versions)

    digest = format_digest(releases, enrichment)

    if not quiet:
        print("\n--- Digest Preview ---")
        print(digest)
        print("--- End Preview ---\n")

    try:
        notifier = TelegramNotifier()

        # Telegram has 4096 char limit - send raw digest (title is redundant)
        if len(digest) > 4000:
            digest = digest[:3997] + "..."

        # Use send with empty title since digest has its own header
        api_url = f"https://api.telegram.org/bot{notifier.bot_token}/sendMessage"
        payload = {
            'chat_id': notifier.chat_id,
            'text': digest,
            'parse_mode': 'Markdown',
            'disable_web_page_preview': True,
            'disable_notification': False
        }

        import requests
        response = requests.post(api_url, json=payload, timeout=10)
        response.raise_for_status()

        if not quiet:
            print("Digest sent to Telegram!")
        return True

    except requests.RequestException as e:
        print(f"Failed to send: {e}")
        return False
    except ValueError as e:
        print(f"Telegram not configured: {e}")
        print("Run 'uv run telegram-setup' to configure Telegram credentials")
        return False


def preview_digest(days: int = 7, enrich: bool = False) -> str:
    """
    Generate and return digest without sending.

    Args:
        days: Look back N days for releases
        enrich: Enable web context enrichment

    Returns:
        Formatted digest string
    """
    releases = fetch_releases(days=days)

    enrichment = ""
    if enrich and releases and ENRICHMENT_AVAILABLE:
        versions = [r["tag_name"] for r in releases[:3]]
        enrichment = enrich_digest(versions)

    return format_digest(releases, enrichment)


def main():
    """CLI entry point."""
    import sys

    days = 7
    preview_only = "--preview" in sys.argv
    enrich = "--enrich" in sys.argv

    if "--days" in sys.argv:
        idx = sys.argv.index("--days")
        if idx + 1 < len(sys.argv):
            days = int(sys.argv[idx + 1])

    if "--help" in sys.argv or "-h" in sys.argv:
        print("Claude Code Digest - Morning release notes summary")
        print()
        print("Usage: claude-digest [OPTIONS]")
        print()
        print("Options:")
        print("  --preview     Show digest without sending to Telegram")
        print("  --days N      Look back N days for releases (default: 7)")
        print("  --enrich      Add community context via Claude web search")
        print("  --help, -h    Show this help message")
        return

    if preview_only:
        print(preview_digest(days, enrich=enrich))
    else:
        success = send_digest(days, enrich=enrich)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
