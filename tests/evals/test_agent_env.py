"""Tests for the eval runners' unattended child env (specs/prK-lifecycle-hooks.md P-D2).

An eval run has no human to answer a hook's ``ask``, so the runners mark the
agent's env unattended and the hook runtime degrades ``ask`` to ``deny``
deterministically instead of hanging or prompting. The agent also runs on the
sample's own environment: the scratch ``.venv`` that ``materialize`` syncs.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.run.agent_env import (
    UNATTENDED_ENV_VAR,
    agent_env,
    scratch_venv_env,
    unattended_agent_env,
)

if TYPE_CHECKING:
    from pathlib import Path

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


# --------------------------------------------------------------------------- #
# The sample's own environment: materialize's ``uv sync`` creates <scratch>/.venv
# --------------------------------------------------------------------------- #


def _scratch_with_venv(tmp_path: Path) -> Path:
    scratch = tmp_path / "scratch"
    (scratch / ".venv" / "bin").mkdir(parents=True)
    return scratch


def test_scratch_venv_env_puts_the_venv_bin_first_and_sets_virtual_env(tmp_path: Path) -> None:
    scratch = _scratch_with_venv(tmp_path)
    env = scratch_venv_env({"PATH": "/usr/bin:/bin"}, scratch)
    venv = scratch.absolute() / ".venv"
    assert env["PATH"] == f"{venv / 'bin'}{os.pathsep}/usr/bin:/bin"
    assert env["VIRTUAL_ENV"] == str(venv)


def test_scratch_venv_env_overrides_an_inherited_venv_and_python_home(tmp_path: Path) -> None:
    # The playbook itself may run from its own venv: the agent must not inherit it.
    scratch = _scratch_with_venv(tmp_path)
    base = {"PATH": "/p/.venv/bin:/usr/bin", "VIRTUAL_ENV": "/p/.venv", "PYTHONHOME": "/x"}
    env = scratch_venv_env(base, scratch)
    assert env["VIRTUAL_ENV"] == str(scratch.absolute() / ".venv")
    assert "PYTHONHOME" not in env


def test_scratch_venv_env_without_a_path_is_just_the_venv_bin(tmp_path: Path) -> None:
    scratch = _scratch_with_venv(tmp_path)
    assert scratch_venv_env({}, scratch)["PATH"] == str(scratch.absolute() / ".venv" / "bin")


def test_scratch_venv_env_is_unchanged_without_a_venv(tmp_path: Path) -> None:
    base = {"PATH": "/usr/bin", "VIRTUAL_ENV": "/p/.venv"}
    assert scratch_venv_env(base, tmp_path) == base


def test_scratch_venv_env_never_mutates_the_base(tmp_path: Path) -> None:
    base = {"PATH": "/usr/bin"}
    scratch_venv_env(base, _scratch_with_venv(tmp_path))
    assert base == {"PATH": "/usr/bin"}


def test_agent_env_is_unattended_and_on_the_scratch_venv(tmp_path: Path) -> None:
    scratch = _scratch_with_venv(tmp_path)
    env = agent_env(scratch, {"PATH": "/usr/bin"})
    assert env[UNATTENDED_ENV_VAR] == "1"
    assert env["VIRTUAL_ENV"] == str(scratch.absolute() / ".venv")


def test_agent_env_names_the_scratch_as_pwd_over_the_callers(tmp_path: Path) -> None:
    """Regression: OpenCode reads its project directory from ``PWD``, not the cwd."""
    scratch = tmp_path / "scratch"

    env = agent_env(scratch, {"PATH": "/usr/bin", "PWD": "/the/caller/checkout"})

    assert env["PWD"] == str(scratch.absolute())
