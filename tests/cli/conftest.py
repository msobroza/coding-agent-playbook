"""Shared fixtures for the ``tests/cli/`` suite.

CLI tests drive subcommands like ``playbook eval <id> --run`` end-to-end against
the shipped eval tasks. C11 wired :func:`materialize` to ``uv sync`` the scratch
tree when a ``setup/pyproject.toml`` is present (every shipped fixture has one),
so without a stub these tests would either shell out to the real ``uv`` binary
(non-hermetic; may be absent on the runner) or raise the documented "uv binary
required" error. Air-gapped/banking CI must not depend on ``uv`` being on PATH
inside pytest, so this autouse fixture short-circuits ``uv`` invocations to a
success result for every CLI test. Runner-internal tests live under
``tests/evaluators/`` and supply their own fine-grained stubs (so they can
exercise the real ``_uv_sync_scratch`` paths) — that scope is not affected.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _stub_uv_sync_for_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Autouse: short-circuit any ``uv`` call from the runner to a success.

    Stubs ``subprocess.run`` (only when the first arg is ``"uv"``; git and other
    calls pass through) and ``shutil.which`` (pretends ``uv`` is on PATH so the
    runner does not raise the missing-binary error; every other lookup, e.g.
    ``SafeGit``'s ``which("git", path=...)``, passes through). Both attributes
    live on the shared modules, so the stubs must stay transparent for every
    other caller. Function-scoped so each test gets a clean stub.
    """
    real_run = subprocess.run
    real_which = shutil.which

    def _stub_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "uv":
            return subprocess.CompletedProcess(args, 0, "", "")
        return real_run(args, **kwargs)

    monkeypatch.setattr("coding_agent_playbook.evals.run.harness_runner.subprocess.run", _stub_run)

    def _stub_which(binary: str, *args: Any, **kwargs: Any) -> str | None:
        return "/fake/uv" if binary == "uv" else real_which(binary, *args, **kwargs)

    monkeypatch.setattr("coding_agent_playbook.evals.run.harness_runner.shutil.which", _stub_which)
