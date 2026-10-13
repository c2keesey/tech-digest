"""Supported, noninteractive Claude invocation with content-free diagnostics."""

import json
import os
import shutil
import subprocess
from pathlib import Path


class ClaudeFailure(RuntimeError):
    """Only this safe code may be logged; never the CLI's raw output."""


def find_claude_executable():
    found = shutil.which("claude")
    if found:
        return found
    # Cron often has a minimal PATH; support the native per-user installation.
    for path in (Path.home() / ".local/bin/claude", Path("/usr/local/bin/claude")):
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def run_claude(prompt, system_prompt, timeout=120):
    executable = find_claude_executable()
    if not executable:
        raise ClaudeFailure("claude-unavailable: install Claude CLI for the service user")
    # Safe mode retains supported OAuth/API-key auth but disables custom hooks,
    # plugins and repo instructions. Never use --bare: it disables OAuth auth.
    cmd = [executable, "--print", "--output-format", "json", "--safe-mode",
           "--no-session-persistence", "--tools", "", "--strict-mcp-config",
           "--mcp-config", '{"mcpServers":{}}', "--system-prompt", system_prompt]
    env = {**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
    try:
        result = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                                timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise ClaudeFailure("claude-timeout") from None
    except OSError:
        raise ClaudeFailure("claude-launch-failed") from None

    # Some auth failures are on stdout, not stderr, even with exit 1.
    diagnostic = (result.stdout + result.stderr).lower()
    if (("oauth" in diagnostic and "expired" in diagnostic)
            or any(marker in diagnostic for marker in
                   ("not logged in", "authentication_error", "invalid api key", "please run /login"))):
        raise ClaudeFailure("claude-auth-required: run claude auth login as the service user")
    if result.returncode:
        raise ClaudeFailure(f"claude-exit-{result.returncode} "
                            f"(stdout={len(result.stdout)}, stderr={len(result.stderr)} bytes)")
    try:
        envelope = json.loads(result.stdout)
        if not isinstance(envelope, dict) or envelope.get("is_error") is not False:
            raise ValueError
        text = envelope["result"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError
        return text
    except (ValueError, KeyError, TypeError):
        raise ClaudeFailure("claude-invalid-result") from None


def validate_release(parsed):
    if not isinstance(parsed, dict):
        raise ClaudeFailure("parse-invalid-schema")
    if not isinstance(parsed.get("summary"), str) or not parsed["summary"].strip():
        raise ClaudeFailure("parse-invalid-summary")
    categories = parsed.get("categories")
    if not isinstance(categories, dict):
        raise ClaudeFailure("parse-invalid-categories")
    if set(categories) - {"New Features", "Improvements", "Bug Fixes", "Changes"}:
        raise ClaudeFailure("parse-unknown-category")
    for items in [parsed.get("try_this", []), *categories.values()]:
        if not isinstance(items, list) or any(not isinstance(x, str) or not x.strip() for x in items):
            raise ClaudeFailure("parse-invalid-items")
    return parsed


def parse_release(content, system_prompt, timeout=120):
    text = run_claude(content, system_prompt, timeout)
    if text.startswith("```"):
        text = "\n".join(text.splitlines()[1:-1])
    try:
        parsed = json.loads(text)
    except ValueError:
        raise ClaudeFailure("parse-invalid-json") from None
    return validate_release(parsed)
