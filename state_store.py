"""Atomic runtime files and a shared digest/maintenance process lock (Linux)."""

from contextlib import contextmanager
import fcntl
import json
import math
import os
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parent
LOCK_FILE = ROOT / ".runtime.lock"


class StateFailure(RuntimeError):
    pass


@contextmanager
def runtime_lock(path=None):
    path = Path(path or LOCK_FILE)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def atomic_text(path, text):
    path = Path(path)
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError:
        raise StateFailure("runtime-write-failed") from None
    finally:
        if temporary:
            os.unlink(temporary)


def atomic_json(path, value):
    atomic_text(path, json.dumps(value, indent=2) + "\n")


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return {}
    except (ValueError, OSError):
        # A corrupt cursor must not turn into an empty cursor and duplicate flood.
        raise StateFailure("runtime-file-unreadable: preserve and repair before retrying") from None


def normalize_versions(values):
    if values is None:
        return []
    if isinstance(values, (str, int, float)) and not isinstance(values, bool):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        raise StateFailure("state-invalid-versions")
    normalized = set()
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise StateFailure("state-invalid-version")
        if isinstance(value, float) and not math.isfinite(value):
            raise StateFailure("state-invalid-version")
        value = str(value).strip()
        if value:
            normalized.add(value)
    return sorted(normalized, key=version_sort_key)


def version_sort_key(value):
    parts = []
    for part in str(value).lstrip("v").split("."):
        match = re.match(r"^(\d+)(.*)", part)
        number, suffix = (int(match[1]), match[2]) if match else (0, part)
        parts.append((number, not bool(suffix), suffix))
    # A tie-breaker makes normalization deterministic for equivalent versions.
    return tuple(parts), str(value)


def normalize_state(state):
    if not isinstance(state, dict):
        raise StateFailure("state-invalid-root")
    result = {}
    for key, entry in state.items():
        if not isinstance(entry, dict):
            raise StateFailure("state-invalid-entry")
        entry = dict(entry)
        if "seen_versions" in entry:
            entry["seen_versions"] = normalize_versions(entry["seen_versions"])
        for cursor in ("content_hash", "content_anchor"):
            if cursor in entry and not isinstance(entry[cursor], str):
                raise StateFailure("state-invalid-web-cursor")
        result[key] = entry
    return result
