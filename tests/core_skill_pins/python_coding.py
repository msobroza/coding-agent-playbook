"""Pins of core skill ``python-coding`` (prU L0-15): the moved rules in mapping sections.

``pydantic-boundaries`` joins from python-tooling (D24). The retired ids
``python-classes-and-protocols`` and ``python-performance-idioms`` have no
mapping row and stay until their content lane retires them, in their
successors' sections. ``python-performance-idioms`` takes 79, the MEDIUM band's
one unmapped slot, so it ties with no mapped rule. The classes section's mapped
rules fill every slot from 60 to 66, so ``python-classes-and-protocols`` keeps
its successor ``python-protocols``'s 61 and sorts after it by id.
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
        "python-meaningful-names",
        "python-typing",
        "python-docstrings",
        "python-comments-why",
        "python-abstract-inputs",
        "python-type-aliases",
        "python-dependency-injection",
        "python-pure-core",
        "python-context-managers",
        "python-retries-and-timeouts",
        "python-async",
        "pydantic-boundaries",
        "python-data-shapes",
        "python-classes-and-protocols",
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
        "python-meaningful-names": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=42,
            name="Meaningful names",
            tags=("python", "naming"),
            section="types",
        ),
        "python-typing": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=43,
            name="Typing",
            tags=("python", "typing"),
            lint_codes={
                "warn": ["ANN001", "ANN201", "ANN401", "B006", "PGH003", "UP007", "UP045"],
                "when": [
                    {
                        "applies_if": {"python_version": ">=3.12"},
                        "warn": ["UP040", "UP046", "UP047"],
                    }
                ],
            },
            section="types",
        ),
        "python-docstrings": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=44,
            name="Docstrings",
            tags=("python", "docs"),
            lint_codes={"warn": ["D100", "D101", "D102", "D103", "D104", "D105", "D106", "D107"]},
            section="types",
        ),
        "python-comments-why": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=45,
            name="Comments that say why",
            tags=("python", "docs"),
            section="types",
        ),
        "python-abstract-inputs": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=46,
            name="Abstract inputs",
            tags=("python", "typing"),
            section="types",
        ),
        "python-type-aliases": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=47,
            name="Type aliases",
            tags=("python", "typing"),
            section="types",
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
