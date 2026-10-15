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

The actual cron/service context must expose the supported Node/Pi installation
and existing service-user Pi subscription store. See the [recorded decision](docs/decisions/2026-10-15-pi-codex-subscription.md),
[CLAUDE.md](CLAUDE.md) for architecture/shipping, and the
[td-f5l handoff](docs/td-f5l-handoff.md) for remaining review, runtime installation,
recovery and preservation actions. Authenticated no-send validation passes in
the isolated worktree; production has not been installed or restarted.
