"""The ``python_design`` pack: two self-contained Agent Skills for designing and
reviewing Python code, written for this engine (see ``ATTRIBUTIONS.md`` in
``content/plugins/python_design/`` for the ideas they distill).

Its content lives in ``content/plugins/python_design/``, not in this package: the
pack ships only ``skills/`` there:

* ``python-design-review`` reviews Python code for design smells, principle
  violations and over- or under-applied patterns. Its ``SKILL.md`` carries the
  decision tables inline; ``references/`` holds the long-form smell catalog,
  checklist, principles, patterns and lint guardrails; ``scripts/`` holds two
  stdlib AST scanners (``detect_smells.py``, ``lcom4_clusters.py``) that print
  candidates as JSON.
* ``python-architecture`` structures a Python application into layers with a
  composition root, dependency injection, testable seams and a persistence
  strategy. Its ``SKILL.md`` carries the layer model and the persistence decision
  flow inline; ``references/`` holds the long form and a worked example;
  ``scripts/layer_map.py`` maps a source tree to layers and reports forbidden
  imports and import cycles.

Each ``SKILL.md`` stands alone (Continue keeps only its body; ``AGENTS.md`` drops
skills), names its own supporting files in plain text, links nowhere, and
depends on no other skill or plugin (SPEC §11.5.2). The scripts are stdlib-only
and run on Python 3.10+.

Enable it in a consumer repo, then run ``playbook sync``::

    overlays_enabled = ["coding_agent_playbook.packs.python_design"]
"""

from __future__ import annotations

#: Dotted package name to list in ``overlays_enabled`` to turn the pack on.
PACK_NAME = __name__

__all__ = ["PACK_NAME"]
