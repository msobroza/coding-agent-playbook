"""``HookFrontmatter`` lives in the ``_hook_frontmatter`` leaf; ``types`` re-exports it.

specs/prS-skills-context.md §6.4.1: the move is a pure refactor, so every importer
keeps ``from coding_agent_playbook.types import HookFrontmatter``. The leaf must
not import ``types`` back (``types`` imports it), or the pair would be an import
cycle. The class's own behaviour stays covered, unmodified, by test_types_hook.py
and test_types_hook_roundtrip.py.
"""

from __future__ import annotations

import dataclasses
import sys
import typing

from coding_agent_playbook import _hook_frontmatter, types
from coding_agent_playbook.types import HookEvent, HookFrontmatter, HookTier
from tests.import_probe import new_modules_after


def test_types_reexports_the_one_hook_frontmatter_class() -> None:
    # One class, not a copy: a copy would make isinstance() checks disagree.
    assert types.HookFrontmatter is _hook_frontmatter.HookFrontmatter


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
    loaded = new_modules_after("import coding_agent_playbook._hook_frontmatter")

    # Not types (that would be a cycle) and not yaml (types.py is what pays for it).
    non_stdlib = [name for name in loaded if name.split(".")[0] not in sys.stdlib_module_names]
    assert non_stdlib == [
        "coding_agent_playbook._hook_frontmatter",
        "coding_agent_playbook._hook_schema",
    ]
