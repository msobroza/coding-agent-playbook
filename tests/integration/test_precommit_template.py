"""The packaged air-gapped pre-commit starter renders to valid, all-local YAML.

Guards three things: the engine-owned ``templates/precommit/config.yaml.j2``
template is actually shipped (resolvable via ``importlib.resources``), a missing
template fails with an explicit error rather than an ``assert`` (which ``-O``
strips), and it renders through the Jinja environment without a
``StrictUndefined`` error to a config whose every hook is ``repo: local`` +
``language: system`` (so pre-commit never clones a remote hook repo).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import yaml

from coding_agent_playbook.commands.init import (
    PrecommitTemplateMissingError,
    _render_fresh_pre_commit,
    precommit_template_dir,
)
from coding_agent_playbook.sources.filesystem import _resource_subdir

if TYPE_CHECKING:
    from pathlib import Path


def test_precommit_template_is_packaged() -> None:
    assert (precommit_template_dir() / "config.yaml.j2").is_file()


def test_precommit_template_dir_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(PrecommitTemplateMissingError) as excinfo:
        precommit_template_dir(templates_root=tmp_path)
    assert str(tmp_path / "precommit") in str(excinfo.value)


def test_precommit_template_dir_without_the_template_file_raises(tmp_path: Path) -> None:
    """The directory alone is not enough: ``config.yaml.j2`` itself must be there."""
    (tmp_path / "precommit").mkdir()
    with pytest.raises(PrecommitTemplateMissingError) as excinfo:
        precommit_template_dir(templates_root=tmp_path)
    assert excinfo.value.path == tmp_path / "precommit" / "config.yaml.j2"


def test_resource_subdir_has_no_engine_precommit() -> None:
    """The template is engine wiring, not content: it left ``resources/`` by design."""
    assert _resource_subdir("coding_agent_playbook", "precommit") is None


def _hooks(parsed: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {hook["id"]: hook for entry in parsed["repos"] for hook in entry["hooks"]}


@pytest.mark.parametrize("output_commit", [False, True])
def test_rendered_starter_is_air_gapped_yaml(output_commit: bool) -> None:
    rendered = _render_fresh_pre_commit(output_commit=output_commit)
    assert "https://" not in rendered  # nothing to clone

    parsed = yaml.safe_load(rendered)
    assert isinstance(parsed, dict)
    repos = parsed["repos"]
    assert isinstance(repos, list) and repos

    for entry in repos:
        assert entry["repo"] == "local"
        for hook in entry["hooks"]:
            assert hook["language"] == "system"

    assert {"coding-agent-playbook-metrics", "ruff", "ruff-format", "mypy"} <= set(_hooks(parsed))


def test_default_starter_auto_syncs_and_guards_local_output():
    """[output] commit = false (the default): gitignored output is re-rendered
    after checkout/merge and a pre-commit guard refuses staged output."""
    parsed = yaml.safe_load(_render_fresh_pre_commit())
    hooks = _hooks(parsed)
    assert parsed["default_install_hook_types"] == ["pre-commit", "post-checkout", "post-merge"]
    # Every other hook (mypy is always_run) must stay off post-checkout/merge.
    assert parsed["default_stages"] == ["pre-commit"]
    assert parsed["minimum_pre_commit_version"] == "3.2.0"
    autosync = hooks["coding-agent-playbook-autosync"]
    assert autosync["entry"] == "playbook sync"
    assert autosync["stages"] == ["post-checkout", "post-merge"]
    assert autosync["always_run"] is True
    guard = hooks["coding-agent-playbook-no-generated-output"]
    assert guard["entry"] == "playbook sync --check-staged"
    assert guard["stages"] == ["pre-commit"]
    assert "coding-agent-playbook-sync" not in hooks


def test_commit_true_starter_keeps_the_legacy_drift_check():
    parsed = yaml.safe_load(_render_fresh_pre_commit(output_commit=True))
    hooks = _hooks(parsed)
    assert hooks["coding-agent-playbook-sync"]["entry"] == "playbook sync --check"
    assert "coding-agent-playbook-autosync" not in hooks
    assert "coding-agent-playbook-no-generated-output" not in hooks
    assert "default_install_hook_types" not in parsed
    assert "default_stages" not in parsed
