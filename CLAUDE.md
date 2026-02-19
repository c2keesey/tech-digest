# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A daily tech release digest system that fetches release notes from GitHub repos and web changelogs, parses them with Claude CLI, and sends formatted summaries via Telegram. It also includes a Telegram bot that lets you send messages to a headless Claude Code session to modify the repo remotely.

## Commands

```bash
# Run digest (sends to Telegram)
uv run python digest.py

# Preview without sending
uv run python digest.py --preview

# List available sources
uv run python digest.py --list

# Run for specific sources only
uv run python digest.py --sources claude-code,cursor

# Show/reset version tracking state
uv run python digest.py --show-state
uv run python digest.py --reset-state

# Run the Telegram bot listener
uv run python bot.py

# Cron wrapper (used by systemd/cron)
./run_digest.sh
```

## Architecture

- **digest.py** — Main digest generator. Fetches sources, calls Claude CLI to parse release notes into structured JSON, formats HTML for Telegram, sends via API. Tracks seen versions in `state.json` to avoid duplicates.
- **sources.py** — Source configuration and fetching. Two types: `GITHUB_SOURCES` (fetched via GitHub API, tracked by version tags) and `WEB_SOURCES` (HTML changelogs, tracked by content hash). `DEFAULT_SOURCES` in digest.py controls which sources are included.
- **bot.py** — Telegram bot that long-polls for messages, routes them to a headless Claude Code session (`claude -p`), auto-commits any changes Claude makes, and replies with results. Maintains session continuity via `.bot_session`.
- **enrich.py** — Optional web enrichment that searches for community discussion about releases.
- **prompts/parse-release.md** — Claude prompt for parsing raw release notes into categorized JSON.
- **telegram_toolkit/** — Telegram API wrapper, reads credentials from `.env`.
- **state.json** — Persisted version tracking (seen GitHub tags, web content hashes). Only updated after successful Telegram send.

## Key Patterns

- Claude CLI is invoked as a subprocess (`claude -p`) for both digest parsing and bot interactions
- Telegram messages use HTML parse mode (not Markdown) — use `escape_html()` for user content
- Messages over 4000 chars are split by source section at `\n\n▎` boundaries
- The bot auto-commits and pushes any file changes Claude makes, with commit messages prefixed `Auto:`
