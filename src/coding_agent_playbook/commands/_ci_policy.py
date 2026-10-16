"""What decides whether a ``playbook ci`` row runs (specs/prK-hook-pack.md §F.5).

Each reader answers one row's "is it configured?" question from the committed
files. Every one fails **closed**: a policy that does not load counts as set,
so the row runs and its child (or the step itself) reports the broken config,
instead of CI silently skipping a check.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "CONFIG_FILE",
    "commit_convention_configured",
    "cutover_date_value",
    "dependency_policy_set",
    "metrics_run_tests",
    "output_committed",
    "trailer_rows_configured",
]

CONFIG_FILE: Final = ".coding-agent-playbook.toml"
_PYPROJECT: Final = "pyproject.toml"
_LOAD_ERRORS: Final = (ValueError, OSError, KeyError, TypeError)


def output_committed(repo_root: Path) -> bool | None:
    """``[output] commit`` of the merged config; ``None`` without one, ``True`` when unloadable.

    Example: ``output_committed(Path("/no/such/repo")) is None``.
    """
    if not (repo_root / CONFIG_FILE).is_file():
        return None
    from coding_agent_playbook.sources.filesystem import FileSystemStateSource

    try:
        return FileSystemStateSource(repo_root=repo_root).load_config().commit_output
    except _LOAD_ERRORS:
        return True  # sync --check then reports the broken config itself


def trailer_rows_configured(repo_root: Path) -> bool:
    """Whether a commit-trailer row is configured; ``True`` when the policy does not load.

    Example: ``trailer_rows_configured(repo_root)`` after ``forbid_trailers = ["X"]``.
    """
    from coding_agent_playbook.commands._twin_policy import commit_trailer_policy

    try:
        return commit_trailer_policy(repo_root).has_rows
    except _LOAD_ERRORS:
        return True  # check-commit-trailers then reports the broken config itself


def dependency_policy_set(repo_root: Path) -> bool:
    """Whether a dependency policy is set; ``True`` when it does not load.

    Example: ``dependency_policy_set(repo_root)`` after an ``allowlist`` row.
    """
    from coding_agent_playbook.commands._twin_policy import dependency_policy_configured

    try:
        return dependency_policy_configured(repo_root)
    except _LOAD_ERRORS:
        return True  # check-deps then reports the broken config itself


def metrics_run_tests(repo_root: Path) -> bool:
    """``[metrics] run_tests``; ``True`` when the config does not load.

    Example: ``metrics_run_tests(repo_root)`` after ``[metrics] run_tests = true``.
    """
    from coding_agent_playbook.evaluators.metrics_gate import (
        MetricsGateUsageError,
        load_metrics_config,
    )

    try:
        return load_metrics_config(repo_root).run_tests
    except (MetricsGateUsageError, OSError):
        return True  # the metrics child then reports the broken config itself


def commit_convention_configured(repo_root: Path) -> bool:
    """``[tool.commitizen]`` in ``pyproject.toml`` or ``[hooks.commit_convention]`` is set (§F.5).

    ``True`` when either file does not parse.

    Example: ``commit_convention_configured(Path("/no/such/repo")) is False``.
    """
    try:
        pyproject = _toml(repo_root / _PYPROJECT)
        config = _toml(repo_root / CONFIG_FILE)
    except (OSError, ValueError):
        return True  # the step then reports the unreadable file itself
    commitizen = _table(_table(pyproject, "tool"), "commitizen")
    convention = _table(config, "hooks").get("commit_convention")
    return bool(commitizen) or isinstance(convention, dict)


def cutover_date_value(repo_root: Path) -> object:
    """The raw ``[hooks.commit_convention] cutover_date`` (``None`` when unset).

    Raises ``ValueError`` naming the file when it does not parse or the table is
    not a table.

    Example: ``cutover_date_value(repo_root) == "2026-10-15"``.
    """
    try:
        config = _toml(repo_root / CONFIG_FILE)
    except OSError as exc:
        raise ValueError(f"cannot read {CONFIG_FILE}: {exc}") from exc
    convention = _table(config, "hooks").get("commit_convention", {})
    if not isinstance(convention, dict):
        raise ValueError(
            f"[hooks.commit_convention] in {CONFIG_FILE} must be a table, got {convention!r}"
        )
    return convention.get("cutover_date")


def _toml(path: Path) -> dict[str, Any]:
    """``path`` parsed (``{}`` when absent); ``ValueError`` naming it when it does not parse."""
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"malformed {path.name}: {exc}") from exc


def _table(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    return value if isinstance(value, dict) else {}
