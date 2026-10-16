# td-f5l / PR #2: external-operator handoff

## Current incident status — 2026-10-16 UTC

**The production Digest is not repaired yet.** PR #2 contains the retained repair;
the protected production checkout and running listener still use `781d7af`.
Passing worktree tests do not install that code or recover swallowed releases.
Chris authorized Pi/Codex parsing, **not historical catch-up**.

This is the same Bead, repository owner `0e5025f5b4821403`, feature branch
`work/td-f5l-ready-work`, and [PR #2](https://github.com/c2keesey/tech-digest/pull/2).
No duplicate issue, worker, PR or corrective infrastructure lineage was created.

### Fresh, real no-send proof

| Run (UTC) | Cursor basis | Real source result | Subscription fixture/advisory | Telegram |
| --- | --- | --- | --- | --- |
| Oct 16 14:08:14 | Retained worktree | 11 checked; 10 summarized, Granola unchanged; exit 0 | Both passed | 0 requests, 0 notifier constructions |
| Oct 16 14:12:57 | **Primary cursor read-only, in memory** | 11 checked; **Pydantic AI and Pi summarized**, 9 unchanged; exit 0 | Both passed | 0 requests, 0 notifier constructions |
| Oct 16 14:15:21 | Primary cursor + minimal candidate operator environment | Same 2 summarized / 9 unchanged; exit 0 | Both passed | 0 requests, 0 notifier constructions |

All three used installed Pi **0.84.1**, explicit `openai-codex/gpt-6.1-sol`,
`openai-codex-responses`, existing subscription OAuth, no API keys/paid fallback.
There were no fetch/parse failures. Runs took 89.06s, 26.39s and 26.77s respectively.
All fingerprinted worktree runtime files and primary state, outbox, manifest,
credentials, offsets/sessions and logs were unchanged. No provider transcript,
release body or credential was persisted. Local mode-0600 receipts:

- `data/pi-codex-all-sources-2026-10-16.json`
- `data/pi-codex-primary-cursor-2026-10-16.json`
- `data/pi-codex-operator-env-2026-10-16.json`

The validator now accepts `--observed-state`: it reads and normalizes that file
once, passes data to generation in memory, **never changes `STATE_FILE` or any
write target**, and rejects missing/corrupt inputs before inference. An observed
file change invalidates the receipt. This is source-selection evidence, not an
outbox reconciler or historical-delivery proof. In particular, nine unchanged
sources may still include previously swallowed releases: cursors are not ACKs.

Offline: **58 Python + 14 Node tests (72 total)** pass, including three new
observed-state safety tests. `bash scripts/check.sh` and the exact catalog
compile gate pass. Existing ACK-only locks/outbox, advisory-only bot, no-key and
no-fallback constraints are unchanged.

## Exact remaining gates and who must authorize them

### 1. Reviewed merge — repository maintainer, not this worker

The catalog requires a **reviewed PR to `main`**, `autoMerge: false`, deployment
policy `pull-request-handoff-only`, worker deployment/restart authority **none**.
It does not prohibit requesting review by removing draft status. With fresh
provider/offline proof, the code is ready **for review**, not production-certified
or original-Bead-complete. Marking PR #2 ready for review does not authorize
merge, installation or sends. Check the current PR head before approving.

A human/repository-designated reviewer must approve the subscription-only
adapter, ACK-only delivery and intentionally advisory-only listener, then a
maintainer must explicitly authorize/perform the reviewed merge. At this audit
there were **no submitted reviews**, no auto-merge, and GitGuardian passed on
`224f49a`. An unprotected GitHub branch/admin permission is **not** permission to
bypass the catalog review requirement. No worker merge is permitted.

Historical recovery remains an open acceptance item on original `td-f5l`; do not
close it simply because the code PR is merged. Review may accept installation of
the forward-path repair separately without approving historical sends.

### 2. Production installation/configuration — named external operator

Read-only host evidence on **`c2k-optiplex`**:

- Primary HEAD: `781d7af6b6d4b8aabd16269cb3813a057237e913` (old implementation).
- One active crontab entry invokes the primary `run_digest.sh`; the crontab has
  **no explicit PATH**. A `/usr/bin:/bin` discovery probe of the new adapter in
  the worktree returns **`pi-runtime-unavailable`**.
- **`systemctl --user` unit `tech-digest-bot.service` is loaded, active/running**,
  fragment `/home/c2k/.config/systemd/user/tech-digest-bot.service`, working
  directory `/home/c2k/repos/tech-digest`, `uv run ... bot.py` entrypoint. Main
  `uv` PID 1297 and Python child 1523 were observed; these PIDs are not stable.
- Its live Python process has HOME `/home/c2k` and a PATH containing the primary
  `.venv/bin` and system paths, **not the installed Node/Pi directory**. A
  worktree-only discovery probe using only that process's nonsecret runtime
  environment also returns **`pi-runtime-unavailable`**.
- Working interactive Node/Pi prefix:
  `/home/c2k/.nvm/versions/node/v24.13.0/bin`. Do not rely on interactive shell
  startup or assume `~/.local/bin/pi` alone exposes the public SDK/runtime.

**Correction to the Oct 15 handoff:** the earlier “no digest/Telegram user unit
found” observation was incomplete. The current worker initially lacked a user
bus environment; explicitly connecting to `/run/user/1000/bus` made the real
unit observable. The listener installation method is now identified; its
runtime PATH is an evidenced blocker, not an unidentified service.

Required operator plan, **not executed and not authorized by parser approval**:

1. Obtain explicit approval for a production no-send maintenance window, the
   named installer, runtime PATH/configuration changes, and preservation-aware
   log handling. Coordinate/pause the existing scheduler/listener only under
   that separate operational authorization; old running code does not honor the
   new shared lock. Do not restart Agent Console or any unrelated service.
2. Preserve the primary's dirty cursor, manifest, outbox if present, offsets,
   sessions and sensitive logs. Record fresh hashes privately; retain restricted
   state/outbox/log evidence. Leave credentials in place: **never copy `.env`,
   Pi `auth.json` or tokens**, including into a worktree or deployment bundle.
3. After the exact PR is reviewed/merged, inspect the merge diff for runtime
   paths and install only the approved main commit. This PR does not change
   `state.json` or the Beads manifest. Use a preservation-aware fast-forward,
   never `reset --hard`, runtime-file stashing/cleanup or blanket staging. If
   another automation changes the branch or a runtime path conflicts, stop and
   reconcile rather than overwrite it. Run the reviewed frozen dependency setup
   only as part of that authorized installation.
4. Review the machine configuration source in `~/repos/dotfiles` and installed
   user-unit configuration; expose the supported Node/Pi prefix in **both** cron
   and listener PATH (not only the current terminal). Keep actual-user HOME and
   its existing supported Pi OAuth/catalog store. No credentials copied, paid
   provider or model substitution; absent Sol/OAuth must fail closed.
5. Re-run no-send validation from the retained worktree with the **approved
   runtime environment**, then verify the installed commit, both effective
   environments and preservation fingerprints. A worktree receipt is not proof
   that the unit/cron configuration was applied. Keep send paths paused until
   the next gate is explicitly approved. Any unit reload/restart/activation is
   a separately authorized external-operator action, never a worker action.

Reproducible **no-send** check (isolated worktree only; real source GETs and
subscription calls; no credential setup):

```bash
cd /home/c2k/repos/tech-digest.work-td-f5l-ready-work
# These values describe the working approved-candidate runtime, not an install.
# The operator must also verify the eventual cron and unit effective PATH/HOME.
env -i HOME=/home/c2k USER=c2k LOGNAME=c2k LANG=C.UTF-8 \
  PATH=/home/c2k/.nvm/versions/node/v24.13.0/bin:/home/c2k/.local/bin:/usr/bin:/bin \
  /home/c2k/.local/bin/uv run --frozen python scripts/validate_pi_no_send.py \
  --observed-state /home/c2k/repos/tech-digest/state.json \
  --sources claude-code,claude-app,cursor,linear,pydantic-ai,granola,agent-deck,beads,gas-city,codex,pi \
  --receipt "data/operator-no-send-$(date -u +%Y%m%dT%H%M%SZ).json"
```

This minimal-environment command was actually validated at 14:15:21 UTC; it
proves the proposed runtime works without inherited worker secrets, not that
cron/service PATH has been installed. Do not overwrite prior evidence. If the
existing actual account uses a supported explicit Pi agent-dir
setting, preserve that context in the reviewed configuration without copying
its contents. Never run `digest.py` without `--preview`, `bot.py`, or
`run_digest.sh` as validation. Do not redirect source previews into service logs.

### 3. Activation / first-run sends / historical recovery — separate human gate

Installing code is not approval to deliver a backlog. At the read-only primary
cursor snapshot, Pydantic AI and the **new Pi GitHub source** had pending current
batches. These change with time and are not an approved send list. The operator
must review the exact fresh pending batch and any frozen outbox, reconcile
`inflight`/`uncertain` chunks against trusted Telegram evidence, and receive
explicit activation/first-run-send approval before resuming scheduled delivery.
Do not mark unseen versions seen to hide the pending batch or delete an outbox.

Historical catch-up is still **unauthorized**. Need trusted Telegram/history
evidence of a last proven good summary, reviewed duplicate reconciliation, an
exact bounded preview and explicit batch-delivery approval. `e45ec38` is only a
provisional inventory boundary; do not turn it into a proven recovery baseline.
The read-only primary cursor used above is not a new recovery baseline either.
See [the retained inventory/reconciliation handoff](td-f5l-handoff.md). No reset,
catch-up send or Bead closure is included in Pi parser approval.

## Retained supervisor-exit evidence (not an application/provider diagnosis)

The retained repository-scoped owner state at
`~/.local/state/agent-console/pi-workers/0e5025f5b4821403/td-f5l/state.json`
records:

- `recoverySource.phase: failed`;
- `recoverySource.error: "worker supervisor exited unexpectedly; the worktree and session were retained for recovery"`;
- inherited `failureCode: supervisor_exit`; **not** a claim that the current
  live attempt is failed;
- the same retained worktree, branch and owner; current supervisor attempt **4**
  began `2026-10-16T14:06:24.305Z` (`events.jsonl`, `supervisor_start`, recover true).

The prior attempt began `2026-10-15T04:51:12.608Z`. The supervisor log is empty;
the bounded prior-attempt journal query only established a start, not an exit
cause/status. The older `pi_exit` code **143** at `2026-10-14T15:54:08.201Z`
belongs to an earlier attempt and is **not evidence of the Oct 15 exit cause**.
Do not invent a timeout/OOM/authentication cause or corrective lineage.

At worker entry the feature branch had again been reset to `origin/main`
(`781d7af`), with a reflog timestamp `2026-10-16T14:06:31Z`; PR #2 and its remote
feature branch still retained `224f49a`. After fetching, divergence was **0 local /
2 remote commits**. The worker fast-forwarded the same branch to that exact PR
head, without reset, cleanup, duplicated implementation or new setup. Lock and
evidence artifacts were preserved. This reset is observed separately from the
supervisor-exit report; causation is not established. Future supervision must
reconcile the actual PR head before any retained-base reuse. Infrastructure
investigation belongs to the existing supervisor's handoff, not a new td Bead.

## Preservation baseline for this continuation

The primary changed between sessions; old hashes are evidence, not restore
instructions. Current initial/final validation hashes:

- `state.json`: `d02f57c6c4dd7260f879189f95472e66cf0674777f5a73722cda81e0d044b7ea`
- `.beads/backup/manifest`: `4e9630cb7dbb482b732d243c7938acd8e3ac77f65a045afad7651e1109122767`
- Primary outbox absent at audit; do not create/reset one to make an installation
  look clean. Preserve any outbox appearing later and re-review the fresh state.

Dirty primary `state.json`, manifest and the existing gate-lock artifact remain
untouched. No worker operation changed services, cron, secrets, logs, delivery
state or recovery baseline. **Production remains unchanged until the explicitly
authorized external-operator installation/activation is verified.**
