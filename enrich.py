#!/usr/bin/env python3
"""Community enrichment is deliberately disabled in the subscription-only path.

The Pi parser has no tools or web-search authority. Do not revive the old Claude
CLI path or introduce a paid/API-key fallback. A future enrichment source needs
an independently reviewed fetch/parse and privacy contract.
"""


def search_release_context(versions, timeout=90):
    print("Community enrichment disabled; source release parsing only")
    return None


def format_community_section(context):
    """Retained formatting helper, not a provider or delivery fallback."""
    lines = ["💬 *Community Buzz*"]
    for line in context.splitlines():
        line = line.strip()
        if line.startswith(("•", "-", "*")):
            clean = line.lstrip("•-* ").strip()
            if clean:
                lines.append(f"  • {clean[:150]}")
    return "\n".join(lines) if len(lines) > 1 else ""


def enrich_digest(versions):
    search_release_context(versions)
    return ""


if __name__ == "__main__":
    enrich_digest([])
