"""The D5 reference probe, shared by the context-budget and core-content tests.

One module-scoped sync of the probe (specs/prS-skills-context.md 6.8.10): the
budget, core-skill and Continue-regression tests read the same output, so a
module pays for one ``playbook init`` and no test can mutate another's tree.
The uv variant adds only a ``uv.lock``, the one input that turns on the gated
``python-uv-workflow`` member (spec 9.6.2). The Domino variant adds the
reliable Domino marker, the worst case of the prU D59 description caps. The
authoring variant adds an empty ``playbook/`` layer, which turns on the
``playbook-creator`` skill (prU D70).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests._budget_probe import (
    init_and_sync_reference_probe,
    write_authoring_probe,
    write_domino_probe,
    write_reference_probe,
)
from tests.conftest import apply_hermetic_git_env

if TYPE_CHECKING:
    from pathlib import Path


def _synced_probe(
    tmp_path_factory: pytest.TempPathFactory,
    *,
    uv_lock: bool,
    domino: bool = False,
    authoring: bool = False,
) -> Path:
    """A fresh probe after ``playbook init``; ``uv.lock``, Domino markers or a layer when asked."""
    if domino:
        repo = tmp_path_factory.mktemp("domino-probe")
        write_domino_probe(repo)
    elif authoring:
        repo = tmp_path_factory.mktemp("authoring-probe")
        write_authoring_probe(repo)
    else:
        repo = tmp_path_factory.mktemp("reference-probe")
        write_reference_probe(repo)
    if uv_lock:
        (repo / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    with pytest.MonkeyPatch.context() as patch:
        config_home = tmp_path_factory.mktemp("xdg-config")
        apply_hermetic_git_env(patch, ceiling=repo.parent, config_home=config_home)
        init_and_sync_reference_probe(repo)
    return repo


@pytest.fixture(scope="module")
def reference_probe_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The D5 reference probe, synced once per module (hooks on, the superpowers plugin).

    Read-only for the tests: each module gets its own copy.

    Example::

        agents_md = (reference_probe_repo / "AGENTS.md").read_text(encoding="utf-8")
    """
    return _synced_probe(tmp_path_factory, uv_lock=False)


@pytest.fixture(scope="module")
def uv_reference_probe_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The reference probe plus a ``uv.lock``, synced once per module; read-only.

    Example::

        skill_md = uv_reference_probe_repo / ".claude/skills/python-tooling/SKILL.md"
    """
    return _synced_probe(tmp_path_factory, uv_lock=True)


@pytest.fixture(scope="module")
def domino_probe_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The reference probe plus the reliable Domino markers (prU D59), synced once; read-only.

    Example::

        skills = sorted(p.name for p in (domino_probe_repo / ".claude/skills").iterdir())
    """
    return _synced_probe(tmp_path_factory, uv_lock=False, domino=True)


@pytest.fixture(scope="module")
def authoring_probe_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The reference probe plus an empty ``playbook/`` layer (prU D70), synced once; read-only.

    Example::

        skill_md = authoring_probe_repo / ".claude/skills/playbook-creator/SKILL.md"
    """
    return _synced_probe(tmp_path_factory, uv_lock=False, authoring=True)
