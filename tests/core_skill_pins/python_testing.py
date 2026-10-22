"""Pins of core skill ``python-testing`` (spec 9.6.2, prU L0-16, C-python-testing-01).

Sections and priorities follow mapping-python-testing.md (prU D17, L0-16; the
priority formula is on :class:`RulePin`). C-python-testing-01 vendors the
mocking, test structure and test isolation rules; pytest-fixtures stays as L0-16
left it until C-python-testing-02.
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
    ),
    probe_inactive=frozenset(),
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
