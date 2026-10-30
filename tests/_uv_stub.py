"""Short-circuit the runner's ``uv sync`` so end-to-end tests never need ``uv`` on PATH.

``materialize`` runs ``uv sync`` when a sample's ``setup/`` ships a
``pyproject.toml`` (every shipped eval sample does). CI installs the project with
uv but has no ``uv`` on PATH inside pytest, so a test that drives the runner over
a shipped sample raises "uv binary required" there while passing locally. Tests
that exercise the real ``_uv_sync_scratch`` paths stub it themselves instead.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pytest

_RUNNER = "coding_agent_playbook.evals.run.harness_runner"


def stub_uv_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every ``uv`` call from the runner succeed, leaving other commands alone.

    Stubs ``subprocess.run`` (only when the first arg is ``"uv"``; git and other
    calls pass through) and ``shutil.which`` (pretends ``uv`` is on PATH so the
    runner does not raise the missing-binary error; every other lookup, e.g.
    ``SafeGit``'s ``which("git", path=...)``, passes through). Both attributes
    live on the shared modules, so the stubs must stay transparent for every
    other caller.

    Example::

        stub_uv_sync(monkeypatch)  # in a function-scoped fixture
    """
    real_run = subprocess.run
    real_which = shutil.which

    def _stub_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "uv":
            return subprocess.CompletedProcess(args, 0, "", "")
        return real_run(args, **kwargs)

    def _stub_which(binary: str, *args: Any, **kwargs: Any) -> str | None:
        return "/fake/uv" if binary == "uv" else real_which(binary, *args, **kwargs)

    monkeypatch.setattr(f"{_RUNNER}.subprocess.run", _stub_run)
    monkeypatch.setattr(f"{_RUNNER}.shutil.which", _stub_which)
