"""The packaged air-gapped pre-commit starter renders to valid, all-local YAML.

Guards two things: the ``resources/precommit/config.yaml.j2`` template is
actually shipped (resolvable via ``importlib.resources``), and it renders
through the Jinja environment without a ``StrictUndefined`` error to a config
whose every hook is ``repo: local`` + ``language: system`` (so pre-commit never
clones a remote hook repo).
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from coding_agent_playbook.commands.init import _render_fresh_pre_commit
from coding_agent_playbook.sources.filesystem import _resource_subdir


def test_precommit_template_is_packaged():
    precommit_dir = _resource_subdir("coding_agent_playbook", "precommit")
    assert precommit_dir is not None
    assert (precommit_dir / "config.yaml.j2").is_file()


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


@pytest.mark.parametrize("output_commit", [False, True])
def test_starter_metrics_hook_passes_no_run_tests(output_commit: bool) -> None:
    """prK §F.0.3 item 6: static only, even when ``[metrics] run_tests = true``."""
    hooks = _hooks(yaml.safe_load(_render_fresh_pre_commit(output_commit=output_commit)))
    metrics = hooks["coding-agent-playbook-metrics"]
    assert metrics["entry"] == "playbook metrics --baseline git:HEAD --no-run-tests"
    assert metrics["language"] == "system"


@pytest.mark.parametrize("output_commit", [False, True])
def test_starter_coverage_hook_is_manual_system(output_commit: bool) -> None:
    """prK §F.1.3: the air-gapped twin of ``playbook-coverage``; it runs the suite, so manual."""
    hooks = _hooks(yaml.safe_load(_render_fresh_pre_commit(output_commit=output_commit)))
    coverage = hooks["coding-agent-playbook-coverage"]
    assert coverage["entry"] == "playbook metrics --run-tests --select testing --baseline git:HEAD"
    assert coverage["language"] == "system"
    assert coverage["stages"] == ["manual"]
    assert coverage["pass_filenames"] is False
    assert coverage["require_serial"] is True


@pytest.mark.parametrize("output_commit", [False, True])
def test_starter_runs_secret_scan(output_commit: bool) -> None:
    """prK §E.4: SPEC §13.2 excludes gitleaks (it clones), so the starter scans with the engine."""
    hooks = _hooks(yaml.safe_load(_render_fresh_pre_commit(output_commit=output_commit)))
    secrets = hooks["coding-agent-playbook-secrets"]
    assert secrets["entry"] == "playbook scan-secrets --staged"
    assert secrets["language"] == "system"
    assert secrets["pass_filenames"] is False
    assert secrets["always_run"] is True
    assert secrets["stages"] == ["pre-commit"]


@pytest.mark.parametrize(
    ("output_commit", "install_types"),
    [
        (False, ["pre-commit", "post-checkout", "post-merge", "commit-msg"]),
        (True, ["pre-commit", "commit-msg"]),
    ],
)
def test_commit_trailers_entry_only_when_rows_configured(
    output_commit: bool, install_types: list[str]
) -> None:
    """prK §E.4: the commit-msg twin and its stage are rendered only with a trailer row."""
    without = yaml.safe_load(_render_fresh_pre_commit(output_commit=output_commit))
    rendered = _render_fresh_pre_commit(output_commit=output_commit, commit_trailers=True)
    parsed = yaml.safe_load(rendered)

    assert "coding-agent-playbook-commit-trailers" not in _hooks(without)
    entry = _hooks(parsed)["coding-agent-playbook-commit-trailers"]
    assert (entry["entry"], entry["language"], entry["stages"]) == (
        "playbook check-commit-trailers",
        "system",
        ["commit-msg"],
    )
    assert parsed["default_install_hook_types"] == install_types
    # Hooks without their own stages must not run again at commit-msg.
    assert parsed["default_stages"] == ["pre-commit"]
    assert "https://" not in rendered
