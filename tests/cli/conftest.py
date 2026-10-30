"""Shared fixtures for the ``tests/cli/`` suite.

CLI tests drive subcommands like ``playbook eval <id> --run`` end-to-end against
the shipped eval samples. C11 wired :func:`materialize` to ``uv sync`` the scratch
tree when a ``setup/pyproject.toml`` is present (every shipped fixture has one),
so without a stub these tests would either shell out to the real ``uv`` binary
(non-hermetic; may be absent on the runner) or raise the documented "uv binary
required" error. Air-gapped/banking CI must not depend on ``uv`` being on PATH
inside pytest, so this autouse fixture short-circuits ``uv`` invocations to a
success result for every CLI test. Runner-internal tests live under
``tests/grading/`` and supply their own fine-grained stubs (so they can
exercise the real ``_uv_sync_scratch`` paths) — that scope is not affected.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.catalog import roots as catalog_roots
from tests._catalog import REPO_ROOT
from tests._uv_stub import stub_uv_sync
from tests.cli.forge_fakes import ForgeEnv, make_forge_env
from tests.edition_fixtures import TAG, freeze_fixture_edition, write_sample

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


@pytest.fixture(autouse=True)
def _stub_uv_sync_for_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Autouse: short-circuit any ``uv`` call from the runner to a success (``tests._uv_stub``).

    Function-scoped so each test gets a clean stub.
    """
    stub_uv_sync(monkeypatch)


@pytest.fixture
def engine_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A copy of the engine catalog with ``review/pinned`` pinned to a frozen fixture edition.

    The engine resolves its catalog from the copy (a checkout layout, ``src/<pkg>``
    next to ``catalog/``), so the pinned sample runs like a shipped one (#281 ticket 09).
    """
    catalog = tmp_path / "engine" / "catalog"
    shutil.copytree(REPO_ROOT / "catalog", catalog)
    monkeypatch.setattr(
        catalog_roots, "_PACKAGE_DIR", tmp_path / "engine" / "src" / "coding_agent_playbook"
    )
    write_sample(catalog / "core", edition=TAG)
    freeze_fixture_edition(catalog)
    return catalog


@pytest.fixture
def fake_uv_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Put a ``uv`` that always succeeds first on ``PATH``; return its directory.

    For tests whose eval runs happen in a **child process** (``playbook eval
    --compare`` runs each side through ``PlaybookEvalRun``): the autouse
    in-process stub above does not reach a child, which would otherwise shell out
    to the real ``uv`` (absent from CI's pytest job, and a network ``uv sync``
    where it is installed) and print no report (PR #266 CI).
    """
    fake_bin = tmp_path / "fake-uv-bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_uv.chmod(0o755)
    monkeypatch.setenv("PATH", os.pathsep.join((str(fake_bin), os.environ.get("PATH", ""))))
    return fake_bin


#: Forge host, repo and prompt variables a developer's shell may set; each forge test starts
#: without them, so it sees only what ``playbook forge`` itself sets in the child env.
_FORGE_ENV_VARS = (
    "GH_HOST",
    "GH_REPO",
    "GITLAB_HOST",
    "GITLAB_URI",
    "GL_HOST",
    "GITLAB_API_HOST",
    "GITLAB_REPO",
    "DOMINO_PROJECT_ID",
    "GH_PROMPT_DISABLED",
    "GLAB_NO_PROMPT",
    "GH_NO_UPDATE_NOTIFIER",
    "GH_NO_EXTENSION_UPDATE_NOTIFIER",
    "GH_TELEMETRY",
    "DO_NOT_TRACK",
    "GLAB_CHECK_UPDATE",
    "GLAB_SEND_TELEMETRY",
)


@pytest.fixture
def forge_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hermetic_git_env: None) -> ForgeEnv:
    """Fake ``gh`` / ``glab`` / ``ssh`` and the real ``git`` as the only executables on ``PATH``."""
    env = make_forge_env(tmp_path / "fakes")
    monkeypatch.setenv("PATH", str(env.bin_dir))
    for name in _FORGE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return env


@pytest.fixture
def forge_repo(tmp_path: Path, forge_env: ForgeEnv) -> Callable[..., Path]:
    """Return ``make(url, *, branch="main", pushed=True, config=None) -> repo path``.

    The repo has one commit on ``branch`` and the remote ``origin`` at ``url``;
    ``pushed`` adds ``refs/remotes/origin/<branch>`` (the branch is on the remote);
    ``config`` is written as the committed ``.coding-agent-playbook.toml``.
    """

    def make(
        url: str, *, branch: str = "main", pushed: bool = True, config: str | None = None
    ) -> Path:
        repo = tmp_path / "repo"
        repo.mkdir()

        def git(*args: str) -> None:
            subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, timeout=30)

        git("init", "-q", "-b", branch)
        if config is not None:
            (repo / ".coding-agent-playbook.toml").write_text(config, encoding="utf-8")
        git("commit", "-q", "--allow-empty", "-m", "chore: start")
        git("remote", "add", "origin", url)
        if pushed:
            git("update-ref", f"refs/remotes/origin/{branch}", "HEAD")
        return repo

    return make
