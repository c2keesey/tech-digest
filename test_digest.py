"""Regressions retained from concurrent main fixes, reconciled with td-f5l.

Main's excerpt fallback/--replay are deliberately NOT retained: Chris chose
Pi/Codex and ACK-only state, with no replay/reset or swallowed-history inference.
These six tests preserve the useful honesty/escaping/auth/send-failure coverage.
"""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests
import delivery
import digest
import pi_runtime
import state_store
from sources import ReleaseData

ROOT = Path(__file__).resolve().parent
PARSED = {'summary': 'v2.0: Added <safe> & useful functionality', 'try_this': [],
          'categories': {'New Features': ['<safe> & useful feature']}}


class DigestSafetyRegressionTests(unittest.TestCase):
    def setUp(self):
        self.release = ReleaseData(source_name='Example',
            content='## v2.0\n- Added <safe> & useful release functionality\n' + 'x' * 20000,
            url='https://example.com/releases', versions=['v2.0'])

    def test_valid_summary_is_honest_escaped_and_bounded(self):
        section = digest.format_source_section(self.release, PARSED)
        self.assertIn('&lt;safe&gt; &amp;', section)
        self.assertIn('v2.0', section)
        self.assertIn('View changelog', section)
        self.assertNotIn('No recent updates', section)
        self.assertLess(len(section), 1500)

    def test_missing_subscription_is_an_explicit_failure_not_excerpt_fallback(self):
        with patch('pi_runtime.run_pi', side_effect=pi_runtime.ParseFailure('pi-subscription-required')):
            with self.assertRaisesRegex(pi_runtime.ParseFailure, '^pi-subscription-required$'):
                pi_runtime.parse_release('release notes', 'fixture')

    def test_invalid_json_shape_is_an_explicit_failure(self):
        with patch('pi_runtime.run_pi', return_value='[]'):
            with self.assertRaisesRegex(pi_runtime.ParseFailure, '^parse-invalid-schema$'):
                pi_runtime.parse_release('release notes', 'fixture')

    def test_generation_keeps_failed_parse_pending_without_unparsed_excerpts(self):
        previous = {'claude-code': {'seen_versions': ['v1.0']}, 'other': {'content_hash': 'keep'}}
        original = json.dumps(previous, sort_keys=True)
        with patch.object(digest, 'load_state', return_value=previous), \
             patch.object(digest, 'get_release_data', return_value=self.release), \
             patch.object(digest, 'parse_with_pi', side_effect=pi_runtime.ParseFailure('pi-subscription-required')):
            generation = digest.generate_digest(['claude-code'], quiet=True)
        self.assertEqual(generation.failures, {'claude-code': 'pi-subscription-required'})
        self.assertEqual(generation.cursors, {})
        self.assertEqual(generation.sections, {})
        self.assertNotIn('useful release functionality', generation.text)
        self.assertNotIn('No recent updates', generation.text)
        self.assertNotIn('caught up', generation.text)
        self.assertLess(len(generation.text), 1500)
        self.assertEqual(json.dumps(previous, sort_keys=True), original)

    def test_replay_and_reset_are_rejected_before_generation_or_send(self):
        with patch.object(digest, 'generate_digest') as generate, \
             patch.object(digest, 'send_digest') as send, patch.object(digest, 'save_state') as save:
            for argv in (['--replay'], ['--preview', '--replay'], ['--reset-state']):
                with self.subTest(argv=argv), redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        digest.main(argv)
                    self.assertEqual(error.exception.code, 2)
        generate.assert_not_called()
        send.assert_not_called()
        save.assert_not_called()

    def test_failed_send_does_not_consume_state_or_lose_unrelated_cursor(self):
        (ROOT / 'data').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'data') as directory:
            root = Path(directory)
            state = root / 'state.json'
            initial = {'claude-code': {'seen_versions': ['v1.0']}, 'other': {'content_hash': 'keep'}}
            state.write_text(json.dumps(initial))
            original = state.read_bytes()
            generation = digest.Generation(sections={'claude-code': 'Public fixture digest'},
                cursors={'claude-code': {'seen_versions': ['v1.0', 'v2.0']}})
            with patch.object(digest, 'STATE_FILE', state), \
                 patch.object(delivery, 'OUTBOX_FILE', root / 'outbox.json'), \
                 patch.object(state_store, 'LOCK_FILE', root / 'runtime.lock'), \
                 patch.object(digest, 'generate_digest', return_value=generation), \
                 patch.object(digest, 'TelegramNotifier', return_value=Mock(bot_token='synthetic', chat_id='synthetic')), \
                 patch('delivery.requests.post', side_effect=requests.ConnectionError('synthetic offline')), \
                 patch.object(digest, 'save_state') as save, redirect_stdout(io.StringIO()):
                self.assertFalse(digest.send_digest(['claude-code'], quiet=True))
            save.assert_not_called()
            self.assertEqual(state.read_bytes(), original)
            self.assertEqual(json.loads(state.read_text())['other'], initial['other'])
            self.assertEqual(json.loads((root / 'outbox.json').read_text())['claude-code']['chunks'][0]['status'], 'uncertain')


if __name__ == '__main__':
    unittest.main()
