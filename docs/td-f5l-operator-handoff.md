# td-f5l / PR #2: executable external-operator handoff

## Delivery status — 2026-10-19 UTC

**Repair and runtime-PATH fix are implemented/validated in the same PR #2;
production still uses legacy Claude parsing (now `3aa7d14`), not this repair.**
PR #2 is open, ready for
review, targeting main, auto-merge disabled. No review/merge/install/activation
has been performed by this worker. Historical catch-up remains unauthorized.

**External operator availability:** no approved Digest deployment dispatcher or
assigned external operator is exposed by the current catalog/application
contract. The catalog specifies `reviewed-pull-request`, `autoMerge: false`,
`workerAuthority: none`, `pull-request-handoff-only`; it has no deployment hook.
`pi-worker handoff` sends an owner-completion message after merge, **not** an
installation/restart request. Agent Console's own promotion machinery is not a
Digest operator. No such hook was invoked, no duplicate owner was created, and
this worker must not impersonate an external operator by clearing its identity.
A human must designate/authorize the external `c2k` login described below.

## Concrete PATH blocker fixed in code

`config/pi-runtime.json` explicitly pins the existing supported Node/Pi bin
directory to `~/.nvm/versions/node/v24.13.0/bin`. `pi_runtime.find_pi_runtime()`
uses that exact pair, resolves the installed Pi CLI to its public SDK, validates
the package name, and fails closed if the pair/config/SDK is unavailable. It
never sources an interactive shell, chooses a version by glob, trusts a PATH
wrapper, installs software, copies credentials, or falls back to another model
or provider. Both cron parsing and the advisory-only bot use this adapter.

**No cron/service PATH edit is now required for this installed runtime.** This
supersedes the Oct 16 handoff's proposed machine-configuration PATH edits. The
existing service-user HOME/OAuth/catalog store remains in place. A future move
of the installed runtime requires reviewing the public runtime pin, not silently
finding another executable. The supported model is still explicitly
`openai-codex/gpt-6.1-sol`, subscription OAuth only, with bounded structured JSON,
no API keys, paid fallback, tools or agent sessions. ACK-only cursors/outbox and
shared locks are unchanged.

## Actual authenticated no-send proof

Installed Pi **0.84.1**, real source GETs and subscription inference, primary
cursor read once **read-only in memory**, all 11 default sources:

| UTC start, Oct 19 | Environment used in isolated worktree | Result |
| --- | --- | --- |
| 14:20:29 | `env -i`, HOME `/home/c2k`, **PATH `/usr/bin:/bin` only** | fixture + preview + advisory passed; 26.76s |
| 14:22:28 | Nonsecret HOME/PATH/context from the actual running listener's Python process; Node prefix absent from PATH | same checks passed; 24.47s |
| 14:33:00 | After rebasing/reconciling concurrent main, system-only PATH | fixture + preview + advisory passed; 27.68s |

First two runs: Pydantic AI/Pi summarized, nine unchanged. The final run picked
up a newly pending Codex update: **three summarized, eight unchanged**. All
returned exit 0, no fetch/parse failures, **zero Telegram requests and notifier constructions**.
Worktree runtime files and primary state/outbox/manifest/credentials/sessions/
offsets/log fingerprints were unchanged. No provider transcripts, release text
or credentials were persisted. Receipts (ignored, mode 0600):

- `data/pi-codex-minimal-path-2026-10-19.json`
- `data/pi-codex-live-unit-env-2026-10-19.json`
- `data/pi-codex-rebased-minimal-path-2026-10-19.json`

Nine unchanged cursors are not proof of historical delivery. The potentially
swallowed-release inventory/provisional baseline in
[the retained recovery handoff](td-f5l-handoff.md) is unchanged.

Offline: **79 Python + 14 Node tests = 93 passing** (73 under `tests/`, six
reconciled root regressions). Five new runtime-discovery tests and ten new
external-install safety tests supplement the retained ACK,
crash-window, concurrency, migration, failure and no-paid-fallback matrices.
`bash scripts/check.sh` and the exact catalog compile gate pass. Real production
installation via the new helper has **not** been executed; its apply path was
validated only with isolated offline fixtures.

## Exactly what the human must approve/do

1. **Review and manually merge the exact latest PR #2 head**, including the
   explicit runtime pin and guarded installer. No submitted GitHub reviews were
   present at audit. Administrative access/unprotected main is not permission to
   skip catalog review. PR readiness is not automatic merge authorization.
2. **Name/authorize an external `c2k` operator on `c2k-optiplex`**, outside the
   worker/Agent Console process context, for a no-send maintenance window:
   pause only the Digest cron entry, stop only `tech-digest-bot.service`, preserve
   state/outbox/history/manifest/credentials/logs, fast-forward the primary to
   the reviewed merged commit, run `uv sync --frozen`, and validate without sends.
   Record the approval reference. This is not activation/catch-up authorization.
3. **After installation**, separately approve activation and the exact fresh
   first-run pending batch/outbox reconciliation. No activation command is
   supplied or run here. Historical recovery additionally requires trusted
   last-good Telegram/history evidence, duplicate reconciliation, an exact
   bounded preview and explicit batch-send approval. No cursor reset/pre-seeding.

Suggested approval wording (a request, **not an already granted approval**):

> I reviewed PR #2 head `<40-char SHA>` and approve its manual merge. I authorize
> `c2k` in an external login on c2k-optiplex for the documented no-send maintenance
> installation, including pausing Digest cron and stopping its bot. Leave both
> paused/stopped after installation; do not activate, reset cursors, send any
> catch-up or copy credentials. Approval record: `<reference>`.

### Executable commands — designated external operator only

Use the retained worktree. Do **not** reset/rebase it to main or copy credentials.
Run the merge command only after actual human review/merge authorization, then
run the installer only after the separately recorded maintenance authorization.
If PR #2 has already been merged by the maintainer, omit the merge command.

```bash
set -euo pipefail
cd /home/c2k/repos/tech-digest.work-td-f5l-ready-work
read -r -p 'Paste the exact reviewed PR2 head SHA: ' REVIEWED_HEAD
[[ "$REVIEWED_HEAD" =~ ^[0-9a-f]{40}$ ]]
read -r -p 'Recorded external no-send maintenance approval reference: ' APPROVAL
[[ -n "$APPROVAL" ]]

# Authorized external maintenance: prevent the legacy bot editing main while
# the reviewed merge/install proceeds. Leaves everything paused on failure.
/usr/bin/python3 - <<'PY'
import os
from scripts.external_operator_install import external_guard, run, paused_crontab, check_quiet, UNIT
external_guard()
cron = run(['crontab', '-l'])
paused = paused_crontab(cron)
if run(['crontab', '-l']) != cron:
    raise SystemExit('Crontab changed; preserve and recheck')
run(['crontab', '-'], input=paused)
env = dict(os.environ, XDG_RUNTIME_DIR='/run/user/1000',
           DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/1000/bus')
run(['systemctl', '--user', 'stop', UNIT], env=env)
check_quiet(paused, env)
PY

# Manual maintainer merge, NOT auto-merge, NOT a worker command.
gh api --method PUT repos/c2keesey/tech-digest/pulls/2/merge \
  -f sha="$REVIEWED_HEAD" -f merge_method=squash --jq '.merged' | grep -Fx true

# Read-only preflight; blocked until PR2 is merged at this reviewed head.
/usr/bin/python3 scripts/external_operator_install.py \
  --approved-head "$REVIEWED_HEAD"

# Explicit EXTERNAL operator action; never run this from the worker.
/usr/bin/python3 scripts/external_operator_install.py --apply \
  --approved-head "$REVIEWED_HEAD" --approval-reference "$APPROVAL"
```

The helper rejects worker identity/Agent Console cgroups **before subprocesses
or file creation** on `--apply`. It requires the correct host/account, exact
merged PR2 head/repository/base, clean retained source, primary branch main,
expected origin, no staged/other dirty tracked files, reviewed merged tree,
fast-forward ancestry and no runtime paths in the installation diff. Existing
dirty `state.json` and Beads manifest are explicitly allowed and preserved.

Under an installer lock it comments **only** the existing Digest crontab line
(never removes unrelated jobs), stops **only** the listener, rejects in-flight
Digest processes instead of killing/replaying them, and fingerprints protected
runtime files/logs. It fetches main and fast-forwards only to the exact reviewed
merged tree. Per-command Git hooks are suppressed solely to avoid incidental
Beads backup writes during installation, not to bypass review/tests. No hard
reset, stash, cleanup, runtime-file overwrite, credential copy or log rotation.
After frozen setup it runs the real no-send validator from the **worktree**, with
system-only PATH, against primary cursors read-only, then checks preservation.
It never invokes the default send/cron entrypoint or starts/restarts a service.

Success writes a mode-0600 handoff record with the exact installed commit,
reviewed head, approval-reference fingerprint and no-send receipt path, and emits
`cron_paused: true`, `listener_stopped: true`, `activation_authorized: false`.
It rechecks the paused crontab, inactive listener and absence of in-flight Digest
processes before installation and before reporting success.
If maintenance fails, stop and preserve the reported partial state; it deliberately
never rolls back dirty runtime files or automatically resumes delivery. The
maintenance marker remains in crontab for explicit subsequent activation review.
The helper does not rotate sensitive logs or close original `td-f5l`.

## Bounded retained supervisor-exit / branch evidence

Same owner `0e5025f5b4821403`, same Bead, worktree, feature branch and PR. Current
attempt **5** began `2026-10-19T14:11:23.461Z`. Retained owner state records prior
`recoverySource.phase: failed`, error **“worker supervisor exited unexpectedly;
the worktree and session were retained for recovery”**, inherited
`failureCode: supervisor_exit`. This is not a claim that the current live attempt
is failed. `supervisor.log` remains empty. A bounded prior-attempt unit-journal
query found a start only, no exit cause/status. The older Oct 14 Pi exit 143 does
not identify this exit. No OOM/timeout/authentication cause is invented.

Before worker actions, the reflog again showed a reset to `781d7af` at
`2026-10-19T14:11:31Z`, despite PR/remote head **`78f986f`**. The worker inspected
that exact head and all three retained unique commits; divergence was **0 local /
3 remote commits**, then restored by **fast-forward**, not reset. Existing locks
and evidence were retained, no new setup/owner/lineage. The reset and supervisor
exit are separate observations; causation is not established. Future supervisor
reuse must reconcile PR/unique work before moving refs. Infrastructure recovery
is not a new corrective Digest implementation.

## Concurrent main changes reconciled, not overwritten

While this worker was running, **other activity advanced primary/remote main**
from `781d7af` through `4083210` to `3aa7d14` (Oct 19 14:19 UTC). Only public
`digest.py`/`test_digest.py` changed: bounded unparsed excerpts and a `--replay`
path using legacy Claude parsing. PR #2 became conflicted. This is observed
concurrent activity, not evidence of the supervisor-exit cause.

The same retained feature was rebased onto the fetched current main. The
conflict was resolved in favor of truthful Pi parse failures, ACK-only delivery
and no replay/reset. Main's six root regression tests were adapted to preserve
honesty/escaping/auth/failure coverage while explicitly asserting replay/reset
are rejected before generation/send and failed parsing stays pending. The root
tests are now in the repository gate. No unique main work was silently ignored;
its original commits remain upstream and the policy conflict is explicit here.
The feature push uses an exact lease on retained PR head `78f986f`, not a blind
force push. Primary was never checked out/reset/edited by this worker.

Protected evidence was preserved, **not restored to an older fingerprint**:

- Primary state stayed `ab2cb182e2fccb32acfe2f0681fbd37e1344311adee07a11ee2255c63cfeae95`;
  outbox remained absent and credentials/session/offset fingerprints unchanged.
- Beads manifest changed concurrently from `4e9630cb7dbb482b732d243c7938acd8e3ac77f65a045afad7651e1109122767`
  to `574ab9421dd1cfb2fe4a3f976456117ec155fba50232ba02cbdcbfc004583ef9`.
- `logs/bot.log` gained **59 bytes**; the entire earlier content is a verified
  unchanged prefix. Other fingerprinted logs were unchanged. No raw log content
  was emitted. Exact writers of these concurrent file updates were not established.
- A new untracked primary `.gc/` appeared and was left alone, as were existing
  dirty state/manifest and gate-lock artifacts.

The initial comparison correctly detected the concurrent updates; all three
actual-provider runs each verified no protected-file changes **during that run**.
This is not a false claim that all primary files stayed unchanged for the whole
turn. Retain initial observations/receipts; do not reset any file to their hashes.
Coordinate the external maintenance window to prevent concurrent writers; the
installer checks quiescence/evidence and fails closed if they change.

Primary is now `3aa7d14`, still legacy code; the Pi repair has not been installed.
No worker merge, installation, service operation, cron change, send/reset,
credential copy, recovery-baseline change or Agent Console deployment occurred.
