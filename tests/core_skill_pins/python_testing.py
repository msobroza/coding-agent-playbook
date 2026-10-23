"""Pins of core skill ``python-testing`` (spec 9.6.2, prU L0-16, C-python-testing-01/02).

Sections and priorities follow mapping-python-testing.md (prU D17, L0-16; the
priority formula is on :class:`RulePin`). C-python-testing-01 vendored the
mocking, test structure and test isolation rules; C-python-testing-02 vendored
the fixtures, parametrization and coverage rules at priorities 48-50 and 60-65,
on the shared test-file glob set (D41).
"""

from __future__ import annotations

from typing import Final

from tests._catalog import TEST_FILE_GLOBS
from tests.core_skill_pins import CoreSkillPins, RulePin

_TEST_FILES: Final = ("tests/**/*.py", "**/conftest.py")
_TESTS_ONLY: Final = ("tests/**/*.py",)
_PYTEST_GATE: Final = {"has_framework": ["pytest"]}
_MOCKING_TAGS: Final = ("python", "testing", "pytest", "mocking")
_STRUCTURE_TAGS: Final = ("python", "testing", "pytest", "structure")
_ISOLATION_TAGS: Final = ("python", "testing", "pytest", "isolation")
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
        "pytest-autospec",
        "pytest",
        "pytest-first-properties",
        "pytest-arrange-act-assert",
        "pytest-one-behavior",
        "pytest-no-test-logic",
        "pytest-assertions",
        "pytest-deterministic-tests",
        "pytest-monkeypatch",
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
            tags=_MOCKING_TAGS,
            section="mocking",
        ),
        "pytest-autospec": RulePin(
            applies_if=_PYTEST_GATE,
            globs=_TEST_FILES,
            priority=21,
            name="pytest autospec",
            tags=(*_MOCKING_TAGS, "autospec"),
            section="mocking",
        ),
        "pytest": RulePin(
            applies_if=_PYTEST_GATE,
            globs=_TESTS_ONLY,
            priority=40,
            name="pytest conventions",
            tags=("python", "testing", "pytest"),
            lint_codes={"warn": ["PT006", "PT007", "PT009", "PT011", "PT018", "PT027"]},
            section="structure",
        ),
        # D72: ungated, so code-legibility's F.I.R.S.T pointer never dangles (D73).
        "pytest-first-properties": RulePin(
            applies_if={},
            globs=TEST_FILE_GLOBS,
            priority=41,
            name="F.I.R.S.T test properties",
            tags=("python", "testing", "structure"),
            section="structure",
        ),
        "pytest-arrange-act-assert": RulePin(
            applies_if=_PYTEST_GATE,
            globs=_TESTS_ONLY,
            priority=42,
            name="Arrange-Act-Assert",
            tags=_STRUCTURE_TAGS,
            section="structure",
        ),
        "pytest-one-behavior": RulePin(
            applies_if=_PYTEST_GATE,
            globs=_TESTS_ONLY,
            priority=43,
            name="One behavior per test",
            tags=_STRUCTURE_TAGS,
            section="structure",
        ),
        "pytest-no-test-logic": RulePin(
            applies_if=_PYTEST_GATE,
            globs=_TESTS_ONLY,
            priority=44,
            name="No logic in tests",
            tags=_STRUCTURE_TAGS,
            section="structure",
        ),
        "pytest-assertions": RulePin(
            applies_if=_PYTEST_GATE,
            globs=_TESTS_ONLY,
            priority=45,
            name="Assertions that can fail",
            tags=_STRUCTURE_TAGS,
            section="structure",
        ),
        "pytest-deterministic-tests": RulePin(
            applies_if=_PYTEST_GATE,
            globs=_TESTS_ONLY,
            priority=46,
            name="Deterministic tests",
            tags=_ISOLATION_TAGS,
            section="isolation",
        ),
        "pytest-monkeypatch": RulePin(
            applies_if=_PYTEST_GATE,
            globs=_TEST_FILES,
            priority=47,
            name="pytest monkeypatch",
            tags=(*_ISOLATION_TAGS, "monkeypatch"),
            section="isolation",
        ),
        **_FIXTURES_RULES,
        **_PARAMETRIZATION_RULES,
        **_COVERAGE_RULES,
    },
)
