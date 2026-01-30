#!/usr/bin/env python3
"""
Web enrichment for Claude Code digest.

Uses Claude Code's -p flag to search Twitter/X and web for additional
context about releases - what people are saying, tips, gotchas, etc.
"""

import subprocess
import json
import shutil
from typing import Optional


def find_claude_executable() -> Optional[str]:
    """Find the claude CLI executable."""
    # Check common locations
    paths = [
        shutil.which("claude"),
        "/usr/local/bin/claude",
        f"{subprocess.os.environ.get('HOME', '')}/.local/bin/claude",
    ]
    for path in paths:
        if path and subprocess.os.path.exists(path):
            return path
    return None


def search_release_context(versions: list[str], timeout: int = 60) -> Optional[str]:
    """
    Search for community discussion and context about releases.

    Args:
        versions: List of version strings (e.g., ["v2.1.25", "v2.1.24"])
        timeout: Max seconds to wait for Claude response

    Returns:
        Formatted context string or None if failed
    """
    claude_path = find_claude_executable()
    if not claude_path:
        print("Claude CLI not found, skipping web enrichment")
        return None

    # Build the search prompt
    version_str = ", ".join(versions[:3])  # Limit to 3 most recent
    prompt = f'''Search the web for community discussion about Claude Code {version_str}.

Look for:
1. Twitter/X posts from @ClaudeCodeLog, @anthropaboris, or developers discussing these versions
2. Blog posts or articles about notable features
3. Tips, gotchas, or interesting use cases people have discovered

Return a brief summary (3-5 bullet points max) of the most interesting findings.
Format as plain text bullets starting with "•".
If you find nothing notable, just say "No community discussion found."
Keep it concise - this will be appended to a Telegram message.'''

    try:
        result = subprocess.run(
            [claude_path, "-p", prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**subprocess.os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
        )

        if result.returncode != 0:
            print(f"Claude search failed: {result.stderr}")
            return None

        output = result.stdout.strip()

        # Check if nothing found
        if "no community discussion" in output.lower() or not output:
            return None

        return output

    except subprocess.TimeoutExpired:
        print(f"Claude search timed out after {timeout}s")
        return None
    except Exception as e:
        print(f"Claude search error: {e}")
        return None


def format_community_section(context: str) -> str:
    """
    Format the community context for inclusion in digest.

    Args:
        context: Raw context from Claude search

    Returns:
        Formatted section string
    """
    lines = ["💬 *Community Buzz*"]

    # Parse bullet points from the response
    for line in context.split("\n"):
        line = line.strip()
        if line.startswith("•") or line.startswith("-") or line.startswith("*"):
            # Clean up and truncate
            clean = line.lstrip("•-* ").strip()
            if len(clean) > 120:
                clean = clean[:117] + "..."
            if clean:
                lines.append(f"  • {clean}")

    # Only return if we have actual content
    if len(lines) > 1:
        lines.append("")
        return "\n".join(lines)
    return ""


def enrich_digest(versions: list[str]) -> str:
    """
    Get enrichment content for digest.

    Args:
        versions: List of version strings

    Returns:
        Formatted enrichment section or empty string
    """
    print("Searching for community context...")
    context = search_release_context(versions)

    if context:
        return format_community_section(context)
    return ""


if __name__ == "__main__":
    # Test the enrichment
    import sys
    versions = sys.argv[1:] if len(sys.argv) > 1 else ["v2.1.25", "v2.1.24"]
    print(f"Testing enrichment for versions: {versions}")
    result = enrich_digest(versions)
    if result:
        print("\n--- Enrichment Result ---")
        print(result)
    else:
        print("No enrichment content found")
