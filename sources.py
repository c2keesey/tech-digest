#!/usr/bin/env python3
"""
Release sources configuration.

Each source defines how to fetch release/changelog data.
"""

from hashlib import sha256
from dataclasses import dataclass, field
from typing import Optional

import re

import requests
from bs4 import BeautifulSoup

# Patterns for dynamic text that changes between fetches without new content
_DYNAMIC_LINE_RE = re.compile(
    r"^(Updated\s+.+|Last\s+updated.+|Table of contents|All Collections)$",
    re.IGNORECASE,
)


@dataclass
class ReleaseData:
    """Normalized release data from any source."""
    source_name: str
    content: str  # Raw content to send to Claude for parsing
    url: str  # Link to changelog/releases
    versions: list[str] = field(default_factory=list)  # GitHub: version tags included
    content_hash: str = ""  # Web: hash of content for change detection
    content_anchor: str = ""  # Web: first substantive line for dedup


# GitHub API sources
GITHUB_SOURCES = {
    "claude-code": {
        "repo": "anthropics/claude-code",
        "name": "Claude Code",
        "url": "https://github.com/anthropics/claude-code/releases",
    },
    "pydantic-ai": {
        "repo": "pydantic/pydantic-ai",
        "name": "Pydantic AI",
        "url": "https://github.com/pydantic/pydantic-ai/releases",
    },
    "agent-deck": {
        "repo": "asheshgoplani/agent-deck",
        "name": "Agent Deck",
        "url": "https://github.com/asheshgoplani/agent-deck/releases",
    },
    "beads": {
        "repo": "steveyegge/beads",
        "name": "Beads",
        "url": "https://github.com/steveyegge/beads/releases",
    },
    "gas-city": {
        "repo": "gastownhall/gascity",
        "name": "Gas City",
        "url": "https://github.com/gastownhall/gascity/releases",
    },
    "codex": {
        "repo": "openai/codex",
        "name": "Codex CLI",
        "url": "https://github.com/openai/codex/releases",
    },
}

# Web changelog sources (HTML pages)
WEB_SOURCES = {
    "linear": {
        "url": "https://linear.app/changelog",
        "name": "Linear",
    },
    "cursor": {
        "url": "https://cursor.com/changelog",
        "name": "Cursor",
    },
    "granola": {
        "url": "https://www.granola.ai/docs/changelog",
        "name": "Granola",
    },
    "claude-app": {
        "url": "https://support.claude.com/en/articles/12138966-release-notes",
        "name": "Claude App",
    },
    "chatgpt-app": {
        "url": "https://help.openai.com/en/articles/6825453-chatgpt-release-notes",
        "name": "ChatGPT App",
    },
    "pi": {
        "url": "https://pi.ai/blog",
        "name": "Pi",
    },
}


def _stable_lines(content: str) -> list[str]:
    """Return content lines with dynamic/metadata lines stripped."""
    return [l for l in content.split("\n") if not _DYNAMIC_LINE_RE.match(l.strip())]


def _stable_hash(content: str) -> str:
    """Hash content after stripping dynamic lines that change between fetches."""
    return sha256("\n".join(_stable_lines(content)).encode()).hexdigest()


def _content_anchor(content: str) -> str:
    """Extract the first substantive line as an anchor for dedup.

    Used to identify where previously-reported content starts, so we can
    send only new entries to Claude on the next run. Skips short nav/header
    lines to find actual changelog content.
    """
    for line in _stable_lines(content):
        stripped = line.strip()
        # Skip empty lines and short nav/title junk (e.g., "Claude", "Release notes")
        if stripped and len(stripped) > 20:
            return stripped
    return ""


def _truncate_at_anchor(content: str, anchor: str) -> str:
    """Return only content above the anchor line (i.e., new entries).

    Changelog pages list newest entries first. If we find the anchor
    (the first substantive line from last run), everything above it is new.
    """
    if not anchor:
        return content
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.strip() == anchor:
            new_lines = lines[:i]
            # Check if there's any real content above the anchor
            # (not just nav/metadata junk)
            has_substance = any(
                len(l.strip()) > 20 and not _DYNAMIC_LINE_RE.match(l.strip())
                for l in new_lines
            )
            return "\n".join(new_lines) if has_substance else ""
    # Anchor not found (page restructured), return full content
    return content


def fetch_github_releases(repo: str, limit: int = 10) -> list[dict]:
    """Fetch recent releases from GitHub API."""
    try:
        response = requests.get(
            f"https://api.github.com/repos/{repo}/releases",
            params={"per_page": limit},
            headers={"Accept": "application/vnd.github+json"},
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Failed to fetch {repo}: {e}")
        return []


def fetch_web_changelog(url: str) -> Optional[str]:
    """Fetch and extract changelog content from web page."""
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; TechDigest/1.0)"},
            timeout=30
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove script/style elements
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

        # Try to find main content area
        main = soup.find("main") or soup.find("article") or soup.find(class_="content")
        if main:
            text = main.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)

        # Limit content length (Claude can handle ~100k tokens but we want concise)
        lines = text.split("\n")
        # Take first ~200 lines which should cover recent changes
        return "\n".join(lines[:200])

    except requests.RequestException as e:
        print(f"Failed to fetch {url}: {e}")
        return None


def get_release_data(source_key: str, seen_versions: set[str] = None, last_anchor: str = "") -> Optional[ReleaseData]:
    """
    Get release data from a source, filtering out already-seen content.

    Args:
        source_key: Key like "claude-code", "linear", etc.
        seen_versions: Set of version tags already reported (GitHub sources only)
        last_anchor: First substantive line from last web fetch (web sources only)

    Returns:
        ReleaseData or None if no new data
    """
    # Check GitHub sources
    if source_key in GITHUB_SOURCES:
        config = GITHUB_SOURCES[source_key]
        releases = fetch_github_releases(config["repo"])

        if not releases:
            return None

        # Filter out already-seen versions
        if seen_versions:
            releases = [r for r in releases if r.get("tag_name", "") not in seen_versions]

        if not releases:
            return None

        # Combine release bodies
        content = ""
        versions = []
        for release in releases:
            version = release.get("tag_name", "unknown")
            body = release.get("body", "")
            content += f"## {version}\n{body}\n\n"
            versions.append(version)

        return ReleaseData(
            source_name=config["name"],
            content=content,
            url=config["url"],
            versions=versions,
        )

    # Check web sources
    if source_key in WEB_SOURCES:
        config = WEB_SOURCES[source_key]
        full_content = fetch_web_changelog(config["url"])

        if not full_content:
            return None

        # Only send new content (above the anchor from last run) to Claude
        content = _truncate_at_anchor(full_content, last_anchor) if last_anchor else full_content

        return ReleaseData(
            source_name=config["name"],
            content=content,
            url=config["url"],
            # Always hash+anchor against full content so tracking is consistent
            content_hash=_stable_hash(full_content),
            content_anchor=_content_anchor(full_content),
        )

    print(f"Unknown source: {source_key}")
    return None


def list_sources() -> list[str]:
    """List all available source keys."""
    return list(GITHUB_SOURCES.keys()) + list(WEB_SOURCES.keys())
