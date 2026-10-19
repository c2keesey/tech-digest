#!/bin/bash
# Cron entry point. Never invoke this wrapper for a no-send validation.
set -u
umask 077
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1
mkdir -p logs
UV_PATH="$(command -v uv || true)"
if [ -z "$UV_PATH" ]; then
    UV_PATH="$HOME/.local/bin/uv"
fi
if [ ! -x "$UV_PATH" ]; then
    printf 'Digest failed: uv unavailable\n' >> logs/error.log
    exit 1
fi
# Python reads Telegram configuration when needed. Do not shell-expand .env,
# echo credential-bearing exceptions, send an extra failure notification, or
# truncate old logs: sensitive evidence rotation requires a reviewed handoff.
"$UV_PATH" run --frozen python digest.py >> logs/digest.log 2>> logs/error.log
STATUS=$?
printf '[%s] Digest exit=%s (0=acknowledged/unchanged, 1=degraded)\n' \
    "$(date -Iseconds)" "$STATUS" >> logs/digest.log
exit "$STATUS"
