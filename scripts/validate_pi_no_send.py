#!/usr/bin/env python3
"""OPT-IN real Pi/Codex subscription validation, isolated worktree only.

No provider/fetch mocks: synthetic schema fixture, real source CLI preview and
advisory call. Telegram POSTs and notifier construction are explicitly blocked.
Only content-free evidence is printed/persisted; no prompts/provider transcripts.
"""

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bot
import delivery
import digest
from pi_runtime import API, MODEL, PROVIDER, ParseFailure, find_pi_runtime, parse_release, run_pi
from state_store import StateFailure, atomic_json, normalize_state

PRIMARY = Path("/home/c2k/repos/tech-digest")


def fingerprint(path):
    try:
        return sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", default="claude-code,pi")
    parser.add_argument("--observed-state", type=Path,
                        help="Read-only cursor snapshot for source selection; never a recovery baseline or write target")
    parser.add_argument("--receipt", type=Path, help="Optional content-free receipt under worktree data/")
    args = parser.parse_args(argv)
    if ROOT == PRIMARY.resolve():
        parser.error("refusing to validate in the protected primary")
    if args.receipt and not args.receipt.resolve().is_relative_to(ROOT / "data"):
        parser.error("receipt must be under this worktree's data/ directory")
    selected = args.sources.split(",")
    if any(source not in digest.list_sources() for source in selected):
        parser.error("unknown source")
    observed_state = None
    observed_hash = None
    if args.observed_state:
        try:
            observed_bytes = args.observed_state.read_bytes()
            observed_state = normalize_state(json.loads(observed_bytes))
            observed_hash = sha256(observed_bytes).hexdigest()
        except (OSError, ValueError, StateFailure):
            parser.error("observed state must be readable valid cursor JSON; no empty-state fallback")
    protected = [PRIMARY / name for name in ("state.json", ".digest-outbox.json", ".beads/backup/manifest", ".env",
                 ".bot_offset", ".bot_session", "logs/digest.log", "logs/error.log", "logs/bot.log", "logs/bot-error.log")]
    runtime = [digest.STATE_FILE, delivery.OUTBOX_FILE, bot.OFFSET_FILE, ROOT / ".bot_session"]
    before_protected = [fingerprint(path) for path in protected]
    before_runtime = [fingerprint(path) for path in runtime]
    started = time.monotonic()
    receipt = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
               "provider": PROVIDER, "model": MODEL, "api": API, "auth": "subscription-oauth",
               "no_api_key_or_paid_fallback": True,
               "state_basis": "observed-read-only" if args.observed_state else "worktree"}
    generated = []
    real_generate = digest.generate_digest
    def observe(*args, **kwargs):
        if observed_state is not None:
            # Pass data in memory, never repoint STATE_FILE/save_state at primary.
            kwargs["state"] = observed_state
        generation = real_generate(*args, **kwargs)
        generated.append(generation)
        return generation
    try:
        with patch("requests.post", side_effect=AssertionError("Telegram prohibited in validation")) as post, \
             patch("digest.TelegramNotifier", side_effect=AssertionError("Notifier prohibited in preview")) as notifier:
            parsed = parse_release(
                "## v1.0.1\nPublic synthetic fixture: adds an offline cache and fixes an empty-input crash.\n",
                digest.PROMPT_FILE.read_text())
            receipt["fixture_schema_valid"] = True
            receipt["fixture_version_present"] = "v1.0.1" in parsed["summary"]
            with patch("digest.generate_digest", side_effect=observe), redirect_stdout(io.StringIO()) as preview:
                receipt["preview_exit"] = digest.main(["--preview", "--sources", args.sources])
            receipt["preview_chars"] = len(preview.getvalue())
            receipt["preview_sources_checked"] = len(dict.fromkeys(selected))
            receipt["preview_sources_summarized"] = list(generated[0].sections) if generated else []
            receipt["preview_sources_unchanged"] = generated[0].unchanged if generated else []
            receipt["source_failures"] = generated[0].failures if generated else {}
            advisory = run_pi("Explain the next safe step for a synthetic maintenance request. Do not perform any action.",
                              bot.CONTEXT_PREFIX)
            receipt["advisory_valid"] = bool(advisory.strip())
            receipt["telegram_requests"] = post.call_count
            receipt["notifier_constructions"] = notifier.call_count
        _, sdk = find_pi_runtime()
        receipt["pi_version"] = json.loads((Path(sdk).parent.parent / "package.json").read_text())["version"]
    except ParseFailure as error:
        receipt["error"] = str(error)
    except Exception:
        receipt["error"] = "validation-failed; raw diagnostics withheld"
    receipt["runtime_files_unchanged"] = before_runtime == [fingerprint(path) for path in runtime]
    receipt["protected_primary_evidence_unchanged"] = before_protected == [fingerprint(path) for path in protected]
    receipt["observed_state_unchanged"] = (not args.observed_state
                                           or observed_hash == fingerprint(args.observed_state))
    receipt["elapsed_seconds"] = round(time.monotonic() - started, 2)
    receipt["ok"] = bool(not receipt.get("error") and receipt.get("fixture_version_present")
                         and receipt.get("preview_exit") == 0 and generated
                         and not generated[0].failures and receipt.get("advisory_valid")
                         and receipt.get("telegram_requests") == 0 and receipt.get("notifier_constructions") == 0
                         and receipt["runtime_files_unchanged"] and receipt["protected_primary_evidence_unchanged"]
                         and receipt["observed_state_unchanged"])
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(args.receipt, receipt)
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
