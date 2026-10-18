"""The D5 reference probe, shared by the context-budget and core-content tests.

One module-scoped sync of the probe (specs/prS-skills-context.md 6.8.10): the
budget, core-skill and Continue-regression tests read the same output, so a
module pays for one ``playbook init`` and no test can mutate another's tree.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests._budget_probe import init_and_sync_reference_probe, write_reference_probe
from tests.conftest import apply_hermetic_git_env

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(scope="module")
def reference_probe_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The D5 reference probe, synced once per module (hooks on, both bundled plugins).

    Read-only for the tests: each module gets its own copy.

    Example::

        agents_md = (reference_probe_repo / "AGENTS.md").read_text(encoding="utf-8")
    """
    repo = tmp_path_factory.mktemp("reference-probe")
    write_reference_probe(repo)
    with pytest.MonkeyPatch.context() as patch:
        config_home = tmp_path_factory.mktemp("xdg-config")
        apply_hermetic_git_env(patch, ceiling=repo.parent, config_home=config_home)
        init_and_sync_reference_probe(repo)
    return repo
