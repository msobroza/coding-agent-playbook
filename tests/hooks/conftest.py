"""Fixtures for the §E pack hook tests (specs/prK-hook-pack.md §E.0.7).

``deps`` (autouse) is a factory of ``RuntimeDeps`` on the named fakes: an empty
env, a ``FakeProc`` that fails the test on any subprocess, ``FakeClock`` and
``FakeTrustStore``. Every pack hook is driven through ``simulate.run``, the
exact dispatch pipeline, so no handler is ever called directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
from tests.hook_runtime.fakes import FakeClock, FakeProc, FakeTrustStore
from tests.hooks.pack_repo import PackRepo

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


@pytest.fixture(autouse=True)
def deps() -> Callable[..., RuntimeDeps]:
    """Return ``make(**overrides) -> RuntimeDeps`` on fakes; ``proc`` refuses every spawn.

    Example::

        def test_x(deps):
            report = repo.simulate(payload, deps(platform="darwin"))
    """

    def make(**overrides: Any) -> RuntimeDeps:
        fields: dict[str, Any] = {
            "env": {},
            "proc": FakeProc(),
            "clock": FakeClock(),
            "trust": FakeTrustStore(),
            "home": "/home/dev",
            "platform": "linux",
            **overrides,
        }
        return RuntimeDeps(**fields)

    return make


@pytest.fixture
def pack_repo(tmp_path: Path) -> PackRepo:
    """An empty fixture repository (``.git/`` only) to install pack hooks into."""
    return PackRepo.create(tmp_path)
