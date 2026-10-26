"""Shared fixtures of the ``guard_config.json`` loading tests (specs/prK-lifecycle-hooks.md §D.8).

``test_guard_config.py`` and ``test_hook_record_shape.py`` both install a
``guard_config.json`` plus a lockfile whose entry matches it, then load it the way
the runtime does; the builders live here so neither module copies them.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.artifacts.hook_schema import HookMatcher
from coding_agent_playbook.hook_runtime.config.guard_config import (
    ConfigFault,
    GuardConfig,
    load_guard_config,
)
from coding_agent_playbook.hook_runtime.config.schema import GUARD_CONFIG_REL, LOCKFILE_REL
from coding_agent_playbook.hook_runtime.dispatch.event import RepoInfo
from coding_agent_playbook.hook_runtime.state.store import StateStore
from coding_agent_playbook.hooks.resolution.resolved import ResolvedHandler, ResolvedHook
from tests.engine_version import ENGINE_VERSION

if TYPE_CHECKING:
    from collections.abc import Mapping


def resolved_hook() -> ResolvedHook:
    """The one-hook fixture every guard_config test starts from.

    Example: ``resolved_hook().to_json()["id"] == "guard-generated-outputs"``.
    """
    return ResolvedHook(
        id="guard-generated-outputs",
        source_package="coding_agent_playbook",
        events=("pre_tool_use",),
        priority=10,
        matcher={"pre_tool_use": HookMatcher(tools=["edit", "write"], paths=["AGENTS.md", "*.MD"])},
        handlers={
            "pre_tool_use": ResolvedHandler(
                "builtin", name="guard_generated_outputs", config={"a": 1}
            )
        },
        decisions=("deny", "ask"),
        timeout=2.0,
        on_error={"pre_tool_use": "ask"},
        supports=("claude_code", "opencode"),
        mandatory=False,
        script_sha256=None,
    )


def guard_document(**overrides: Any) -> dict[str, Any]:
    """A complete ``guard_config.json`` document; ``overrides`` replace top-level keys.

    Example: ``guard_document(state_ttl_days=0)["state_ttl_days"] == 0``.
    """
    document: dict[str, Any] = {
        "schema_version": 1,
        "engine_version": ENGINE_VERSION,
        "hooks": {"guard-generated-outputs": resolved_hook().to_json()},
        "deadlines_ms": {"pre_tool_use": 2000},
        "unattended_ask": "warn",
        "logging": {"decisions": True, "audit": False, "audit_mode": ""},
        "shell": {"wrapper_prefixes": ["proxy"], "runner_wrappers": ["uv run"]},
        "path_classes": {"py": ["*.py"], "generated": ["AGENTS.md"]},
        "secret_path_globs": [".env*", "*.pem"],
        "allow_code_from": ["acme_rules"],
        "state_ttl_days": 3,
        "protected": {"output_dirs": [".claude/"]},
    }
    document.update(overrides)
    return document


def canonical_bytes(document: Mapping[str, Any]) -> bytes:
    """The writer's canonical JSON encoding of ``document``.

    Example: ``canonical_bytes({"b": 1, "a": 2}) == b'{"a":2,"b":1}\\n'``.
    """
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return (text + "\n").encode("ascii")


def lockfile_text(sha256: str | None, *, extra: str = "") -> str:
    """A lockfile with a ``guard_config.json`` entry of ``sha256`` (none when ``None``).

    Example: ``GUARD_CONFIG_REL not in lockfile_text(None)``.
    """
    entry = (
        f'\n[[entries]]\npath = "{GUARD_CONFIG_REL}"\nsha256 = "{sha256}"\nbytes = 10\n'
        'kind = "runtime"\n'
        if sha256 is not None
        else ""
    )
    return (
        f'schema_version = 2\nengine_version = "{ENGINE_VERSION}"\nrendered_at = "2026-10-14T00:00:00Z"\n'
        f'{extra}\n[[entries]]\npath = "AGENTS.md"\nsha256 = "ab"\nbytes = 2\n{entry}'
    )


def repo_at(tmp_path: Path) -> RepoInfo:
    """A plain (non-linked) git worktree rooted at ``tmp_path``.

    Example: ``repo_at(tmp_path).is_linked_worktree is False``.
    """
    root = Path(os.path.realpath(tmp_path))
    (root / ".git").mkdir(exist_ok=True)
    return RepoInfo(
        worktree_root=str(root),
        git_dir=str(root / ".git"),
        common_dir=str(root / ".git"),
        is_linked_worktree=False,
    )


def install_guard_config(
    repo: RepoInfo, document: Mapping[str, Any] | bytes, *, lock_sha: str | None = None
) -> bytes:
    """Write ``guard_config.json`` and a lockfile whose entry matches it (or ``lock_sha``).

    Example: ``install_guard_config(repo, guard_document())`` returns the bytes written.
    """
    data = document if isinstance(document, bytes) else canonical_bytes(document)
    path = Path(repo.worktree_root) / GUARD_CONFIG_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest() if lock_sha is None else lock_sha
    (Path(repo.worktree_root) / LOCKFILE_REL).write_text(lockfile_text(sha), encoding="utf-8")
    return data


def load_config(repo: RepoInfo, **kwargs: Any) -> GuardConfig | ConfigFault:
    """Load ``repo``'s config through its state store on a linux host by default.

    Example: ``isinstance(load_config(repo, platform="darwin"), GuardConfig)``.
    """
    kwargs.setdefault("platform", "linux")
    kwargs.setdefault("home", "/home/dev")
    return load_guard_config(repo, StateStore.for_repo(repo), **kwargs)
