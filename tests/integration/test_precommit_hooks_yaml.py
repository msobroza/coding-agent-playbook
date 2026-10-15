"""Sanity tests for the engine's .pre-commit-hooks.yaml (SPEC §13.1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

HOOKS_PATH = Path(__file__).resolve().parents[2] / ".pre-commit-hooks.yaml"


def _load_hooks() -> list[dict[str, Any]]:
    with HOOKS_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, list), ".pre-commit-hooks.yaml must be a YAML list of hooks"
    return data


def test_hooks_file_exists():
    assert HOOKS_PATH.is_file(), f"{HOOKS_PATH} not present"


# Valid ``stages`` values, verified against pre-commit 4.7.0's
# ``pre_commit.clientlib.STAGES`` (hook-type names since pre-commit 3.2.0; the
# legacy ``commit``/``push``/``merge-commit`` aliases are deprecated).
_VALID_STAGES = {
    "commit-msg",
    "post-checkout",
    "post-commit",
    "post-merge",
    "post-rewrite",
    "pre-commit",
    "pre-merge-commit",
    "pre-push",
    "pre-rebase",
    "prepare-commit-msg",
    "manual",
}


def _hook(hook_id: str) -> dict[str, Any]:
    hook = next((h for h in _load_hooks() if h["id"] == hook_id), None)
    assert hook is not None, f"missing {hook_id} hook"
    return hook


def test_every_hook_uses_valid_stage_names():
    for hook in _load_hooks():
        assert set(hook.get("stages", [])) <= _VALID_STAGES, hook["id"]


def test_autosync_hook_runs_after_checkout_and_merge():
    """[output] commit = false: output is gitignored, so re-render it locally
    after every checkout/merge. Those hook types pass no files -> always_run."""
    hook = _hook("playbook-sync")
    assert hook["entry"] == "playbook sync"
    assert hook["language"] == "python"
    assert hook["stages"] == ["post-checkout", "post-merge"]
    assert hook["always_run"] is True
    assert hook["pass_filenames"] is False
    assert hook["minimum_pre_commit_version"] == "3.2.0"


def test_no_generated_output_hook_guards_commits():
    hook = _hook("playbook-no-generated-output")
    assert hook["entry"] == "playbook sync --check-staged"
    assert hook["language"] == "python"
    assert hook["stages"] == ["pre-commit"]
    assert hook["always_run"] is True
    assert hook["pass_filenames"] is False
    assert hook["minimum_pre_commit_version"] == "3.2.0"


def test_cap_sync_check_hook_is_kept_as_legacy_and_well_formed():
    """``playbook-sync-check`` stays for ``[output] commit = true`` repos."""
    sync_check = _hook("playbook-sync-check")
    assert sync_check["entry"] == "playbook sync --check"
    assert sync_check["language"] == "python"
    assert sync_check["pass_filenames"] is False
    assert sync_check["always_run"] is True
    assert "legacy" in sync_check["name"]
    # playbook-sync-check runs on every commit — no `stages: [manual]`
    assert "stages" not in sync_check or "manual" not in sync_check["stages"]


def test_cap_validate_hook_is_manual_only():
    hooks = _load_hooks()
    validate = next((h for h in hooks if h["id"] == "playbook-validate"), None)
    assert validate is not None, "missing playbook-validate hook"
    assert validate["entry"] == "playbook validate"
    assert validate["language"] == "python"
    assert validate["stages"] == ["manual"], "playbook-validate must be manual-only"


def test_cap_metrics_hook_is_static_only():
    """PR-M Track M3: the default metrics hook runs the *static* gate against
    HEAD and must never opt into execution evaluators (`--run-tests`).

    prK §F.0.3 item 6: ``--no-run-tests`` keeps it static even when the
    consumer's ``[metrics] run_tests = true``.
    """
    hooks = _load_hooks()
    metrics = next((h for h in hooks if h["id"] == "playbook-metrics"), None)
    assert metrics is not None, "missing playbook-metrics hook"
    assert metrics["entry"] == "playbook metrics --baseline git:HEAD --no-run-tests"
    assert metrics["language"] == "python"
    # STATIC ONLY — execution evaluators (cost + side effects) stay out of the
    # default hook.
    assert "--run-tests" not in metrics["entry"].split()
    # Runs on staged Python only (not always_run).
    assert metrics["types_or"] == ["python", "pyi"]
    assert metrics.get("always_run") in (None, False)


def test_no_unexpected_hooks():
    hooks = _load_hooks()
    ids = {h["id"] for h in hooks}
    expected = {
        "playbook-sync",
        "playbook-no-generated-output",
        "playbook-sync-check",
        "playbook-validate",
        "playbook-metrics",
        "playbook-coverage",
        "playbook-notebooks",
        "playbook-scan-sinks",
        "playbook-secrets",
        "playbook-commit-msg",
    }
    assert ids == expected, f"unexpected hook IDs: {ids - expected}"


def test_commit_msg_hook_stage_and_language_system():
    """prK §F.4.3: commitizen from the consumer's environment, at the commit-msg stage."""
    hook = _hook("playbook-commit-msg")
    assert hook["entry"] == "cz check --commit-msg-file"
    assert hook["language"] == "system"
    assert hook["stages"] == ["commit-msg"]
    assert hook.get("pass_filenames", True) is True  # pre-commit appends the message file


def test_header_recipe_names_the_commit_msg_hook_type():
    """The commit-msg twin needs its hook type installed; the recipe says how."""
    assert "--hook-type commit-msg" in _header_comment()


def test_coverage_hook_is_manual_only():
    """prK §F.1.3: it runs the consumer's suite, so never on an ordinary commit (SPEC §21.7)."""
    hook = _hook("playbook-coverage")
    assert hook["entry"] == "playbook metrics --run-tests --select testing --baseline git:HEAD"
    assert hook["language"] == "python"
    assert hook["stages"] == ["manual"]
    assert hook["pass_filenames"] is False
    assert hook["types_or"] == ["python"]
    assert hook["require_serial"] is True


def test_notebooks_hook_types_jupyter_language_python():
    """prK §E.3: the stdlib twin of notebook-output-hygiene, on staged notebooks only."""
    hook = _hook("playbook-notebooks")
    assert hook["entry"] == "playbook check-notebooks"
    assert hook["language"] == "python"
    assert hook["types"] == ["jupyter"]
    assert hook.get("pass_filenames", True) is True  # the staged notebooks are its PATHS
    assert hook.get("always_run") in (None, False)


def test_scan_sinks_hook_scans_the_index_once():
    """prK §E.3: the guard's twin reads the index itself, so it takes no filenames."""
    hook = _hook("playbook-scan-sinks")
    assert hook["entry"] == "playbook scan-sinks --staged"
    assert hook["language"] == "python"
    assert hook["types_or"] == ["python", "jupyter"]
    assert hook["pass_filenames"] is False
    assert hook["stages"] == ["pre-commit"]


def test_secrets_hook_scans_staged():
    """prK §E.4: the stdlib gitleaks stand-in; every commit, reading the index itself."""
    hook = _hook("playbook-secrets")
    assert hook["entry"] == "playbook scan-secrets --staged"
    assert hook["language"] == "python"
    assert hook["pass_filenames"] is False
    assert hook["always_run"] is True
    assert hook["stages"] == ["pre-commit"]


def _header_comment() -> str:
    lines = HOOKS_PATH.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if line.startswith("#"))


def test_header_recipe_installs_all_three_hook_types():
    """Regression: explicit ``--hook-type`` flags replace the default list, so a
    recipe naming only post-checkout/post-merge never installs the guard."""
    install_lines = [
        line for line in _header_comment().splitlines() if "pre-commit install --hook-type" in line
    ]
    assert install_lines
    for line in install_lines:
        assert "--hook-type pre-commit --hook-type post-checkout --hook-type post-merge" in line


def test_header_recipe_confines_other_hooks_and_names_overlay_deps():
    header = _header_comment()
    assert "default_stages: [pre-commit]" in header
    assert "additional_dependencies" in header
    assert "language: system" in header  # the init-written alternative for overlay users
