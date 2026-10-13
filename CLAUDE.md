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

# Show safe cursor counts (does not print private page anchors)
uv run --frozen python digest.py --show-state

# Inventory candidates without network, Claude, sends or state rewrites
uv run --frozen python recovery_preview.py --baseline-ref <reviewed-ref> --inventory-only

# Bounded catch-up preview ONLY; no send mode exists
uv run --frozen python recovery_preview.py --baseline-ref <reviewed-ref> --max-pages 3 --max-releases 5

# Offline reliability gate (mocked network/Claude/Telegram)
bash scripts/check.sh

# Run the Telegram bot listener
uv run python bot.py

# Cron wrapper (used by systemd/cron)
./run_digest.sh
```

## Architecture

- **digest.py** — Per-source generation and delivery. Validates parser output; failed fetches/parses remain pending and return a degraded/nonzero result. Explicit `--preview` neither sends nor changes cursor/outbox files.
- **claude_runtime.py** — PATH-discovered Claude print/JSON adapter, safe mode, no tools/MCP or session persistence; retains supported OAuth/API-key auth. Reports content-free error codes, including expired auth on stdout.
- **state_store.py** — Legacy cursor normalization, shared `.runtime.lock`, atomic mode-0600 writes with file/directory fsync.
- **delivery.py** — Frozen `.digest-outbox.json` payloads and per-chunk Telegram JSON acknowledgements. Rejected chunks may retry; acknowledged chunks never re-send. Ambiguous/crash-window sends require operator reconciliation, not automatic retry.
- **recovery_preview.py** — Read-only historical cursor candidate inventory and bounded archive preview. A cursor is not proof of a delivered summary.
- **sources.py** — Source configuration and fetching. Two types: `GITHUB_SOURCES` (fetched via GitHub API, tracked by version tags) and `WEB_SOURCES` (HTML changelogs, tracked by content hash). `DEFAULT_SOURCES` in digest.py controls which sources are included.
- **bot.py** — Advisory-only maintenance listener. Uses the shared lock and tool-free, nonpersistent Claude adapter. Never resumes legacy unsafe sessions, modifies the repository, commits, pushes, deploys or restarts. Repairs belong to isolated reviewed workers.
- **enrich.py** — Optional web enrichment that searches for community discussion about releases.
- **prompts/parse-release.md** — Claude prompt for parsing raw release notes into categorized JSON.
- **telegram_toolkit/** — Telegram API wrapper, reads credentials from `.env`.
- **state.json** — Persisted version tracking (GitHub tags, web hashes/anchors). Each source is updated only after validated parsing and durable acknowledgements for all of its chunks. Corrupt state fails closed; there is no blind reset command.

## Key Patterns

- Claude CLI is invoked as a subprocess (`claude -p`) for both digest parsing and bot interactions
- Telegram messages use HTML parse mode (not Markdown) — use `escape_html()` for user content
- Messages are bounded to 4000 UTF-16 units, split between balanced HTML lines, with repeated source headers.
- Cron/send logs contain statuses only, never previews, CLI output, chat/session identifiers or exception URLs. Explicit previews may contain release summaries: do not redirect them into service logs.
- Automatic bot repository mutation has been intentionally removed; do not reintroduce `git add -A` or direct-main pushes.

## Isolated shipping contract

Use the current Agent Console repository catalog, not `origin/HEAD` (which may point to a stale branch): default base is **origin/main**, setup is exactly **uv sync --frozen**, shipping is a **reviewed PR targeting main**, auto-merge is false and worker deployment authority is **none**. Reuse an existing claimed owner; infrastructure recovery is not corrective implementation lineage.

Work only in the retained feature worktree. Never copy credentials into it, reset primary runtime state, stage its dirty `state.json`/Beads manifest, invoke its cron wrapper, restart its bot, or send a catch-up digest. Do not run the Gas City setup/ship symlinks in place of the catalog's fixed contract.

Before shipping, run `bash scripts/check.sh` plus the fixed catalog gate:

```bash
uv run --frozen python -m compileall -q digest.py bot.py enrich.py sources.py telegram_toolkit
```

Stage only intended source/test/documentation files, commit on the feature branch, `git fetch origin main`, `git rebase origin/main`, rerun gates after any change, push **only the feature branch**, and open/update a PR with `--base main`. Leave merge, installation, production restarts, credential rotation, catch-up approval and Bead closure to the reviewed handoff. See [td-f5l handoff](docs/td-f5l-handoff.md) for unresolved live-auth/recovery evidence and preservation instructions.
