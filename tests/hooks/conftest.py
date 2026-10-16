"""Fixtures for the §E pack hook tests (specs/prK-hook-pack.md §E.0.7).

``deps`` (autouse) is a factory of ``RuntimeDeps`` on the named fakes: an empty
env, a ``FakeProc`` that fails the test on any subprocess, ``FakeClock`` and
``FakeTrustStore``. Every pack hook is driven through ``simulate.run``, the
exact dispatch pipeline, so no handler is ever called directly. ``real_proc``
is the real ``ProcPort``, for the fresh-interpreter probes only.
``regulated_overlay`` is the §E.5 fixture overlay as an importable package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
from coding_agent_playbook.hook_runtime.proc import SubprocessProc
from tests.hook_runtime.fakes import FakeClock, FakeProc, FakeTrustStore
from tests.hooks.pack_repo import PackRepo, install_fixture_overlay

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


@pytest.fixture
def regulated_overlay(make_package: Callable[..., str]) -> str:
    """The regulated fixture overlay (``tests/fixtures/overlays/regulated``) as a package.

    It activates the §E.5 overlay-tier mechanisms (promotes them to ``tier:
    default``, supplies their data); pass its name as ``overlays=``.
    """
    return install_fixture_overlay(make_package, "regulated", "playbook_rules_regulated")


@pytest.fixture
def real_proc() -> SubprocessProc:
    """The real ``ProcPort``: only the fresh-interpreter import probes spawn."""
    return SubprocessProc()


@pytest.fixture
def ruff_program(tmp_path: Path) -> Path:
    """The stub file ``machine.json`` pins as ruff (``FakeRuff`` answers its calls)."""
    program = tmp_path / "tools" / "ruff"
    program.parent.mkdir()
    program.write_bytes(b"#!/bin/sh\n")
    return program
