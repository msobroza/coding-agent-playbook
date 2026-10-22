"""Pins of core skill ``design-patterns`` (prU D4, D14): the shape of code inside a module.

C-design-patterns-01 creates the skill with its six sections and the ten rules of
the responsibilities and abstractions sections; C-design-patterns-03 adds the seven
rules of the common-patterns section; later lanes append theirs.
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
        "design-plugin-loading",
        "design-dispatch-table",
        "design-strategy",
        "design-adapter",
        "design-value-objects",
        "design-domain-events",
        "design-lazy-loading",
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
        "design-plugin-loading": RulePin(
            applies_if={},
            globs=_PY,
            priority=64,
            name="Plugin loading",
            tags=("python", "design", "patterns"),
            section="common-patterns",
        ),
        "design-dispatch-table": RulePin(
            applies_if={},
            globs=_PY,
            priority=65,
            name="Dispatch table",
            tags=("python", "design", "patterns"),
            section="common-patterns",
        ),
        "design-strategy": RulePin(
            applies_if={},
            globs=_PY,
            priority=66,
            name="Strategy",
            tags=("python", "design", "patterns"),
            section="common-patterns",
        ),
        "design-adapter": RulePin(
            applies_if={},
            globs=_PY,
            priority=67,
            name="Adapter",
            tags=("python", "design", "patterns"),
            section="common-patterns",
        ),
        "design-value-objects": RulePin(
            applies_if={},
            globs=_PY,
            priority=68,
            name="Value objects",
            tags=("python", "design", "patterns"),
            section="common-patterns",
        ),
        "design-domain-events": RulePin(
            applies_if={},
            globs=_PY,
            priority=69,
            name="Domain events",
            tags=("python", "design", "patterns"),
            section="common-patterns",
        ),
        "design-lazy-loading": RulePin(
            applies_if={},
            globs=_PY,
            priority=70,
            name="Lazy loading",
            tags=("python", "design", "patterns"),
            section="common-patterns",
        ),
    },
)
