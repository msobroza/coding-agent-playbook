"""Pins of core skill ``python-tooling`` (prU L0-15): one rule per tool, in mapping sections."""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

PINS: Final = CoreSkillPins(
    skill_id="python-tooling",
    where="Tool configuration and pyproject.toml",
    members=(
        "python-static-checks",
        "pytest-configuration",
        "python-uv-workflow",
    ),
    # The reference probe has no uv.lock, so the uv gate fails there (spec 9.6.2).
    probe_inactive=frozenset({"python-uv-workflow"}),
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
            globs=("**/*.py", "pyproject.toml", "ruff.toml", ".ruff.toml", "mypy.ini", ".mypy.ini"),
            priority=20,
            name="Static checks",
            tags=("python", "tooling", "ruff", "mypy"),
        ),
        "pytest-configuration": RulePin(
            applies_if={"has_framework": ["pytest"]},
            globs=("pyproject.toml", "pytest.ini", "tox.ini", "setup.cfg", "**/conftest.py"),
            priority=42,
            name="pytest configuration",
            tags=("python", "tooling", "pytest"),
        ),
        "python-uv-workflow": RulePin(
            applies_if={"package_manager": "uv"},
            globs=("pyproject.toml",),
            priority=60,
            name="uv workflow",
            tags=("python", "tooling", "uv"),
        ),
    },
)
