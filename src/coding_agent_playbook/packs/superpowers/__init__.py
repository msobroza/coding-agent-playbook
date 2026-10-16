"""The ``superpowers`` pack: a vendored, self-contained port of the Superpowers
skills library (MIT, Copyright (c) 2025 Jesse Vincent — see ``LICENSE`` and
``ATTRIBUTIONS.md`` in ``content/plugins/superpowers/``).

Its content lives in ``content/plugins/superpowers/``, not in this package: the
pack ships only ``skills/`` there — one Agent Skills directory per
skill (``SKILL.md`` + optional ``scripts/`` and ``references/``). It has no
runtime dependency on the upstream plugin: cross-references between skills use
plain skill names, every supporting file lives inside its skill directory, and
no body links outside the pack (SPEC §11.5).

Enable it in a consumer repo, then run ``playbook sync``::

    overlays_enabled = ["coding_agent_playbook.packs.superpowers"]
"""

from __future__ import annotations

#: Dotted package name to list in ``overlays_enabled`` to turn the pack on.
PACK_NAME = __name__

__all__ = ["PACK_NAME"]
