"""The expected ``guard_config.json`` digest, from the lockfile (specs/prK-lifecycle-hooks.md §D.8.1).

``guard_config.json`` is a whole-file ``[[entries]]`` row of
``.coding-agent-playbook.lock``, and only that row's ``sha256`` is trusted:
tampering then needs two coordinated, guarded edits. The lockfile is TOML and
``tomllib`` costs about 19 ms, too much for every tool call, so the answer is
cached in ``<state>/cfg-digest.json`` with the lockfile's
``(size, mtime_ns, ino)``; ``tomllib`` loads only when that stat changes, or
when ``session_start`` asks for a refresh.

The runtime may not import ``coding_agent_playbook.lockfile`` (§D.1), so
:func:`lock_entry_sha256` is a minimal ``[[entries]]`` lookup, pinned to
``Lockfile.from_dict(...).find`` by a parity test.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Final, Protocol

from coding_agent_playbook.hook_runtime.config.reader import read_small_file
from coding_agent_playbook.hook_runtime.state.store import StateUnavailable

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.state.store import StateStore

__all__ = [
    "CFG_DIGEST_DOC",
    "TomlLoader",
    "expected_digest",
    "load_toml",
    "lock_entry_sha256",
]

CFG_DIGEST_DOC: Final = "cfg-digest.json"
#: A lockfile larger than this is not read on a hook path.
MAX_LOCK_BYTES: Final = 8 * 1024 * 1024
_SIGNATURE_KEYS: Final = ("lock_size", "lock_mtime_ns", "lock_ino")
_SHA_KEY: Final = "guard_config_sha256"
_MISS: Final = object()


class TomlLoader(Protocol):
    """Parses TOML bytes; injectable so the digest-cache test can count parses."""

    def __call__(self, data: bytes) -> Mapping[str, Any]: ...


def load_toml(data: bytes) -> Mapping[str, Any]:
    """Parse ``data`` with ``tomllib``, imported here and only here (a §D.1 branch-local row).

    Example::

        >>> load_toml(b"a = 1\\n")
        {'a': 1}
    """
    import tomllib

    return tomllib.loads(data.decode("utf-8"))


def lock_entry_sha256(document: Mapping[str, Any], path: str) -> str | None:
    """The ``sha256`` of the first whole-file ``[[entries]]`` row for ``path``, else ``None``.

    Scoped rows (``scope = "json:..."``) own one element of a JSON file and
    never vouch for a whole file; a malformed table yields ``None``.

    Example::

        >>> lock_entry_sha256({"entries": [{"path": "a", "sha256": "ff"}]}, "a")
        'ff'
    """
    entries = document.get("entries")
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if isinstance(entry, dict) and entry.get("path") == path and not entry.get("scope"):
            sha = entry.get("sha256")
            return sha if isinstance(sha, str) else None
    return None


def expected_digest(
    lock_path: Path,
    target: str,
    state: StateStore | None,
    *,
    load_toml: TomlLoader = load_toml,
    refresh: bool = False,
) -> str | None:
    """The lockfile's sha256 for ``target``, from the cache unless the lockfile changed.

    ``None`` when the lockfile is missing, unreadable, not TOML or has no
    whole-file row for ``target``.

    Example::

        >>> expected_digest(root / LOCKFILE_REL, GUARD_CONFIG_REL, store)  # doctest: +SKIP
        '9f2c...'
    """
    try:
        signature = _signature(os.stat(lock_path))
    except OSError:
        return None
    cached = _MISS if refresh else _cached(state, signature)
    if cached is not _MISS:
        return cached if isinstance(cached, str) else None
    try:
        data, info = read_small_file(lock_path, MAX_LOCK_BYTES)
        sha = lock_entry_sha256(load_toml(data), target)
    except (OSError, ValueError):
        return None  # tomllib.TOMLDecodeError and UnicodeDecodeError are ValueErrors
    _remember(state, _signature(info), sha)
    return sha


def _signature(info: os.stat_result) -> list[int]:
    return [info.st_size, info.st_mtime_ns, info.st_ino]


def _cached(state: StateStore | None, signature: list[int]) -> object:
    """The cached sha (or ``None``) for exactly this lockfile stat, else ``_MISS``."""
    if state is None:
        return _MISS
    try:
        document = state.read_json(CFG_DIGEST_DOC)
    except StateUnavailable:
        return _MISS
    if [document.get(key) for key in _SIGNATURE_KEYS] != signature or _SHA_KEY not in document:
        return _MISS
    return document[_SHA_KEY]


def _remember(state: StateStore | None, signature: list[int], sha: str | None) -> None:
    if state is None:
        return
    document: dict[str, Any] = dict(zip(_SIGNATURE_KEYS, signature, strict=True))
    document[_SHA_KEY] = sha
    try:
        state.write_json(CFG_DIGEST_DOC, document)
    except StateUnavailable:
        return  # stateless: the next event parses the lockfile again
