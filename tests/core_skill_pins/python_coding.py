"""Pins of core skill ``python-coding`` (prU L0-15): the moved rules in mapping sections.

``pydantic-boundaries`` joins from python-tooling (D24). The retired ids
``python-classes-and-protocols`` and ``python-performance-idioms`` have no
mapping row and stay until their content lane retires them, in their
successors' sections. ``python-performance-idioms`` takes 79, the MEDIUM band's
one unmapped slot, so it ties with no mapped rule. The classes section's mapped
rules fill every slot from 60 to 66, so ``python-classes-and-protocols`` keeps
its successor ``python-protocols``'s 61 and sorts after it by id.

The effects section is vendored (C-python-coding-03): its seven rules are
pinned at the mapping's priorities 48-54.
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
        "python-no-global-singletons",
        "python-context-managers",
        "python-parameterized-queries",
        "python-retries-and-timeouts",
        "python-custom-context-managers",
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
        "python-dependency-injection": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=48,
            name="Dependency injection",
            tags=("python", "design", "di"),
            section="effects",
        ),
        "python-pure-core": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=49,
            name="Pure core",
            tags=("python", "design", "testability"),
            section="effects",
        ),
        "python-no-global-singletons": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=50,
            name="No global singletons",
            tags=("python", "design", "di"),
            section="effects",
        ),
        "python-context-managers": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=51,
            name="Context managers",
            tags=("python", "resources"),
            section="effects",
        ),
        "python-parameterized-queries": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=52,
            name="Parameterized queries",
            tags=("python", "sql", "security"),
            section="effects",
        ),
        "python-retries-and-timeouts": RulePin(
            applies_if={"any_framework": ["requests", "httpx", "aiohttp"]},
            globs=_PY_FILES,
            priority=53,
            name="Timeouts and retries",
            tags=("python", "network", "resilience"),
            section="effects",
        ),
        "python-custom-context-managers": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=54,
            name="Custom context managers",
            tags=("python", "resources"),
            section="effects",
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
