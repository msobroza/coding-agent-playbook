"""Pins of core skill ``python-tooling`` (prU L0-15, C-python-tooling-01).

Seven rules in five sections, one tool topic each, at the mapping's priorities
(``specs/prU-core-python-skills/mapping-python-tooling.md``). Four members are
ungated, so the skill is written in every Python repo; the two package-management
rules gate on a uv project.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_RUFF_CONFIGS: Final = ("pyproject.toml", "ruff.toml", ".ruff.toml")
_UV: Final = {"package_manager": "uv"}

PINS: Final = CoreSkillPins(
    skill_id="python-tooling",
    where="Tool configuration and pyproject.toml",
    members=(
        "python-static-checks",
        "ruff-lint",
        "mypy-type-checking",
        "ruff-format",
        "pytest-configuration",
        "python-uv-workflow",
        "python-pyproject-dependencies",
    ),
    # The reference probe has no uv.lock, so the uv gate fails there (spec 9.6.2).
    probe_inactive=frozenset({"python-uv-workflow", "python-pyproject-dependencies"}),
    section_ids=(
        "linting",
        "type-checking",
        "formatting",
        "test-configuration",
        "package-management",
    ),
    rules={
        "python-static-checks": RulePin(
            applies_if={},
            globs=(
                "**/*.py",
                *_RUFF_CONFIGS,
                "mypy.ini",
                ".mypy.ini",
                "pyrightconfig.json",
                ".pre-commit-config.yaml",
            ),
            priority=20,
            name="Static checks",
            tags=("python", "tooling", "ruff", "mypy"),
            section="linting",
        ),
        "ruff-lint": RulePin(
            applies_if={},
            globs=("**/*.py", *_RUFF_CONFIGS),
            priority=21,
            name="Linting with ruff",
            tags=("python", "tooling", "ruff"),
            section="linting",
        ),
        "mypy-type-checking": RulePin(
            applies_if={},
            globs=(
                "**/*.py",
                "**/*.pyi",
                "pyproject.toml",
                "mypy.ini",
                ".mypy.ini",
                "pyrightconfig.json",
            ),
            priority=40,
            name="Type checking with mypy",
            tags=("python", "tooling", "mypy"),
            section="type-checking",
        ),
        "ruff-format": RulePin(
            applies_if={},
            globs=("**/*.py", "**/*.pyi", *_RUFF_CONFIGS),
            priority=41,
            name="Formatting with ruff",
            tags=("python", "tooling", "ruff"),
            section="formatting",
        ),
        "pytest-configuration": RulePin(
            applies_if={"has_framework": ["pytest"]},
            globs=(
                "pyproject.toml",
                "pytest.ini",
                "tox.ini",
                "setup.cfg",
                ".coveragerc",
                "**/conftest.py",
            ),
            priority=42,
            name="pytest configuration",
            tags=("python", "tooling", "pytest"),
            section="test-configuration",
        ),
        "python-uv-workflow": RulePin(
            applies_if=_UV,
            globs=("pyproject.toml",),
            priority=60,
            name="uv workflow",
            tags=("python", "tooling", "uv"),
            section="package-management",
        ),
        "python-pyproject-dependencies": RulePin(
            applies_if=_UV,
            globs=("pyproject.toml",),
            priority=61,
            name="Declaring dependencies",
            tags=("python", "tooling", "uv"),
            section="package-management",
        ),
    },
)

#: The members with an empty ``applies_if``, sorted by id: written in every Python repo.
UNGATED_MEMBERS: Final = tuple(
    sorted(rule_id for rule_id, pin in PINS.rules.items() if not pin.applies_if)
)
#: The ungated members' globs, each once, in first-seen order over :data:`UNGATED_MEMBERS`.
UNGATED_GLOBS: Final = tuple(
    dict.fromkeys(glob for rule_id in UNGATED_MEMBERS for glob in PINS.rules[rule_id].globs)
)
