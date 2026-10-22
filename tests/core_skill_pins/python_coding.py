"""Pins of core skill ``python-coding`` (prU L0-15): the moved rules in mapping sections.

``pydantic-boundaries`` joins from python-tooling (D24). The retired ids
``python-classes-and-protocols`` and ``python-performance-idioms`` have no
mapping row and stay until their content lane retires them, in their
successors' sections. ``python-performance-idioms`` takes 79, the MEDIUM band's
one unmapped slot, so it ties with no mapped rule. The classes section's mapped
rules fill every slot from 60 to 66, so ``python-classes-and-protocols`` keeps
its successor ``python-protocols``'s 61 and sorts after it by id.

The classes section is vendored (C-python-coding-05): its seven rules are
pinned at the mapping's priorities 60-66.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_PY_FILES: Final = ("**/*.py",)

PINS: Final = CoreSkillPins(
    skill_id="python-coding",
    where="Any Python file",
    members=(
        "python-error-handling",
        "python-typing",
        "python-docstrings",
        "python-dependency-injection",
        "python-pure-core",
        "python-context-managers",
        "python-retries-and-timeouts",
        "python-async",
        "pydantic-boundaries",
        "python-data-shapes",
        "python-classes-and-protocols",
        "python-protocols",
        "python-properties",
        "python-frozen-dataclasses",
        "python-enums",
        "python-dataclass-post-init",
        "python-hide-internal-state",
        "python-idioms",
        "python-performance-idioms",
    ),
    probe_inactive=frozenset(),
    section_ids=(
        "errors",
        "shape",
        "types",
        "effects",
        "async",
        "pydantic",
        "classes",
        "functions",
        "idioms",
    ),
    rules={
        "python-data-shapes": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=60,
            name="Data shapes",
            tags=("python", "design", "data"),
            section="classes",
        ),
        "python-protocols": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=61,
            name="Protocols",
            tags=("python", "design", "typing"),
            section="classes",
        ),
        "python-properties": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=62,
            name="Properties",
            tags=("python", "design", "oop"),
            section="classes",
        ),
        "python-frozen-dataclasses": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=63,
            name="Frozen dataclasses",
            tags=("python", "design", "data"),
            section="classes",
        ),
        "python-enums": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=64,
            name="Enums for closed sets",
            tags=("python", "design", "typing"),
            section="classes",
        ),
        "python-dataclass-post-init": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=65,
            name="Dataclass post-init",
            tags=("python", "design", "data"),
            section="classes",
        ),
        "python-hide-internal-state": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=66,
            name="Hide internal state",
            tags=("python", "design", "oop"),
            section="classes",
        ),
        "python-performance-idioms": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=79,
            name="Performance idioms",
            tags=("python", "performance"),
            section="idioms",
        ),
        "python-async": RulePin(
            applies_if={"python_version": ">=3.11"},
            globs=_PY_FILES,
            priority=55,
            name="Asyncio",
            tags=("python", "async", "concurrency"),
            section="async",
        ),
        "python-classes-and-protocols": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=61,
            name="Classes and protocols",
            tags=("python", "design", "oop"),
            section="classes",
        ),
        "pydantic-boundaries": RulePin(
            applies_if={"has_framework": ["pydantic"]},
            globs=_PY_FILES,
            priority=59,
            name="Pydantic boundaries",
            tags=("python", "pydantic", "validation"),
            section="pydantic",
        ),
    },
)
