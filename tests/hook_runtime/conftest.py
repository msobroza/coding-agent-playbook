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
- ``real_git`` (root conftest) runs the real ``git`` binary to build fixture
  repositories; it skips when git is not on PATH and isolates git from the
  developer's machine through the root ``hermetic_git_env`` fixture.
- ``repo``, ``resolver`` and ``make_deps`` set up an in-process dispatch: a
  synced fixture repository, a scripted handler table, and deps whose watchdog
  timer and exit are fakes (helpers in ``dispatch_kit``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
from coding_agent_playbook.hook_runtime.dispatch.proc import SubprocessProc
from tests.hook_runtime.fakes import (
    FakeClock,
    FakeHandlerResolver,
    FakeProc,
    FakeTimers,
    FakeTrustStore,
    fake_exit,
)
from tests.hook_runtime.guard_repo import GuardRepo, streams

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


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
def repo(tmp_path: Path) -> GuardRepo:
    """A fresh fixture repository: ``.git/`` only, until a test installs a config."""
    return GuardRepo.create(tmp_path)


@pytest.fixture
def resolver() -> FakeHandlerResolver:
    """The handler table ``make_deps`` dispatches through; tests fill ``resolver.handlers``."""
    return FakeHandlerResolver()


@pytest.fixture
def make_deps(
    runtime_deps: Callable[..., RuntimeDeps], repo: GuardRepo, resolver: FakeHandlerResolver
) -> Callable[..., RuntimeDeps]:
    """Return ``make(**env)``: dispatch deps on fakes with fresh streams and ``repo``'s env.

    The watchdog's timer and exit are fakes too, so no thread is started.
    """

    def make(**env: str) -> RuntimeDeps:
        out, err = streams()
        return runtime_deps(
            env=repo.env(**env),
            out=out,
            err=err,
            resolve_handler=resolver,
            timer_factory=FakeTimers(),
            exit=fake_exit,
        )

    return make
