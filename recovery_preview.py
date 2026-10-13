#!/usr/bin/env python3
"""Read-only swallowed-release inventory and bounded catch-up preview.

A historical cursor is evidence of tracking, NOT proof of a delivered summary.
An operator must review the baseline and approve a send plan separately. This
program has deliberately no send/reset/state-rewrite mode.
"""

import argparse
import json
import subprocess
from pathlib import Path

from digest import DEFAULT_SOURCES, STATE_FILE, generate_digest
from sources import (GITHUB_SOURCES, SourceFailure, ReleaseData,
                     fetch_github_releases, get_release_data, list_sources)
from state_store import StateFailure, normalize_state, read_json, runtime_lock


class RecoveryFailure(RuntimeError):
    pass


def historical_state(ref):
    try:
        text = subprocess.check_output(["git", "show", f"{ref}:state.json"],
                                       stderr=subprocess.DEVNULL, text=True)
        return normalize_state(json.loads(text))
    except (subprocess.SubprocessError, ValueError, StateFailure):
        raise RecoveryFailure("baseline-state-unavailable") from None


def inventory(baseline_ref, observed_state):
    baseline = historical_state(baseline_ref)
    states = [observed_state]
    try:
        refs = subprocess.check_output(
            ["git", "rev-list", f"{baseline_ref}..HEAD", "--", "state.json"],
            text=True, stderr=subprocess.DEVNULL).splitlines()
    except subprocess.SubprocessError:
        raise RecoveryFailure("state-history-unavailable") from None
    states += [historical_state(ref) for ref in refs]
    candidates = {}
    for source in list_sources():
        seen = set(baseline.get(source, {}).get("seen_versions", []))
        marked = set()
        for state in states:
            marked.update(state.get(source, {}).get("seen_versions", []))
        candidates[source] = sorted(marked - seen)
    return baseline, candidates


def bounded_fetch(candidates, max_pages, max_releases):
    def fetch(source, seen_versions=None, last_anchor=""):
        if source not in GITHUB_SOURCES:
            return get_release_data(source, seen_versions, last_anchor)
        config = GITHUB_SOURCES[source]
        wanted = set(candidates[source])
        matched = []
        seen = set()
        for page in range(1, max_pages + 1):
            if not wanted:
                break
            releases = fetch_github_releases(config["repo"], limit=100, page=page)
            if not releases:
                break
            for release in releases:
                tag = release["tag_name"]
                if tag in wanted and tag not in seen:
                    matched.append(release)
                    seen.add(tag)
                    if len(matched) >= max_releases:
                        break
            if len(matched) >= max_releases:
                break
        if not matched:
            if wanted:
                raise SourceFailure("catch-up-history-not-found-within-bound: review archive manually")
            return None
        tags = [release["tag_name"] for release in matched]
        print(f"{source}: preview-selected={','.join(tags)}; "
              f"unselected-or-unlocated={len(wanted - set(tags))}")
        return ReleaseData(config["name"],
                           "\n\n".join(f"## {r['tag_name']}\n{r.get('body') or ''}" for r in matched),
                           config["url"], versions=tags)
    return fetch


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", required=True,
                        help="Operator-reviewed Git ref; never inferred as last proven delivery")
    parser.add_argument("--observed-state", type=Path, default=STATE_FILE)
    parser.add_argument("--sources", default=",".join(DEFAULT_SOURCES))
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--max-releases", type=int, default=5)
    parser.add_argument("--inventory-only", action="store_true", help="No network or Claude calls")
    args = parser.parse_args(argv)
    if not 1 <= args.max_pages <= 5 or not 1 <= args.max_releases <= 10:
        parser.error("bounds: 1..5 pages and 1..10 releases per source")
    sources = args.sources.split(",")
    if any(source not in list_sources() for source in sources):
        parser.error("unknown source; use digest.py --list")
    try:
        with runtime_lock():
            baseline, candidates = inventory(args.baseline_ref,
                                             normalize_state(read_json(args.observed_state)))
            print("Candidate inventory only: seen cursors do not prove delivered summaries.")
            print("No sends, cursor rewrites or duplicate-delivery approval in this program.")
            for source in sources:
                if source in GITHUB_SOURCES:
                    print(f"{source}: potentially-swallowed={len(candidates[source])}; "
                          f"tags={','.join(candidates[source]) or 'none'}")
                else:
                    print(f"{source}: web-history-requires-baseline/anchor review; no exact version inventory")
            if args.inventory_only:
                return 0
            generation = generate_digest(sources, state=baseline,
                                         fetch=bounded_fetch(candidates, args.max_pages, args.max_releases))
            print(generation.text)
            print("Catch-up PREVIEW ONLY. Unselected history remains unresolved; no sending is enabled.")
            return 1 if generation.failures else 0
    except (StateFailure, RecoveryFailure) as error:
        print(f"Recovery preview failed: {error}")
        return 1
    except Exception:
        print("Recovery preview failed: internal-error; diagnostics withheld")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
