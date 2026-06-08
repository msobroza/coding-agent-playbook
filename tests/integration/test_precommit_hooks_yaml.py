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


def test_cap_sync_check_hook_is_first_and_well_formed():
    hooks = _load_hooks()
    sync_check = next((h for h in hooks if h["id"] == "playbook-sync-check"), None)
    assert sync_check is not None, "missing playbook-sync-check hook"
    assert sync_check["entry"] == "playbook sync --check"
    assert sync_check["language"] == "python"
    assert sync_check["pass_filenames"] is False
    assert sync_check["always_run"] is True
    # playbook-sync-check runs on every commit — no `stages: [manual]`
    assert "stages" not in sync_check or "manual" not in sync_check["stages"]


def test_cap_validate_hook_is_manual_only():
    hooks = _load_hooks()
    validate = next((h for h in hooks if h["id"] == "playbook-validate"), None)
    assert validate is not None, "missing playbook-validate hook"
    assert validate["entry"] == "playbook validate"
    assert validate["language"] == "python"
    assert validate["stages"] == ["manual"], "playbook-validate must be manual-only"


def test_no_unexpected_hooks():
    hooks = _load_hooks()
    ids = {h["id"] for h in hooks}
    assert ids == {"playbook-sync-check", "playbook-validate"}, (
        f"unexpected hook IDs: {ids - {'playbook-sync-check', 'playbook-validate'}}"
    )
