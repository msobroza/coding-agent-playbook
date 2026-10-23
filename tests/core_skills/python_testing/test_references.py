"""The python-testing skill's references and their ``playbook.references`` entries.

prU C-python-testing-refs: the mapping (specs/prU-core-python-skills/mapping-
python-testing.md, "References") names three engine-written decision guides, each
with an open-when line, the skill's ``has_framework: pytest`` gate and the rule ids
it routes to. D47 lists each in ``playbook.references``; D49 caps an internal
decision guide at 120 lines.
"""

from __future__ import annotations

import re
from typing import Final

import pytest

from coding_agent_playbook.hook_runtime.handlers.feedback._lint_ast import (
    ASYNCIO_MARK,
    LOOP_ASSERT,
    UNITTEST_CLASS,
)
from tests._catalog import core_rules, core_skill_root
from tests._core_skill_layout import names_rule_id
from tests.core_skills._references import (
    INTERNAL_GUIDE_MAX_LINES,
    cross_skill_mentions,
    guide_line_count,
    known_rule_ids,
    reference_text,
    references_block,
    skill_md_parts,
    skill_rule_ids,
)

pytestmark = pytest.mark.catalog

SKILL_ROOT: Final = core_skill_root("python-testing")
TEST_DOUBLE: Final = "references/choosing-a-test-double.md"
ASYNC_TESTS: Final = "references/async-tests.md"
REVIEWING: Final = "references/reviewing-tests.md"
#: The mapping's references, in its order, with their open-when lines.
MAPPED_OPEN_WHEN: Final = {
    TEST_DOUBLE: (
        "Before picking what replaces a dependency in a test: fake, stub, autospec, "
        "monkeypatch, override or a real database."
    ),
    ASYNC_TESTS: (
        "Adding the first async test or async fixture, or choosing between pytest-asyncio, "
        "anyio's marker and asyncio.run."
    ),
    REVIEWING: (
        "Reviewing a test diff, or a ruff PT code or pytest-conventions-feedback finding "
        "that links to the pytest rule."
    ),
}
#: The mapping's gate, shared by every reference: the skill's own pytest gate.
PYTEST_GATE: Final = {"has_framework": ["pytest"]}
#: The mapping's "Routes to" column: the rule ids each reference must name.
ROUTES_TO: Final = {
    TEST_DOUBLE: [
        "pytest-test-doubles",
        "pytest-autospec",
        "pytest-monkeypatch",
        "pytest-deterministic-tests",
        "pytest-fixtures",
        "pytest-conftest",
    ],
    ASYNC_TESTS: ["pytest", "pytest-fixtures", "pytest-conftest", "pytest-test-doubles"],
    REVIEWING: [
        "pytest",
        "pytest-arrange-act-assert",
        "pytest-one-behavior",
        "pytest-no-test-logic",
        "pytest-assertions",
        "pytest-test-doubles",
        "pytest-autospec",
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
    ],
}
#: The mapping's outlines: the other skills' rules each guide names as "<skill>'s <id>".
CROSS_SKILL_POINTERS: Final = {
    TEST_DOUBLE: {
        ("python-coding", "python-pure-core"),
        ("ml-data", "ml-seeded-randomness"),
        ("python-architecture", "arch-make-legacy-testable"),
        ("python-architecture", "arch-test-use-cases-with-fakes"),
        ("python-architecture", "arch-contract-tests-for-fakes"),
        ("web-application", "sqlalchemy-test-rollback"),
        ("web-application", "fastapi-dependency-overrides"),
    },
    ASYNC_TESTS: {
        ("web-application", "sqlalchemy-test-rollback"),
        ("web-application", "fastapi-dependency-overrides"),
        ("python-architecture", "arch-test-use-cases-with-fakes"),
        ("python-tooling", "pytest-configuration"),
        ("python-coding", "python-async"),
    },
    REVIEWING: {
        ("web-application", "sqlalchemy-test-rollback"),
        ("web-application", "fastapi-dependency-overrides"),
        ("python-architecture", "arch-contract-tests-for-fakes"),
        ("python-architecture", "arch-tests-by-layer"),
        ("python-tooling", "pytest-configuration"),
        ("ml-data", "ml-numeric-assertions"),
    },
}
#: The mapping's SKILL.md See Also: plain-text skill names (D32).
SEE_ALSO_SKILLS: Final = (
    "python-tooling",
    "python-coding",
    "python-architecture",
    "web-application",
    "ml-data",
)
#: A whole token shaped like one of this skill's rule ids: ``pytest`` or ``pytest-...``.
_RULE_ID_LIKE_RE: Final = re.compile(r"(?<![\w-])pytest(?:-[a-z0-9]+)*(?![\w-])")
#: Tokens of that shape that are no rule of this skill: plugins, the feedback hook and
#: its findings. Other skills' rules are named "<skill>'s <id>" and checked apart.
_RULE_ID_LOOKALIKES: Final = frozenset(
    {
        "pytest-asyncio",
        "pytest-mock",
        "pytest-cov",
        "pytest-conventions-feedback",
        UNITTEST_CLASS,
        LOOP_ASSERT,
        ASYNCIO_MARK,
    }
)


def _guide(path: str) -> str:
    """The text of one of the skill's guides: ``_guide(REVIEWING)``."""
    return reference_text(SKILL_ROOT, path)


def _rule_id_like_names(text: str) -> set[str]:
    """The names in ``text`` shaped like this skill's rule ids, lookalikes left out.

    >>> sorted(_rule_id_like_names("the pytest rule, pytest-asyncio and pytest-fixtures."))
    ['pytest', 'pytest-fixtures']
    """
    return set(_RULE_ID_LIKE_RE.findall(text)) - _RULE_ID_LOOKALIKES


def test_skill_lists_each_mapped_reference_gated_on_pytest_in_mapping_order() -> None:
    entries = references_block(SKILL_ROOT)

    listed = {entry["path"]: entry["open_when"] for entry in entries}

    assert list(listed) == list(MAPPED_OPEN_WHEN)
    assert listed == MAPPED_OPEN_WHEN
    assert all(entry.get("applies_if") == PYTEST_GATE for entry in entries)


def test_rule_id_pattern_skips_plugins_hook_findings_and_module_names() -> None:
    text = "pytest_asyncio.fixture, pytest-loop-assert (pytest-parametrize); pytest-mock."

    assert _rule_id_like_names(text) == {"pytest-parametrize"}


@pytest.mark.parametrize("path", list(ROUTES_TO))
def test_reference_names_every_rule_it_routes_to(path: str) -> None:
    text = _guide(path)

    missing = [rule_id for rule_id in ROUTES_TO[path] if not names_rule_id(text, rule_id)]

    assert missing == [], f"{path} does not name {missing}"


@pytest.mark.parametrize("path", list(ROUTES_TO))
def test_reference_names_only_rule_ids_the_skill_ships(path: str) -> None:
    text = _guide(path)

    other_skills = {rule_id for _, rule_id in cross_skill_mentions(text)}
    unknown = sorted(_rule_id_like_names(text) - other_skills - skill_rule_ids(SKILL_ROOT))

    assert unknown == [], f"{path} names rule ids python-testing does not ship: {unknown}"


@pytest.mark.parametrize("path", list(CROSS_SKILL_POINTERS))
def test_reference_names_the_mapped_rules_of_other_skills(path: str) -> None:
    mentions = cross_skill_mentions(_guide(path))

    missing = sorted(CROSS_SKILL_POINTERS[path] - mentions)

    assert missing == [], f"{path} does not name {missing}"


@pytest.mark.parametrize("path", list(ROUTES_TO))
def test_reference_names_only_rules_other_skills_ship_or_plan(path: str) -> None:
    """A "<skill>'s <id>" pointer names a rule that skill ships or its mapping plans."""
    mentions = cross_skill_mentions(_guide(path))

    dangling = sorted(
        (skill, rule) for skill, rule in mentions if rule not in known_rule_ids(skill)
    )

    assert dangling == [], f"{path} names rules their skills neither ship nor plan: {dangling}"


def test_async_guide_orders_the_markers_as_the_pytest_rule_branches() -> None:
    """D27(4) as amended by D43: the installed plugin, then anyio's marker, then asyncio.run."""
    text = _guide(ASYNC_TESTS)

    positions = [
        text.find(marker)
        for marker in ("`@pytest.mark.asyncio`", "`@pytest.mark.anyio`", "`asyncio.run(...)`")
    ]

    assert -1 not in positions, positions
    assert positions == sorted(positions), positions


def test_review_guide_routes_every_code_and_finding_reported_under_the_pytest_rule() -> None:
    """D16, D21: the PT codes and the hook's findings all link to the pytest rule."""
    text = _guide(REVIEWING)
    lint_codes = core_rules()["pytest"].frontmatter.lint_codes or {}
    reported = [*lint_codes.get("warn", []), UNITTEST_CLASS, LOOP_ASSERT, ASYNCIO_MARK]

    unrouted = [name for name in reported if not names_rule_id(text, name)]

    assert len(reported) == 9, reported
    assert unrouted == [], f"{REVIEWING} does not route {unrouted}"


def test_test_double_guide_leaves_the_symptoms_to_the_review_guide() -> None:
    """Mapping: one line names reviewing-tests.md, so the symptoms live in one guide."""
    signs = _guide(TEST_DOUBLE).partition("## Signs the choice was wrong")[2]

    assert "reviewing-tests.md" in signs
    assert "references/" not in signs


def test_hand_written_body_leaves_navigation_to_the_engine() -> None:
    """D47: no hand-written picking bullets; D32: Quick Reference and plain-text See Also."""
    _, body = skill_md_parts(SKILL_ROOT)
    headings = re.findall(r"^## (.+)$", body, re.MULTILINE)

    assert headings == ["Quick Reference", "See Also"]
    assert not any(path in body for path in MAPPED_OPEN_WHEN)
    see_also = body.partition("## See Also")[2]
    for skill in SEE_ALSO_SKILLS:
        assert f"- {skill}:" in see_also, skill


def test_quick_reference_doubles_with_a_named_fake_before_any_patch() -> None:
    """Mapping (pbp-B#23): a named fake first, autospec only as the thin-seam fallback."""
    quick_reference = skill_md_parts(SKILL_ROOT)[1].partition("## Quick Reference")[2]
    mocking = quick_reference.partition("### Mocking")[2]

    assert "class Fake" in mocking
    assert mocking.index("class Fake") < mocking.index("autospec=True")
    assert "mocker" not in quick_reference


def test_quick_reference_factory_takes_keyword_only_parameters() -> None:
    """Mapping (pbp-B#21): the factory fixture's parameters are keyword-only and typed."""
    quick_reference = skill_md_parts(SKILL_ROOT)[1].partition("## Quick Reference")[2]

    assert re.search(r"def _make\(\*, [a-z_]+: [A-Za-z]+ = ", quick_reference), quick_reference


@pytest.mark.parametrize("path", list(ROUTES_TO))
def test_internal_guide_stays_within_the_d49_budget(path: str) -> None:
    lines = guide_line_count(SKILL_ROOT, path)

    assert lines <= INTERNAL_GUIDE_MAX_LINES, f"{path} is {lines} lines"
