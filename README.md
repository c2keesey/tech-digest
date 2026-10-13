# Tech Digest

Daily release summaries with per-source, acknowledged-only Telegram delivery.

```bash
uv sync --frozen
uv run --frozen python digest.py --preview  # no sends or cursor/outbox changes
bash scripts/check.sh                     # offline reliability gate
```

Running without `--preview` sends updates. The maintenance bot is advisory-only;
repository changes require an isolated worker and reviewed PR to `main`.

See [CLAUDE.md](CLAUDE.md) for architecture and shipping, and the
[td-f5l handoff](docs/td-f5l-handoff.md) for live-auth, recovery and preservation blockers.
