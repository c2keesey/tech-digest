"""Offline acceptance tests: synthetic content/credentials, no real Telegram sends."""

from contextlib import redirect_stdout
import io
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import requests

import bot
import claude_runtime
import delivery
import digest
import recovery_preview
import sources
import state_store
from claude_runtime import ClaudeFailure
from state_store import StateFailure

ROOT = Path(__file__).resolve().parents[1]
PARSED = {"summary": "v1.0 → v1.1 • Public fixture feature",
          "try_this": ["Try the public fixture"], "categories": {"New Features": ["Fixture feature"]}}
PRIVATE = "synthetic-private-body"
TOKEN = "12345:synthetic-secret"
CHAT = "synthetic-private-chat"


def release(key="claude-code", version="v1.1", web=False):
    return sources.ReleaseData(key, PRIVATE, "https://example.com/releases",
                               versions=[] if web else [version],
                               content_hash="new-hash" if web else "",
                               content_anchor="new-anchor" if web else "")


def response(status=200, body=None):
    result = Mock(status_code=status)
    result.json.return_value = body if body is not None else {"ok": True, "result": {"message_id": 7}}
    return result


class IsolatedTest(unittest.TestCase):
    def setUp(self):
        (ROOT / "data").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "data")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state.json"
        self.outbox = self.root / "outbox.json"
        self.lock = self.root / "runtime.lock"
        for target, value in [("digest.STATE_FILE", self.state),
                              ("delivery.OUTBOX_FILE", self.outbox),
                              ("state_store.LOCK_FILE", self.lock),
                              ("bot.OFFSET_FILE", self.root / "offset")]:
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)
        self.initial = {"claude-code": {"seen_versions": ["v1.0"]}}
        state_store.atomic_json(self.state, self.initial)
        self.original = self.state.read_bytes()
        self.post = self.start_patch("delivery.requests.post", side_effect=AssertionError("unmocked Telegram request"))
        self.get = self.start_patch("sources.requests.get", side_effect=AssertionError("unmocked source request"))
        self.notifier = self.start_patch("digest.TelegramNotifier", return_value=Mock(bot_token=TOKEN, chat_id=CHAT))
        self.fetch = self.start_patch("digest.get_release_data", side_effect=lambda key, **kw: release(key))
        self.parse = self.start_patch("digest.parse_with_claude", return_value=PARSED)

    def start_patch(self, target, **kwargs):
        p = patch(target, **kwargs)
        value = p.start()
        self.addCleanup(p.stop)
        return value

    def send(self, keys=None):
        with redirect_stdout(io.StringIO()) as captured:
            result = digest.send_digest(keys or ["claude-code"], quiet=True)
        return result, captured.getvalue()

    def assert_no_leak(self, text):
        for value in (PRIVATE, TOKEN, CHAT, "api.telegram.org/bot", "Bearer", "raw-environment"):
            self.assertNotIn(value, text)


class GenerationTests(IsolatedTest):
    def test_parse_failure_never_advances_or_claims_unchanged(self):
        self.parse.side_effect = ClaudeFailure("claude-auth-required")
        generation = digest.generate_digest(["claude-code"], quiet=True)
        self.assertIn("claude-code", generation.failures)
        self.assertNotIn("No recent updates", generation.text)
        self.assertNotIn("caught up", generation.text)
        self.assertEqual(generation.cursors, {})
        self.assertFalse(self.send()[0])
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assertFalse(self.outbox.exists())
        self.post.assert_not_called()

    def test_invalid_schema_never_advances(self):
        for parsed in (None, {}, [], {"summary": "", "categories": {}},
                       {"summary": "v1", "categories": {"New Features": [1]}},
                       {"summary": "v1", "categories": [], "try_this": []}):
            with self.subTest(parsed=parsed):
                self.parse.side_effect = None
                self.parse.return_value = parsed
                self.assertFalse(self.send()[0])
                self.assertEqual(self.state.read_bytes(), self.original)
        self.post.assert_not_called()

    def test_fetch_failure_is_not_unchanged(self):
        self.fetch.side_effect = sources.SourceFailure("github-http-403")
        generation = digest.generate_digest(["claude-code"], quiet=True)
        self.assertIn("github-http-403", generation.text)
        self.assertNotIn("caught up", generation.text)
        self.parse.assert_not_called()
        self.assertFalse(self.send()[0])

    def test_successful_source_commits_but_degraded_run_is_failure(self):
        self.fetch.side_effect = lambda key, **kw: release(key)
        self.parse.side_effect = [PARSED, ClaudeFailure("claude-timeout")]
        self.post.side_effect = None
        self.post.return_value = response()
        result, output = self.send(["claude-code", "beads"])
        self.assertFalse(result)
        state = digest.load_state()
        self.assertIn("v1.1", state["claude-code"]["seen_versions"])
        self.assertNotIn("beads", state)
        self.assertEqual(self.post.call_count, 1)
        self.assert_no_leak(output)

    def test_unchanged_does_not_notify_or_write(self):
        self.fetch.side_effect = None
        self.fetch.return_value = None
        self.assertTrue(self.send()[0])
        self.notifier.assert_not_called()
        self.post.assert_not_called()
        self.assertEqual(self.state.read_bytes(), self.original)

    def test_web_failure_keeps_both_cursors(self):
        initial = {"cursor": {"content_hash": "old", "content_anchor": "old-anchor"}}
        state_store.atomic_json(self.state, initial)
        self.fetch.side_effect = lambda key, **kw: release(key, web=True)
        self.parse.side_effect = ClaudeFailure("parse-invalid-json")
        self.assertFalse(self.send(["cursor"])[0])
        self.assertEqual(digest.load_state(), initial)

    def test_web_unchanged_hash_does_not_parse(self):
        state_store.atomic_json(self.state, {"cursor": {"content_hash": "new-hash"}})
        self.fetch.side_effect = lambda key, **kw: release(key, web=True)
        self.assertTrue(self.send(["cursor"])[0])
        self.parse.assert_not_called()

    def test_unknown_source_is_safe(self):
        result, output = self.send([TOKEN])
        self.assertFalse(result)
        self.assert_no_leak(output)
        self.fetch.assert_not_called()

    def test_no_send_end_to_end_preview_uses_real_runtime_adapter(self):
        with patch("digest.parse_with_claude", side_effect=lambda text: claude_runtime.parse_release(text, "fixture")), \
             patch("claude_runtime.find_claude_executable", return_value="/supported/claude"), \
             patch("claude_runtime.subprocess.run", return_value=subprocess.CompletedProcess(
                 [], 0, json.dumps({"is_error": False, "result": json.dumps(PARSED)}), "")) as invoke, \
             redirect_stdout(io.StringIO()) as output:
            self.assertEqual(digest.main(["--preview", "--sources", "claude-code"]), 0)
        self.assertIn("Public fixture feature", output.getvalue())
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assertFalse(self.outbox.exists())
        self.post.assert_not_called()
        self.notifier.assert_not_called()
        self.assertIn("--safe-mode", invoke.call_args.args[0])
        self.assertIn("--no-session-persistence", invoke.call_args.args[0])
        self.assertEqual(invoke.call_args.kwargs["input"], PRIVATE)

    def test_preview_failure_returns_nonzero_and_preserves_pending_journal(self):
        state_store.atomic_json(self.outbox, {"claude-code": {"cursor": self.initial["claude-code"],
             "chunks": [{"text": "frozen", "status": "uncertain"}]}})
        before = self.outbox.read_bytes()
        self.parse.side_effect = ClaudeFailure("claude-auth-required")
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(digest.main(["--preview", "--sources", "claude-code"]), 1)
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assertEqual(self.outbox.read_bytes(), before)
        self.assertNotIn("caught up", output.getvalue())
        self.post.assert_not_called()


class DeliveryTests(IsolatedTest):
    def test_ack_required_even_with_http_200(self):
        self.post.side_effect = None
        self.post.return_value = response(body={"ok": False, "description": TOKEN + CHAT + PRIVATE})
        result, output = self.send()
        self.assertFalse(result)
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assertEqual(delivery.load_outbox()["claude-code"]["chunks"][0]["status"], "pending")
        self.assert_no_leak(output)

    def test_missing_ack_is_uncertain_and_not_retried(self):
        for body in ({"ok": True}, {"ok": True, "result": {"message_id": True}}, {}, []):
            with self.subTest(body=body):
                state_store.atomic_json(self.outbox, {})
                self.post.side_effect = None
                self.post.return_value = response(body=body)
                self.post.reset_mock()
                self.assertFalse(self.send()[0])
                self.assertFalse(self.send()[0])
                self.assertEqual(self.post.call_count, 1)
                self.assertEqual(self.state.read_bytes(), self.original)

    def test_network_timeout_is_ambiguous_and_never_replayed(self):
        self.post.side_effect = requests.Timeout(f"https://api.telegram.org/bot{TOKEN} {CHAT} {PRIVATE}")
        result, output = self.send()
        self.assertFalse(result)
        self.assertFalse(self.send()[0])
        self.assertEqual(self.post.call_count, 1)
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assert_no_leak(output)

    def test_server_error_is_ambiguous(self):
        self.post.side_effect = None
        self.post.return_value = response(status=500, body={"unknown": TOKEN})
        self.assertFalse(self.send()[0])
        self.assertEqual(delivery.load_outbox()["claude-code"]["chunks"][0]["status"], "uncertain")

    def test_invalid_response_json_is_ambiguous(self):
        self.post.side_effect = None
        r = response()
        r.json.side_effect = ValueError(PRIVATE)
        self.post.return_value = r
        self.assertFalse(self.send()[0])
        self.assertFalse(self.send()[0])
        self.assertEqual(self.post.call_count, 1)

    def test_partial_chunk_rejection_retries_only_unsent_chunk(self):
        section = "▎<b>Fixture</b>\n" + "\n".join("<i>" + "x" * 1500 + "</i>" for _ in range(4))
        with patch("digest.format_source_section", return_value=section):
            self.post.side_effect = [response(), response(status=429, body={"ok": False})]
            self.assertFalse(self.send()[0])
        pending = delivery.load_outbox()["claude-code"]
        self.assertEqual([c["status"] for c in pending["chunks"]], ["ack", "pending"])
        self.assertEqual(self.state.read_bytes(), self.original)
        self.post.side_effect = [response()]
        self.parse.reset_mock()
        self.assertTrue(self.send()[0])
        self.assertEqual(self.post.call_count, 3)
        self.parse.assert_not_called()
        self.assertEqual(delivery.load_outbox(), {})
        self.assertIn("v1.1", digest.load_state()["claude-code"]["seen_versions"])

    def test_crash_between_send_and_durable_ack_fails_closed(self):
        self.post.side_effect = None
        self.post.return_value = response()
        real_save = delivery.save_outbox
        calls = 0
        def fail_ack(outbox):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise StateFailure("simulated-write-failure")
            real_save(outbox)
        with patch("delivery.save_outbox", side_effect=fail_ack):
            self.assertFalse(self.send()[0])
        self.assertEqual(delivery.load_outbox()["claude-code"]["chunks"][0]["status"], "inflight")
        self.assertFalse(self.send()[0])
        self.assertEqual(self.post.call_count, 1)
        self.assertEqual(self.state.read_bytes(), self.original)

    def test_ack_journal_recovers_failed_cursor_commit_without_resend(self):
        self.post.side_effect = None
        self.post.return_value = response()
        with patch("digest.save_state", side_effect=StateFailure("simulated-write-failure")):
            self.assertFalse(self.send()[0])
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assertEqual(delivery.load_outbox()["claude-code"]["chunks"][0]["status"], "ack")
        self.assertTrue(self.send()[0])
        self.assertEqual(self.post.call_count, 1)
        self.assertIn("v1.1", digest.load_state()["claude-code"]["seen_versions"])

    def test_rejected_source_does_not_block_independent_source_ack(self):
        self.post.side_effect = [response(status=403, body={"ok": False}), response()]
        self.assertFalse(self.send(["claude-code", "beads"])[0])
        self.assertEqual(digest.load_state()["claude-code"], self.initial["claude-code"])
        self.assertIn("beads", digest.load_state())

    def test_failed_outbox_prepare_prevents_network_side_effect(self):
        with patch("digest.save_outbox", side_effect=StateFailure("write-failed")):
            self.assertFalse(self.send()[0])
        self.post.assert_not_called()

    def test_html_chunks_balanced_bounded_and_unicode_safe(self):
        parsed = {"summary": "<" * 350, "try_this": ["&" * 160] * 2,
                  "categories": {"New Features": ["🧪" * 80] * 8}}
        section = digest.format_source_section(release(), parsed)
        chunks = delivery.source_chunks(section)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(delivery.message_length(chunk), 4000)
            self.assertEqual(chunk.count("<i>"), chunk.count("</i>"))
            self.assertEqual(chunk.count("<b>"), chunk.count("</b>"))
        self.assertIn("&lt;", chunks[0])

    def test_corrupt_outbox_blocks_sending(self):
        self.outbox.write_text('{"claude-code":{"cursor":{}}}')
        self.assertFalse(self.send()[0])
        self.post.assert_not_called()

    def test_corrupt_ack_and_cursor_are_checked_before_sending(self):
        for cursor, chunk in [({"seen_versions": [None]}, {"text": "public", "status": "pending"}),
                              ({}, {"text": "public", "status": "ack"})]:
            with self.subTest(cursor=cursor, chunk=chunk):
                state_store.atomic_json(self.outbox, {"claude-code": {"cursor": cursor, "chunks": [chunk]}})
                self.assertFalse(self.send()[0])
                self.assertEqual(self.state.read_bytes(), self.original)
        self.post.assert_not_called()

    def test_unknown_selected_outbox_source_cannot_bypass_validation(self):
        state_store.atomic_json(self.outbox, {TOKEN: {"cursor": {}, "chunks": [{"text": PRIVATE, "status": "pending"}]}})
        result, output = self.send([TOKEN])
        self.assertFalse(result)
        self.assert_no_leak(output)
        self.post.assert_not_called()

    def test_missing_telegram_configuration_does_not_prepare_or_send(self):
        self.notifier.side_effect = ValueError(TOKEN + CHAT)
        result, output = self.send()
        self.assertFalse(result)
        self.assert_no_leak(output)
        self.assertFalse(self.outbox.exists())
        self.assertEqual(self.state.read_bytes(), self.original)
        self.post.assert_not_called()


class StateTests(IsolatedTest):
    def test_legacy_versions_normalize_and_sort_deterministically(self):
        versions = [2, "v2.1.123", "v2.1.98", 2.5, "2", "v2.1.0-rc1", "v2.1.0"]
        normalized = state_store.normalize_versions(versions)
        self.assertTrue(all(isinstance(v, str) for v in normalized))
        self.assertEqual(normalized, state_store.normalize_versions(list(reversed(versions))))
        self.assertLess(normalized.index("v2.1.98"), normalized.index("v2.1.123"))
        self.assertLess(normalized.index("v2.1.0-rc1"), normalized.index("v2.1.0"))
        # Existing mixed cursors migrate only when delivery is acknowledged.
        state_store.atomic_json(self.state, {"claude-code": {"seen_versions": versions}})
        original = self.state.read_bytes()
        self.parse.side_effect = ClaudeFailure("auth-required")
        self.assertFalse(self.send()[0])
        self.assertEqual(self.state.read_bytes(), original)
        self.parse.side_effect = None
        self.post.side_effect = None
        self.post.return_value = response()
        self.assertTrue(self.send()[0])
        self.assertTrue(all(isinstance(v, str) for v in digest.load_state()["claude-code"]["seen_versions"]))

    def test_invalid_legacy_values_fail_safely(self):
        for values in ([True], [None], [{}], [float("inf")]):
            with self.subTest(values=values), self.assertRaises(StateFailure):
                state_store.normalize_versions(values)

    def test_corrupt_state_never_becomes_empty(self):
        self.state.write_text("invalid-json")
        self.assertFalse(self.send()[0])
        self.post.assert_not_called()
        self.assertEqual(self.state.read_text(), "invalid-json")

    def test_atomic_write_preserves_original_when_replace_fails(self):
        with patch("state_store.os.replace", side_effect=OSError(TOKEN)), self.assertRaises(StateFailure):
            state_store.atomic_json(self.state, {"changed": {}})
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assertEqual(list(self.root.glob(".state.json.*")), [])

    def test_runtime_file_permissions(self):
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)
        with state_store.runtime_lock():
            self.assertEqual(self.lock.stat().st_mode & 0o777, 0o600)

    def test_version_cap_stays_bounded(self):
        state_store.atomic_json(self.state, {"claude-code": {"seen_versions": [f"v1.{n}" for n in range(80)]}})
        self.fetch.side_effect = lambda key, **kw: release(key, "v1.100")
        self.post.side_effect = None
        self.post.return_value = response()
        self.assertTrue(self.send()[0])
        self.assertEqual(len(digest.load_state()["claude-code"]["seen_versions"]), 50)


class RuntimeTests(unittest.TestCase):
    def invoke(self, stdout, stderr="", code=0):
        with patch("claude_runtime.find_claude_executable", return_value="/supported/claude"), \
             patch("claude_runtime.subprocess.run", return_value=subprocess.CompletedProcess([], code, stdout, stderr)):
            return claude_runtime.run_claude(PRIVATE, "fixture")

    def test_expired_oauth_on_stdout_is_actionable_not_echoed(self):
        for text in ("OAuth token has expired. ", "Failed to authenticate: expired OAuth token. "):
            with self.subTest(text=text), self.assertRaises(ClaudeFailure) as error:
                self.invoke(text + TOKEN + CHAT + PRIVATE, code=1)
            self.assertIn("claude-auth-required", str(error.exception))
            self.assertNotIn(TOKEN, str(error.exception))
            self.assertNotIn(PRIVATE, str(error.exception))

    def test_failure_diagnostic_uses_exit_and_sizes_only(self):
        with self.assertRaises(ClaudeFailure) as error:
            self.invoke(PRIVATE + TOKEN, "raw-environment", 1)
        self.assertIn("claude-exit-1", str(error.exception))
        self.assertNotIn(PRIVATE, str(error.exception))
        self.assertNotIn("raw-environment", str(error.exception))

    def test_error_envelope_and_malformed_result_fail(self):
        for value in ("not json", "[]", '{"is_error":true,"result":"secret"}',
                      '{"is_error":false,"result":null}', '{"result":"v1"}'):
            with self.subTest(value=value), self.assertRaises(ClaudeFailure):
                self.invoke(value)

    def test_unavailable_timeout_launch_matrix(self):
        with patch("claude_runtime.find_claude_executable", return_value=None), self.assertRaises(ClaudeFailure):
            claude_runtime.run_claude("fixture", "fixture")
        for error in (subprocess.TimeoutExpired("claude", 1, PRIVATE), OSError(TOKEN)):
            with patch("claude_runtime.find_claude_executable", return_value="claude"), \
                 patch("claude_runtime.subprocess.run", side_effect=error), self.assertRaises(ClaudeFailure):
                claude_runtime.run_claude("fixture", "fixture")

    def test_json_and_fenced_json_validate(self):
        for text in (json.dumps(PARSED), "```json\n" + json.dumps(PARSED) + "\n```"):
            with patch("claude_runtime.run_claude", return_value=text):
                self.assertEqual(claude_runtime.parse_release("fixture", "fixture"), PARSED)


class SourceTests(IsolatedTest):
    def test_pi_uses_supported_installed_package_upstream(self):
        self.assertNotIn("pi", sources.WEB_SOURCES)
        self.assertEqual(sources.GITHUB_SOURCES["pi"]["repo"], "earendil-works/pi")

    def test_github_http_and_network_failures_are_content_free(self):
        for exception in (requests.HTTPError(TOKEN, response=response(status=403)), requests.ConnectionError(PRIVATE + TOKEN)):
            self.get.side_effect = exception
            with self.assertRaises(sources.SourceFailure) as error:
                sources.fetch_github_releases("public/repo")
            self.assert_no_leak(str(error.exception))

    def test_github_schema_and_empty_body(self):
        self.get.side_effect = None
        self.get.return_value = response(body=[{"tag_name": "v1", "body": None}])
        data = sources.get_release_data("pi")
        self.assertEqual(data.versions, ["v1"])
        self.assertIn("## v1", data.content)
        for body in ({"error": TOKEN}, [{"tag_name": 1}], [{"tag_name": "v1", "body": 3}]):
            self.get.return_value = response(body=body)
            with self.assertRaises(sources.SourceFailure):
                sources.get_release_data("pi")

    def test_web_403_does_not_look_unchanged(self):
        self.get.side_effect = requests.HTTPError(TOKEN + CHAT, response=response(status=403))
        with self.assertRaises(sources.SourceFailure) as error:
            sources.get_release_data("cursor")
        self.assertIn("web-http-403", str(error.exception))
        self.assert_no_leak(str(error.exception))

    def test_empty_web_is_actionable(self):
        with patch("sources.fetch_web_changelog", return_value=""):
            with self.assertRaises(sources.SourceFailure):
                sources.get_release_data("cursor")

    def test_anchor_and_dynamic_metadata_unchanged(self):
        page = "Updated today\nNavigation\nA substantive old release headline\nOld feature"
        self.assertEqual(sources._truncate_at_anchor(page, "A substantive old release headline"), "")
        self.assertEqual(sources._stable_hash(page), sources._stable_hash(page.replace("today", "yesterday")))
        self.assertIn("A substantive new release headline", sources._truncate_at_anchor(
            "A substantive new release headline\n" + page, "A substantive old release headline"))


class BotTests(IsolatedTest):
    def test_failed_claude_turn_never_stages_commits_pushes_or_logs_content(self):
        with patch("bot.invoke_claude", side_effect=ClaudeFailure("claude-auth-required")), \
             patch("bot.send_message") as reply, \
             patch("subprocess.run") as process, redirect_stdout(io.StringIO()) as output:
            bot.handle_message(TOKEN, CHAT, PRIVATE)
        process.assert_not_called()
        reply.assert_called_once()
        self.assertIn("No repository changes", reply.call_args.args[2])
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assert_no_leak(output.getvalue())

    def test_successful_advisory_does_not_commit_runtime_changes(self):
        with patch("bot.invoke_claude", return_value="Use a reviewed worker"), \
             patch("bot.send_message"), patch("subprocess.run") as process:
            bot.handle_message(TOKEN, CHAT, "repair digest")
        process.assert_not_called()
        self.assertEqual(self.state.read_bytes(), self.original)

    def test_corrupt_bot_offset_does_not_replay_old_requests(self):
        bot.OFFSET_FILE.write_text("broken")
        with self.assertRaises(StateFailure):
            bot.load_offset()

    def test_bot_poll_never_exposes_request_url(self):
        self.get.side_effect = requests.Timeout(f"https://api.telegram.org/bot{TOKEN} {CHAT}")
        with self.assertRaises(delivery.DeliveryFailure) as error:
            bot.get_updates(TOKEN, 1)
        self.assert_no_leak(str(error.exception))

    def test_cron_bot_overlap_is_serialized(self):
        context = multiprocessing.get_context("fork")
        started, resume = context.Event(), context.Event()
        observed = self.root / "bot-observed.json"
        def ack(*args, **kwargs):
            started.set()
            if not resume.wait(5):
                raise AssertionError("test synchronization timeout")
            return response()
        self.post.side_effect = ack
        def cron():
            if not digest.send_digest(["claude-code"], quiet=True):
                raise AssertionError("cron failed")
        def advisory(*args):
            observed.write_text(json.dumps(digest.load_state()))
            return "advice", True
        def maintenance():
            with patch("bot.run_claude", side_effect=advisory), patch("bot.send_message"):
                bot.handle_message(TOKEN, CHAT, PRIVATE)
        first = context.Process(target=cron)
        second = context.Process(target=maintenance)
        first.start()
        self.assertTrue(started.wait(5))
        second.start()
        time.sleep(0.15)
        self.assertFalse(observed.exists(), "bot must wait for the cron transaction")
        resume.set()
        first.join(5)
        second.join(5)
        for child in (first, second):
            if child.is_alive():
                child.terminate()
                child.join()
            self.assertEqual(child.exitcode, 0)
        self.assertIn("v1.1", json.loads(observed.read_text())["claude-code"]["seen_versions"])

    def test_overlapping_cron_runs_send_release_only_once(self):
        context = multiprocessing.get_context("fork")
        probe = self.root / "sends"
        def fetch(key, seen_versions=None, **kwargs):
            return None if "v1.1" in seen_versions else release(key)
        def ack(*args, **kwargs):
            with probe.open("a") as stream:
                stream.write("ack\n")
            time.sleep(0.05)
            return response()
        self.fetch.side_effect = fetch
        self.post.side_effect = ack
        def cron():
            if not digest.send_digest(["claude-code"], quiet=True):
                raise AssertionError("cron failed")
        children = [context.Process(target=cron) for _ in range(2)]
        for child in children:
            child.start()
        for child in children:
            child.join(5)
            if child.is_alive():
                child.terminate()
                child.join()
            self.assertEqual(child.exitcode, 0)
        self.assertEqual(probe.read_text(), "ack\n")


class RecoveryTests(IsolatedTest):
    def test_bounded_archive_preview_excludes_baseline_and_duplicates(self):
        candidates = {"claude-code": ["v1.1", "v1.2", "v1.3"]}
        releases = [{"tag_name": v, "body": "public fixture"} for v in ("v1.0", "v1.1", "v1.1", "v1.2", "v1.3")]
        with patch("recovery_preview.fetch_github_releases", return_value=releases) as fetch:
            data = recovery_preview.bounded_fetch(candidates, 3, 2)("claude-code", {"v1.0"})
        self.assertEqual(data.versions, ["v1.1", "v1.2"])
        self.assertEqual(fetch.call_count, 1)
        self.post.assert_not_called()
        self.assertEqual(self.state.read_bytes(), self.original)

    def test_bounded_catchup_end_to_end_is_no_send_and_no_state_write(self):
        candidates = {"claude-code": ["v1.1", "v1.2"]}
        archive = [{"tag_name": "v1.1", "body": "public fixture"}]
        with patch("recovery_preview.inventory", return_value=(self.initial, candidates)), \
             patch("recovery_preview.fetch_github_releases", return_value=archive), \
             redirect_stdout(io.StringIO()) as output:
            result = recovery_preview.main(["--baseline-ref", "reviewed-ref", "--sources", "claude-code",
                                            "--max-pages", "1", "--max-releases", "1"])
        self.assertEqual(result, 0)
        self.assertIn("Public fixture feature", output.getvalue())
        self.assertIn("unselected-or-unlocated=1", output.getvalue())
        self.assertIn("PREVIEW ONLY", output.getvalue())
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assertFalse(self.outbox.exists())
        self.post.assert_not_called()
        self.notifier.assert_not_called()

    def test_missing_archive_is_failure_not_all_caught_up(self):
        with patch("recovery_preview.fetch_github_releases", return_value=[]):
            with self.assertRaises(sources.SourceFailure):
                recovery_preview.bounded_fetch({"claude-code": ["v1.1"]}, 1, 1)("claude-code")

    def test_inventory_only_has_no_network_parser_or_state_write(self):
        with patch("recovery_preview.inventory", return_value=(self.initial, {"claude-code": ["v1.1"]})), \
             redirect_stdout(io.StringIO()) as output:
            self.assertEqual(recovery_preview.main(["--baseline-ref", "reviewed-ref", "--inventory-only",
                                                   "--sources", "claude-code"]), 0)
        self.get.assert_not_called()
        self.post.assert_not_called()
        self.parse.assert_not_called()
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assertIn("do not prove delivered", output.getvalue())


if __name__ == "__main__":
    unittest.main()
