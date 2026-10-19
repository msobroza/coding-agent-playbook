"""Shared builders for the ``compile_guard_config`` tests (specs/prT-package-layout.md 9 AC.2.6).

A request needs a ``repo_root`` the writer reads its repo inputs from; the ``repo``
fixture (``conftest.py``) is an empty one, so each input keeps its reader's default
unless a test writes the file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter
from coding_agent_playbook.config.tables.hooks import GuardrailsConfig, HooksConfig
from coding_agent_playbook.hooks.guard_config.compile import (
    GuardConfigRequest,
    compile_guard_config,
)
from coding_agent_playbook.hooks.guard_config.inputs import ProtectInputs
from tests.hook_samples import resolved_from_disk, resolved_hook

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook

__all__ = ["PROTECT", "compiled_document", "handler_config", "prompt", "request_for", "two_hooks"]

#: The ``protected`` inputs of a sync with two adapters and one overlay.
PROTECT = ProtectInputs(
    entries=(),
    output_dirs=(".claude/commands/", "AGENTS.md"),
    packages=("coding_agent_playbook", "coding_agent_playbook.plugins.superpowers"),
)


def request_for(
    repo: Path, hooks: Sequence[ResolvedHook] = (), protect: ProtectInputs = PROTECT
) -> GuardConfigRequest:
    """A request for ``hooks`` with ``[hooks]`` on and two adapters' outputs generated.

    Example: ``dataclasses.replace(request_for(repo, hooks), prompts=prompts)``.
    """
    return GuardConfigRequest(
        repo_root=repo,
        hooks=hooks,
        hooks_config=HooksConfig(enabled=True),
        guardrails=GuardrailsConfig(),
        engine_version="0.2.0",
        generated=(".claude/commands/", "AGENTS.md"),
        protected=protect,
    )


def compiled_document(request: GuardConfigRequest) -> dict[str, Any]:
    """The compiled document of ``request``, typed for indexing.

    Example: ``compiled_document(request_for(repo))["ruff"]["default_select"] is True``.
    """
    return dict(compile_guard_config(request).document)


def handler_config(document: Mapping[str, Any], hook_id: str) -> dict[str, Any]:
    """The compiled config of ``hook_id``'s first handler.

    Example: ``handler_config(document, "skill-nudge")["skills"]``.
    """
    handlers = document["hooks"][hook_id]["handlers"]
    return dict(next(iter(handlers.values()))["config"])


def two_hooks(tmp_path: Path) -> list[ResolvedHook]:
    """An external hook built from disk under ``tmp_path`` and a builtin Stop hook.

    Example: ``[hook.id for hook in two_hooks(tmp_path)] == ["guard-ext", "guard-y"]``.
    """
    return [
        resolved_from_disk(tmp_path / "src", "guard-ext"),
        resolved_hook("guard-y", events=("stop",), timeout=1.5),
    ]


def prompt(prompt_id: str, applies_if: dict[str, Any] | None = None) -> Prompt:
    """A repo-local prompt whose slash is its id.

    Example: ``prompt("explain").frontmatter.slash == "explain"``.
    """
    frontmatter = PromptFrontmatter(
        id=prompt_id, name=prompt_id, description="d", slash=prompt_id, applies_if=applies_if or {}
    )
    return Prompt(frontmatter, "Body.\n", "Body.\n", False, None, "<repo-local>")
