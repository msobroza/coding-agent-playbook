"""Private forward-reference shims for the public ABCs.

The ``Adapter``, ``ArtifactSource`` and ``StateSource`` ABCs (PR 1) reference
canonical types that do not exist yet: ``Rule`` / ``Prompt`` / ``Skill`` land
in PR 2, ``Config`` / ``Lockfile`` in PR 5, ``EvalTask`` in PR 11. Until then
each name aliases to ``Any`` so the ABC signatures type-check. Every later PR
replaces the matching alias with a re-export of the real type; the ABC modules
themselves never change.

Private to the engine — do not import outside the ABC modules.
"""

from __future__ import annotations

from typing import Any

Rule = Any
Prompt = Any
Skill = Any
Config = Any
Lockfile = Any
EvalTask = Any

__all__ = ["Config", "EvalTask", "Lockfile", "Prompt", "Rule", "Skill"]
