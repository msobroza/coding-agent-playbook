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
    missing_sibling_guides,
    names_a_rule,
    rule_id_like_names,
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


def test_rule_id_like_names_takes_tokens_with_the_given_prefixes() -> None:
    text = "docs-changelog and sphinx-api-reference, not python-async"

    assert rule_id_like_names(text, ("docs", "sphinx")) == {
        "docs-changelog",
        "sphinx-api-reference",
    }


def test_rule_id_like_names_skips_file_names_and_longer_hyphenated_words() -> None:
    text = "see which-document.md and docs-guide.md; x-docs-changelog; docs-changelog"

    assert rule_id_like_names(text, ("docs", "which")) == {"docs-changelog"}


def test_rule_id_like_names_leaves_out_the_excluded_names() -> None:
    text = "python-coding's python-async; `playbook docs-check`"

    named = rule_id_like_names(text, ("python", "docs"), excluded={"python-coding", "docs-check"})

    assert named == {"python-async"}


def test_rule_id_like_names_takes_every_prefix_and_skips_file_and_excluded_names() -> None:
    text = "python-async, pydantic-boundaries; python-version-idioms.md and python-coding"

    named = rule_id_like_names(text, ("python", "pydantic"), {"python-coding"})

    assert named == {"python-async", "pydantic-boundaries"}


def _write_guides(root: Path, last_lines: dict[str, str]) -> None:
    (root / "references").mkdir()
    for path, last_line in last_lines.items():
        (root / path).write_text(f"# Guide\n\n{last_line}\n", encoding="utf-8")


def test_missing_sibling_guides_is_empty_when_the_last_line_names_each_sibling(
    tmp_path: Path,
) -> None:
    _write_guides(tmp_path, {"references/a.md": "See b.md.", "references/b.md": "See a.md."})

    assert (
        missing_sibling_guides(tmp_path, "references/a.md", ["references/a.md", "references/b.md"])
        == []
    )


def test_missing_sibling_guides_reports_an_unnamed_sibling_and_a_path_prefix(
    tmp_path: Path,
) -> None:
    _write_guides(tmp_path, {"references/a.md": "See references/c.md."})
    guides = ["references/a.md", "references/b.md", "references/c.md"]

    assert missing_sibling_guides(tmp_path, "references/a.md", guides) == ["b.md", "references/"]
