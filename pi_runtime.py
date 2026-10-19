"""Bounded Pi OpenAI Codex subscription calls; no Claude/API-key/paid fallback."""

import json
import math
import os
from pathlib import Path
import subprocess

PROVIDER = "openai-codex"
MODEL = "gpt-6.1-sol"
API = "openai-codex-responses"
# Fits the observed ~128KB ten-release Claude Code batch without truncation,
# while staying below this model's supported context even for dense tokenization.
MAX_INPUT_BYTES = 192 * 1024
MAX_REQUEST_BYTES = 256 * 1024
MAX_OUTPUT_BYTES = 16 * 1024
MAX_TIMEOUT = 120
HELPER = Path(__file__).resolve().parent / "scripts" / "pi_subscription.mjs"
RUNTIME_CONFIG = HELPER.parent.parent / "config" / "pi-runtime.json"
SAFE_ERRORS = {
    "pi-invalid-request", "pi-input-too-large", "pi-runtime-unavailable",
    "pi-subscription-required", "pi-model-unavailable", "pi-provider-mismatch",
    "pi-timeout", "pi-output-too-large", "pi-invalid-result", "pi-provider-failed",
}


class ParseFailure(RuntimeError):
    """Only fixed, content-free codes may reach service logs."""


def find_pi_runtime():
    # Cron and the bot inherit a system-only PATH. Resolve one reviewed installed
    # Node/Pi pair explicitly, not an interactive shell, wrapper, version glob or
    # alternate provider. Missing/broken configuration fails closed.
    try:
        config = json.loads(RUNTIME_CONFIG.read_text())
        if (not isinstance(config, dict) or set(config) != {"bin_dir"}
                or not isinstance(config["bin_dir"], str)):
            raise ValueError
        location = config["bin_dir"]
        base = Path.home() / location[2:] if location.startswith("~/") else Path(location)
        if not base.is_absolute() or ".." in base.parts:
            raise ValueError
        executable, node = base / "pi", base / "node"
        if any(not path.is_file() or not os.access(path, os.X_OK) for path in (executable, node)):
            raise ValueError
        entry = executable.resolve(strict=True)
        sdk = entry.parent / "index.js"
        package = json.loads((entry.parent.parent / "package.json").read_text())
        if (not isinstance(package, dict)
                or package.get("name") != "@earendil-works/pi-coding-agent" or not sdk.is_file()):
            raise ValueError
    except (OSError, ValueError):
        raise ParseFailure("pi-runtime-unavailable") from None
    return str(node.resolve()), str(sdk)


def provider_environment():
    # No API keys, paid-provider settings, parent session metadata or worker
    # secrets in the child. Pi reads/refreshes the existing user's OAuth store
    # in place through its supported SDK; never copy credentials into the repo.
    allowed = {"HOME", "PATH", "USER", "LOGNAME", "LANG", "LC_ALL", "TZ",
               "XDG_CONFIG_HOME", "PI_CODING_AGENT_DIR", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"}
    env = {key: value for key, value in os.environ.items() if key in allowed}
    env.update(PI_OFFLINE="1", PI_SKIP_VERSION_CHECK="1", PI_TELEMETRY="0")
    return env


def run_pi(prompt, system_prompt, timeout=MAX_TIMEOUT, structured=False):
    if (not isinstance(prompt, str) or not prompt.strip()
            or not isinstance(system_prompt, str) or not system_prompt.strip()
            or type(timeout) not in (int, float) or not math.isfinite(timeout)
            or not 1 <= timeout <= MAX_TIMEOUT or type(structured) is not bool):
        raise ParseFailure("pi-invalid-request")
    if len(prompt.encode()) + len(system_prompt.encode()) > MAX_INPUT_BYTES:
        # Never truncate release input and then mark all fetched tags as seen.
        raise ParseFailure("pi-input-too-large")
    request = json.dumps({"prompt": prompt, "system_prompt": system_prompt,
                          "timeout": timeout, "structured": structured}, ensure_ascii=False)
    if len(request.encode()) > MAX_REQUEST_BYTES:
        raise ParseFailure("pi-input-too-large")
    node, sdk = find_pi_runtime()
    try:
        result = subprocess.run([node, str(HELPER), sdk], input=request,
                                capture_output=True, text=True, timeout=timeout + 5,
                                cwd=str(HELPER.parent.parent), env=provider_environment())
    except subprocess.TimeoutExpired:
        raise ParseFailure("pi-timeout") from None
    except (OSError, UnicodeError):
        raise ParseFailure("pi-launch-failed") from None
    if len(result.stdout.encode()) > MAX_REQUEST_BYTES:
        raise ParseFailure("pi-output-too-large")
    try:
        envelope = json.loads(result.stdout)
    except ValueError:
        raise ParseFailure("pi-invalid-result") from None
    if not isinstance(envelope, dict):
        raise ParseFailure("pi-invalid-result")
    if result.returncode:
        code = envelope.get("error")
        raise ParseFailure(code if isinstance(code, str) and code in SAFE_ERRORS else "pi-provider-failed")
    if (envelope.get("ok") is not True or envelope.get("provider") != PROVIDER
            or envelope.get("model") != MODEL or envelope.get("api") != API
            or envelope.get("auth") != "subscription-oauth"):
        raise ParseFailure("pi-provider-mismatch")
    text = envelope.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ParseFailure("pi-invalid-result")
    if len(text.encode()) > MAX_OUTPUT_BYTES:
        raise ParseFailure("pi-output-too-large")
    return text


def validate_release(parsed):
    if not isinstance(parsed, dict) or set(parsed) - {"summary", "try_this", "categories"}:
        raise ParseFailure("parse-invalid-schema")
    summary = parsed.get("summary")
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 350:
        raise ParseFailure("parse-invalid-summary")
    categories = parsed.get("categories")
    if not isinstance(categories, dict):
        raise ParseFailure("parse-invalid-categories")
    if set(categories) - {"New Features", "Improvements", "Bug Fixes", "Changes"}:
        raise ParseFailure("parse-unknown-category")
    try_this = parsed.get("try_this", [])
    for items, count, width in [(try_this, 2, 160), *((items, 8, 80) for items in categories.values())]:
        if (not isinstance(items, list) or len(items) > count
                or any(not isinstance(x, str) or not x.strip() or len(x) > width for x in items)):
            raise ParseFailure("parse-invalid-items")
    total = sum(len(items) for items in categories.values())
    if total > 8:
        raise ParseFailure("parse-too-many-items")
    return parsed


def parse_release(content, system_prompt, timeout=MAX_TIMEOUT):
    text = run_pi(content, system_prompt, timeout, structured=True)
    # Provider-side strict JSON plus client validation; never rescue prose or a
    # truncated/failed result by extracting an apparently JSON-looking substring.
    try:
        parsed = json.loads(text)
    except ValueError:
        raise ParseFailure("parse-invalid-json") from None
    return validate_release(parsed)
