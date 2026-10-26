"""``release.edition``: the edition loader is closed-world and lenient (#281 ticket 09)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.release.edition import EditionError, edition_file_problems, load_edition
from coding_agent_playbook.release.edition_digests import (
    DIGESTS_FILENAME,
    EditionArtifact,
    EditionDigests,
    render_edition_digests,
)
from tests.edition_fixtures import (
    FROZEN_PROMPT_BODY,
    FROZEN_RULE_BODY,
    PROMPT_PATH,
    TAG,
    write_digests,
    write_edition_files,
)

if TYPE_CHECKING:
    from pathlib import Path


def _edition_root(tmp_path: Path) -> Path:
    root = write_edition_files(tmp_path / "catalog")
    write_digests(root)
    return root


def test_frozen_files_with_retired_keys_load(tmp_path: Path) -> None:
    edition = load_edition(_edition_root(tmp_path))

    assert edition.tag == TAG
    assert edition.prompt("review").template_body == FROZEN_PROMPT_BODY
    assert [rule.template_body for rule in edition.rules] == [FROZEN_RULE_BODY]


def test_a_rule_under_a_skill_belongs_to_that_skill(tmp_path: Path) -> None:
    (rule,) = load_edition(_edition_root(tmp_path)).rules

    assert rule.frontmatter.skill == "python-coding"


def test_a_prompt_resolves_only_by_an_id_the_edition_lists(tmp_path: Path) -> None:
    root = _edition_root(tmp_path)
    stray = root / "core/prompts/explain.md"
    stray.write_text(
        "---\nid: explain\nname: E\ndescription: d\nslash: explain\n---\nx\n", encoding="utf-8"
    )

    with pytest.raises(EditionError, match=r"no prompt 'explain'.*\['review'\]"):
        load_edition(root).prompt("explain")


def test_a_prompt_including_a_rule_the_edition_lacks_is_refused(tmp_path: Path) -> None:
    root = write_edition_files(tmp_path / "catalog")
    (root / "core/skills/python-coding/rules/typing.md").unlink()
    root.joinpath("core/skills/python-coding/rules/other.md").write_text(
        "---\nid: other\nname: O\ndescription: d\nscope: always\n---\nx\n", encoding="utf-8"
    )
    _rewrite_rule_entry(root)

    with pytest.raises(EditionError, match="'typing'"):
        load_edition(root).prompt("review")


def test_a_file_whose_id_differs_from_its_digests_entry_is_refused(tmp_path: Path) -> None:
    root = _edition_root(tmp_path)
    prompt = root / PROMPT_PATH
    prompt.write_text(
        prompt.read_text(encoding="utf-8").replace("id: review", "id: other"), encoding="utf-8"
    )

    with pytest.raises(EditionError, match="has id 'other'"):
        load_edition(root)


def test_a_missing_edition_names_its_directory(tmp_path: Path) -> None:
    with pytest.raises(EditionError, match="no edition"):
        load_edition(tmp_path / "catalog/editions/v0.0.0")


def test_files_matching_the_digests_file_have_no_problem(tmp_path: Path) -> None:
    assert edition_file_problems(_edition_root(tmp_path)) == []


def test_an_edited_frozen_file_is_named(tmp_path: Path) -> None:
    root = _edition_root(tmp_path)
    (root / PROMPT_PATH).write_text("edited\n", encoding="utf-8")

    (problem,) = edition_file_problems(root)

    assert PROMPT_PATH in problem
    assert "differs from its digest" in problem


def test_an_unlisted_and_a_missing_file_are_named(tmp_path: Path) -> None:
    root = _edition_root(tmp_path)
    (root / PROMPT_PATH).rename(root / "core/prompts/moved.md")

    problems = edition_file_problems(root)

    assert any("core/prompts/moved.md" in p and "not listed" in p for p in problems)
    assert any(PROMPT_PATH in p and "missing" in p for p in problems)


def _rewrite_rule_entry(root: Path) -> None:
    """Point the digests file at ``other.md`` (id ``other``) instead of ``typing.md``."""
    prompt = EditionArtifact("prompt", "review", PROMPT_PATH, "aa")
    rule = EditionArtifact("rule", "other", "core/skills/python-coding/rules/other.md", "bb")
    digests = EditionDigests(TAG, "f00d", (prompt, rule), ())
    (root / DIGESTS_FILENAME).write_text(render_edition_digests(digests), encoding="utf-8")
