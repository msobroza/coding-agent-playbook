"""The D5 reference probe, shared by the context-budget and core-content tests.

One module-scoped sync of the probe (specs/prS-skills-context.md 6.8.10): the
budget, core-skill and Continue-regression tests read the same output, so a
module pays for one ``playbook init`` and no test can mutate another's tree.
The uv variant adds only a ``uv.lock``, the one input that turns on the gated
``python-uv-workflow`` member (spec 9.6.2). The Domino variant adds the
reliable Domino marker, the worst case of the prU D59 description caps. The
authoring variant adds an empty ``playbook/`` layer, which turns on the
``playbook-creator`` skill (prU D70). ``probe_repo`` picks one of them by the
test's ``probe`` parameter, so a check written once runs on every probe kind.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

import pytest

from tests._budget_probe import (
    init_and_sync_reference_probe,
    write_authoring_probe,
    write_domino_probe,
    write_reference_probe,
)
from tests.conftest import apply_hermetic_git_env

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from tests.core_skill_pins import ProbeKind

#: Probe kind -> the writer of its source tree (prU D5, D59, D70).
_PROBE_WRITERS: Final[Mapping[ProbeKind, Callable[[Path], None]]] = {
    "reference": write_reference_probe,
    "domino": write_domino_probe,
    "authoring": write_authoring_probe,
}


def _synced_probe(
    tmp_path_factory: pytest.TempPathFactory,
    probe: ProbeKind = "reference",
    *,
    uv_lock: bool = False,
) -> Path:
    """A fresh ``probe`` after ``playbook init``, plus a ``uv.lock`` when asked."""
    repo = tmp_path_factory.mktemp(f"{probe}-probe")
    _PROBE_WRITERS[probe](repo)
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
    return _synced_probe(tmp_path_factory)


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
    return _synced_probe(tmp_path_factory, "domino")


@pytest.fixture(scope="module")
def authoring_probe_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The reference probe plus an empty ``playbook/`` layer (prU D70), synced once; read-only.

    Example::

        skill_md = authoring_probe_repo / ".claude/skills/playbook-creator/SKILL.md"
    """
    return _synced_probe(tmp_path_factory, "authoring")


@pytest.fixture
def probe_repo(request: pytest.FixtureRequest, probe: ProbeKind) -> Path:
    """The synced repo of the test's ``probe`` parameter: ``<probe>_probe_repo``; read-only.

    Example::

        @pytest.mark.parametrize("probe", PROBE_KINDS)
        def test_x(probe: ProbeKind, probe_repo: Path) -> None: ...
    """
    return cast("Path", request.getfixturevalue(f"{probe}_probe_repo"))
