"""The shared readers behind each core skill's ``test_references.py`` (prU D47, D49)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from tests._attributions import MAPPING_SPECS_DIR
from tests._catalog import core_skill_root
from tests.core_skills._references import (
    backticked_ids,
    cross_skill_mentions,
    known_rule_ids,
    last_notes_bullets,
    names_a_rule,
    opens_with_table_of_contents,
    rule_source,
    skill_rule_ids,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog


def _planned_rule_ids(skill: str) -> set[str]:
    """The rule ids ``skill``'s mapping spec lists in its rule table."""
    spec = (MAPPING_SPECS_DIR / f"mapping-{skill}.md").read_text(encoding="utf-8")
    return set(re.findall(r"^\| `rules/([a-z0-9-]+)\.md", spec, re.MULTILINE))


def test_cross_skill_mentions_reads_a_plain_list() -> None:
    text = "python-architecture's arch-ports, arch-unit-of-work and arch-composition-root."

    mentions = cross_skill_mentions(text)

    assert mentions == {
        ("python-architecture", "arch-ports"),
        ("python-architecture", "arch-unit-of-work"),
        ("python-architecture", "arch-composition-root"),
    }


def test_cross_skill_mentions_strips_backticks_from_ids() -> None:
    text = "python-coding's `python-data-shapes` and `python-small-units`"

    mentions = cross_skill_mentions(text)

    assert mentions == {
        ("python-coding", "python-data-shapes"),
        ("python-coding", "python-small-units"),
    }


def test_cross_skill_mentions_ignores_a_name_with_no_mapping() -> None:
    mentions = cross_skill_mentions("the reviewer's first-pass and the team's style-guide")

    assert mentions == set()


def test_known_rule_ids_of_a_skill_not_yet_landed_are_its_planned_rules() -> None:
    skill = "python-documentation"
    assert not (core_skill_root(skill) / "rules").is_dir(), f"{skill} has landed; pick another"

    known = known_rule_ids(skill)

    assert known
    assert known == _planned_rule_ids(skill)


def test_known_rule_ids_of_a_landed_skill_include_what_it_ships() -> None:
    root = core_skill_root("design-patterns")

    assert skill_rule_ids(root) <= known_rule_ids("design-patterns")


def test_backticked_ids_take_only_hyphenated_tokens_in_backticks() -> None:
    assert backticked_ids("`design-strategy`, design-callback and `ruff`") == {"design-strategy"}


def test_names_a_rule_accepts_an_own_rule_or_another_skills_rule() -> None:
    rule_ids = {"design-strategy"}

    assert names_a_rule("see `design-strategy`", rule_ids)
    assert names_a_rule("python-coding's python-data-shapes", rule_ids)
    assert not names_a_rule("see `design-callback` and design-strategy", rule_ids)


def _skill_with_rule(tmp_path: Path, file_name: str, body: str) -> Path:
    """A skill root under ``tmp_path`` holding one rule file ``rules/<file_name>``."""
    (tmp_path / "rules").mkdir()
    (tmp_path / "rules" / file_name).write_text(body, encoding="utf-8")
    return tmp_path


def test_last_notes_bullets_reads_a_template_rule_up_to_the_next_section(tmp_path: Path) -> None:
    body = (
        "# R\n\n## Notes\n\n- one\n  wrapped\n- two: see a.md\n- three: see b.md\n\n## Next\n- x\n"
    )
    root = _skill_with_rule(tmp_path, "arch-r.md.j2", body)

    assert last_notes_bullets(root, "arch-r", 2) == ["- two: see a.md", "- three: see b.md"]


def test_last_notes_bullets_names_the_rule_when_it_has_too_few(tmp_path: Path) -> None:
    root = _skill_with_rule(tmp_path, "arch-r.md", "## Notes\n\n- only: see a.md\n")

    with pytest.raises(AssertionError, match="arch-r: 1 Notes bullets"):
        last_notes_bullets(root, "arch-r", 2)


def test_rule_source_names_the_rule_when_no_file_matches(tmp_path: Path) -> None:
    root = _skill_with_rule(tmp_path, "arch-other.md", "")

    with pytest.raises(AssertionError, match=r"arch-r: expected one rules/arch-r\.md\[\.j2\]"):
        rule_source(root, "arch-r")


def test_opens_with_table_of_contents_checks_only_the_first_section() -> None:
    assert opens_with_table_of_contents("# T\n\nIntro.\n\n## Contents\n\n- A\n\n## A\n")
    assert not opens_with_table_of_contents("# T\n\n## A\n\n## Contents\n")
