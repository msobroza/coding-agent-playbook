"""Fixtures for the ``hook_runtime`` suite (specs/prK-lifecycle-hooks.md §D.9).

The runtime reaches processes, git, clocks and the trust store only through
``RuntimeDeps``, so isolation is dependency injection, never patching:

- ``runtime_deps`` (autouse) is a factory whose ``RuntimeDeps`` carry
  ``FakeProc``, ``FakeClock`` and ``FakeTrustStore`` and an empty env, so an
  in-process dispatch that tries to spawn fails with ``unexpected
  subprocess``. ``subprocess.run`` itself is never patched: the import
  probes and the ``real_git`` rows spawn interpreters and git legitimately.
- ``real_proc`` is the plain real ``ProcPort``, requested by the tests that
  must spawn (concurrency, timeouts, ``SafeGit`` against a real repo).
- ``real_git`` runs the real ``git`` binary to build fixture repositories; it
  skips when git is not on PATH and isolates git from the developer's machine
  through the root ``hermetic_git_env`` fixture.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
from coding_agent_playbook.hook_runtime.proc import SubprocessProc
from tests.hook_runtime.fakes import FakeClock, FakeProc, FakeTrustStore

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

GIT_TIMEOUT_S = 30


@pytest.fixture(autouse=True)
def runtime_deps() -> Callable[..., RuntimeDeps]:
    """Return ``make(**overrides) -> RuntimeDeps`` built on fakes, with an empty env.

    Example::

        def test_x(runtime_deps):
            deps = runtime_deps(env={"CI": "true"})
    """

    def make(**overrides: Any) -> RuntimeDeps:
        fields: dict[str, Any] = {
            "env": {},
            "proc": FakeProc(),
            "clock": FakeClock(),
            "trust": FakeTrustStore(),
            "home": "/home/dev",
            **overrides,
        }
        return RuntimeDeps(**fields)

    return make


@pytest.fixture
def real_proc() -> SubprocessProc:
    """The real ``ProcPort``, for the tests that must start processes."""
    return SubprocessProc()


@pytest.fixture
def real_git(hermetic_git_env: None) -> Callable[..., str]:
    """Return ``run(*args, cwd=path) -> stdout`` for the real git, or skip without one.

    Example::

        def test_x(real_git, tmp_path):
            real_git("init", "-q", cwd=tmp_path)
    """
    if shutil.which("git") is None:
        pytest.skip("git not on PATH")

    def _run(*args: str, cwd: Path) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
        )
        return completed.stdout.strip()

    return _run
