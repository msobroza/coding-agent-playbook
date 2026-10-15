"""``opencode_restart_notice``: when sync must ask for an OpenCode restart (prK §C.1.5, §C.3.2).

OpenCode V1 has no plugin hot reload, so a change to the shim's bytes (its
``REG``) needs a restart, while a ``guard_config.json``-only change is read by
the next dispatch. The notice is a pure comparison of the previous and the new
lockfile's whole-file entry for the shim, so it holds under both ``[output]
commit`` settings.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.commands._sync_hooks import opencode_restart_notice
from coding_agent_playbook.guard_config import GUARD_CONFIG_PATH
from coding_agent_playbook.hook_registrations import OPENCODE_SHIM_PATH
from coding_agent_playbook.lockfile import LockEntry, Lockfile

CHANGED = f"! {OPENCODE_SHIM_PATH} changed: restart OpenCode to load it"
REMOVED = f"! {OPENCODE_SHIM_PATH} removed: restart OpenCode to unload it"


def _entry(path: str, sha256: str, *, scope: str = "") -> LockEntry:
    return LockEntry(path, sha256, 10, kind="runtime", scope=scope)


def _lock(*entries: LockEntry) -> Lockfile:
    return Lockfile(2, "0.1.0a0", "2026-10-15T00:00:00Z", list(entries))


def test_restart_notice_when_shim_hash_changes() -> None:
    previous = _lock(_entry(OPENCODE_SHIM_PATH, "a" * 64))
    current = _lock(_entry(OPENCODE_SHIM_PATH, "b" * 64))

    assert opencode_restart_notice(previous, current) == CHANGED


@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [
        (None, _lock(_entry(OPENCODE_SHIM_PATH, "a" * 64)), CHANGED),
        (_lock(), _lock(_entry(OPENCODE_SHIM_PATH, "a" * 64)), CHANGED),
        (_lock(_entry(OPENCODE_SHIM_PATH, "a" * 64)), _lock(), REMOVED),
    ],
    ids=["first-sync", "first-written", "removed"],
)
def test_restart_notice_when_shim_first_written_or_removed(
    previous: Lockfile | None, current: Lockfile, expected: str
) -> None:
    assert opencode_restart_notice(previous, current) == expected


def test_no_restart_notice_when_only_guard_config_changes() -> None:
    shim = _entry(OPENCODE_SHIM_PATH, "a" * 64)
    previous = _lock(_entry(GUARD_CONFIG_PATH, "1" * 64), shim)
    current = _lock(_entry(GUARD_CONFIG_PATH, "2" * 64), shim)

    assert opencode_restart_notice(previous, current) is None


@pytest.mark.parametrize(
    ("previous", "current"),
    [
        (None, _lock(_entry(GUARD_CONFIG_PATH, "1" * 64))),
        (_lock(_entry(GUARD_CONFIG_PATH, "1" * 64)), _lock(_entry(GUARD_CONFIG_PATH, "2" * 64))),
        (None, _lock()),
    ],
    ids=["first-sync", "guard-config-only", "empty"],
)
def test_no_restart_notice_without_shim_in_either_lockfile(
    previous: Lockfile | None, current: Lockfile
) -> None:
    assert opencode_restart_notice(previous, current) is None


def test_scoped_entry_at_the_shim_path_is_not_the_shim() -> None:
    # Only a whole-file entry vouches for the shim's bytes; a scoped one owns a JSON element.
    previous = _lock(_entry(OPENCODE_SHIM_PATH, "a" * 64, scope="json:/hooks"))

    assert opencode_restart_notice(previous, _lock()) is None
