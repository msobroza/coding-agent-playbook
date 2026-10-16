"""prompt-write-scope-guard's ``scopes``, rendered into its guard_config record at sync (specs/prK-hook-pack.md §E.3).

``gc:prompt-write-scope-guard.scopes`` maps each rendered prompt's slash to
its ``write_scope`` (``{read_only: true}`` or ``{globs: [...]}``). It is
derived from ``PromptFrontmatter`` only, never from ``[hooks.<id>]``, so the
prompt text and the enforcing guard share one source; the guard declares no
``scopes`` config key, so a consumer cannot widen it. Machine-independent.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.active_prompt import SCOPE_GUARD_ID

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from coding_agent_playbook.types import Prompt

__all__ = ["SCOPE_GUARD_ID", "prompt_scopes", "with_prompt_scopes"]

#: The guard's one handler event, whose config carries ``scopes``.
_SCOPE_EVENT: Final = "pre_tool_use"


def prompt_scopes(prompts: Iterable[Prompt]) -> dict[str, dict[str, Any]]:
    """``slash -> write_scope`` for every prompt that declares a scope, sorted by slash.

    Example::

        >>> prompt_scopes([])
        {}
    """
    scopes = {
        prompt.frontmatter.slash: copy.deepcopy(prompt.frontmatter.write_scope)
        for prompt in prompts
        if prompt.frontmatter.write_scope
    }
    return dict(sorted(scopes.items()))


def with_prompt_scopes(record: Mapping[str, Any], scopes: Mapping[str, Any]) -> dict[str, Any]:
    """``record`` (a ``ResolvedHook.to_json()``) with ``scopes`` in its pre_tool_use config.

    Any other hook's record comes back unchanged (a copy).

    Example::

        >>> with_prompt_scopes({"id": "x", "handlers": {}}, {"review": {"read_only": True}})
        {'id': 'x', 'handlers': {}}
    """
    updated = copy.deepcopy(dict(record))
    handler = updated.get("handlers", {}).get(_SCOPE_EVENT)
    if updated.get("id") == SCOPE_GUARD_ID and isinstance(handler, dict):
        handler["config"] = {**handler.get("config", {}), "scopes": copy.deepcopy(dict(scopes))}
    return updated
