# Tech Digest

Daily release summaries through **Pi / OpenAI Codex subscription OAuth** with
per-source, acknowledged-only Telegram delivery. Explicit model:
`openai-codex/gpt-6.1-sol`. No Claude auth, API-key/paid fallback or credential copying.

```bash
uv sync --frozen
uv run --frozen python digest.py --preview  # no sends or cursor/outbox changes
bash scripts/check.sh                     # offline reliability gate
```

Running without `--preview` sends updates. The maintenance bot is advisory-only;
repository changes require an isolated worker and reviewed PR to `main`.

`config/pi-runtime.json` pins the existing supported Node/Pi installation, so
cron and bot work with system-only PATH and the existing service-user subscription
store; no credential copying or machine PATH edit is needed. See the [recorded decision](docs/decisions/2026-10-15-pi-codex-subscription.md),
[CLAUDE.md](CLAUDE.md) for architecture/shipping, and the
[current external-operator handoff](docs/td-f5l-operator-handoff.md) for exact
review/install/activation blockers and executable external-operator commands.
No approved automatic Digest installer is configured; worker deployment remains
forbidden. `scripts/external_operator_install.py` is a guarded manual external
handoff, not permission to deploy from a worker. The [retained historical
recovery evidence](docs/td-f5l-handoff.md) is not approval to reset or send a
catch-up. Authenticated no-send validation passes even using the primary cursor
read-only; **production still runs the old code** and has not been installed or
restarted. Pi parser approval alone does not authorize deployment or recovery
sends.
