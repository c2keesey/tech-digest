"""Offline discovery tests: no installed-provider calls or machine changes."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pi_runtime


class RuntimePathTests(unittest.TestCase):
    def setUp(self):
        data = Path(__file__).resolve().parents[1] / 'data'
        data.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=data)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.dist = self.root / 'package' / 'dist'
        self.dist.mkdir(parents=True)
        self.node = self.bin / 'node'
        self.node.write_text('#!/bin/sh\nexit 99\n')
        self.node.chmod(0o755)
        cli = self.dist / 'cli.js'
        cli.write_text('// offline fixture, never executed\n')
        cli.chmod(0o755)
        (self.bin / 'pi').symlink_to(cli)
        (self.dist / 'index.js').write_text('// offline SDK fixture\n')
        self.package = self.dist.parent / 'package.json'
        self.package.write_text('{"name":"@earendil-works/pi-coding-agent"}')
        self.config = self.root / 'runtime.json'
        self.config.write_text(json.dumps({'bin_dir': str(self.bin)}))
        p = patch('pi_runtime.RUNTIME_CONFIG', self.config)
        p.start()
        self.addCleanup(p.stop)

    def test_system_only_path_resolves_reviewed_pair_without_launching_anything(self):
        with patch.dict(os.environ, {'PATH': '/usr/bin:/bin'}), patch('subprocess.run') as launch:
            node, sdk = pi_runtime.find_pi_runtime()
        self.assertEqual(node, str(self.node))
        self.assertEqual(sdk, str(self.dist / 'index.js'))
        launch.assert_not_called()

    def test_home_relative_pin_uses_existing_actual_user_home(self):
        self.config.write_text('{"bin_dir":"~/bin"}')
        with patch('pi_runtime.Path.home', return_value=self.root):
            self.assertEqual(pi_runtime.find_pi_runtime()[0], str(self.node))

    def test_missing_pin_or_executable_never_falls_back_to_path_or_wrapper(self):
        for path in (self.node, self.bin / 'pi', self.config):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                if path == self.bin / 'pi':
                    target = path.readlink()
                path.unlink()
                with self.assertRaisesRegex(pi_runtime.ParseFailure, '^pi-runtime-unavailable$'):
                    pi_runtime.find_pi_runtime()
                if path == self.bin / 'pi':
                    path.symlink_to(target)
                else:
                    path.write_bytes(original)
                    if path == self.node:
                        path.chmod(0o755)

    def test_invalid_configuration_fails_closed_with_no_private_diagnostic(self):
        for config in ('broken', 'null', '[]', '{}', '{"bin_dir":42}',
                       '{"bin_dir":"relative/bin"}', '{"bin_dir":"/tmp/../bin"}',
                       '{"bin_dir":"~other/bin"}', '{"bin_dir":"/private/path","model":"paid"}'):
            with self.subTest(config=config):
                self.config.write_text(config)
                with self.assertRaisesRegex(pi_runtime.ParseFailure, '^pi-runtime-unavailable$'):
                    pi_runtime.find_pi_runtime()

    def test_foreign_package_or_missing_public_sdk_is_not_a_supported_runtime(self):
        for package in ('{"name":"foreign"}', '[]', 'broken'):
            self.package.write_text(package)
            with self.assertRaisesRegex(pi_runtime.ParseFailure, '^pi-runtime-unavailable$'):
                pi_runtime.find_pi_runtime()
        self.package.write_text('{"name":"@earendil-works/pi-coding-agent"}')
        (self.dist / 'index.js').unlink()
        with self.assertRaisesRegex(pi_runtime.ParseFailure, '^pi-runtime-unavailable$'):
            pi_runtime.find_pi_runtime()
