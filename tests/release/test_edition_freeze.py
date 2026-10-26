"""Writing and removing an edition's files, and checking them against their tag (#281 ticket 13).

The blobs of a fake tag live in :class:`FakeTagTree`: ``read_blob(commit, repo
path)`` and ``list_tree(commit, repo dir)`` answer from a dict, so no git runs
here (``test_freeze_real_git.py`` runs the real one).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath

import pytest

from coding_agent_playbook.release.edition import edition_file_problems
from coding_agent_playbook.release.edition_digests import (
    DIGESTS_FILENAME,
    NOTICE_KIND,
    EditionDigests,
    PinDigests,
    read_edition_digests,
)
from coding_agent_playbook.release.edition_freeze import (
    EDITIONS_README_FILENAME,
    CurrentPathFinder,
    EditionFreezeError,
    TagResolver,
    edition_tag_problems,
    graded_prompt_ids,
    remove_edition,
    write_edition,
    write_edition_digests,
)
from coding_agent_playbook.release.edition_notices import notice_paths
from coding_agent_playbook.release.manifest import (
    ManifestEntry,
    ReleaseManifest,
    release_dir,
    render_manifest,
)

TAG = "v9.9.9"
COMMIT = "c0ffee" * 6
PROMPT = "catalog/core/prompts/review.md"
RULE = "catalog/core/skills/python-coding/rules/typing.md"
ATTRIBUTIONS = "catalog/core/ATTRIBUTIONS.md"
LICENSE = "catalog/core/skills/python-coding/references/LICENSE.python-best-practices"
#: A reference that is not a license: freeze leaves it out.
REFERENCE = "catalog/core/skills/python-coding/references/error-flow.md"
#: Another skill's license: no graded file belongs to that skill.
OTHER_LICENSE = "catalog/core/skills/ml-data/references/LICENSE.python-best-practices"
PROMPT_BYTES = b"---\nid: review\nversion: 3\nincludes_rules:\n  - typing\n---\nFrozen review.\r\n"
RULE_BYTES = b"---\nid: typing\n---\nFrozen typing.\n"
LICENSE_BYTES = b"MIT License\r\n\r\nCopyright (c) upstream\r\n"
ATTRIBUTIONS_BYTES = b"# Attributions\n\nCredits for the vendored rules.\n"


def _entries() -> tuple[ManifestEntry, ...]:
    return (
        ManifestEntry("coding_agent_playbook", "prompt", "review", PROMPT, "d1"),
        ManifestEntry("coding_agent_playbook", "rule", "typing", RULE, "d2"),
    )


def _manifest(*graded: ManifestEntry) -> ReleaseManifest:
    return ReleaseManifest("9.9.9", "ba5e", graded or _entries(), ())


def _manifest_path(tag: str = TAG) -> str:
    return (release_dir(Path("catalog"), tag.removeprefix("v")) / "manifest.toml").as_posix()


@dataclass
class FakeTagTree:
    """The blobs of tag :data:`TAG` at :data:`COMMIT`, keyed by repo path."""

    blobs: dict[str, bytes] = field(
        default_factory=lambda: {
            PROMPT: PROMPT_BYTES,
            RULE: RULE_BYTES,
            ATTRIBUTIONS: ATTRIBUTIONS_BYTES,
            LICENSE: LICENSE_BYTES,
            REFERENCE: b"# Error flow\n",
            OTHER_LICENSE: b"another notice\n",
            _manifest_path(): render_manifest(_manifest()).encode(),
        }
    )

    def read_blob(self, commit: str, path: str) -> bytes | None:
        return self.blobs.get(path) if commit == COMMIT else None

    def list_tree(self, commit: str, directory: str) -> list[str]:
        if commit != COMMIT:
            return []
        return sorted(p for p in self.blobs if PurePosixPath(p).parent.as_posix() == directory)


def _frozen(tmp_path: Path, tag_tree: FakeTagTree | None = None) -> Path:
    tree = tag_tree or FakeTagTree()
    catalog = tmp_path / "catalog"
    write_edition(catalog, TAG, COMMIT, _manifest(), tree.read_blob, tree.list_tree)
    return catalog


def _root(catalog: Path) -> Path:
    return catalog / "editions" / TAG


def test_write_edition_copies_each_graded_file_byte_for_byte_under_core(tmp_path: Path) -> None:
    root = _root(_frozen(tmp_path))

    assert (root / "core/prompts/review.md").read_bytes() == PROMPT_BYTES
    assert (root / "core/skills/python-coding/rules/typing.md").read_bytes() == RULE_BYTES
    digests = read_edition_digests(root / DIGESTS_FILENAME)
    assert (digests.tag, digests.commit, digests.pins) == (TAG, COMMIT, ())
    graded = {(a.kind, a.id, a.path) for a in digests.artifacts if a.kind != NOTICE_KIND}
    assert graded == {
        ("prompt", "review", "core/prompts/review.md"),
        ("rule", "typing", "core/skills/python-coding/rules/typing.md"),
    }
    assert edition_file_problems(root) == []


def test_write_edition_copies_the_notices_the_graded_rules_need(tmp_path: Path) -> None:
    root = _root(_frozen(tmp_path))

    notices = [
        a for a in read_edition_digests(root / DIGESTS_FILENAME).artifacts if a.kind == NOTICE_KIND
    ]
    assert [(a.id, a.path) for a in notices] == [
        ("core/ATTRIBUTIONS.md", "core/ATTRIBUTIONS.md"),
        (LICENSE.removeprefix("catalog/"), LICENSE.removeprefix("catalog/")),
    ]
    assert (root / "core/ATTRIBUTIONS.md").read_bytes() == ATTRIBUTIONS_BYTES
    assert (root / LICENSE.removeprefix("catalog/")).read_bytes() == LICENSE_BYTES
    assert not (root / REFERENCE.removeprefix("catalog/")).exists()
    assert not (root / OTHER_LICENSE.removeprefix("catalog/")).exists()
    assert edition_file_problems(root) == []


def test_notice_paths_are_the_attributions_and_the_licenses_of_the_graded_skills() -> None:
    tree = FakeTagTree()

    assert notice_paths([PROMPT], COMMIT, tree.list_tree) == [ATTRIBUTIONS]
    assert notice_paths([PROMPT, RULE], COMMIT, tree.list_tree) == [ATTRIBUTIONS, LICENSE]


def test_a_tag_without_notices_freezes_the_graded_files_only(tmp_path: Path) -> None:
    tree = FakeTagTree()
    for path in (ATTRIBUTIONS, LICENSE):
        del tree.blobs[path]

    root = _root(_frozen(tmp_path, tree))

    kinds = {a.kind for a in read_edition_digests(root / DIGESTS_FILENAME).artifacts}
    assert kinds == {"prompt", "rule"}


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
    stray = _root(catalog) / "core/prompts/old.md"
    stray.write_text("old", encoding="utf-8")

    _frozen(tmp_path)

    assert not stray.exists()
    assert edition_file_problems(_root(catalog)) == []


def test_write_edition_digests_records_the_pins(tmp_path: Path) -> None:
    root = _root(_frozen(tmp_path))
    pin = PinDigests("review/pinned", "aa", "bb")

    write_edition_digests(root, read_edition_digests(root / DIGESTS_FILENAME), (pin,))

    assert read_edition_digests(root / DIGESTS_FILENAME).pins == (pin,)


def test_a_graded_file_missing_from_the_tag_refuses_naming_it(tmp_path: Path) -> None:
    tree = FakeTagTree()
    del tree.blobs[RULE]

    with pytest.raises(EditionFreezeError, match=f"tag {TAG} .* has no file {RULE}"):
        _frozen(tmp_path, tree)


def test_a_graded_entry_outside_the_engine_layer_refuses(tmp_path: Path) -> None:
    entry = ManifestEntry("x", "prompt", "p", "catalog/plugins/x/prompts/p.md", "d")
    tree = FakeTagTree()

    with pytest.raises(EditionFreezeError, match="catalog/core/"):
        write_edition(
            tmp_path / "catalog", TAG, COMMIT, _manifest(entry), tree.read_blob, tree.list_tree
        )


def test_graded_prompt_ids_are_the_manifests_graded_prompts() -> None:
    assert graded_prompt_ids(_manifest()) == ["review"]


def test_remove_edition_drops_the_readme_with_the_last_edition(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)

    assert remove_edition(catalog, TAG) is True

    assert not (catalog / "editions").exists()
    assert remove_edition(catalog, TAG) is False


def test_remove_edition_keeps_the_readme_while_another_edition_remains(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)
    tree = FakeTagTree()
    write_edition(catalog, "v9.9.8", COMMIT, _manifest(), tree.read_blob, tree.list_tree)

    remove_edition(catalog, TAG)

    assert (catalog / "editions" / EDITIONS_README_FILENAME).is_file()
    assert (catalog / "editions" / "v9.9.8").is_dir()


# --------------------------------------------------------------------------- #
# The CI check: every edition file equals its tag's blob
# --------------------------------------------------------------------------- #


def _resolve(tag: str) -> str | None:
    return COMMIT if tag == TAG else None


def _tag_problems(
    catalog: Path,
    tree: FakeTagTree | None = None,
    *,
    resolve: TagResolver = _resolve,
    current_path: CurrentPathFinder | None = None,
) -> list[str]:
    tag_tree = tree or FakeTagTree()
    return edition_tag_problems(
        catalog, resolve, tag_tree.read_blob, tag_tree.list_tree, current_path
    )


def _write_current(catalog: Path, repo_path: str) -> None:
    """Put the current text of ``repo_path`` in the checkout (``<tmp>/catalog/...``)."""
    path = catalog.parent / repo_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("current text\n", encoding="utf-8")


def test_an_untouched_edition_matches_its_tag(tmp_path: Path) -> None:
    assert _tag_problems(_frozen(tmp_path)) == []


def test_no_editions_directory_has_no_problems(tmp_path: Path) -> None:
    assert _tag_problems(tmp_path / "catalog") == []


def _hand_edit(catalog: Path, rel: str) -> Path:
    """Edit the edition's copy of ``rel`` and update its digest to match, as a careful hand would."""
    root = _root(catalog)
    edited = root / rel
    edited.write_bytes(edited.read_bytes() + b"tweak\n")
    digests = read_edition_digests(root / DIGESTS_FILENAME)
    write_edition_digests(root, _with_sha(digests, edited), ())
    return edited


def test_a_hand_edited_edition_file_names_the_current_file_to_edit(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)
    _write_current(catalog, PROMPT)
    # Even with a digests file updated to match, the tag's blob is the reference.
    edited = _hand_edit(catalog, "core/prompts/review.md")

    (problem,) = _tag_problems(catalog)

    assert str(edited) in problem
    assert f"tag {TAG}" in problem
    assert f"edit the current text in {PROMPT} instead" in problem


def test_a_hand_edit_of_a_moved_artifact_names_its_current_path(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)
    moved = "catalog/core/prompts/review.md.j2"
    lookups: list[tuple[str, str]] = []

    def current_path(kind: str, artifact_id: str) -> str | None:
        lookups.append((kind, artifact_id))
        return moved

    _hand_edit(catalog, "core/prompts/review.md")

    (problem,) = _tag_problems(catalog, current_path=current_path)

    assert lookups == [("prompt", "review")]
    assert f"edit the current text in {moved} instead" in problem
    assert f"in {PROMPT} instead" not in problem


def test_a_hand_edit_of_a_removed_artifact_says_to_restore_it(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)
    _hand_edit(catalog, "core/prompts/review.md")

    (problem,) = _tag_problems(catalog, current_path=lambda _kind, _id: None)

    assert "the current catalog has no prompt 'review'" in problem
    assert f"scripts/release.py freeze {TAG}" in problem


def test_a_hand_edited_notice_differs_from_its_tag(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)
    _write_current(catalog, LICENSE)
    edited = _hand_edit(catalog, LICENSE.removeprefix("catalog/"))

    (problem,) = _tag_problems(catalog)

    assert str(edited) in problem
    assert f"edit the current text in {LICENSE} instead" in problem


def _with_sha(digests: EditionDigests, path: Path) -> EditionDigests:
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    artifacts = tuple(
        replace(a, sha256=sha) if path.as_posix().endswith(a.path) else a for a in digests.artifacts
    )
    return replace(digests, artifacts=artifacts)


def test_an_artifact_dropped_from_the_digests_file_and_the_directory_is_a_problem(
    tmp_path: Path,
) -> None:
    catalog = _frozen(tmp_path)
    root = _root(catalog)
    digests = read_edition_digests(root / DIGESTS_FILENAME)
    kept = tuple(a for a in digests.artifacts if a.id != "typing")
    write_edition_digests(root, replace(digests, artifacts=kept), ())
    (root / "core/skills/python-coding/rules/typing.md").unlink()
    assert edition_file_problems(root) == []  # the offline check cannot see it

    (problem,) = _tag_problems(catalog)

    assert "lists no rule 'typing' at core/skills/python-coding/rules/typing.md" in problem
    assert f"unfreeze and freeze {TAG} again" in problem


def test_an_artifact_the_tag_does_not_grade_is_a_problem(tmp_path: Path) -> None:
    tree = FakeTagTree()
    catalog = _frozen(tmp_path, tree)
    tree.blobs[_manifest_path()] = render_manifest(_manifest(_entries()[1])).encode()

    problems = _tag_problems(catalog, tree)

    assert any("lists prompt 'review' at core/prompts/review.md" in p for p in problems)


def test_a_tag_without_a_manifest_is_a_problem(tmp_path: Path) -> None:
    tree = FakeTagTree()
    catalog = _frozen(tmp_path, tree)
    del tree.blobs[_manifest_path()]

    (problem,) = _tag_problems(catalog, tree)

    assert f"has no manifest at {_manifest_path()}" in problem


def test_a_digests_commit_other_than_the_tags_commit_is_a_problem(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)

    problems = _tag_problems(catalog, resolve=lambda _tag: "0ther" * 8)

    assert any(f"tag {TAG} names commit {'0ther' * 8}" in p for p in problems)


def test_a_missing_tag_is_a_problem_that_says_to_fetch_tags(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)

    (problem,) = _tag_problems(catalog, resolve=lambda _tag: None)

    assert f"no tag {TAG}" in problem
    assert "fetch" in problem


def test_a_missing_edition_file_is_a_problem(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)
    (_root(catalog) / "core/prompts/review.md").unlink()

    (problem,) = _tag_problems(catalog)

    assert "missing" in problem
