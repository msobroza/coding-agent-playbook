"""Pins of core skill ``python-testing`` (spec 9.6.2): pytest plus test doubles and fixtures.

Sections and priorities follow mapping-python-testing.md (prU D17, L0-16; the
priority formula is on :class:`RulePin`).
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_TEST_FILES: Final = ("tests/**/*.py", "**/conftest.py")
_PYTEST_GATE: Final = {"has_framework": ["pytest"]}

PINS: Final = CoreSkillPins(
    skill_id="python-testing",
    where="Test files and conftest.py",
    members=("pytest-test-doubles", "pytest", "pytest-fixtures"),
    probe_inactive=frozenset(),
    rules={
        "pytest-test-doubles": RulePin(
            applies_if=_PYTEST_GATE,
            globs=_TEST_FILES,
            priority=20,
            name="pytest test doubles",
            tags=("python", "testing", "pytest", "mocking"),
            section="mocking",
        ),
        "pytest": RulePin(
            applies_if=_PYTEST_GATE,
            globs=("tests/**/*.py",),
            priority=40,
            name="pytest conventions",
            tags=("python", "testing", "pytest"),
            lint_codes={"warn": ["PT006", "PT007", "PT009", "PT011", "PT018", "PT027"]},
            section="structure",
        ),
        "pytest-fixtures": RulePin(
            applies_if=_PYTEST_GATE,
            globs=_TEST_FILES,
            priority=48,
            name="pytest fixtures",
            tags=("python", "testing", "pytest", "fixtures"),
            section="fixtures",
        ),
    },
)
