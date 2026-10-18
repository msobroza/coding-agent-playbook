"""The Agent Skills naming rules live in ``_agent_skill_rules``; ``_skill_writer`` re-exports them.

specs/prS-skills-context.md §6.4.5 item 1: the move is a pure refactor, so
``commands/validate.py`` and test_skill_writer.py keep importing the rules from
``_skill_writer``. The rules' behaviour stays covered, unmodified, by
test_skill_writer.py, which reaches the moved code through that re-export.
"""

from __future__ import annotations

import sys

import pytest

from coding_agent_playbook.adapters import _agent_skill_rules, _skill_writer
from tests.import_probe import new_modules_after

#: Every public name callers could import from _skill_writer before the move.
MOVED_NAMES = (
    "AGENT_SKILL_DESCRIPTION_MAX_CHARS",
    "AGENT_SKILL_NAME_MAX_CHARS",
    "AGENT_SKILL_NAME_PATTERN",
    "agent_skill_issues",
    "has_declared_id",
    "skill_id_of",
)


@pytest.mark.parametrize("name", MOVED_NAMES)
def test_skill_writer_reexports_the_one_object_the_rules_module_defines(name: str) -> None:
    assert getattr(_skill_writer, name) is getattr(_agent_skill_rules, name)


def test_agent_skill_rules_module_has_a_docstring() -> None:
    assert (_agent_skill_rules.__doc__ or "").strip()


def test_agent_skill_rules_leaf_loads_no_other_playbook_module() -> None:
    loaded = new_modules_after("import coding_agent_playbook.adapters._agent_skill_rules")

    # Only the (empty) adapters package beside the module itself: no types, no
    # _skill_writer (it imports this module, so that would be a cycle), no yaml.
    non_stdlib = [name for name in loaded if name.split(".")[0] not in sys.stdlib_module_names]
    assert non_stdlib == [
        "coding_agent_playbook.adapters",
        "coding_agent_playbook.adapters._agent_skill_rules",
    ]
