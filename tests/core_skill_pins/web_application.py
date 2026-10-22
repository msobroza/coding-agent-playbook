"""Pins of core skill ``web-application`` (prU D4, L0-15): the two FastAPI rules re-homed."""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

PINS: Final = CoreSkillPins(
    skill_id="web-application",
    where="Web endpoints, database access and migrations",
    members=(
        "fastapi-error-boundaries",
        "fastapi-app-wiring",
    ),
    probe_inactive=frozenset(),
    rules={
        "fastapi-error-boundaries": RulePin(
            applies_if={"has_framework": ["fastapi"]},
            globs=("**/*.py",),
            priority=41,
            name="FastAPI error boundaries",
            tags=("python", "fastapi", "errors"),
        ),
        "fastapi-app-wiring": RulePin(
            applies_if={"has_framework": ["fastapi"]},
            globs=(
                "**/routers/**/*.py",
                "**/routes/**/*.py",
                "**/api/**/*.py",
                "**/main.py",
                "**/app.py",
                "**/dependencies.py",
                "**/deps.py",
                "tests/**/*.py",
            ),
            priority=44,
            name="FastAPI app wiring",
            tags=("python", "fastapi"),
        ),
    },
)
