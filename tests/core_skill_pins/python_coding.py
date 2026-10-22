"""Pins of core skill ``python-coding`` (prU L0-15): the moved rules in mapping sections.

``pydantic-boundaries`` joins from python-tooling (D24). The retired id
``python-classes-and-protocols`` has no mapping row and stays until its content
lane retires it, in its successors' section. The classes section's mapped
rules fill every slot from 60 to 66, so ``python-classes-and-protocols`` keeps
its successor ``python-protocols``'s 61 and sorts after it by id.

The effects section is vendored (C-python-coding-03): its seven rules are
pinned at the mapping's priorities 48-54.

``python-early-return`` owns the guard-clause guidance and its pinned phrase, which
left ``python-idioms`` so that one rule holds each topic.

The idioms section is vendored (C-python-coding-07): its seven rules are pinned at
the mapping's priorities 72-78. ``python-imports`` takes the import items from
``python-idioms``, and the retired ``python-performance-idioms`` is gone, split into
``python-collection-choice``, ``python-optional-keys``, ``python-comprehensions``,
``python-generators`` and ``python-str-join``.
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
        "python-imports",
        "python-collection-choice",
        "python-optional-keys",
        "python-comprehensions",
        "python-generators",
        "python-str-join",
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
        "python-idioms": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=72,
            name="Idioms",
            tags=("python", "style"),
            section="idioms",
        ),
        "python-imports": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=73,
            name="Imports",
            tags=("python", "style", "imports"),
            section="idioms",
        ),
        "python-collection-choice": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=74,
            name="Collection choice",
            tags=("python", "performance", "data-structures"),
            section="idioms",
        ),
        "python-optional-keys": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=75,
            name="Optional keys",
            tags=("python", "dict"),
            section="idioms",
        ),
        "python-comprehensions": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=76,
            name="Comprehensions",
            tags=("python", "performance", "loops"),
            section="idioms",
        ),
        "python-generators": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=77,
            name="Generators",
            tags=("python", "performance", "memory"),
            section="idioms",
        ),
        "python-str-join": RulePin(
            applies_if={},
            globs=_PY_FILES,
            priority=78,
            name="String joining",
            tags=("python", "performance", "strings"),
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
