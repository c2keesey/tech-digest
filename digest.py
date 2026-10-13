#!/usr/bin/env python3
"""Per-source release generation and acknowledged-only Telegram delivery."""

import argparse
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from claude_runtime import ClaudeFailure, parse_release, validate_release
from delivery import (DeliveryFailure, deliver_sources, load_outbox, save_outbox,
                      source_chunks)
from sources import SourceFailure, ReleaseData, get_release_data, list_sources
from state_store import (StateFailure, atomic_json, normalize_state,
                         normalize_versions, read_json, runtime_lock,
                         version_sort_key)
from telegram_toolkit.telegram import TelegramNotifier

PROMPT_FILE = Path(__file__).parent / "prompts" / "parse-release.md"
STATE_FILE = Path(__file__).parent / "state.json"
DEFAULT_SOURCES = ["claude-code", "claude-app", "cursor", "linear", "pydantic-ai",
                   "granola", "agent-deck", "beads", "gas-city", "codex", "pi"]
MAX_STORED_VERSIONS = 50
_version_sort_key = version_sort_key
escape_html = escape


def load_state():
    return normalize_state(read_json(STATE_FILE))


def save_state(state):
    # Callers must own runtime_lock across read/modify/deliver/write.
    atomic_json(STATE_FILE, normalize_state(state))


def parse_with_claude(content, timeout=120):
    try:
        prompt = PROMPT_FILE.read_text()
    except OSError:
        raise ClaudeFailure("parse-prompt-unavailable") from None
    return parse_release(content, prompt, timeout)


def _text(text, limit):
    return escape(" ".join(text.split())[:limit])


def format_source_section(data: ReleaseData, parsed):
    # Failure must never be represented as an unchanged/no-updates section.
    validate_release(parsed)
    lines = [f"▎<b>{_text(data.source_name, 100)}</b>",
             f"<i>{_text(parsed['summary'], 350)}</i>"]
    for item in parsed.get("try_this", [])[:2]:
        lines.append(f"  🎯 {_text(item, 160)}")
    count = 0
    for category, emoji in [("New Features", "✨"), ("Improvements", "📈"),
                            ("Bug Fixes", "🐛"), ("Changes", "🔄")]:
        items = parsed["categories"].get(category, [])
        if not items:
            continue
        if category == "Bug Fixes":
            lines.append(f"  {emoji} {len(items)} notable bug fixes")
            continue
        for item in items:
            if count >= 8:
                break
            lines.append(f"  {emoji} {_text(item, 80)}")
            count += 1
    lines.append(f'<a href="{escape(data.url, quote=True)}">View changelog →</a>')
    return "\n".join(lines)


@dataclass
class Generation:
    sections: dict = field(default_factory=dict)
    cursors: dict = field(default_factory=dict)
    failures: dict = field(default_factory=dict)
    unchanged: list = field(default_factory=list)

    @property
    def text(self):
        lines = ["☀️ <b>Tech Morning Digest</b>", *self.sections.values()]
        for source, error in self.failures.items():
            lines.append(f"▎<b>{source}</b>\n<i>Update unavailable: {escape(error)}</i>")
        if not self.sections and not self.failures:
            lines.append("No new updates. You're all caught up!")
        if self.failures:
            lines.append("Degraded preview: failed sources remain pending.")
        return "\n\n".join(lines)


def generate_digest(sources=None, quiet=False, state=None, fetch=None):
    sources = DEFAULT_SOURCES if sources is None else sources
    if any(source not in list_sources() for source in sources):
        raise SourceFailure("unknown-source: use --list")
    state = load_state() if state is None else normalize_state(state)
    fetch = fetch or get_release_data
    generation = Generation()
    for source in dict.fromkeys(sources):
        if not quiet:
            print(f"{source}: fetching")
        entry = state.get(source, {})
        try:
            data = fetch(source, seen_versions=set(entry.get("seen_versions", [])),
                         last_anchor=entry.get("content_anchor", ""))
            if data is None or (data.content_hash and data.content_hash == entry.get("content_hash")):
                generation.unchanged.append(source)
                continue
            if not data.content.strip():
                if data.content_hash and entry.get("content_anchor"):
                    generation.unchanged.append(source)
                    continue
                raise SourceFailure("source-empty-release")
            parsed = parse_with_claude(data.content)
            section = format_source_section(data, parsed)
            # Validate size before preparing a cursor or any network side effect.
            source_chunks(section)
            cursor = dict(entry)
            if data.versions:
                cursor["seen_versions"] = normalize_versions(
                    entry.get("seen_versions", []) + data.versions)[-MAX_STORED_VERSIONS:]
            if data.content_hash:
                cursor["content_hash"] = data.content_hash
            if data.content_anchor:
                cursor["content_anchor"] = data.content_anchor
            generation.sections[source] = section
            generation.cursors[source] = cursor
        except (ClaudeFailure, SourceFailure, DeliveryFailure) as error:
            generation.failures[source] = str(error)
            if not quiet:
                print(f"{source}: {error}")
    return generation


def send_digest(sources=None, quiet=False):
    sources = DEFAULT_SOURCES if sources is None else sources
    try:
        if any(source not in list_sources() for source in sources):
            raise SourceFailure("unknown-source: use --list")
        with runtime_lock():
            state = load_state()
            outbox = load_outbox()
            if any(source not in list_sources() for source in outbox):
                raise StateFailure("outbox-unknown-source: preserve and review")
            # Never re-parse/re-send pending sources; use their frozen payloads.
            generation = generate_digest([s for s in sources if s not in outbox],
                                         quiet=quiet, state=state)
            if not generation.sections and not any(s in outbox for s in sources):
                if generation.failures:
                    return False
                if not quiet:
                    print("No new updates (no messages sent).")
                return True
            notifier = TelegramNotifier()
            for source, section in generation.sections.items():
                outbox[source] = {"cursor": generation.cursors[source],
                                  "chunks": [{"text": text, "status": "pending"}
                                             for text in source_chunks(section)]}
            save_outbox(outbox)
            delivered = deliver_sources(outbox, sources, notifier, state, save_state)
            success = delivered and not generation.failures
            if not quiet:
                print("Digest delivery acknowledged." if success
                      else "Digest degraded; failed or uncertain sources remain pending.")
            return success
    except (StateFailure, SourceFailure, DeliveryFailure) as error:
        print(f"Digest failed: {error}")
        return False
    except ValueError:
        # May include malformed .env values; never echo the exception itself.
        print("Digest failed: Telegram configuration unavailable")
        return False
    except Exception:
        # Last-resort boundary prevents secrets in request URLs / tracebacks.
        print("Digest failed: internal-error; preserve runtime files for review")
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tech Digest (default: send acknowledged updates)")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--preview", action="store_true", help="No sends or runtime-state writes")
    modes.add_argument("--list", action="store_true")
    modes.add_argument("--show-state", action="store_true", help="Show cursor counts, not private page text")
    parser.add_argument("--sources", help="Comma-separated source keys")
    # Kept for the existing wrapper; enrichment is not part of delivery correctness.
    parser.add_argument("--enrich", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    sources = args.sources.split(",") if args.sources else DEFAULT_SOURCES
    if args.list:
        print("\n".join(list_sources()))
        return 0
    try:
        if args.show_state:
            with runtime_lock():
                for source, entry in load_state().items():
                    print(f"{source}: {len(entry.get('seen_versions', []))} versions, "
                          f"web cursor={'present' if entry.get('content_hash') else 'absent'}")
            return 0
        if args.preview:
            with runtime_lock():
                pending = load_outbox()
                generation = generate_digest(sources=sources)
                print(generation.text)  # Explicit preview only, never cron/send logs.
                if any(source in pending for source in sources):
                    print("Pending delivery outbox exists; preview does not reconcile or send it.")
            return 1 if generation.failures else 0
        return 0 if send_digest(sources=sources) else 1
    except (ClaudeFailure, StateFailure, SourceFailure) as error:
        print(f"Digest failed: {error}")
        return 1
    except Exception:
        print("Digest failed: internal-error; preserve runtime files for review")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
