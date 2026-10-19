# Repository guidance

## What This Is

A daily release digest that fetches GitHub releases and web changelogs, parses
bounded structured summaries through **Pi OpenAI Codex subscription OAuth**, and
sends them to Telegram only after validated parsing. The maintenance bot is
**advisory-only**, not a repository editor or deployment agent.

Chris explicitly chose Pi/Codex instead of Claude authentication. See the
[recorded decision](docs/decisions/2026-10-15-pi-codex-subscription.md).
**No Claude invocation, API-key or paid fallback, other model/provider fallback,
or credential copying is permitted.**

## Commands

```bash
# DEFAULT SEND PATH: do not use as a validation command
uv run --frozen python digest.py

# No-send preview: no cursor/outbox/session writes
uv run --frozen python digest.py --preview --sources claude-code,pi
uv run --frozen python digest.py --list
uv run --frozen python digest.py --show-state  # counts, not private anchors

# Historical candidate inventory only: no network/model calls or state rewrites
uv run --frozen python recovery_preview.py --baseline-ref <reviewed-ref> --inventory-only

# Bounded catch-up PREVIEW ONLY; baseline must be reviewed, never inferred
uv run --frozen python recovery_preview.py --baseline-ref <reviewed-ref> --max-pages 3 --max-releases 5

# Offline gate: no real provider or Telegram requests
bash scripts/check.sh

# OPT-IN authenticated provider validation, ISOLATED WORKTREE ONLY:
# real source GETs and subscription calls; Telegram blocked; content-free receipt
uv run --frozen python scripts/validate_pi_no_send.py --receipt data/pi-no-send.json
# Use an existing cursor read-only for source selection, never as a write target:
uv run --frozen python scripts/validate_pi_no_send.py \
  --observed-state /home/c2k/repos/tech-digest/state.json \
  --receipt data/pi-primary-cursor-no-send.json

# Production listener / cron entrypoints: never start from a worker
uv run --frozen python bot.py
./run_digest.sh
```

## Architecture and safety contract

- **digest.py** — Distinct per-source fetch/parse/schema/unchanged/delivery
  outcomes. Failed sources remain pending and make the run degraded/nonzero.
  `--preview` never sends or changes cursor/outbox files.
- **pi_runtime.py**, **scripts/pi_subscription.mjs**, **config/pi-runtime.json** —
  Public Pi `ModelRuntime` invocation from the explicit reviewed installed Node/Pi
  pair, independent of cron/service PATH. No wrapper/shell/version-glob discovery;
  a missing pair/config/SDK fails closed. Explicit
  `openai-codex/gpt-6.1-sol`, low reasoning, native subscription-only OAuth,
  fixed Codex API/endpoint and response identity checks. No tools, agent
  sessions, context/resource discovery, hooks or extensions. No new npm setup.
- **config/pi-models.json** — Explicit empty provider override config. The
  supported catalog and OAuth store stay in the actual user's existing Pi
  directory; they are not copied. Model absence fails closed, not to another
  model/provider. The child excludes API keys and worker/session secrets.
- **prompts/parse-release.md** — Strict source-as-data JSON contract. Bounds:
  192 KiB prompt, 256 KiB frame, 16 KiB result, 64 KiB stream including thinking,
  120-second deadline, zero request retries; summary <=350 chars, try-this <=2,
  <=8 category items total. Oversized input fails without truncating versions.
  Codex ignores `maxTokens`, so do not claim a server-side token cap.
- **state_store.py** — Deterministic legacy cursor normalization, shared
  `.runtime.lock`, atomic mode-0600 replacement and file/directory fsync.
  Corrupt state fails closed, never as an empty cursor. No reset command.
- **delivery.py** — Frozen `.digest-outbox.json` payloads and per-chunk durable
  Telegram acknowledgements (`ok: true`, positive integer message ID). Commit
  a source cursor only after all its chunks are acknowledged. Skip durable acks
  on retry; explicit rejections may retry, ambiguities/crash windows block for
  operator reconciliation. Telegram has no idempotency key: do not claim
  exactly-once delivery or delete an uncertain outbox to retry.
- **sources.py** — GitHub/web sources with isolated actionable failures. Pi
  coding-agent releases use `earendil-works/pi`, not the unrelated Pi AI blog.
- **recovery_preview.py** — Read-only historical candidate inventory and bounded
  archive preview. Cursors are not delivery receipts; preserve the provisional
  baseline and unresolved evidence. There is no send/state-rewrite mode.
- **bot.py** — Shared-lock advisory calls through the same Pi subscription
  adapter. Never resumes unsafe legacy sessions, edits files, stages, commits,
  pushes, deploys or restarts. Receipt offsets persist atomically; ambiguous
  replies do not automatically replay a maintenance turn.
- **enrich.py** — Community enrichment disabled; no dormant Claude/paid fallback.
- **telegram_toolkit/** — Telegram configuration/API helpers. Never log tokens,
  raw exception URLs, chat/session IDs, environments or private release content.

HTML messages are split between balanced lines to <=4000 UTF-16 units with
repeated source headers. Send/cron logs contain status codes only. Explicit
previews can contain source summaries: do not redirect them into service logs.
Historical sensitive logs require preservation-aware reviewed rotation, not
in-place truncation. Runtime JSON, sessions, credentials and logs must never be
staged by maintenance automation. Do not reintroduce `git add -A` or main pushes.

## Isolated shipping contract

Use the current Agent Console repository catalog, not `origin/HEAD` (which may
point to a stale branch): base **origin/main**, setup exactly **uv sync --frozen**,
shipping a **reviewed PR targeting main**, auto-merge false, worker deployment
and restart authority **none**. Reuse the existing claimed owner; infrastructure
recovery is not corrective implementation lineage.

Work only in the retained feature worktree. Never copy credentials into it,
reset primary runtime state, stage its dirty `state.json`/Beads manifest, invoke
its cron wrapper, restart its bot or send a catch-up digest. Do not substitute
Gas City setup/ship symlinks for the catalog's fixed setup and shipping contract.

Run `bash scripts/check.sh` plus the exact fixed catalog gate:

```bash
uv run --frozen python -m compileall -q digest.py bot.py enrich.py sources.py telegram_toolkit
```

Stage only intended source/test/docs, commit on the feature branch, fetch origin
main, rebase onto `origin/main`, rerun gates after changes, push **only the feature
branch**, and update existing PR #2 with base main. Requesting review is
permitted after validation; it never authorizes merge or operations. Leave merge,
production installation, runtime PATH/account verification, service
activation/restart, log/credential operations, recovery approval and Bead closure
to the reviewed handoff. See the [current external-operator checklist](docs/td-f5l-operator-handoff.md)
and [retained recovery evidence](docs/td-f5l-handoff.md). Claude authentication is
not an installation blocker. The reviewed runtime pin now works even with the
actual listener environment or system-only PATH; installing this PR fixes that
blocker without cron/service PATH edits. Production is unchanged until an
external operator installs the reviewed merge and separately activates it.
No approved Digest external dispatcher is configured. The guarded
`scripts/external_operator_install.py` is an executable handoff for an explicitly
authorized external login, **not worker deployment authority**; its read-only
default requires an exact reviewed head, and `--apply` is forbidden here. It
leaves cron paused/listener stopped and never starts/restarts or sends. Preserve
the existing subscription store without credential copying; parser approval is
not installation, activation or catch-up-send approval.
