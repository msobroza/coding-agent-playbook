"""Pins of core skill ``python-coding`` (prU L0-15): the moved rules in mapping sections.

``pydantic-boundaries`` joins from python-tooling (D24). The retired ids
``python-classes-and-protocols`` and ``python-performance-idioms`` have no
mapping row and stay until their content lane retires them, in their
successors' sections. ``python-performance-idioms`` takes 79, the MEDIUM band's
one unmapped slot, so it ties with no mapped rule. The classes section's mapped
rules fill every slot from 60 to 66, so ``python-classes-and-protocols`` keeps
its successor ``python-protocols``'s 61 and sorts after it by id.

C-python-coding-01 adds the vendored errors and shape rules; ``python-early-return``
takes the guard-clause guidance (and its pinned phrase) from ``python-idioms``.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_PY_FILES: Final = ("**/*.py",)
#: The kept id's lint codes (D16): the error-handling-lint-feedback hook reads them.
_ERROR_HANDLING_LINT_CODES: Final = (
    "E722",
    "BLE001",
    "S110",
    "S112",
    "B904",
    "TRY400",
    "TRY401",
    "S101",
)

PINS: Final = CoreSkillPins(
    skill_id="python-coding",
    where="Any Python file",
    members=(
        "python-error-handling",
        "python-error-messages-with-context",
        "python-error-boundaries",
        "python-custom-exceptions",
        "python-small-units",
        "python-early-return",
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
        "python-error-handling": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=20,
            name="Error handling",
            tags=("python", "errors"),
            lint_codes={"warn": list(_ERROR_HANDLING_LINT_CODES)},
            section="errors",
        ),
        "python-error-messages-with-context": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=21,
            name="Error messages with context",
            tags=("python", "errors"),
            section="errors",
        ),
        "python-error-boundaries": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=22,
            name="Error boundaries",
            tags=("python", "errors"),
            section="errors",
        ),
        "python-custom-exceptions": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=23,
            name="Custom exceptions",
            tags=("python", "errors"),
            section="errors",
        ),
        "python-small-units": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=40,
            name="Small units",
            tags=("python", "readability"),
            section="shape",
        ),
        "python-early-return": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=41,
            name="Shallow nesting",
            tags=("python", "readability"),
            section="shape",
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
