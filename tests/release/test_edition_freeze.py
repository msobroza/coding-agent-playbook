"""Writing and removing an edition's files, and checking them against their tag (#281 ticket 13).

The blobs of a fake tag are a dict: ``read_blob(commit, repo path)`` answers from
it, so no git runs here (``test_freeze_real_git.py`` runs the real one).
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.release.edition import edition_file_problems
from coding_agent_playbook.release.edition_digests import (
    DIGESTS_FILENAME,
    EditionDigests,
    PinDigests,
    read_edition_digests,
)
from coding_agent_playbook.release.edition_freeze import (
    EDITIONS_README_FILENAME,
    EditionFreezeError,
    edition_tag_problems,
    graded_prompt_ids,
    remove_edition,
    write_edition,
    write_edition_digests,
)
from coding_agent_playbook.release.manifest import ManifestEntry, ReleaseManifest

if TYPE_CHECKING:
    from pathlib import Path

TAG = "v9.9.9"
COMMIT = "c0ffee" * 6
PROMPT = "catalog/core/prompts/review.md"
RULE = "catalog/core/skills/python-coding/rules/typing.md"
PROMPT_BYTES = b"---\nid: review\nversion: 3\n---\nFrozen review.\r\n"
RULE_BYTES = b"---\nid: typing\n---\nFrozen typing.\n"
BLOBS = {(COMMIT, PROMPT): PROMPT_BYTES, (COMMIT, RULE): RULE_BYTES}


def _manifest(*graded: ManifestEntry) -> ReleaseManifest:
    entries = graded or (
        ManifestEntry("coding_agent_playbook", "prompt", "review", PROMPT, "d1"),
        ManifestEntry("coding_agent_playbook", "rule", "typing", RULE, "d2"),
    )
    return ReleaseManifest("9.9.9", "ba5e", entries, ())


def _read_blob(commit: str, path: str) -> bytes | None:
    return BLOBS.get((commit, path))


def _frozen(tmp_path: Path) -> Path:
    catalog = tmp_path / "catalog"
    write_edition(catalog, TAG, COMMIT, _manifest(), _read_blob)
    return catalog


def test_write_edition_copies_each_graded_file_byte_for_byte_under_core(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)

    root = catalog / "editions" / TAG
    assert (root / "core/prompts/review.md").read_bytes() == PROMPT_BYTES
    assert (root / "core/skills/python-coding/rules/typing.md").read_bytes() == RULE_BYTES
    digests = read_edition_digests(root / DIGESTS_FILENAME)
    assert (digests.tag, digests.commit, digests.pins) == (TAG, COMMIT, ())
    assert {(a.kind, a.id, a.path) for a in digests.artifacts} == {
        ("prompt", "review", "core/prompts/review.md"),
        ("rule", "typing", "core/skills/python-coding/rules/typing.md"),
    }
    assert edition_file_problems(root) == []


def test_the_editions_readme_says_the_directory_is_generated_and_where_to_edit(
    tmp_path: Path,
) -> None:
    readme = (_frozen(tmp_path) / "editions" / EDITIONS_README_FILENAME).read_text("utf-8")

    assert "scripts/release.py freeze" in readme
    assert "catalog/core/" in readme


def test_re_freezing_replaces_a_stale_copy_and_drops_files_no_longer_graded(
    tmp_path: Path,
) -> None:
    catalog = _frozen(tmp_path)
    stray = catalog / "editions" / TAG / "core/prompts/old.md"
    stray.write_text("old", encoding="utf-8")

    write_edition(catalog, TAG, COMMIT, _manifest(), _read_blob)

    assert not stray.exists()
    assert edition_file_problems(catalog / "editions" / TAG) == []


def test_write_edition_digests_records_the_pins(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)
    root = catalog / "editions" / TAG
    pin = PinDigests("review/pinned", "aa", "bb")

    write_edition_digests(root, read_edition_digests(root / DIGESTS_FILENAME), (pin,))

    assert read_edition_digests(root / DIGESTS_FILENAME).pins == (pin,)


def test_a_graded_file_missing_from_the_tag_refuses_naming_it(tmp_path: Path) -> None:
    def missing(commit: str, path: str) -> bytes | None:
        return None if path == RULE else _read_blob(commit, path)

    with pytest.raises(EditionFreezeError, match=f"tag {TAG} .* has no file {RULE}"):
        write_edition(tmp_path / "catalog", TAG, COMMIT, _manifest(), missing)


def test_a_graded_entry_outside_the_engine_layer_refuses(tmp_path: Path) -> None:
    entry = ManifestEntry("x", "prompt", "p", "catalog/plugins/x/prompts/p.md", "d")

    with pytest.raises(EditionFreezeError, match="catalog/core/"):
        write_edition(tmp_path / "catalog", TAG, COMMIT, _manifest(entry), _read_blob)


def test_graded_prompt_ids_are_the_manifests_graded_prompts() -> None:
    assert graded_prompt_ids(_manifest()) == ["review"]


def test_remove_edition_drops_the_readme_with_the_last_edition(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)

    assert remove_edition(catalog, TAG) is True

    assert not (catalog / "editions").exists()
    assert remove_edition(catalog, TAG) is False


def test_remove_edition_keeps_the_readme_while_another_edition_remains(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)
    write_edition(catalog, "v9.9.8", COMMIT, _manifest(), _read_blob)

    remove_edition(catalog, TAG)

    assert (catalog / "editions" / EDITIONS_README_FILENAME).is_file()
    assert (catalog / "editions" / "v9.9.8").is_dir()


# --------------------------------------------------------------------------- #
# The CI check: every edition file equals its tag's blob
# --------------------------------------------------------------------------- #


def _resolve(tag: str) -> str | None:
    return COMMIT if tag == TAG else None


def test_an_untouched_edition_matches_its_tag(tmp_path: Path) -> None:
    assert edition_tag_problems(_frozen(tmp_path), _resolve, _read_blob) == []


def test_no_editions_directory_has_no_problems(tmp_path: Path) -> None:
    assert edition_tag_problems(tmp_path / "catalog", _resolve, _read_blob) == []


def test_a_hand_edited_edition_file_names_the_current_file_to_edit(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)
    edited = catalog / "editions" / TAG / "core/prompts/review.md"
    edited.write_bytes(PROMPT_BYTES + b"tweak\n")
    # Even with a digests file updated to match, the tag's blob is the reference.
    root = catalog / "editions" / TAG
    digests = read_edition_digests(root / DIGESTS_FILENAME)
    write_edition_digests(root, _with_sha(digests, edited), ())

    (problem,) = edition_tag_problems(catalog, _resolve, _read_blob)

    assert str(edited) in problem
    assert f"tag {TAG}" in problem
    assert f"edit the current text in {PROMPT} instead" in problem


def _with_sha(digests: EditionDigests, path: Path) -> EditionDigests:
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    artifacts = tuple(
        replace(a, sha256=sha) if path.as_posix().endswith(a.path) else a for a in digests.artifacts
    )
    return replace(digests, artifacts=artifacts)


def test_a_digests_commit_other_than_the_tags_commit_is_a_problem(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)

    problems = edition_tag_problems(catalog, lambda _tag: "0ther" * 8, _read_blob)

    assert any(f"tag {TAG} names commit {'0ther' * 8}" in p for p in problems)


def test_a_missing_tag_is_a_problem_that_says_to_fetch_tags(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)

    (problem,) = edition_tag_problems(catalog, lambda _tag: None, _read_blob)

    assert f"no tag {TAG}" in problem
    assert "fetch" in problem


def test_a_missing_edition_file_is_a_problem(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)
    (catalog / "editions" / TAG / "core/prompts/review.md").unlink()

    (problem,) = edition_tag_problems(catalog, _resolve, _read_blob)

    assert "missing" in problem
