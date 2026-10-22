"""The shared readers behind each core skill's ``test_references.py`` (prU D47, D49)."""

from __future__ import annotations

import re

import pytest

from tests._attributions import MAPPING_SPECS_DIR
from tests._catalog import core_skill_root
from tests.core_skills._references import (
    backticked_ids,
    cross_skill_mentions,
    known_rule_ids,
    names_a_rule,
    shipped_rule_ids,
)

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

    assert shipped_rule_ids(root) <= known_rule_ids("design-patterns")


def test_backticked_ids_take_only_hyphenated_tokens_in_backticks() -> None:
    assert backticked_ids("`design-strategy`, design-callback and `ruff`") == {"design-strategy"}


def test_names_a_rule_accepts_an_own_rule_or_another_skills_rule() -> None:
    rule_ids = {"design-strategy"}

    assert names_a_rule("see `design-strategy`", rule_ids)
    assert names_a_rule("python-coding's python-data-shapes", rule_ids)
    assert not names_a_rule("see `design-callback` and design-strategy", rule_ids)
