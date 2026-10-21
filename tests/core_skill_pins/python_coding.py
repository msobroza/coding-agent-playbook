"""Pins of core skill ``python-coding`` (spec 9.6.2, H13): nine moved rules, three distilled."""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_PY_FILES: Final = ("**/*.py",)

PINS: Final = CoreSkillPins(
    skill_id="python-coding",
    where="Any Python file",
    members=(
        "python-dependency-injection",
        "python-pure-core",
        "python-data-shapes",
        "python-typing",
        "python-performance-idioms",
        "python-async",
        "python-classes-and-protocols",
        "python-error-handling",
        "python-context-managers",
        "python-docstrings",
        "python-retries-and-timeouts",
        "python-idioms",
    ),
    probe_inactive=frozenset(),
    rules={
        "python-performance-idioms": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=51,
            name="Performance idioms",
            tags=("python", "performance"),
        ),
        "python-async": RulePin(
            applies_if={"python_version": ">=3.11"},
            globs=_PY_FILES,
            priority=53,
            name="Asyncio",
            tags=("python", "async", "concurrency"),
        ),
        "python-classes-and-protocols": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=53,
            name="Classes and protocols",
            tags=("python", "design", "oop"),
        ),
    },
)
