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

``python-early-return`` owns the guard-clause guidance and its pinned phrase, which
left ``python-idioms`` so that one rule holds each topic.

The asyncio and pydantic sections are vendored (C-python-coding-04): the four
async rules take 55-58 and the six pydantic rules share the HIGH band's last
slot, 59, so they sort by id. ``pydantic-typed-settings`` gates on
pydantic-settings, which the reference probe does not declare.
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
        "python-meaningful-names",
        "python-typing",
        "python-docstrings",
        "python-comments-why",
        "python-abstract-inputs",
        "python-type-aliases",
        "python-dependency-injection",
        "python-pure-core",
        "python-no-global-singletons",
        "python-context-managers",
        "python-parameterized-queries",
        "python-retries-and-timeouts",
        "python-custom-context-managers",
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
