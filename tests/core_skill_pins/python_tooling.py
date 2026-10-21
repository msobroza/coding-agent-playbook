"""Pins of core skill ``python-tooling`` (spec 9.6.2): two FastAPI rules plus four distilled."""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

PINS: Final = CoreSkillPins(
    skill_id="python-tooling",
    where="Tool configuration and framework wiring",
    members=(
        "python-static-checks",
        "pytest-configuration",
        "python-uv-workflow",
        "fastapi-app-wiring",
        "fastapi-error-boundaries",
        "pydantic-boundaries",
    ),
    # The reference probe has no uv.lock, so the uv gate fails there (spec 9.6.2).
    probe_inactive=frozenset({"python-uv-workflow"}),
    rules={
        "python-static-checks": RulePin(
            applies_if={},
            globs=("**/*.py", "pyproject.toml", "ruff.toml", ".ruff.toml", "mypy.ini", ".mypy.ini"),
            priority=21,
            name="Static checks",
            tags=("python", "tooling", "ruff", "mypy"),
        ),
        "pytest-configuration": RulePin(
            applies_if={"has_framework": ["pytest"]},
            globs=("pyproject.toml", "pytest.ini", "tox.ini", "setup.cfg", "**/conftest.py"),
            priority=23,
            name="pytest configuration",
            tags=("python", "tooling", "pytest"),
        ),
        "python-uv-workflow": RulePin(
            applies_if={"package_manager": "uv"},
            globs=("pyproject.toml",),
            priority=28,
            name="uv workflow",
            tags=("python", "tooling", "uv"),
        ),
        "pydantic-boundaries": RulePin(
            applies_if={"has_framework": ["pydantic"]},
            globs=("**/*.py",),
            priority=63,
            name="Pydantic boundaries",
            tags=("python", "pydantic", "validation"),
        ),
    },
)
