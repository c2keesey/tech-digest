# td-f5l repair and reviewed operational handoff

**Updated 2026-10-19:** Production is **still not repaired/installed**. See the
[current executable external-operator handoff](td-f5l-operator-handoff.md).
The cron/service PATH blocker is now fixed **in code** with an explicit validated
installed Node/Pi pin, proved by real subscription calls with system-only PATH
and the actual listener environment, against primary cursors **read-only**.
93 offline tests pass, including the reconciled regressions from concurrent main
commits. No approved Digest external dispatcher exists; the exact
manual merge/install commands, guarded no-send installer, current supervisor-exit
evidence and separate activation/historical-send approvals are documented.
Chris chose Pi/Codex, not Claude authentication or historical catch-up.
[Decision](decisions/2026-10-15-pi-codex-subscription.md) and historical evidence
below are retained; no reset or new recovery baseline is authorized.

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

On continuation, the local feature ref had been reset to `origin/main`, while
PR #2 still retained `4692634`. The worker verified that exact remote PR head,
verified zero local-only commits, fetched and **fast-forwarded** the same retained
branch back to it. Existing lock/evidence artifacts were preserved. No new owner,
setup, branch lineage, destructive reset or duplicate implementation was created.

## Implemented design

- Fetch, parse/schema, unchanged and delivery failures are distinct per source.
  Failed parsing cannot format as “No recent updates,” advance that cursor, or
  claim a fully successful run. Healthy sources can acknowledge independently.
- Supported public Pi `ModelRuntime` SDK invocation, explicitly
  `openai-codex/gpt-6.1-sol` with low reasoning and existing subscription OAuth.
  Native provider/API/endpoint and response identity are checked; no API keys,
  paid fallback, other model fallback, user provider overrides or credential
  copying. No tools, agent sessions, context/resource loading, hooks or extensions.
- Provider-side strict JSON and client validation; 192 KiB prompt / 256 KiB frame,
  16 KiB final text / 64 KiB stream including thinking, 120-second deadline and
  zero inference retries. Oversize fails without truncation or cursor advancement.
  Dormant Claude community enrichment is disabled, not a fallback.
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

## Historical Claude failure — superseded, not an authentication requirement

Read-only bounded diagnostics found 37 Claude parse failures, 39 false
“No recent updates” strings, 11 reported sends and 11 Pi 403s in the retained
500-line digest log; the error log contains one mixed-type sort failure.
The older September 13–15 digest logs have already rolled out of that retention
window. Their raw content, tokens, chat IDs and private release text were never
echoed or newly persisted by the worker.

The **original** parser invocation with public synthetic input was reproduced:
exit 1, 73 stdout bytes, zero stderr bytes, expired-OAuth diagnostics on stdout.
The first PR iteration reproduced the same expired Claude OAuth through a safe
adapter and reported it honestly. That proposal is now superseded by Chris's
explicit Pi/Codex decision: **do not reauthenticate Claude, provision API keys,
or use Claude as fallback**. No credentials were rotated or copied by the worker.

## Authenticated Pi/Codex no-send evidence

The real public Pi SDK call passed a synthetic strict-schema fixture using the
existing subscription. At `2026-10-15T05:02:14Z`, the opt-in real validation
checked all **11 default sources**, summarized **10** (Granola unchanged), and
returned CLI preview exit **0**, with no fetch/parse failures and a valid real
advisory response. Pi version **0.84.1**, explicit provider/model/API:
`openai-codex` / `gpt-6.1-sol` / `openai-codex-responses`. The bridge checked
subscription OAuth and the native Codex endpoint before dispatch; raw model
output and release text were captured in memory, never persisted in logs.

**Zero Telegram requests**, zero notifier constructions, no cursor/outbox/session
writes, and protected-primary state, manifest, credentials, offsets/sessions and
logs unchanged across validation. Fixture + full preview + advisory took 75.12s.
The normal two-source Claude Code/Pi validation also passed (22.13s). The initial
96 KiB input limit safely rejected the observed 127,959-byte Claude Code batch;
raising the explicit limit to 192 KiB fixed this without dropping any releases.

Local content-free receipts (mode 0600, ignored) are retained under `data/`:
`pi-codex-all-sources-2026-10-15.json` and
`pi-codex-no-send-2026-10-15-verified.json`; the initial failing-bound receipt was
preserved too. Reproduce only from the isolated worktree:

```bash
uv run --frozen python scripts/validate_pi_no_send.py \
  --sources claude-code,claude-app,cursor,linear,pydantic-ai,granola,agent-deck,beads,gas-city,codex,pi \
  --receipt data/pi-codex-recheck.json
```

This is real authenticated subscription inference and real source fetching, not
provider mocks. It blocks Telegram POSTs/notifier construction and refuses the
protected primary. The offline gate remains entirely mocked/network-free.

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

# After review of a proven-good baseline (Pi subscription already validated):
uv run --frozen python recovery_preview.py --baseline-ref <reviewed-ref> \
  --max-pages 3 --max-releases 5 --sources claude-code,beads
```

The second command only builds a bounded preview: at most three 100-release
archive pages and five selected candidates per GitHub source (hard caps:
five pages/ten selected releases). It excludes baseline tags, deduplicates
archive results, reports unresolved/unselected candidates, and fails honestly
when the bound does not locate needed history or parsing fails. There is
**no send or state-rewrite option**. A synthetic archive catch-up fixture passes.
In the first PR iteration (before the Pi/Codex decision), a live two-release
preview selected Claude Code `v2.1.296`/`v2.1.295`, reported 51 unselected/unlocated
candidates and failed Claude auth safely. That is historical evidence, not the
current provider state. No live recovery baseline was changed or newly approved
on continuation. A successful current-source Pi preview does **not** establish
last-proven historical delivery. A human must choose the proven-good boundary,
review duplicates against Telegram history, approve the
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
Fingerprints during the **October 13 initial implementation** remained:

- `state.json`: `c47497c35eef4b2091c03d51ea06b1da3ec02092a405acc78155caf0d2134657`
- `.beads/backup/manifest`: `9f435406983abb46eebe766dbcde2507c2d1b367725ab0b9593b286afd1a0d90`

On the October 15 continuation, the primary had legitimately changed since
that earlier run. Its new read-only baseline was preserved rather than restored
or reset to an older snapshot:

- `state.json`: `29cebefbca1f2b0446442a6833f4a11cebeb171bd91a0d9d03e98ebd39cced99`
- `.beads/backup/manifest`: `4e9630cb7dbb482b732d243c7938acd8e3ac77f65a045afad7651e1109122767`

Authenticated validation verified all protected evidence unchanged across its
runs. Credentials, existing sessions/offsets, logs and uncertain backups remain
in place. No original sensitive log was changed. Pi's supported SDK can refresh
its own existing OAuth store in place; it never copies credentials here.
After reviewed authorization:

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

Repository gate: `bash scripts/check.sh` — **79 Python + 14 Node tests pass**
(offline failure matrices, process
concurrency, parser/state migration, atomic crash-window retries, bot safety,
no-send end-to-end preview, syntax/compile and whitespace checks). Also run the
catalog's exact fixed compile gate separately. Node tests additionally cover
subscription-only auth, wrong-provider/model/API/endpoint refusal, strict schema,
input/output/stream/deadline limits and no fallback after quota/network failures.
No offline gate runs a real bot listener, provider or Telegram request.

Push only `work/td-f5l-ready-work`; update existing PR #2 targeting `main`,
with no auto-merge. The code is ready for review, not a claim of production
installation or completed historical recovery. Requesting review is allowed;
merge and operations still require external authorization. Exact boundaries:

1. **Review/merge:** approve the Pi subscription adapter and advisory-only bot.
   Original swallowed-release acceptance still needs a proven-good delivery
   baseline and an approved recovery plan; do not infer delivery from cursors.
   Review pending first-run batches (especially the new Pi GitHub cursor) before
   enabling scheduled sends; never pre-seed seen cursors to hide the backlog.
   Claude authentication/API-key provisioning is no longer a blocker or action.
2. **Production installation:** the Oct 16 PATH failure is superseded by the
   reviewed runtime pin in `config/pi-runtime.json`. The actual listener
   environment and system-only PATH now pass real subscription no-send checks
   in the worktree; no cron/service PATH edit is needed. This does not install
   code in the primary. No approved external Digest dispatcher exists; a human
   must authorize/designate an external installer after reviewed merge. The
   [current executable handoff](td-f5l-operator-handoff.md) includes exact
   commands and a guarded no-send installation helper that preserves dirty
   runtime evidence and leaves cron paused/listener stopped. No worker merge,
   install, restart or activation authority is granted.
3. **Operations:** installation into production, any authorized activation/restart,
   preservation-aware sensitive-log rotation, recovery reconciliation and explicit
   bounded catch-up-send approval remain operator actions. Bead closure waits
   for reviewed completion of original acceptance. No worker deployment authority.

No merge, installation, activation/restart, catch-up send or state reset occurred.
Because runtime state is tracked historically, reviewed installation must preserve
its dirty cursor and manifest rather than use `git reset --hard`.
