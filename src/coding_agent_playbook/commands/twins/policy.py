"""The policy a guard twin enforces, and what decides whether a ``playbook ci`` row runs.

The twin rows (specs/prK-hook-pack.md §E.4): a twin (``check-commit-trailers``
in commit-msg and CI, ``check-deps`` in CI) must apply a hook's data
rows even in a repository that keeps ``[hooks]`` off, or where the hook is
disabled for the agent: humans and CI commit too. So it reads the hook's merged
handler config straight from the same layers sync merges (the engine
``HOOK.md``, overlays and repo-local definitions, then ``[guardrails]`` and
``[hooks.<hook-id>]``), skipping only the §B.1 on-formula.

The ``playbook ci`` rows (specs/prK-hook-pack.md §F.5): each reader answers one
row's "is it configured?" question from the committed
files. Every one fails **closed**: a policy that does not load counts as set,
so the row runs and its child (or the step itself) reports the broken config,
instead of CI silently skipping a check.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.security.commit_trailers import GitPolicy

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "CONFIG_FILE",
    "DEPENDENCY_HOOK",
    "GIT_POLICY_HOOK",
    "commit_convention_configured",
    "commit_trailer_policy",
    "cutover_date_value",
    "dependency_policy_configured",
    "dependency_policy_set",
    "dependency_twin_config",
    "metrics_run_tests",
    "output_committed",
    "trailer_rows_configured",
    "twin_hook_config",
]

CONFIG_FILE: Final = ".coding-agent-playbook.toml"
#: The hook whose trailer rows ``check-commit-trailers`` runs.
GIT_POLICY_HOOK: Final = "git-commit-push-policy-guard"
#: The hook whose allowlist and index rules ``check-deps`` applies.
DEPENDENCY_HOOK: Final = "dependency-allowlist-guard"
_PYPROJECT: Final = "pyproject.toml"
_LOAD_ERRORS: Final = (ValueError, OSError, KeyError, TypeError)


def twin_hook_config(
    repo_root: Path, hook_id: str, event: str = "pre_tool_use"
) -> dict[str, Any] | None:
    """``hook_id``'s merged handler config for ``event``; ``None`` when no layer defines it.

    Raises what loading the config raises (``ValueError``, ``FileNotFoundError``,
    ``HookSchemaError``): a twin must not pass silently on a config it cannot read.

    Example::

        >>> twin_hook_config(Path("."), "git-commit-push-policy-guard")  # doctest: +SKIP
        {'forbid_trailers': ['Co-Authored-By'], 'allowed_coauthors': [], ...}
    """
    from coding_agent_playbook.hook_policy import RegistryCatalog, merged_handler_config
    from coding_agent_playbook.hook_policy.override_rules import bound_handler
    from coding_agent_playbook.validation.context import SyncContext

    # An internal policy read: the command that owns the config (sync, init's final
    # sync) prints the deprecated-overlay warning once (SPEC v0.19), not this helper.
    ctx = SyncContext.from_repo(repo_root, warn_deprecated=False)
    hook = next((h for h in ctx.hooks_resolved if h.frontmatter.id == hook_id), None)
    handler = None if hook is None else bound_handler(hook.frontmatter, event)
    if hook is None or handler is None:
        return None
    tables = ctx.policy_tables
    return merged_handler_config(
        hook,
        handler,
        tables.hooks_config(),
        tables.guardrails_config(),
        schemas=RegistryCatalog(),
    )


def commit_trailer_policy(repo_root: Path) -> GitPolicy:
    """The trailer rows of git-commit-push-policy-guard; empty in a repo without a config.

    Example::

        >>> commit_trailer_policy(Path(".")).has_rows  # doctest: +SKIP
        False
    """
    if not (repo_root / CONFIG_FILE).is_file():
        return GitPolicy()
    return GitPolicy.from_config(twin_hook_config(repo_root, GIT_POLICY_HOOK) or {})


def dependency_twin_config(repo_root: Path) -> dict[str, Any]:
    """dependency-allowlist-guard's merged config; ``{}`` (the defaults) without a config file.

    Example::

        >>> dependency_twin_config(Path("."))  # doctest: +SKIP
        {'index_mode': 'ask', 'allowlist': [], 'required_index': ''}
    """
    if not (repo_root / CONFIG_FILE).is_file():
        return {}
    return twin_hook_config(repo_root, DEPENDENCY_HOOK) or {}


def dependency_policy_configured(repo_root: Path) -> bool:
    """Whether a dependency policy is set: an allowlist, a required index or ``index_mode = deny``.

    Example::

        >>> dependency_policy_configured(Path("."))  # doctest: +SKIP
        False
    """
    config = dependency_twin_config(repo_root)
    modes = (config.get("index_mode"), config.get("mode"))
    return bool(config.get("allowlist") or config.get("required_index") or "deny" in modes)


def output_committed(repo_root: Path) -> bool | None:
    """``[output] commit`` of the merged config; ``None`` without one, ``True`` when unloadable.

    Example: ``output_committed(Path("/no/such/repo")) is None``.
    """
    if not (repo_root / CONFIG_FILE).is_file():
        return None
    from coding_agent_playbook.config.files import FileSystemStateSource

    try:
        return FileSystemStateSource(repo_root=repo_root).load_config().commit_output
    except _LOAD_ERRORS:
        return True  # sync --check then reports the broken config itself


def trailer_rows_configured(repo_root: Path) -> bool:
    """Whether a commit-trailer row is configured; ``True`` when the policy does not load.

    Example: ``trailer_rows_configured(repo_root)`` after ``forbid_trailers = ["X"]``.
    """
    try:
        return commit_trailer_policy(repo_root).has_rows
    except _LOAD_ERRORS:
        return True  # check-commit-trailers then reports the broken config itself


def dependency_policy_set(repo_root: Path) -> bool:
    """Whether a dependency policy is set; ``True`` when it does not load.

    Example: ``dependency_policy_set(repo_root)`` after an ``allowlist`` row.
    """
    try:
        return dependency_policy_configured(repo_root)
    except _LOAD_ERRORS:
        return True  # check-deps then reports the broken config itself


def metrics_run_tests(repo_root: Path) -> bool:
    """``[metrics] run_tests``; ``True`` when the config does not load.

    Example: ``metrics_run_tests(repo_root)`` after ``[metrics] run_tests = true``.
    """
    from coding_agent_playbook.metrics_gate.run import (
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
