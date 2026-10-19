#!/usr/bin/env bash
# Offline repository gate; never starts services or sends real Telegram messages.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python -m unittest test_digest -v
node --test tests/test_pi_subscription.mjs
node --check scripts/pi_subscription.mjs
uv run --frozen python -m compileall -q digest.py bot.py enrich.py sources.py telegram_toolkit \
    pi_runtime.py state_store.py delivery.py recovery_preview.py scripts/validate_pi_no_send.py \
    scripts/external_operator_install.py test_digest.py tests
bash -n run_digest.sh
git diff --check
