"""``release.manifest``: the manifest round-trips and refuses a file of another shape."""

from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent_playbook.release.manifest import (
    ManifestEntry,
    ManifestError,
    ReleaseManifest,
    parse_manifest,
    read_manifest,
    release_dir,
    render_manifest,
)

_REVIEW = ManifestEntry(
    "coding_agent_playbook", "prompt", "review", "catalog/core/prompts/review.md.j2", "aa"
)
_RULE = ManifestEntry("coding_agent_playbook", "rule", "typing", "catalog/core/rules/t.md", "bb")


def _manifest() -> ReleaseManifest:
    return ReleaseManifest("9.9.9", "f00d", graded=(_REVIEW,), artifacts=(_RULE, _REVIEW))


def test_render_then_parse_gives_the_same_manifest_with_entries_sorted() -> None:
    parsed = parse_manifest(render_manifest(_manifest()))

    assert parsed == ReleaseManifest("9.9.9", "f00d", (_REVIEW,), (_REVIEW, _RULE))


def test_rendered_manifest_says_who_writes_it() -> None:
    assert render_manifest(_manifest()).startswith("# Written by `scripts/release.py prepare`")


def test_release_dir_is_under_the_catalog_releases_directory() -> None:
    assert release_dir(Path("catalog"), "9.9.9") == Path("catalog/releases/9.9.9")


@pytest.mark.parametrize(
    ("text", "names"),
    [
        ("schema_version = 2\nversion = 'x'\nbase = 'y'\n", "schema_version 2"),
        ("schema_version = 1\nversion = ''\nbase = 'y'\n", "version = ''"),
        ("schema_version = 1\nversion = 'x'\nbase = 'y'\nextra = 1\n", "unknown keys ['extra']"),
        (
            "schema_version = 1\nversion = 'x'\nbase = 'y'\n[[graded]]\nid = 'r'\n",
            "[[graded]] entry",
        ),
        ("schema_version = = 1", "malformed TOML"),
    ],
)
def test_parse_names_what_is_wrong(text: str, names: str) -> None:
    with pytest.raises(ManifestError, match=r".*") as caught:
        parse_manifest(text)

    assert names in str(caught.value)


def test_read_manifest_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / "manifest.toml"
    path.write_text("schema_version = 7\n", encoding="utf-8")

    with pytest.raises(ManifestError) as caught:
        read_manifest(path)

    assert str(path) in str(caught.value)
