"""``HookFrontmatter`` lives in the ``artifacts.hook_frontmatter`` leaf.

specs/prS-skills-context.md §6.4.1 split it out of ``types``; specs/prT-package-layout.md
A1 moved it to ``artifacts/`` and removed the ``types`` re-export, so importers name
the defining module. The leaf must not import ``types`` back (``types`` imports it),
or the pair would be an import cycle. The class's own behaviour stays covered,
unmodified, by test_types_hook.py and test_types_hook_roundtrip.py.
"""

from __future__ import annotations

import dataclasses
import sys
import typing

from coding_agent_playbook.artifacts import hook_frontmatter as _hook_frontmatter
from coding_agent_playbook.artifacts.hook_frontmatter import HookFrontmatter
from coding_agent_playbook.artifacts.hook_schema import HookEvent, HookTier
from tests.import_probe import new_modules_after


def test_hook_frontmatter_module_has_a_docstring() -> None:
    assert (_hook_frontmatter.__doc__ or "").strip()


def test_hook_frontmatter_annotations_still_resolve_at_run_time() -> None:
    # Regression: get_type_hints() evaluates the field annotations in the namespace
    # of the module that defines the class. It resolved all 19 when the class lived
    # in types.py (the Literal aliases are imported there); the move must keep that.
    hints = typing.get_type_hints(HookFrontmatter)

    assert hints["tier"] == HookTier
    assert hints["events"] == list[HookEvent]
    assert set(hints) == {field.name for field in dataclasses.fields(HookFrontmatter)}


def test_hook_frontmatter_leaf_loads_nothing_but_the_hook_schema() -> None:
    loaded = new_modules_after("import coding_agent_playbook.artifacts.hook_frontmatter")

    # Not artifacts.hook (a cycle) and not yaml (artifacts/frontmatter.py pays for it).
    non_stdlib = [name for name in loaded if name.split(".")[0] not in sys.stdlib_module_names]
    assert non_stdlib == [
        "coding_agent_playbook.artifacts",
        "coding_agent_playbook.artifacts.hook_frontmatter",
        "coding_agent_playbook.artifacts.hook_schema",
    ]
