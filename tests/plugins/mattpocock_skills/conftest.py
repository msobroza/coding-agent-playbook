"""Fixtures shared by the ``mattpocock_skills`` gates (T01 only; lanes never edit it).

``synced_repo`` is one probe consumer repo per test package, opted into the
plugin through ``playbook init --non-interactive --overlays …`` with every skill
adapter, and shared read-only. A test that needs the plugin off builds its own
probe in ``tmp_path`` with :func:`init_probe`.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import init as _init
from tests.conftest import apply_hermetic_git_env
from tests.plugins.mattpocock_skills._expectations import PLUGIN_NAME
from tests.plugins.superpowers_expectations import SKILL_ADAPTERS

if TYPE_CHECKING:
    from pathlib import Path


def init_probe(repo: Path, *, overlays: str | None, adapters: str | None = None) -> Path:
    """Run ``playbook init --non-interactive`` (which ends with a sync) in ``repo``.

    Example: ``init_probe(tmp_path, overlays=None)`` -> a probe with the plugin off.
    """
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "probe"\nrequires-python = ">=3.10"\ndependencies = []\n',
        encoding="utf-8",
    )
    args = argparse.Namespace(
        repo_root=str(repo),
        non_interactive=True,
        name="probe",
        kind="python-application",
        description="",
        adapters=adapters,
        overlays=overlays,
    )
    assert _init.run(args) == 0, f"playbook init failed in {repo}"
    return repo


@pytest.fixture(scope="package")
def synced_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A probe repo synced with the plugin and adapters ``continue,claude_code,opencode,shared_skills``."""
    repo = tmp_path_factory.mktemp("mattpocock-skills-consumer")
    with pytest.MonkeyPatch.context() as patch:
        config_home = tmp_path_factory.mktemp("xdg-config")
        apply_hermetic_git_env(patch, ceiling=repo.parent, config_home=config_home)
        return init_probe(repo, overlays=PLUGIN_NAME, adapters=",".join(SKILL_ADAPTERS))
