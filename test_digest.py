import json
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import digest
from sources import ReleaseData


class DigestFallbackTests(unittest.TestCase):
    def setUp(self):
        self.release = ReleaseData(
            source_name="Example", content="## v2.0\n- Added <safe> & useful release functionality\n" + "x" * 20000,
            url="https://example.com/releases", versions=["v2.0"],
        )

    def test_cron_discovery_prefers_nvm_runtime_over_stale_wrapper(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            cli = home / ".nvm/versions/node/v24.13.0/bin/pi"
            cli.parent.mkdir(parents=True)
            cli.touch()
            with patch.object(digest.Path, "home", return_value=home), \
                 patch.object(digest.shutil, "which", return_value="/stale/wrapper/pi"):
                self.assertEqual(digest.find_summary_executable(), str(cli))

    def test_fallback_is_honest_escaped_and_bounded(self):
        section = digest.format_source_section(self.release, None)
        self.assertIn("AI summary unavailable", section)
        self.assertIn("&lt;safe&gt; &amp;", section)
        self.assertIn("v2.0", section)
        self.assertIn("View changelog", section)
        self.assertNotIn("No recent updates", section)
        self.assertLess(len(section), 1500)

    @patch.object(digest, "find_summary_executable", return_value="/bin/pi")
    @patch.object(digest.subprocess, "run")
    def test_expired_auth_returns_none(self, run, _find):
        run.return_value = subprocess.CompletedProcess([], 1, "OAuth expired", "")
        self.assertIsNone(digest.parse_with_codex("release notes"))

    @patch.object(digest, "find_summary_executable", return_value="/bin/pi")
    @patch.object(digest.subprocess, "run")
    def test_invalid_json_shape_returns_none(self, run, _find):
        for output in ["[]", "not JSON", '{"summary":"ok","categories":[]}',
                       '{"summary":"ok","try_this":[42]}']:
            with self.subTest(output=output):
                run.return_value = subprocess.CompletedProcess([], 0, output, "")
                self.assertIsNone(digest.parse_with_codex("release notes"))

    @patch.object(digest, "find_summary_executable", return_value="/bin/pi")
    @patch.object(digest.subprocess, "run")
    def test_luna_low_command_and_final_output(self, run, _find):
        expected = {"summary": "v2.0 • Faster editing", "categories": {"New Features": ["Fast editing"]}}
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps(expected), "")
        with patch.dict(digest.subprocess.os.environ, {"TELEGRAM_BOT_TOKEN": "not-a-real-secret"}):
            self.assertEqual(digest.parse_with_codex("release notes"), expected)
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[cmd.index("--provider") + 1], "openai-codex")
        self.assertEqual(cmd[cmd.index("--model") + 1], "gpt-6-luna")
        self.assertEqual(cmd[cmd.index("--thinking") + 1], "low")
        for flag in ["--no-session", "--no-tools", "--no-extensions", "--no-context-files"]:
            self.assertIn(flag, cmd)
        self.assertIn("release notes", run.call_args.kwargs["input"])
        self.assertTrue(run.call_args.kwargs["env"]["PATH"].startswith("/bin:"))
        self.assertNotIn("TELEGRAM_BOT_TOKEN", run.call_args.kwargs["env"])

    @patch.object(digest, "find_summary_executable", return_value="/bin/pi")
    @patch.object(digest.subprocess, "run", side_effect=subprocess.TimeoutExpired("pi", 120))
    def test_timeout_returns_none(self, _run, _find):
        self.assertIsNone(digest.parse_with_codex("release notes"))

    @patch.object(digest, "find_summary_executable", return_value=None)
    def test_missing_cli_returns_none(self, _find):
        self.assertIsNone(digest.parse_with_codex("release notes"))

    def test_generation_delivers_real_excerpts_on_parse_failure(self):
        with patch.object(digest, "load_state", return_value={}), \
             patch.object(digest, "get_release_data", return_value=self.release), \
             patch.object(digest, "parse_with_codex", return_value=None):
            text, state = digest.generate_digest(["example"], quiet=True)
        self.assertIn("useful release functionality", text)
        self.assertEqual(state["example"]["seen_versions"], ["v2.0"])

    def test_replay_ignores_seen_markers_and_preserves_other_state(self):
        previous = {"example": {"seen_versions": ["v2.0"]}, "other": {"content_hash": "keep"}}
        with patch.object(digest, "load_state", return_value=previous), \
             patch.object(digest, "get_release_data", return_value=self.release) as fetch, \
             patch.object(digest, "parse_with_codex", return_value=None):
            _, state = digest.generate_digest(["example"], quiet=True, replay=True)
        fetch.assert_called_once_with("example", seen_versions=set(), last_anchor="")
        self.assertEqual(state["other"], previous["other"])

    def test_failed_send_does_not_consume_state(self):
        with patch.object(digest, "generate_digest", return_value=("digest", {"new": {}})), \
             patch.object(digest, "TelegramNotifier"), \
             patch.object(digest.requests, "post", side_effect=digest.requests.ConnectionError("offline")), \
             patch.object(digest, "save_state") as save:
            self.assertFalse(digest.send_digest(quiet=True))
            save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
