"""Pins of core skill ``python-testing`` (spec 9.6.2): pytest plus test doubles and fixtures."""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_TEST_FILES: Final = ("tests/**/*.py", "**/conftest.py")
_PYTEST_GATE: Final = {"has_framework": ["pytest"]}

PINS: Final = CoreSkillPins(
    skill_id="python-testing",
    where="Test files and conftest.py",
    members=("pytest", "pytest-test-doubles", "pytest-fixtures"),
    probe_inactive=frozenset(),
    rules={
        "pytest-test-doubles": RulePin(
            applies_if=_PYTEST_GATE,
            globs=_TEST_FILES,
            priority=61,
            name="pytest test doubles",
            tags=("python", "testing", "pytest", "mocking"),
        ),
        "pytest-fixtures": RulePin(
            applies_if=_PYTEST_GATE,
            globs=_TEST_FILES,
            priority=63,
            name="pytest fixtures",
            tags=("python", "testing", "pytest", "fixtures"),
        ),
    },
)
