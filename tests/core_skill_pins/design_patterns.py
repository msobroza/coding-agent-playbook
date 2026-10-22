"""Pins of core skill ``design-patterns`` (prU D4, D14): the shape of code inside a module.

C-design-patterns-01 creates the skill with its six sections and the ten rules of
the responsibilities and abstractions sections; C-design-patterns-02 adds the seven
rules of the simplicity and smells sections; later lanes append theirs.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_PY: Final = ("**/*.py",)

PINS: Final = CoreSkillPins(
    skill_id="design-patterns",
    where="Python classes and modules under design or refactoring",
    members=(
        "design-single-responsibility",
        "design-tell-dont-ask",
        "design-split-god-class",
        "design-grasp-responsibilities",
        "design-low-coupling",
        "design-dependency-inversion",
        "design-open-closed",
        "design-composition-over-inheritance",
        "design-liskov-substitution",
        "design-interface-segregation",
        "design-dry-yagni-kiss",
        "design-lightest-construct",
        "design-pattern-from-smell",
        "design-review-by-severity",
        "design-start-with-the-data",
        "design-name-for-intent",
        "design-complete-construction",
    ),
    probe_inactive=frozenset(),
    section_ids=(
        "responsibilities",
        "abstractions",
        "simplicity",
        "smells",
        "common-patterns",
        "specialized-patterns",
    ),
    rules={
        "design-single-responsibility": RulePin(
            applies_if={},
            globs=_PY,
            priority=40,
            name="Single responsibility",
            tags=("python", "design", "solid"),
            section="responsibilities",
        ),
        "design-tell-dont-ask": RulePin(
            applies_if={},
            globs=_PY,
            priority=41,
            name="Tell, don't ask",
            tags=("python", "design", "coupling"),
            section="responsibilities",
        ),
        "design-split-god-class": RulePin(
            applies_if={},
            globs=_PY,
            priority=42,
            name="Split a god class",
            tags=("python", "design", "cohesion"),
            section="responsibilities",
        ),
        "design-grasp-responsibilities": RulePin(
            applies_if={},
            globs=_PY,
            priority=43,
            name="GRASP responsibilities",
            tags=("python", "design", "grasp"),
            section="responsibilities",
        ),
        "design-low-coupling": RulePin(
            applies_if={},
            globs=_PY,
            priority=44,
            name="Low coupling",
            tags=("python", "design", "coupling"),
            section="abstractions",
        ),
        "design-dependency-inversion": RulePin(
            applies_if={},
            globs=_PY,
            priority=45,
            name="Dependency inversion",
            tags=("python", "design", "solid"),
            section="abstractions",
        ),
        "design-open-closed": RulePin(
            applies_if={},
            globs=_PY,
            priority=46,
            name="Open/closed",
            tags=("python", "design", "solid"),
            section="abstractions",
        ),
        "design-composition-over-inheritance": RulePin(
            applies_if={},
            globs=_PY,
            priority=47,
            name="Composition over inheritance",
            tags=("python", "design", "oop"),
            section="abstractions",
        ),
        "design-liskov-substitution": RulePin(
            applies_if={},
            globs=_PY,
            priority=48,
            name="Liskov substitution",
            tags=("python", "design", "solid"),
            section="abstractions",
        ),
        "design-interface-segregation": RulePin(
            applies_if={},
            globs=_PY,
            priority=49,
            name="Interface segregation",
            tags=("python", "design", "solid"),
            section="abstractions",
        ),
        "design-dry-yagni-kiss": RulePin(
            applies_if={},
            globs=_PY,
            priority=50,
            name="DRY, YAGNI and KISS",
            tags=("python", "design", "simplicity"),
            section="simplicity",
        ),
        "design-lightest-construct": RulePin(
            applies_if={},
            globs=_PY,
            priority=51,
            name="The lightest construct",
            tags=("python", "design", "simplicity"),
            section="simplicity",
        ),
        "design-pattern-from-smell": RulePin(
            applies_if={},
            globs=_PY,
            priority=52,
            name="A pattern only for a present smell",
            tags=("python", "design", "patterns"),
            section="simplicity",
        ),
        "design-review-by-severity": RulePin(
            applies_if={},
            globs=_PY,
            priority=60,
            name="Design review by severity",
            tags=("python", "design", "review"),
            section="smells",
        ),
        "design-start-with-the-data": RulePin(
            applies_if={},
            globs=_PY,
            priority=61,
            name="Start with the data",
            tags=("python", "design", "data"),
            section="smells",
        ),
        "design-name-for-intent": RulePin(
            applies_if={},
            globs=_PY,
            priority=62,
            name="Names that match intent",
            tags=("python", "design", "naming"),
            section="smells",
        ),
        "design-complete-construction": RulePin(
            applies_if={},
            globs=_PY,
            priority=63,
            name="Complete construction",
            tags=("python", "design", "construction"),
            section="smells",
        ),
    },
)
