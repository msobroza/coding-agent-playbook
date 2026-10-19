"""Tests for the eval runners' unattended child env (specs/prK-lifecycle-hooks.md P-D2).

An eval run has no human to answer a hook's ``ask``, so the runners mark the
agent's env unattended and the hook runtime degrades ``ask`` to ``deny``
deterministically instead of hanging or prompting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evals.run.agent_env import UNATTENDED_ENV_VAR, unattended_agent_env

if TYPE_CHECKING:
    import pytest


def test_env_var_name_is_the_shared_hook_runtime_contract() -> None:
    # The hook runtime (K2) re-declares this name without importing evals.
    assert UNATTENDED_ENV_VAR == "PLAYBOOK_HOOK_UNATTENDED"


def test_unattended_agent_env_forces_the_flag_over_the_base() -> None:
    base = {"PATH": "/usr/bin", UNATTENDED_ENV_VAR: "0"}
    assert unattended_agent_env(base) == {"PATH": "/usr/bin", UNATTENDED_ENV_VAR: "1"}


def test_unattended_agent_env_never_mutates_the_base() -> None:
    base = {"PATH": "/usr/bin"}
    env = unattended_agent_env(base)
    env["EXTRA"] = "x"
    assert base == {"PATH": "/usr/bin"}


def test_unattended_agent_env_defaults_to_the_process_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLAYBOOK_TEST_PARENT_MARKER", "kept")
    monkeypatch.delenv(UNATTENDED_ENV_VAR, raising=False)
    env = unattended_agent_env()
    assert env["PLAYBOOK_TEST_PARENT_MARKER"] == "kept"
    assert env[UNATTENDED_ENV_VAR] == "1"
