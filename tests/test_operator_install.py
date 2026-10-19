"""Offline tests of external-only installation guards; no production writes."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import external_operator_install as install

HEAD = 'a' * 40
TARGET = 'b' * 40
DATA = Path(__file__).resolve().parents[1] / 'data'


def pr():
    return {'number': 2, 'head': {'sha': HEAD, 'ref': 'work/td-f5l-ready-work'},
            'base': {'ref': 'main', 'repo': {'full_name': 'c2keesey/tech-digest'}},
            'merged_at': '2026-10-19T00:00:00Z', 'merge_commit_sha': TARGET}


class OperatorInstallTests(unittest.TestCase):
    def setUp(self):
        DATA.mkdir(exist_ok=True)

    def test_only_exact_reviewed_merged_PR2_can_be_installed(self):
        self.assertEqual(install.merged_target(pr(), HEAD), TARGET)
        for update in ({'merged_at': None}, {'number': 3}, {'merge_commit_sha': 'bad'},
                       {'head': {'sha': TARGET, 'ref': 'work/td-f5l-ready-work'}},
                       {'base': {'ref': 'main', 'repo': {'full_name': 'foreign/repo'}}}):
            with self.subTest(update=update), self.assertRaises(install.InstallBlocked):
                install.merged_target({**pr(), **update}, HEAD)

    def test_pause_changes_only_one_digest_line_and_never_enables_a_retry(self):
        original = 'MAILTO=""\n0 9 * * * /other/job\n0 8 * * * ' + install.WRAPPER + '\n'
        paused = install.paused_crontab(original)
        self.assertEqual(paused, 'MAILTO=""\n0 9 * * * /other/job\n' + install.PAUSED + '0 8 * * * ' + install.WRAPPER + '\n')
        self.assertEqual(install.paused_crontab(paused), paused)
        for value in ('', original + original, paused + original):
            with self.assertRaises(install.InstallBlocked):
                install.paused_crontab(value)

    def test_dirty_runtime_is_preserved_but_other_or_staged_changes_block(self):
        install.check_dirty(['state.json', '.beads/backup/manifest'], '')
        for changed, staged in ((['digest.py'], ''), ([], 'state.json')):
            with self.assertRaises(install.InstallBlocked):
                install.check_dirty(changed, staged)

    def test_merged_tree_cannot_touch_runtime_credentials_logs_or_beads(self):
        install.check_install_paths(['pi_runtime.py', 'config/pi-runtime.json'])
        for path in ('state.json', '.digest-outbox.json', '.env', '.bot_session', '.runtime.lock',
                     '.beads/backup/manifest', 'logs/error.log'):
            with self.subTest(path=path), self.assertRaises(install.InstallBlocked):
                install.check_install_paths([path])

    def test_worker_apply_is_blocked_before_any_subprocess_or_file_creation(self):
        with patch.dict(os.environ, {'PI_WORKER_BEAD': 'td-f5l'}), \
             patch('scripts.external_operator_install.Path.read_text', return_value='0::/user.slice'), \
             patch('scripts.external_operator_install.run') as run, \
             patch('scripts.external_operator_install.os.open') as create, redirect_stdout(io.StringIO()) as output:
            result = install.main(['--apply', '--approved-head', HEAD, '--approval-reference', 'human approval'])
        self.assertEqual(result, 2)
        self.assertIn('external-login-required', output.getvalue())
        run.assert_not_called()
        create.assert_not_called()

    def test_agent_console_cgroup_is_not_an_external_operator(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch('scripts.external_operator_install.Path.read_text', return_value='0::/agent-console.service'):
            with self.assertRaises(install.InstallBlocked):
                install.external_guard()

    def test_unmerged_read_only_check_never_invokes_installation(self):
        with patch('scripts.external_operator_install.run', return_value=json.dumps({**pr(), 'merged_at': None})) as run, \
             patch('scripts.external_operator_install.git') as git, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(install.main(['--approved-head', HEAD]), 2)
        self.assertIn('PR2-not-merged', output.getvalue())
        self.assertEqual(run.call_args.args[0][:2], ['gh', 'api'])
        self.assertEqual(run.call_count, 1)
        git.assert_not_called()

    def apply_fixture(self, fail_sync=False):
        directory = tempfile.TemporaryDirectory(dir=DATA)
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / 'data').mkdir()
        cron = '0 8 * * * ' + install.WRAPPER + '\n'
        def fake_run(argv, **kwargs):
            nonlocal cron
            if argv[:2] == ['gh', 'api']:
                return json.dumps(pr())
            if argv == ['crontab', '-l']:
                return cron
            if argv == ['crontab', '-']:
                cron = kwargs['input']
            if argv[:3] == ['systemctl', '--user', 'show']:
                return 'inactive\n'
            if fail_sync and argv[1:3] == ['sync', '--frozen']:
                raise install.InstallBlocked('synthetic-sync-failure')
            return ''
        def fake_git(repo, *args):
            if args == ('status', '--porcelain', '--untracked-files=no'):
                return ''
            if args == ('branch', '--show-current'):
                return 'main'
            if args == ('remote', 'get-url', 'origin'):
                return 'git@github.com:c2keesey/tech-digest.git'
            if args == ('diff', '--name-only'):
                return 'state.json\n.beads/backup/manifest'
            if args[:2] == ('diff', '--name-only'):
                return 'pi_runtime.py\nconfig/pi-runtime.json'
            if args == ('rev-parse', 'HEAD'):
                return HEAD if repo == root else TARGET
            if args[0] == 'rev-parse':
                return 'c' * 40
            return ''
        with patch.object(install, 'ROOT', root), patch.object(install, 'external_guard'), \
             patch.object(install, 'run', side_effect=fake_run) as run, \
             patch.object(install, 'git', side_effect=fake_git), \
             patch.object(install, 'fingerprints', return_value={'state.json': 'unchanged'}), \
             patch.object(install, 'no_live_digest'), redirect_stdout(io.StringIO()) as output:
            result = install.main(['--apply', '--approved-head', HEAD, '--approval-reference', 'recorded approval'])
        return result, json.loads(output.getvalue()), [call.args[0] for call in run.call_args_list]

    def test_external_install_leaves_delivery_paused_and_only_runs_no_send_validation(self):
        result, receipt, commands = self.apply_fixture()
        self.assertEqual(result, 0)
        self.assertEqual(receipt['installed_commit'], TARGET)
        self.assertTrue(receipt['cron_paused'])
        self.assertTrue(receipt['listener_stopped'])
        self.assertFalse(receipt['activation_authorized'])
        record = Path(receipt['handoff_record'])
        self.assertEqual(record.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(record.read_text())['installed_commit'], TARGET)
        self.assertNotIn('recorded approval', record.read_text())
        self.assertIn(['systemctl', '--user', 'stop', install.UNIT], commands)
        for command in commands:
            self.assertFalse(set(command) & {'start', 'restart', 'digest.py', 'bot.py', 'agent-console.service'})
        self.assertTrue(any('scripts/validate_pi_no_send.py' in command for command in commands))

    def test_partial_install_failure_is_reported_without_rollback_or_resume(self):
        result, receipt, commands = self.apply_fixture(fail_sync=True)
        self.assertEqual(result, 2)
        self.assertEqual(receipt['state'], 'maintenance-incomplete')
        self.assertTrue(receipt['source_fast_forward_performed'])
        self.assertFalse(receipt['activation_authorized'])
        self.assertFalse(any('restart' in command or 'start' in command for command in commands))

    def test_in_flight_delivery_is_never_killed_or_replayed(self):
        with tempfile.TemporaryDirectory(dir=DATA) as directory:
            root = Path(directory)
            proc = root / '123'
            proc.mkdir()
            (proc / 'cmdline').write_bytes(install.WRAPPER.encode() + b'\0')
            with self.assertRaisesRegex(install.InstallBlocked, 'in-flight-digest'):
                install.no_live_digest(root)
