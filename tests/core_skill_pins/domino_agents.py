"""Pins of core skill ``domino-agents`` (prU D52, D63; mapping-domino-agents.md).

Every member gates on ``domino_project``, so the reference probe activates none.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

#: The shared test-file glob set of test-related rules (prU D41).
_TEST_GLOBS: Final = (
    "**/test_*.py",
    "**/*_test.py",
    "**/tests/**/*.py",
    "**/conftest.py",
    "**/fakes.py",
)
#: The A2A rules' globs.
_A2A_GLOBS: Final = ("**/a2a.py", "**/*agent*.py", "**/main.py", "**/chat_app.py")
#: The packages that bring an A2A server or client in (pydantic-ai's a2a extra pulls fasta2a).
#: A tuple, so the pins cannot share a mutable list; each gate takes its own list copy.
_A2A_DEPENDENCIES: Final = ("fasta2a", "a2a-sdk", "pydantic-ai", "pydantic-ai-slim")

_MEMBERS: Final = (
    "a2a-mount-lifespan",
    "a2a-agent-card",
    "a2a-client-deadlines",
    "domino-agent-fake-llm-tests",
    "domino-agent-fake-domino-tests",
)

PINS: Final = CoreSkillPins(
    skill_id="domino-agents",
    domino_only=True,
    where="Agent service code, launch script, agent config, evaluation Jobs and their tests",
    members=_MEMBERS,
    probe_inactive=frozenset(_MEMBERS),
    section_ids=(
        "secrets",
        "service",
        "configuration",
        "tracing",
        "evaluation",
        "a2a",
        "testing",
    ),
    rules={
        "a2a-mount-lifespan": RulePin(
            applies_if={
                "domino_project": True,
                "has_framework": ["fastapi"],
                "any_dependency": list(_A2A_DEPENDENCIES),
            },
            globs=_A2A_GLOBS,
            priority=60,
            name="A2A mount and lifespan",
            tags=("python", "domino", "a2a", "fastapi"),
            section="a2a",
        ),
        "a2a-agent-card": RulePin(
            applies_if={"domino_project": True, "any_dependency": list(_A2A_DEPENDENCIES)},
            globs=_A2A_GLOBS,
            priority=61,
            name="A2A agent card",
            tags=("python", "domino", "a2a"),
            section="a2a",
        ),
        "a2a-client-deadlines": RulePin(
            applies_if={"domino_project": True, "any_dependency": list(_A2A_DEPENDENCIES)},
            globs=_A2A_GLOBS,
            priority=62,
            name="A2A client deadlines",
            tags=("python", "domino", "a2a", "httpx"),
            section="a2a",
        ),
        "domino-agent-fake-llm-tests": RulePin(
            applies_if={"domino_project": True, "has_framework": ["pytest"]},
            globs=_TEST_GLOBS,
            priority=63,
            name="Agent tests on a fake model",
            tags=("python", "domino", "pytest"),
            section="testing",
        ),
        "domino-agent-fake-domino-tests": RulePin(
            applies_if={"domino_project": True, "has_framework": ["pytest"]},
            globs=_TEST_GLOBS,
            priority=64,
            name="Agent tests on Domino fakes",
            tags=("python", "domino", "pytest"),
            section="testing",
        ),
    },
)
