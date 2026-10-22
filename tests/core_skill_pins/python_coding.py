"""Pins of core skill ``python-coding`` (prU L0-15): the moved rules in mapping sections.

``pydantic-boundaries`` joins from python-tooling (D24). The retired ids
``python-classes-and-protocols`` and ``python-performance-idioms`` have no
mapping row and stay until their content lane retires them, in their
successors' sections. ``python-performance-idioms`` takes 79, the MEDIUM band's
one unmapped slot, so it ties with no mapped rule. The classes section's mapped
rules fill every slot from 60 to 66, so ``python-classes-and-protocols`` keeps
its successor ``python-protocols``'s 61 and sorts after it by id.

The asyncio and pydantic sections are vendored (C-python-coding-04): the four
async rules take 55-58 and the six pydantic rules share the HIGH band's last
slot, 59, so they sort by id. ``pydantic-typed-settings`` gates on
pydantic-settings, which the reference probe does not declare.
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
        "python-async-tasks",
        "python-async-fanout",
        "python-async-generators",
        "pydantic-boundaries",
        "pydantic-field-constraints",
        "pydantic-model-validators",
        "pydantic-serializers",
        "pydantic-special-types",
        "pydantic-typed-settings",
        "python-data-shapes",
        "python-classes-and-protocols",
        "python-idioms",
        "python-performance-idioms",
    ),
    probe_inactive=frozenset({"pydantic-typed-settings"}),
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
        "python-performance-idioms": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=79,
            name="Performance idioms",
            tags=("python", "performance"),
            section="idioms",
        ),
        "python-async": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=55,
            name="Asyncio",
            tags=("python", "async", "concurrency"),
            section="async",
        ),
        "python-async-tasks": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=56,
            name="Background tasks",
            tags=("python", "async", "concurrency"),
            section="async",
        ),
        "python-async-fanout": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=57,
            name="Bounded fan-out",
            tags=("python", "async", "concurrency"),
            section="async",
        ),
        "python-async-generators": RulePin(
            applies_if={"python_version": ">=3.10"},
            globs=_PY_FILES,
            priority=58,
            name="Async generators",
            tags=("python", "async", "streaming"),
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
        "pydantic-field-constraints": RulePin(
            applies_if={"has_framework": ["pydantic"]},
            globs=_PY_FILES,
            priority=59,
            name="Pydantic field constraints",
            tags=("python", "pydantic", "validation"),
            section="pydantic",
        ),
        "pydantic-model-validators": RulePin(
            applies_if={"has_framework": ["pydantic"]},
            globs=_PY_FILES,
            priority=59,
            name="Pydantic model validators",
            tags=("python", "pydantic", "validation"),
            section="pydantic",
        ),
        "pydantic-serializers": RulePin(
            applies_if={"has_framework": ["pydantic"]},
            globs=_PY_FILES,
            priority=59,
            name="Pydantic serializers",
            tags=("python", "pydantic", "serialization"),
            section="pydantic",
        ),
        "pydantic-special-types": RulePin(
            applies_if={"has_framework": ["pydantic"]},
            globs=_PY_FILES,
            priority=59,
            name="Pydantic special types",
            tags=("python", "pydantic", "validation"),
            section="pydantic",
        ),
        "pydantic-typed-settings": RulePin(
            applies_if={"has_dependency": ["pydantic-settings"]},
            globs=_PY_FILES,
            priority=59,
            name="Typed settings",
            tags=("python", "pydantic", "configuration"),
            section="pydantic",
        ),
    },
)
