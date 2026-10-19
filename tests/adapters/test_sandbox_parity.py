"""Shipped templates render byte-identically under the Jinja sandbox (prK §P1).

``build_environment`` now returns a ``SandboxedEnvironment``. The sandbox only
blocks unsafe attribute access, so every engine-shipped ``.md.j2`` must render
exactly as it did under the plain ``jinja2.Environment``: the adapter outputs
are the goldens. Each test renders twice, once through the plain twin (the
module-level ``SandboxedEnvironment`` name swapped for ``jinja2.Environment``,
same kwargs) and once sandboxed, and compares the bytes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import jinja2
import pytest
from jinja2.sandbox import SandboxedEnvironment

from coding_agent_playbook import precommit, renderer
from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.sync import pipeline as _sync
from coding_agent_playbook.types import Prompt, Rule
from tests._catalog import CORE_ROOT

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    SyntheticRepoFactory = Callable[..., Path]

_LOCKFILE = ".coding-agent-playbook.lock"  # carries a render timestamp

#: Facts that switch on every shipped template's ``applies_if`` and branches:
#: python >= 3.12, pytest + pytest-asyncio as dev deps, the ML stack at runtime.
_RICH_PYPROJECT = """\
[project]
name = "synthetic"
description = "A consumer repo exercising every shipped template."
requires-python = ">=3.12"
dependencies = ["numpy", "pandas", "scikit-learn", "torch", "transformers"]

[dependency-groups]
dev = ["pytest", "pytest-asyncio"]
"""


def _use_plain_twin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``build_environment`` build the pre-§P1 plain environment."""
    monkeypatch.setattr(renderer, "SandboxedEnvironment", jinja2.Environment)
    assert not isinstance(renderer.build_environment([]), SandboxedEnvironment)


def _rich_repo(root: Path, make_synthetic_repo: SyntheticRepoFactory) -> Path:
    root.mkdir()
    repo = make_synthetic_repo(root)
    (repo / "pyproject.toml").write_text(_RICH_PYPROJECT, encoding="utf-8")
    return repo


def _synced_outputs(repo: Path) -> dict[str, bytes]:
    """Run ``playbook sync`` on ``repo``; return every file but the lockfile."""
    assert _sync.execute(repo) == 0
    return {
        p.relative_to(repo).as_posix(): p.read_bytes()
        for p in sorted(repo.rglob("*"))
        if p.is_file() and p.name != _LOCKFILE
    }


def _shipped_templated_ids() -> set[str]:
    """Ids of every engine-shipped ``.md.j2`` rule and prompt."""
    rules = {
        Rule.from_markdown(p, "coding_agent_playbook").frontmatter.id
        for p in (CORE_ROOT / "rules").rglob("*.md.j2")
    }
    prompts = {
        Prompt.from_markdown(p, "coding_agent_playbook").frontmatter.id
        for p in (CORE_ROOT / "prompts").rglob("*.md.j2")
    }
    return rules | prompts


def _rendered_artifact_ids(repo: Path) -> set[str]:
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    return {entry.artifact_id for entry in lockfile.entries if entry.artifact_id}


@pytest.mark.catalog
def test_shipped_templates_render_byte_identical_under_sandbox(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain_repo = _rich_repo(tmp_path / "plain", make_synthetic_repo)
    sandboxed_repo = _rich_repo(tmp_path / "sandboxed", make_synthetic_repo)
    with monkeypatch.context() as patch:
        _use_plain_twin(patch)
        plain = _synced_outputs(plain_repo)
    sandboxed = _synced_outputs(sandboxed_repo)
    assert sandboxed == plain
    # Not vacuous: every shipped template was actually rendered.
    assert _shipped_templated_ids() <= _rendered_artifact_ids(sandboxed_repo)


def test_precommit_starter_renders_byte_identical_under_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandboxed = precommit.render_fresh_pre_commit()
    _use_plain_twin(monkeypatch)
    assert precommit.render_fresh_pre_commit() == sandboxed
