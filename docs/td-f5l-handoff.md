# td-f5l repair and reviewed operational handoff

## Scope and retained-owner audit

This is the original `td-f5l` implementation, not a new corrective Bead. The
failed attempt had no Pi session and no setup completion; its retained
`work/td-f5l-ready-work` head `1a587b8` was an ancestor of `origin/main` with
**zero unique commits**. The supervisor safely reused that same owner/worktree,
realigned it to `781d7af` (`origin/main`), and completed the reviewed fixed
`uv sync --frozen` setup. The stale `origin/HEAD` cron-integration branch is not
an implementation base. No cleanup, duplicate owner or corrective lineage was
created. The original acceptance criteria were read from an isolated copy of
existing Beads evidence; no Bead was created, updated or closed by the worker.

## Implemented design

- Fetch, parse/schema, unchanged and delivery failures are distinct per source.
  Failed parsing cannot format as “No recent updates,” advance that cursor, or
  claim a fully successful run. Healthy sources can acknowledge independently.
- Supported PATH-discovered Claude print/JSON invocation, safe mode (not bare),
  no tools/MCP and no session persistence. Safe mode retains normal supported
  auth while disabling user hooks/plugins. No hardcoded obsolete bot model,
  unsafe resumed session or permission bypass.
- Legacy numeric/string tags normalize deterministically; malformed state
  fails closed rather than becoming an empty cursor. A shared Linux flock
  serializes digest/cron and bot turns. Runtime writes use same-directory atomic
  replacement, mode 0600, file fsync and directory fsync.
- Frozen source payloads and a durable per-chunk outbox. Require HTTP 200,
  `ok: true` and a positive integer `result.message_id` before recording an ack;
  require every source chunk acknowledged before committing its cursor.
- Telegram has **no sendMessage idempotency key**. Explicit rejections remain
  retryable; durable acks are skipped on retry; a network ambiguity, malformed
  ack or crash between send and journal commit blocks that chunk for human
  reconciliation. This is fail-closed, not a false exactly-once claim.
- Pi now uses `earendil-works/pi` GitHub releases, matching the installed Pi
  coding-agent package's repository, rather than the unrelated `pi.ai/blog`.
- The maintenance bot is intentionally **advisory-only**. Automatic edits,
  staging, commits and pushes were removed entirely. No cron-created cursor or
  unrelated manifest can be confused with an agent diff. Bot receipt offsets
  persist atomically; failed/ambiguous replies do not replay a maintenance turn.
- Cron/send logs now contain statuses only, with no raw CLI diagnostics,
  previews, private identifiers or request URLs. The cron wrapper no longer
  shell-expands `.env`, sends a second failure notification, or truncates
  historical evidence. Explicit previews must not go into service logs.

## Reproduced runtime failure — still requires human authentication

Read-only bounded diagnostics found 37 Claude parse failures, 39 false
“No recent updates” strings, 11 reported sends and 11 Pi 403s in the retained
500-line digest log; the error log contains one mixed-type sort failure.
The older September 13–15 digest logs have already rolled out of that retention
window. Their raw content, tokens, chat IDs and private release text were never
echoed or newly persisted by the worker.

The **original** parser invocation with public synthetic input was reproduced:
exit 1, 73 stdout bytes, zero stderr bytes, expired-OAuth diagnostics on stdout.
The supported safe-mode JSON adapter also reproduces expired OAuth, now as
`claude-auth-required` rather than a misleading empty-stderr parse failure.
`claude auth status` reports `loggedIn: false`, `authMethod: none`; the worker
has no supported API-key/OAuth-token environment credential, and the primary
`.env` has no supported Claude auth variable. No credentials were rotated,
reauthenticated or copied by the worker.

**Blocker:** a human must run supported `claude auth login` as the actual
service user, or provision an approved supported API credential in that
service's environment, then verify a tool-free public-fixture parse. Do not
use `--bare` with subscription OAuth, suppress auth errors, bypass permission
checks, or put raw auth output in logs. Until then live parsed summaries and a
successful live catch-up preview are **not verified**. The offline end-to-end
fixture preview passes; live preview returns nonzero honestly. The new Pi
GitHub fetch succeeds; its parsing is independently blocked by Claude auth.

## Swallowed-release evidence and no-send recovery

Historical `seen_versions` and anchors prove tracking, **not successful summary
delivery**. The retained logs do not establish the last proven good summary.
Therefore **no automatic state rewind/reset or catch-up send is authorized**.

A provisional inventory uses `e45ec38` (August 14 code/state snapshot) solely
as an evidence comparison boundary, **not a proven-good delivery baseline**.
Unioning subsequent committed cursor snapshots with the protected primary's
read-only October 13 cursor produced these potentially swallowed candidates:

| Source | Candidate tags after provisional boundary |
| --- | ---: |
| Claude Code | 53 |
| Pydantic AI | 30 |
| Agent Deck | 33 |
| Beads | 10 |
| Gas City | 6 |
| Codex | 104 |
| Pi | 0 (old web source never acquired a GitHub cursor) |

The inventory tool emits the exact public tag list, not release bodies. Counts
are bounded by available history and the rolling 50-version cap, include alpha
and toolchain tags under the existing source policy, and are **not a definitive
missed-delivery list**. Uncommitted versions that already rolled out can be
missing. Web hashes/anchors cannot recover exact historical entries; a human
must review the archived changelog/Telegram evidence.

Read-only commands, run only from the isolated worktree:

```bash
# Inventory only: no network, parser, sends or cursor writes.
uv run --frozen python recovery_preview.py --baseline-ref e45ec38 \
  --observed-state /home/c2k/repos/tech-digest/state.json --inventory-only

# After authentication AND review of a proven-good baseline:
uv run --frozen python recovery_preview.py --baseline-ref <reviewed-ref> \
  --max-pages 3 --max-releases 5 --sources claude-code,beads
```

The second command only builds a bounded preview: at most three 100-release
archive pages and five selected candidates per GitHub source (hard caps:
five pages/ten selected releases). It excludes baseline tags, deduplicates
archive results, reports unresolved/unselected candidates, and fails honestly
when the bound does not locate needed history or parsing fails. There is
**no send or state-rewrite option**. A synthetic archive catch-up fixture passes;
a live authenticated catch-up is blocked as above. A live one-page/two-release
attempt selected Claude Code `v2.1.296` and `v2.1.295`, reported 51 unselected or
unlocated candidates, and returned exit 1 for `claude-auth-required` without
sending or changing cursor/outbox files. A human must choose the proven-good
boundary, review duplicates against Telegram history, approve the
exact bounded batch and a separate recovery delivery plan. Do not just clear
`state.json` or run the cron wrapper as a test.

## Ambiguous delivery reconciliation

Preserve `.digest-outbox.json` (private runtime data, mode 0600, gitignored).
Never delete it to retry. Under the shared `.runtime.lock`, an authorized
operator must inspect trusted Telegram history for each `uncertain`/`inflight`
chunk. Only a verified matching delivery may be recorded as `ack` with its real
message ID; only a verified non-delivery plus explicit resend approval may
return it to `pending`. If proof is unavailable, leave it blocked. An all-ack
entry whose cursor commit failed is safe to resume: it commits the cursor
without re-sending. Production state/outbox editing was not performed here.

## Protected evidence and sensitive-log handoff

The primary remains on `main`. Its pre-existing dirty `state.json`, Beads backup
manifest and gate-lock artifact were not reset, staged, cleaned or rewritten.
Fingerprints at worker audit and after implementation remained:

- `state.json`: `c47497c35eef4b2091c03d51ea06b1da3ec02092a405acc78155caf0d2134657`
- `.beads/backup/manifest`: `9f435406983abb46eebe766dbcde2507c2d1b367725ab0b9593b286afd1a0d90`

These are current evidence, not the older September manifest fingerprint.
Credentials, existing sessions/offsets, logs and uncertain backups remain in
place. No original sensitive log was changed. After reviewed authorization:

1. Preserve old logs in a restricted mode-0600 archive outside the checkout,
   record hashes/access ownership privately, and prevent public log ingestion.
2. Produce a **content-free** diagnostic extract (dates, stages, exit codes,
   source keys, counts), not a partial regex-redaction assumed to remove all
   secrets/private release content. Keep originals restricted until retention
   and incident-review policy allows destruction.
3. Rotate to fresh restricted logs only as part of the reviewed production
   installation. Existing open service descriptors must be reconciled by the
   authorized operator. Do not truncate evidence in place.
4. Review possible token exposure and explicitly authorize any Telegram/Claude
   credential rotation. Do not publish raw request URLs or private chat IDs.

## Shipping and deployment boundary

Repository gate: `bash scripts/check.sh` (offline failure matrices, process
concurrency, parser/state migration, atomic crash-window retries, bot safety,
no-send end-to-end preview, syntax/compile and whitespace checks). Also run the
catalog's exact fixed compile gate separately. No gate runs a real bot listener
or Telegram request.

Push only `work/td-f5l-ready-work`; PR targets `main`, with no auto-merge. Keep
the PR draft while the live-auth/proven-baseline acceptance remains unresolved.
**Merge, dependency installation into production, cron/service installation or
restart, credential rotation, any catch-up send and Bead closure are left to
the reviewed handoff.** Workers have no deployment/restart authority. Because
runtime state is tracked historically, production checkout/deployment must
preserve its dirty cursor and manifest rather than use `git reset --hard`.
