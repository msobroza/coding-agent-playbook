"""``release.edition_digests``: an edition's digests file round-trips and refuses other shapes."""

from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent_playbook.release.edition_digests import (
    EditionArtifact,
    EditionDigests,
    EditionDigestsError,
    PinDigests,
    edition_dir,
    parse_edition_digests,
    read_edition_digests,
    render_edition_digests,
)

_PROMPT = EditionArtifact("prompt", "review", "core/prompts/review.md.j2", "aa")
_RULE = EditionArtifact("rule", "typing", "core/rules/typing.md", "bb")
_PIN = PinDigests("review/spot-the-bug", "cc", "dd")


def _digests() -> EditionDigests:
    return EditionDigests("v9.9.9", "f00d", artifacts=(_RULE, _PROMPT), pins=(_PIN,))


def test_render_then_parse_gives_the_same_digests_with_entries_sorted() -> None:
    parsed = parse_edition_digests(render_edition_digests(_digests()))

    assert parsed == EditionDigests("v9.9.9", "f00d", (_PROMPT, _RULE), (_PIN,))


def test_rendered_digests_file_says_it_is_never_edited_by_hand() -> None:
    assert "Never edit it by hand" in render_edition_digests(_digests()).splitlines()[0]


def test_edition_dir_is_under_the_catalog_editions_directory() -> None:
    assert edition_dir(Path("catalog"), "v9.9.9") == Path("catalog/editions/v9.9.9")


def test_an_artifact_path_outside_the_edition_core_copy_is_refused() -> None:
    text = render_edition_digests(_digests()).replace("core/rules/typing.md", "../core/x.md")

    with pytest.raises(EditionDigestsError, match=r"'\.\./core/x\.md'"):
        parse_edition_digests(text)


def test_an_unknown_key_is_named() -> None:
    text = render_edition_digests(_digests()) + 'extra = "x"\n'

    with pytest.raises(EditionDigestsError, match="extra"):
        parse_edition_digests(text)


def test_a_duplicate_artifact_id_is_refused() -> None:
    twice = EditionDigests("v9.9.9", "f00d", (_PROMPT, _PROMPT), ())

    with pytest.raises(EditionDigestsError, match="'review'"):
        parse_edition_digests(render_edition_digests(twice))


def test_reading_a_missing_file_names_the_path(tmp_path: Path) -> None:
    with pytest.raises(EditionDigestsError, match=r"digests\.toml"):
        read_edition_digests(tmp_path / "digests.toml")
