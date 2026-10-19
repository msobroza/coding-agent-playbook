"""The Agent Skills naming rules live in ``skills.naming``, a leaf any layer may import.

A3 (specs/prT-package-layout.md 4.12) moved them out of ``adapters/`` so the skills
modules no longer import an adapters private module, and removed the
``_skill_writer`` re-exports (L2): callers import the rules from here. Their
behaviour stays covered, unmodified, by tests/adapters/test_skill_writer.py.
"""

from __future__ import annotations

import sys

from coding_agent_playbook.skills import naming
from tests.import_probe import new_modules_after


def test_naming_module_has_a_docstring() -> None:
    assert (naming.__doc__ or "").strip()


def test_naming_leaf_loads_no_other_playbook_module() -> None:
    loaded = new_modules_after("import coding_agent_playbook.skills.naming")

    # Only the docstring-only skills package beside the module itself: no types, no
    # _skill_writer (it imports this module, so that would be a cycle), no yaml.
    non_stdlib = [name for name in loaded if name.split(".")[0] not in sys.stdlib_module_names]
    assert non_stdlib == [
        "coding_agent_playbook.skills",
        "coding_agent_playbook.skills.naming",
    ]
