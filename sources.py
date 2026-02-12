#!/usr/bin/env python3
"""
Release sources configuration.

Each source defines how to fetch release/changelog data.
"""

from hashlib import sha256
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup


@dataclass
class ReleaseData:
    """Normalized release data from any source."""
    source_name: str
    content: str  # Raw content to send to Claude for parsing
    url: str  # Link to changelog/releases
    versions: list[str] = field(default_factory=list)  # GitHub: version tags included
    content_hash: str = ""  # Web: hash of content for change detection


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
}


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


def get_release_data(source_key: str, seen_versions: set[str] = None) -> Optional[ReleaseData]:
    """
    Get release data from a source, filtering out already-seen versions.

    Args:
        source_key: Key like "claude-code", "linear", etc.
        seen_versions: Set of version tags already reported (GitHub sources only)

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
        content = fetch_web_changelog(config["url"])

        if not content:
            return None

        return ReleaseData(
            source_name=config["name"],
            content=content,
            url=config["url"],
            content_hash=sha256(content.encode()).hexdigest(),
        )

    print(f"Unknown source: {source_key}")
    return None


def list_sources() -> list[str]:
    """List all available source keys."""
    return list(GITHUB_SOURCES.keys()) + list(WEB_SOURCES.keys())
