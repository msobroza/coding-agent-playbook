"""Pins of core skill ``python-testing`` (spec 9.6.2): pytest plus test doubles and fixtures.

Sections and priorities follow mapping-python-testing.md (prU D17, L0-16; the
priority formula is on :class:`RulePin`). C-python-testing-02 vendored the
fixtures, parametrization and coverage rules at priorities 48-50 and 60-65, on
the shared test-file glob set (D41); the rules C-python-testing-01 revises still
use ``tests/**/*.py`` until it moves them.
"""

from __future__ import annotations

from typing import Final

from tests._catalog import TEST_FILE_GLOBS
from tests.core_skill_pins import CoreSkillPins, RulePin

_TEST_FILES: Final = ("tests/**/*.py", "**/conftest.py")
_PYTEST_GATE: Final = {"has_framework": ["pytest"]}
#: D23: the coverage rule renders only where the repo already measures coverage.
_COVERAGE_GATE: Final = {**_PYTEST_GATE, "any_dependency": ["pytest-cov", "coverage"]}
#: D23: the Hypothesis rules render only where the repo depends on Hypothesis.
_HYPOTHESIS_GATE: Final = {**_PYTEST_GATE, "has_dependency": ["hypothesis"]}

_FIXTURES_RULES: Final = {
    "pytest-fixtures": RulePin(
        applies_if=_PYTEST_GATE,
        globs=TEST_FILE_GLOBS,
        priority=48,
        name="pytest fixtures",
        tags=("python", "testing", "pytest", "fixtures"),
        section="fixtures",
    ),
    "pytest-conftest": RulePin(
        applies_if=_PYTEST_GATE,
        globs=TEST_FILE_GLOBS,
        priority=49,
        name="Fixtures in the nearest conftest.py",
        tags=("python", "testing", "pytest", "fixtures", "conftest"),
        section="fixtures",
    ),
    "pytest-factory-fixtures": RulePin(
        applies_if=_PYTEST_GATE,
        globs=TEST_FILE_GLOBS,
        priority=50,
        name="Factory fixtures",
        tags=("python", "testing", "pytest", "fixtures", "test-data"),
        section="fixtures",
    ),
}

_PARAMETRIZATION_RULES: Final = {
    "pytest-parametrize": RulePin(
        applies_if=_PYTEST_GATE,
        globs=TEST_FILE_GLOBS,
        priority=60,
        name="Parametrized case tables",
        tags=("python", "testing", "pytest", "parametrize"),
        section="parametrization",
    ),
    "pytest-parametrize-ids": RulePin(
        applies_if=_PYTEST_GATE,
        globs=TEST_FILE_GLOBS,
        priority=61,
        name="Readable parametrize ids",
        tags=("python", "testing", "pytest", "parametrize"),
        section="parametrization",
    ),
}

_COVERAGE_RULES: Final = {
    "pytest-edge-cases": RulePin(
        applies_if=_PYTEST_GATE,
        globs=TEST_FILE_GLOBS,
        priority=62,
        name="Edge cases",
        tags=("python", "testing", "pytest", "coverage"),
        section="coverage",
    ),
    "pytest-branch-coverage": RulePin(
        applies_if=_COVERAGE_GATE,
        globs=TEST_FILE_GLOBS,
        priority=63,
        name="Branch coverage",
        tags=("python", "testing", "pytest", "coverage"),
        section="coverage",
    ),
    "pytest-hypothesis-properties": RulePin(
        applies_if=_HYPOTHESIS_GATE,
        globs=TEST_FILE_GLOBS,
        priority=64,
        name="Hypothesis properties",
        tags=("python", "testing", "pytest", "hypothesis"),
        section="coverage",
    ),
    "pytest-hypothesis-stateful": RulePin(
        applies_if=_HYPOTHESIS_GATE,
        globs=TEST_FILE_GLOBS,
        priority=65,
        name="Hypothesis stateful tests",
        tags=("python", "testing", "pytest", "hypothesis"),
        section="coverage",
    ),
}

PINS: Final = CoreSkillPins(
    skill_id="python-testing",
    where="Test files and conftest.py",
    members=(
        "pytest-test-doubles",
        "pytest",
        "pytest-fixtures",
        "pytest-conftest",
        "pytest-factory-fixtures",
        "pytest-parametrize",
        "pytest-parametrize-ids",
        "pytest-edge-cases",
        "pytest-branch-coverage",
        "pytest-hypothesis-properties",
        "pytest-hypothesis-stateful",
    ),
    probe_inactive=frozenset(
        {"pytest-branch-coverage", "pytest-hypothesis-properties", "pytest-hypothesis-stateful"}
    ),
    section_ids=("mocking", "structure", "isolation", "fixtures", "parametrization", "coverage"),
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
        **_FIXTURES_RULES,
        **_PARAMETRIZATION_RULES,
        **_COVERAGE_RULES,
    },
)
