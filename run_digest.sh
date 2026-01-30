#!/bin/bash

# Claude Code Morning Digest
# Run daily to send release notes summary via Telegram
# Designed for cron automation with logging

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/logs/digest.log"
ERROR_LOG="$SCRIPT_DIR/logs/error.log"

# Create logs directory
mkdir -p "$SCRIPT_DIR/logs"

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

log "Starting Claude Code digest..."

# Change to script directory
cd "$SCRIPT_DIR"

# Load environment variables from .env if it exists
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
    log "Loaded environment variables"
fi

# Find uv executable
UV_PATH=$(which uv 2>/dev/null)
if [ -z "$UV_PATH" ]; then
    UV_PATH="$HOME/.local/bin/uv"
fi

if [ ! -x "$UV_PATH" ]; then
    log "ERROR: uv not found"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] uv not found at $UV_PATH" >> "$ERROR_LOG"
    exit 1
fi

# Build command with optional enrichment
DIGEST_CMD="$UV_PATH run python digest.py"
if [ "${ENABLE_ENRICHMENT:-true}" = "true" ]; then
    DIGEST_CMD="$DIGEST_CMD --enrich"
    log "Running with web enrichment enabled"
fi

# Run the digest
$DIGEST_CMD >> "$LOG_FILE" 2>> "$ERROR_LOG"
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    log "Digest sent successfully"
else
    log "ERROR: Digest failed with exit code $EXIT_CODE"

    # Send error notification via Telegram if configured
    if [ ! -z "$TELEGRAM_BOT_TOKEN" ] && [ ! -z "$TELEGRAM_CHAT_ID" ]; then
        curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
            -d chat_id="$TELEGRAM_CHAT_ID" \
            -d text="⚠️ Claude Code Digest failed with exit code $EXIT_CODE" \
            -d parse_mode="Markdown" > /dev/null 2>&1
    fi
fi

# Keep logs under control (keep last 500 lines)
if [ -f "$LOG_FILE" ]; then
    tail -n 500 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
fi

if [ -f "$ERROR_LOG" ]; then
    tail -n 200 "$ERROR_LOG" > "$ERROR_LOG.tmp" && mv "$ERROR_LOG.tmp" "$ERROR_LOG"
fi

exit $EXIT_CODE
