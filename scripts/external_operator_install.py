#!/usr/bin/env python3
"""EXTERNAL OPERATOR ONLY: install reviewed/merged PR2, leaving delivery paused.

Default is a read-only readiness check. --apply requires a separately authorized
external c2k login, reviewed head and an approval reference. It never merges a
PR, starts/restarts a service, sends, resets state, copies credentials or rotates
logs. Partial failure deliberately leaves cron paused and the listener stopped.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import fcntl
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIMARY = Path('/home/c2k/repos/tech-digest')
UNIT = 'tech-digest-bot.service'
WRAPPER = str(PRIMARY / 'run_digest.sh')
PAUSED = '# td-f5l no-send maintenance: '
SOURCES = 'claude-code,claude-app,cursor,linear,pydantic-ai,granola,agent-deck,beads,gas-city,codex,pi'
RUNTIME_NAMES = ('state.json', '.digest-outbox.json', '.beads/backup/manifest', '.env', '.bot_offset', '.bot_session')
ALLOWED_DIRTY = {'state.json', '.beads/backup/manifest'}


class InstallBlocked(RuntimeError):
    pass


def run(argv, *, cwd=None, input=None, env=None):
    result = subprocess.run(argv, cwd=cwd, input=input, env=env, capture_output=True, text=True)
    if result.returncode:
        raise InstallBlocked('operator-command-failed; raw diagnostics withheld; do not resume delivery')
    return result.stdout


def git(repo, *args):
    # Avoid incidental Beads post-merge backup writes during an approved install;
    # this is not a PR merge or a replacement for the repository quality gates.
    return run(['git', '-c', 'core.hooksPath=/dev/null', '-C', str(repo), *args]).strip()


def external_guard():
    cgroup = Path('/proc/self/cgroup').read_text()
    if any(k.startswith('PI_WORKER_') for k in os.environ) or 'agent-console' in cgroup:
        raise InstallBlocked('external-login-required; never strip worker identity to bypass this guard')
    if socket.gethostname() != 'c2k-optiplex' or Path.home() != Path('/home/c2k') or os.getuid() != 1000:
        raise InstallBlocked('approved-c2k-optiplex-login-required')


def merged_target(pr, approved):
    if (not re.fullmatch(r'[0-9a-f]{40}', approved)
            or pr.get('number') != 2 or pr.get('head', {}).get('sha') != approved
            or pr.get('head', {}).get('ref') != 'work/td-f5l-ready-work'
            or pr.get('base', {}).get('ref') != 'main'
            or pr.get('base', {}).get('repo', {}).get('full_name') != 'c2keesey/tech-digest'):
        raise InstallBlocked('reviewed-PR-head-mismatch')
    target = pr.get('merge_commit_sha')
    if not pr.get('merged_at') or not isinstance(target, str) or not re.fullmatch(r'[0-9a-f]{40}', target):
        raise InstallBlocked('PR2-not-merged; maintainer-reviewed-merge-required; autoMerge-remains-false')
    return target


def paused_crontab(text):
    lines = text.splitlines()
    active = [i for i, line in enumerate(lines) if WRAPPER in line and not line.lstrip().startswith('#')]
    paused = [i for i, line in enumerate(lines) if line.startswith(PAUSED) and WRAPPER in line]
    if not active and len(paused) == 1:
        return text  # Safe retry after a partial install; never enable delivery.
    if len(active) != 1 or paused:
        raise InstallBlocked('expected-one-digest-cron-entry; reconcile-schedulers-manually')
    lines[active[0]] = PAUSED + lines[active[0]]
    return '\n'.join(lines) + '\n'


def check_dirty(changed, staged):
    if staged or set(changed) - ALLOWED_DIRTY:
        raise InstallBlocked('unexpected-primary-diff; preserve-and-review; no-stash-or-reset')


def check_install_paths(changed):
    for name in changed:
        if (name in RUNTIME_NAMES or name.startswith(('.beads/', 'logs/', '.bot', '.runtime'))):
            raise InstallBlocked('merge-touches-runtime-evidence; manual-preservation-review-required')


def fingerprints():
    paths = [PRIMARY / name for name in RUNTIME_NAMES]
    paths += sorted(p for p in (PRIMARY / 'logs').rglob('*') if p.is_file())
    return {str(p.relative_to(PRIMARY)): hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
            for p in paths}


def no_live_digest(proc=Path('/proc')):
    for p in proc.iterdir():
        if not p.name.isdigit():
            continue
        try:
            args = (p / 'cmdline').read_bytes().split(b'\0')
            if any(WRAPPER.encode() in a for a in args):
                raise InstallBlocked('in-flight-digest; leave-paused-and-wait; never-kill-or-replay')
            if (p / 'cwd').resolve() == PRIMARY and any(a in (b'digest.py', b'bot.py',
                    str(PRIMARY / 'digest.py').encode(), str(PRIMARY / 'bot.py').encode()) for a in args):
                raise InstallBlocked('in-flight-digest-or-listener; preserve-and-review')
        except (OSError, PermissionError):
            continue


def check_quiet(paused, service_env):
    if (run(['crontab', '-l']) != paused or run(['systemctl', '--user', 'show', UNIT,
            '--property=ActiveState', '--value'], env=service_env).strip() != 'inactive'):
        raise InstallBlocked('maintenance-no-longer-quiescent; preserve-and-review')
    no_live_digest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approved-head', required=True, help='Exact 40-char PR head approved by the reviewer')
    parser.add_argument('--apply', action='store_true', help='External approved no-send maintenance install ONLY')
    parser.add_argument('--approval-reference', help='Recorded human installation/window approval, not an API credential')
    args = parser.parse_args(argv)
    maintenance = False
    installed = False
    lock = None
    try:
        if args.apply:
            external_guard()  # Before subprocesses, fetch, mkdir, cron or service operations.
            if not args.approval_reference or not args.approval_reference.strip():
                raise InstallBlocked('explicit-installation-window-approval-reference-required')
            lock = os.open(ROOT / 'data' / '.operator-install.lock', os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pr = json.loads(run(['gh', 'api', 'repos/c2keesey/tech-digest/pulls/2']))
        target = merged_target(pr, args.approved_head)
        if git(ROOT, 'rev-parse', 'HEAD') != args.approved_head or git(ROOT, 'status', '--porcelain', '--untracked-files=no'):
            raise InstallBlocked('retained-worktree-is-not-the-clean-reviewed-head')
        if git(PRIMARY, 'branch', '--show-current') != 'main':
            raise InstallBlocked('primary-is-not-main')
        if git(PRIMARY, 'remote', 'get-url', 'origin') not in (
                'git@github.com:c2keesey/tech-digest.git', 'https://github.com/c2keesey/tech-digest.git'):
            raise InstallBlocked('primary-origin-identity-mismatch')
        check_dirty(git(PRIMARY, 'diff', '--name-only').splitlines(), git(PRIMARY, 'diff', '--cached', '--name-only'))
        cron = run(['crontab', '-l'])
        paused = paused_crontab(cron)
        if not args.apply:
            print(json.dumps({'ready_for_external_install': True, 'target': target,
                              'applied': False, 'activation_authorized': False}))
            return 0
        critical = {k: v for k, v in fingerprints().items() if k in RUNTIME_NAMES}
        # Compare again before replacing the crontab; unrelated entries remain byte-identical.
        if run(['crontab', '-l']) != cron:
            raise InstallBlocked('crontab-changed; preserve-and-recheck')
        run(['crontab', '-'], input=paused)
        maintenance = True
        service_env = dict(os.environ, XDG_RUNTIME_DIR='/run/user/1000',
                           DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/1000/bus')
        run(['systemctl', '--user', 'stop', UNIT], env=service_env)
        check_quiet(paused, service_env)
        before = fingerprints()
        if critical != {k: v for k, v in before.items() if k in RUNTIME_NAMES}:
            raise InstallBlocked('runtime-changed-during-quiesce; preserve-and-review-before-install')
        git(PRIMARY, 'fetch', 'origin', 'main')
        git(PRIMARY, 'merge-base', '--is-ancestor', target, 'origin/main')
        git(PRIMARY, 'merge-base', '--is-ancestor', 'HEAD', target)
        if git(PRIMARY, 'rev-parse', target + '^{tree}') != git(ROOT, 'rev-parse', args.approved_head + '^{tree}'):
            raise InstallBlocked('merged-tree-differs-from-reviewed-head; review-before-install')
        check_install_paths(git(PRIMARY, 'diff', '--name-only', 'HEAD', target).splitlines())
        check_dirty(git(PRIMARY, 'diff', '--name-only').splitlines(), git(PRIMARY, 'diff', '--cached', '--name-only'))
        if before != fingerprints():
            raise InstallBlocked('runtime-changed-before-fast-forward; leave-delivery-paused')
        check_quiet(paused, service_env)
        git(PRIMARY, 'merge', '--ff-only', target)
        installed = True
        run(['/home/c2k/.local/bin/uv', 'sync', '--frozen'], cwd=PRIMARY)
        # Real provider proof remains in the isolated worktree: never run the live bot/send entrypoints.
        receipt = ROOT / 'data' / ('operator-install-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.json')
        env = {'HOME': '/home/c2k', 'USER': 'c2k', 'LOGNAME': 'c2k', 'LANG': 'C.UTF-8', 'PATH': '/usr/bin:/bin'}
        run(['/home/c2k/.local/bin/uv', 'run', '--frozen', 'python', 'scripts/validate_pi_no_send.py',
             '--observed-state', str(PRIMARY / 'state.json'), '--sources', SOURCES, '--receipt', str(receipt)], cwd=ROOT, env=env)
        if before != fingerprints() or git(PRIMARY, 'rev-parse', 'HEAD') != target:
            raise InstallBlocked('post-install-evidence-mismatch; leave-delivery-paused')
        check_quiet(paused, service_env)
        record = {'installed_commit': target, 'reviewed_head': args.approved_head,
                  'no_send_receipt': str(receipt), 'runtime_evidence_unchanged': True,
                  'approval_reference_sha256': hashlib.sha256(args.approval_reference.encode()).hexdigest(),
                  'cron_paused': True, 'listener_stopped': True, 'activation_authorized': False}
        record_path = receipt.with_name(receipt.stem + '-handoff.json')
        fd = os.open(record_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(record, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps({**record, 'handoff_record': str(record_path)}))
        return 0
    except (InstallBlocked, OSError, ValueError):
        error = sys.exc_info()[1]
        print(json.dumps({'blocked': str(error) if isinstance(error, InstallBlocked) else 'operator-preflight-failed',
                          'state': 'maintenance-incomplete' if maintenance else 'blocked-before-install',
                          'source_fast_forward_performed': installed, 'activation_authorized': False,
                          'warning': 'If maintenance began, leave cron paused/listener stopped; no automatic rollback or resume.'}))
        return 2
    finally:
        if lock is not None:
            os.close(lock)


if __name__ == '__main__':
    raise SystemExit(main())
