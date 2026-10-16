"""Tests never inherit the runner's attendance variables (specs/prK-lifecycle-hooks.md §D.3.6).

GitHub Actions exports ``CI=true`` and ``GITHUB_ACTIONS=true`` to every step, and
``is_unattended`` turns each ``ask`` into a ``deny`` under either. A dispatcher
spawned with an inherited env then takes the unattended path on CI only: other
exit codes ("unattended run, so denied") and other imports (PR #32's red
``test_cli_argv`` / ``test_import_budget`` / ``test_latency_budget`` rows).
``probe_env`` drops them and the root conftest clears them for the whole
session, so a test that wants an unattended run sets one itself.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pytest

from coding_agent_playbook.hook_runtime.event import Harness
from coding_agent_playbook.hook_runtime.policy import is_unattended
from tests.attendance_env import ATTENDANCE_ENV_VARS, without_attendance_vars
from tests.import_probe import probe_env

#: A value that makes each variable alone mark a run unattended.
_UNATTENDED_VALUES = {"PLAYBOOK_HOOK_UNATTENDED": "1", "CI": "true", "GITHUB_ACTIONS": "true"}


@dataclass(frozen=True, slots=True)
class _AttendedEvent:
    """An ``AttendanceFacts`` no env-free signal marks unattended."""

    harness: Harness = Harness.CLAUDE_CODE
    permission_mode: str | None = "default"


class _ReadRecordingEnv(dict[str, str]):
    """An empty env that records every key looked up in it."""

    def __init__(self) -> None:
        super().__init__()
        self.read: set[str] = set()

    def get(self, key: str, default: object = None) -> object:  # type: ignore[override]
        self.read.add(key)
        return super().get(key, default)

    def __getitem__(self, key: str) -> str:
        self.read.add(key)
        return super().__getitem__(key)

    def __contains__(self, key: object) -> bool:
        self.read.add(str(key))
        return super().__contains__(key)


def test_attendance_vars_are_exactly_the_keys_is_unattended_reads() -> None:
    """The list cannot drift: a new signal in ``is_unattended`` fails here first."""
    env = _ReadRecordingEnv()

    assert is_unattended(_AttendedEvent(), env) is False
    assert env.read == set(ATTENDANCE_ENV_VARS)


@pytest.mark.parametrize("name", ATTENDANCE_ENV_VARS)
def test_each_attendance_var_alone_marks_the_run_unattended(name: str) -> None:
    assert is_unattended(_AttendedEvent(), {name: _UNATTENDED_VALUES[name]}) is True


def test_without_attendance_vars_keeps_every_other_key() -> None:
    env = {**_UNATTENDED_VALUES, "PATH": "/usr/bin", "CLAUDE_PROJECT_DIR": "/r"}

    assert without_attendance_vars(env) == {"PATH": "/usr/bin", "CLAUDE_PROJECT_DIR": "/r"}


def test_probe_env_drops_the_attendance_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dispatcher subprocesses of the import and latency budgets run attended."""
    for name, value in _UNATTENDED_VALUES.items():
        monkeypatch.setenv(name, value)

    env = probe_env()

    assert set(ATTENDANCE_ENV_VARS).isdisjoint(env)
    assert is_unattended(_AttendedEvent(), env) is False


def test_suite_runs_without_the_runner_attendance_vars() -> None:
    """The root conftest's session fixture: in-process tests never see ``CI=true``."""
    assert set(ATTENDANCE_ENV_VARS).isdisjoint(os.environ)
