"""Per-skill pins of the core skills that take member rules (prU D13, L0-03).

One module per core skill (``<skill_snake>.py``) defines ``PINS``, a
:class:`CoreSkillPins`. :data:`ALL_PINS` discovers every module of this package
with ``pkgutil``, so a content lane that adds or edits a skill touches only its
own module and no shared test file. The catalog gates in
``tests/integration/test_core_skills.py`` and ``tests/catalog/test_source_bundled.py``
read :data:`ALL_PINS`.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hooks.guardrails_skill import GUARDRAILS_SKILL_ID

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True)
class RulePin:
    """A member rule's pinned frontmatter (spec 9.4.1 / 9.6.1); the file path is not pinned.

    ``version`` and ``lint_codes`` default to a distilled rule's values (D23: no ``lint_codes``).

    Example: ``RulePin({}, ("**/*.py",), 53, name="Asyncio", tags=("python", "async"))``.
    """

    applies_if: Mapping[str, object]
    globs: tuple[str, ...]
    priority: int
    name: str
    tags: tuple[str, ...]
    version: int = 1
    lint_codes: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CoreSkillPins:
    """One core skill's pins: its Where phrase, members and the frontmatter of pinned rules.

    ``members`` lists every member rule id in index order (priority, then id);
    ``probe_inactive`` holds the members the reference probe does not activate;
    ``section_ids`` lists the declared section ids in the order of the skill's
    mapping (``specs/prU-core-python-skills/mapping-<skill>.md``), ``()`` while
    the skill declares none.

    Example: ``CoreSkillPins("ml-data", "Model code", ("ml-vectorization",), frozenset(), {})``.
    """

    skill_id: str
    where: str
    members: tuple[str, ...]
    probe_inactive: frozenset[str]
    rules: Mapping[str, RulePin]
    section_ids: tuple[str, ...] = ()


#: Core skills that take no member rules: no ``playbook:`` block, an authored "Use when".
PLAIN_CORE_SKILL_IDS: Final = frozenset({GUARDRAILS_SKILL_ID})


def _discover_pins() -> tuple[CoreSkillPins, ...]:
    """Every module's ``PINS`` in this package, sorted by skill id."""
    found = []
    for module in pkgutil.iter_modules(__path__):
        if module.name.startswith("_"):
            continue
        pins = importlib.import_module(f"{__name__}.{module.name}").PINS
        if not isinstance(pins, CoreSkillPins):
            raise TypeError(f"{__name__}.{module.name}.PINS is {pins!r}; expected CoreSkillPins")
        found.append(pins)
    return tuple(sorted(found, key=lambda pins: pins.skill_id))


#: Every core skill with member rules, one entry per pins module, sorted by skill id.
ALL_PINS: Final = _discover_pins()
