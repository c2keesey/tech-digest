#!/usr/bin/env bash
# Offline repository gate; never starts services or sends real Telegram messages.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python -m compileall -q digest.py bot.py enrich.py sources.py telegram_toolkit \
    claude_runtime.py state_store.py delivery.py recovery_preview.py tests
bash -n run_digest.sh
git diff --check
