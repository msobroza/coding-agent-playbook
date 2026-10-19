"""The writer's hook record and the runtime's schema share one shape (GC-4, #140).

``ResolvedHook.to_json()`` writes each ``hooks.<id>`` record of
``guard_config.json``; ``HOOK_RECORD_KEYS`` is the key set the runtime reads.
Pinning one against the other, for every handler kind, keeps the two sides from
drifting apart silently.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig
from coding_agent_playbook.hook_runtime.config.schema import HOOK_RECORD_KEYS
from coding_agent_playbook.hooks.resolution.resolved import ResolvedHandler
from tests.hook_runtime.config.guard_config_kit import (
    guard_document,
    install_guard_config,
    load_config,
    repo_at,
    resolved_hook,
)

if TYPE_CHECKING:
    from pathlib import Path

_HANDLER_OF_EACH_KIND = {
    "builtin": ResolvedHandler("builtin", name="guard_generated_outputs"),
    "entry_point": ResolvedHandler("entry_point", target="acme.rules:check", dist="acme==1.0"),
    "external": ResolvedHandler("external", argv=("python", "scripts/check.py")),
}


@pytest.mark.parametrize("kind", sorted(_HANDLER_OF_EACH_KIND))
def test_resolved_hook_json_has_exactly_the_record_keys(tmp_path: Path, kind: str) -> None:
    """The writer's record and the runtime's schema name the same twelve keys (GC-4)."""
    handlers = {"pre_tool_use": _HANDLER_OF_EACH_KIND[kind]}
    resolved = dataclasses.replace(resolved_hook(), handlers=handlers)

    record = resolved.to_json()

    assert set(record) == HOOK_RECORD_KEYS
    assert record["handlers"]["pre_tool_use"]["kind"] == kind
    repo = repo_at(tmp_path)
    install_guard_config(repo, guard_document(hooks={resolved.id: record}))
    assert isinstance(load_config(repo), GuardConfig)
