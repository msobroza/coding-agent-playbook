"""Docs-consistency guard: SPEC describes rules inside skills (prU D-01; D5, D17, D21, ADR 0005).

Member rules live in their skill's ``rules/`` directory, in the catalog and in every
rendered skill root, and a sectioned skill ranks them by impact band. The SPEC body may
no longer describe the earlier ``references/<rule-id>.md`` delivery or the kind-based
priority bands (the changelogs keep that history), and §12.6 must quote, for each
layout check R1-R6 and section check S1-S7, the message the engine prints. Messages are
produced by the validation code itself, so a reworded message fails here until the
SPEC row follows. Prose-only on the SPEC side: these tests never change engine state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.unit.test_docs_lifecycle_hooks_spec import _spec_section
from tests.validation.layout_samples import (
    engine_resources,
    layout_errors,
    write_rule,
    write_skill,
)
from tests.validation.section_samples import (
    FIXTURES,
    MOCKING,
    SECTIONLESS_BLOCK,
    check,
    make_rule,
    make_skill,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill

#: The phrases of the pre-D5 delivery and priority policy (the ticket's acceptance grep).
_STALE_PHRASES = (
    "references/<rule-id>",
    "references/python-typing.md",
    "kind bands",
    "40-59 language",
    "is a reference of",
)


def _validate_section() -> str:
    return _spec_section("### 12.6 `playbook validate`", "### 12.7 ")


def _row(check_id: str) -> str:
    """The one §12.6 table row of ``check_id`` (``R1``, ``S4``, ...)."""
    rows = [line for line in _validate_section().splitlines() if line.startswith(f"| {check_id} |")]
    assert len(rows) == 1, f"SPEC §12.6 needs exactly one row for {check_id}, found {rows}"
    return rows[0]


@pytest.mark.parametrize("phrase", _STALE_PHRASES)
def test_spec_body_no_longer_describes_the_old_delivery(phrase: str) -> None:
    body = _spec_section("## 1. Context", "## Changelog")
    stale = [line[:80] for line in body.splitlines() if phrase in line]
    assert not stale, f"SPEC body still says {phrase!r} (only the changelogs may): {stale}"


def test_section_10_2_1_states_the_impact_bands() -> None:
    policy = _spec_section("#### 10.2.1 Numbering scheme", "### 10.3 Claude Code adapter")
    for band in ("`00`-`19`", "`20`-`39`", "`40`-`59`", "`60`-`79`", "`80`-`99`"):
        assert f"| {band} |" in policy, f"SPEC §10.2.1 lacks the {band} row"


def test_section_12_6_retires_v12_and_quotes_the_rules_heading() -> None:
    assert "| V12 |" not in _validate_section(), "V12 was retired by prU D5"
    assert "'## Rules' heading" in _row("V13")


def test_section_12_6_gives_both_ways_to_join_a_skill() -> None:
    """Membership is by location or by ``skill:`` (D5, ADR 0005), never ``skill:`` alone."""
    section = _validate_section()
    assert "A scoped rule that names a skill in `skill:` is a member rule" not in section
    assert "by its location in that skill's `rules/` or, from another layer, by `skill:`" in section


# --- S1-S7 and the D42 warning: the engine's own messages ----------------------------------


def _messages(rules: list[Rule], skill: Skill) -> list[str]:
    """Every error and warning message the section checks report, errors first."""
    findings = check(rules, skill)
    return [f.message for f in (*findings.errors, *findings.warnings)]


def _section_list_messages(sections: object) -> list[str]:
    """The messages for a skill declaring ``sections`` and no member rule."""
    return _messages([], make_skill({"sections": sections}))


#: One malformed ``sections`` value per S1 message the engine prints (skills/sections.py).
_MALFORMED_SECTION_LISTS: tuple[object, ...] = (
    [{**MOCKING, "impact": "URGENT"}],
    "mocking",
    ["mocking"],
    [{**MOCKING, "when": "x"}],
    [{key: value for key, value in MOCKING.items() if key != "summary"}],
    [{**MOCKING, "summary": ""}],
    [{**MOCKING, "summary": "a\nb"}],
    [{**MOCKING, "id": "Mocking"}],
    [{**MOCKING, "title": "Mocking, stubbing and faking collaborators"}],
    [MOCKING, MOCKING],
)

_SECTION_CASES: dict[str, Callable[[], list[str]]] = {
    "S1": lambda: [
        message
        for sections in _MALFORMED_SECTION_LISTS
        for message in _section_list_messages(sections)
    ],
    "S2": lambda: _section_list_messages([FIXTURES, MOCKING]),
    "S3": lambda: _messages([make_rule(section="mokcing")], make_skill()),
    "S4": lambda: _messages([make_rule(section=None)], make_skill()),
    "S5": lambda: [
        *_messages([make_rule(section="mocking", priority=50)], make_skill(SECTIONLESS_BLOCK)),
        *_messages([make_rule(skill=None, scope="always")], make_skill()),
    ],
    "S6": lambda: _messages([make_rule(priority=45)], make_skill()),
    "S7": lambda: _messages([make_rule(body="# Use fakes [HIGH]\n")], make_skill()),
    "W4": lambda: _messages([make_rule(section=None, package="other")], make_skill()),
}


def test_every_malformed_section_list_yields_its_own_s1_message() -> None:
    """Guards the S1 case table: each fixture must still hit one distinct engine message."""
    per_fixture = [_section_list_messages(sections) for sections in _MALFORMED_SECTION_LISTS]
    assert all(len(messages) == 1 for messages in per_fixture), per_fixture
    assert len({messages[0] for messages in per_fixture}) == len(per_fixture)


@pytest.mark.parametrize("check_id", sorted(_SECTION_CASES))
def test_section_12_6_row_quotes_the_section_check_message(check_id: str) -> None:
    messages = _SECTION_CASES[check_id]()
    assert messages, f"the {check_id} fixture produced no finding"
    row = _row(check_id)
    missing = [message for message in messages if message not in row]
    assert not missing, f"SPEC §12.6 row {check_id} must quote {missing}"


# --- R1-R6: the rules/ layout messages, paths relative to the repo ------------------------


def _in_skill_rule_naming_another_skill(repo: Path) -> None:
    """R1: a rule in the rules/ of skill 's' declares 'skill: t'."""
    write_rule(write_skill(repo / "playbook", "s") / "rules" / "r.md", "r", extra="skill: t\n")


def _in_skill_rule_file_named_otherwise(repo: Path) -> None:
    """R2: rule 'python-typing' lies in a skill's rules/ as typing.md.j2."""
    write_rule(write_skill(repo / "playbook", "s") / "rules" / "typing.md.j2", "python-typing")


def _one_rule_id_twice_in_one_layer(repo: Path) -> None:
    """R3: rule id 'r' is defined by two files of the repo-local layer."""
    write_rule(repo / "playbook" / "rules" / "r-old.md", "r", extra="skill: s\n")
    write_rule(write_skill(repo / "playbook", "s") / "rules" / "r.md", "r")


def _rules_dirs_of_unusable_skills(repo: Path) -> None:
    """R4, both messages: a rules/ without SKILL.md, and one in a skill without 'playbook:'."""
    write_rule(repo / "playbook" / "skills" / "orphan" / "rules" / "r.md", "r")
    (write_skill(repo / "playbook", "plain", block="") / "rules").mkdir()


def _always_rule_in_a_skill_rules_dir(repo: Path) -> None:
    """R6: always rule 'house' lies in the rules/ of skill 's'."""
    write_rule(write_skill(repo / "playbook", "s") / "rules" / "house.md", "house", scope="always")


_LAYOUT_CASES: dict[str, Callable[[Path], None]] = {
    "R1": _in_skill_rule_naming_another_skill,
    "R2": _in_skill_rule_file_named_otherwise,
    "R3": _one_rule_id_twice_in_one_layer,
    "R4": _rules_dirs_of_unusable_skills,
    "R6": _always_rule_in_a_skill_rules_dir,
}


@pytest.fixture
def engine(make_package: Callable[..., str]) -> str:
    """A throwaway engine package, so the real catalog stays out of these fixtures."""
    return make_package("docs_layout_engine", resources=True)


def _layout_messages(repo: Path, engine: str) -> list[str]:
    """Each layout finding as ``<path>: <message>``, with ``<repo>/`` stripped from both."""
    prefix = f"{repo}/"
    return [
        f"{error.path.removeprefix(prefix)}: {error.message.replace(prefix, '')}"
        for error in layout_errors(repo, engine)
    ]


@pytest.mark.parametrize("check_id", sorted(_LAYOUT_CASES))
def test_section_12_6_row_quotes_the_layout_check_message(
    check_id: str, tmp_path: Path, engine: str
) -> None:
    _LAYOUT_CASES[check_id](tmp_path)
    messages = _layout_messages(tmp_path, engine)
    assert messages, f"the {check_id} fixture produced no finding"
    row = _row(check_id)
    missing = [message for message in messages if f"`FAIL {message}`" not in row]
    assert not missing, f"SPEC §12.6 row {check_id} must quote {missing}"


def test_section_12_6_row_quotes_the_r5_move_hint(tmp_path: Path, engine: str) -> None:
    """R5's paths name the engine package, so the row is checked around them."""
    layer = engine_resources(engine)
    write_skill(layer, "python-coding")
    write_rule(layer / "rules" / "typing.md.j2", "python-typing", extra="skill: python-coding\n")
    [message] = _layout_messages(tmp_path, engine)
    row = _row("R5")
    for fragment in (
        "scoped rule 'python-typing' lies in the engine's rules/ directory ",
        ", which holds only always rules; move it to ",
        "/skills/python-coding/rules/python-typing.md.j2 and remove its 'skill:' line",
    ):
        assert fragment in message, f"the engine's R5 message changed: {message!r}"
        assert fragment in row, f"SPEC §12.6 row R5 must quote {fragment!r}"
