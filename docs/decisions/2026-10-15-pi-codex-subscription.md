# Decision: Pi / OpenAI Codex subscription, not Claude authentication

- **Decision owner:** Chris, explicit follow-up on the existing `td-f5l` / PR #2.
- **Recorded:** 2026-10-15 UTC.
- **Status:** implemented and authenticated no-send validation passed in the
  retained isolated worktree; not merged, installed or deployed.
- **Rechecked 2026-10-19:** [current executable operator handoff](../td-f5l-operator-handoff.md)
  records fresh real subscription proof with system-only PATH and the actual
  listener environment, against primary cursors read-only. The explicit reviewed
  `config/pi-runtime.json` Node/Pi pin resolves the prior PATH blocker in code;
  no machine PATH edits are needed. 87 offline tests pass. No approved external
  Digest dispatcher exists: human review/merge and a named external no-send
  installer are still needed. Production remains old code.

## Decision and non-negotiable boundaries

Replace the production Claude parsing path with supported Pi OpenAI Codex
**ChatGPT subscription OAuth**, explicitly selecting **`openai-codex/gpt-6.1-sol`**
with low reasoning. The old proposal to reauthenticate Claude is superseded:
**Claude authentication is not a remaining repair requirement**.

No API-key path, paid provider, other model/provider fallback, credential copying
or new authentication setup is authorized. Reuse the actual service user's
existing Pi OAuth store through the supported SDK, including its locked in-place
refresh. Never copy `auth.json`, tokens, `.env` or credentials into the worktree,
a session artifact, a deployment bundle or a new service account.

Preserve the existing ACK-only source cursors, shared lock, atomic outbox and
ambiguous-delivery barrier. Keep the maintenance bot advisory-only. Do not reset
or rewrite primary state, establish a new recovery baseline by inference, send a
catch-up, merge, deploy, install into production, or restart any service here.

## Implementation contract

Python invokes a small Node bridge through the **public Pi `ModelRuntime` SDK**
from the existing installed `pi` package; no npm dependency installation or
private provider transport/token extraction is used. The bridge uses an explicit
empty provider-override config and the existing supported public model catalog.
It accepts only subscription OAuth for the native Codex provider, verifies the
exact model/API and `https://chatgpt.com/backend-api` endpoint before dispatch,
and checks the returned model identity. No user model/provider overrides,
settings, resource discovery, context files, extensions, hooks, tools or agent
sessions are loaded. All provider API-key and parent-worker secret environment
variables are excluded from the child.

One source parse is one inference request: strict JSON schema via the supported
`onPayload` hook, client schema validation, zero automatic request retries, SSE,
192 KiB combined prompt limit (no truncation), 256 KiB request-frame limit,
16 KiB final-text limit, 64 KiB streamed-text/thinking limit, and a 120-second
hard deadline with parent-process timeout protection. The Codex adapter does not
honor `maxTokens`; byte/schema/deadline bounds are used honestly instead of
claiming a server token cap. Oversized/invalid/failed responses leave cursors
pending. Community enrichment's dormant Claude invocation is disabled, not a
fallback. Advisory requests use the same subscription adapter without tools.

## Evidence

The real supported provider call, not a mock, returned validated synthetic JSON
with the expected fixture version. The subsequent real default-source CLI
preview and advisory validation passed at **2026-10-15T05:02:14Z**, using Pi
**0.84.1**:

- explicit `openai-codex` / `gpt-6.1-sol` / `openai-codex-responses`, OAuth only;
- all **11 default sources** checked, **10 summarized**, Granola unchanged;
- preview exit **0**, no fetch/parse failures, advisory response valid;
- **zero Telegram requests** and zero notifier constructions;
- worktree cursor/outbox/session files and protected-primary state, manifest,
  credentials, offsets/sessions and logs unchanged across validation;
- 75.12 seconds for fixture + full preview + advisory; no raw release text,
  private identifiers, credentials or provider transcript persisted;
- offline gate: **55 Python + 14 Node tests (69 total)** pass, plus the exact
  catalog compile gate, JavaScript/shell syntax and whitespace checks.

An initial 96 KiB limit correctly rejected the real 127,959-byte Claude Code
batch without changing state. It was raised to the explicit 192 KiB bound,
without truncation, and both the two-source and full-default runs then passed.
Local content-free receipts remain under ignored `data/`; the failing attempt
was retained rather than overwritten. Re-run explicitly from this worktree:

```bash
uv run --frozen python scripts/validate_pi_no_send.py \
  --sources claude-code,claude-app,cursor,linear,pydantic-ai,granola,agent-deck,beads,gas-city,codex,pi \
  --receipt data/pi-codex-recheck.json
```

This command makes real subscription requests and real source GETs, but blocks
Telegram POSTs/notifier construction and captures preview text in memory only.
It refuses to run in the protected primary.

## Remaining review / installation boundaries

1. **Review/merge:** PR #2 targets main, with no auto-merge. Fresh evidence makes
   the code ready for review; requesting review does not authorize merge or
   complete historical recovery. A maintainer must approve the reviewed merge.
   Review the subscription-only integration and intentional advisory-only bot.
   Original swallowed-release acceptance still lacks a proven delivery baseline;
   the historical August snapshot remains provisional, not approval to rewind
   or re-send. Current successful previews do not prove historical delivery.
   Review first-run pending batches, particularly Pi's new GitHub source, before
   enabling scheduled sends; do not pre-seed cursors as seen to hide a backlog.
2. **Runtime installation:** the prior PATH failure is now fixed in the PR by
   the explicit validated installed Node/Pi pair in `config/pi-runtime.json`;
   real no-send calls passed with `/usr/bin:/bin` and the actual running
   `tech-digest-bot.service` environment. This supersedes the earlier proposal
   for machine PATH edits, not the installation boundary. Install only the
   reviewed merged code via a separately authorized external operator, preserving
   HOME and the existing OAuth/catalog store. No credentials copied, API keys or
   model/provider fallback. The guarded external helper leaves delivery paused;
   activation still needs separate approval. No approved Digest deployment
   dispatcher is configured. See the executable handoff.
3. **Operations:** production checkout/dependency installation, any authorized
   activation/restart, sensitive-log preservation/rotation, historical recovery
   reconciliation and explicit batch delivery approval remain operator actions.
   The existing dirty primary cursor/manifest must survive installation.

No Claude reauthentication or API-key provisioning is on this list.
