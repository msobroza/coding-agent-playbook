"""The policy rows an off-workstation twin enforces, whatever ``[hooks]`` says (specs/prK-hook-pack.md §E.4).

A twin (``check-commit-trailers`` in commit-msg and CI, ``check-deps`` in CI)
must apply a hook's data
rows even in a repository that keeps ``[hooks]`` off, or where the hook is
disabled for the agent: humans and CI commit too. So it reads the hook's merged
handler config straight from the same layers sync merges (the engine
``HOOK.md``, overlays and repo-local definitions, then ``[guardrails]`` and
``[hooks.<hook-id>]``), skipping only the §B.1 on-formula.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.security.commit_trailers import GitPolicy

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "CONFIG_FILE",
    "DEPENDENCY_HOOK",
    "GIT_POLICY_HOOK",
    "commit_trailer_policy",
    "dependency_policy_configured",
    "dependency_twin_config",
    "twin_hook_config",
]

CONFIG_FILE: Final = ".coding-agent-playbook.toml"
#: The hook whose trailer rows ``check-commit-trailers`` runs.
GIT_POLICY_HOOK: Final = "git-commit-push-policy-guard"
#: The hook whose allowlist and index rules ``check-deps`` applies.
DEPENDENCY_HOOK: Final = "dependency-allowlist-guard"


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
    from coding_agent_playbook.orchestrator import SyncContext

    ctx = SyncContext.from_repo(repo_root)
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
