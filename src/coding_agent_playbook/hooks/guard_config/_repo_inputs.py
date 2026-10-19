"""What the guard_config writer reads from the repository itself (specs/prT-package-layout.md 9 AC.2.3).

Sync hands ``compile_guard_config`` only what sync computes (``inputs``); every
input kept in a repository file is read here, once per compile, from ``repo_root``
(GC-D2). That is the real repository in every mode, so ``sync --check``, which
writes into an empty scratch dir, compiles the same bytes (GC-D3). Each reader keeps
its own policy: a missing, unreadable or malformed file gives that reader's default
and never raises (GC-D5), because sync reads these after its adapters wrote.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.hooks.guard_config._tables_precommit import precommit_hook_ids
from coding_agent_playbook.hooks.guard_config._tables_quality import (
    QualityLint,
    read_quality_lint,
)
from coding_agent_playbook.hooks.guard_config._tables_ruff import (
    RuffSelection,
    read_project_ruff_selection,
)
from coding_agent_playbook.hooks.guard_config._tables_toolchain import (
    ToolchainInputs,
    read_toolchain_inputs,
)
from coding_agent_playbook.hooks.guard_config._tables_verify import RepoLayout, repo_layout

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

__all__ = ["RepoInputs", "read_repo_inputs"]


@dataclass(frozen=True, slots=True, kw_only=True)
class RepoInputs:
    """The repository's own files, read for the tables that need them.

    ``precommit_ids``: the playbook hook ids of ``.pre-commit-config.yaml``;
    ``layout``: tests-with-source-nudge's roots (``src``, pytest ``testpaths``);
    ``ruff``: the selection of the ruff config ruff itself would read;
    ``toolchain``: the install hints and the asyncio flag from ``pyproject.toml``;
    ``quality``: the committed ``[metrics.ruff_violations]``.

    Example: ``read_repo_inputs(bare_repo, {}).layout.test_roots == ("tests",)``.
    """

    precommit_ids: tuple[str, ...]
    layout: RepoLayout
    ruff: RuffSelection
    toolchain: ToolchainInputs
    quality: QualityLint


def read_repo_inputs(repo_root: Path, facts: Mapping[str, Any]) -> RepoInputs:
    """Read each repo input of ``repo_root`` once; ``facts`` name the package manager.

    Example::

        >>> read_repo_inputs(Path("/no/such/repo"), {}).precommit_ids
        ()
    """
    return RepoInputs(
        precommit_ids=tuple(precommit_hook_ids(repo_root)),
        layout=repo_layout(repo_root),
        ruff=read_project_ruff_selection(repo_root),
        toolchain=read_toolchain_inputs(repo_root, facts),
        quality=read_quality_lint(repo_root),
    )
