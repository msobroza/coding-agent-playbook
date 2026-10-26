"""``release.changes`` and ``release.versions``: the digest diff and the bump rules."""

from __future__ import annotations

import pytest

from coding_agent_playbook.release.changes import diff_entries, graded_set_changed
from coding_agent_playbook.release.manifest import ManifestEntry, ReleaseManifest
from coding_agent_playbook.release.versions import (
    VersionError,
    check_next_version,
    is_release_tag,
    raises_minor,
    release_tag,
)


def _entry(artifact_id: str, digest: str) -> ManifestEntry:
    return ManifestEntry("coding_agent_playbook", "rule", artifact_id, f"p/{artifact_id}", digest)


def test_diff_names_added_changed_and_removed_entries() -> None:
    before = [_entry("kept", "1"), _entry("edited", "1"), _entry("gone", "1")]
    after = [_entry("kept", "1"), _entry("edited", "2"), _entry("new", "1")]

    changes = diff_entries(before, after)

    assert changes.added == (_entry("new", "1"),)
    assert changes.changed == (_entry("edited", "2"),)
    assert changes.removed == (_entry("gone", "1"),)
    assert not changes.is_empty


def test_graded_set_changed_compares_only_the_graded_entries() -> None:
    previous = ReleaseManifest("9.9.8", "a", (_entry("g", "1"),), (_entry("other", "1"),))
    same_graded = ReleaseManifest("9.9.9", "b", (_entry("g", "1"),), (_entry("other", "2"),))
    new_graded = ReleaseManifest("9.9.9", "b", (_entry("g", "2"),), (_entry("other", "1"),))

    assert graded_set_changed(previous, same_graded) is False
    assert graded_set_changed(previous, new_graded) is True
    assert graded_set_changed(None, same_graded) is True


def test_tags_are_v_prefixed_final_releases() -> None:
    assert release_tag("9.9.9") == "v9.9.9"
    assert [is_release_tag(n) for n in ("v9.9.9", "v9.9.9a0", "9.9.9", "vx")] == [
        True,
        False,
        False,
        False,
    ]


@pytest.mark.parametrize(
    ("current", "proposed", "expected"),
    [("9.9.9", "9.9.10", False), ("9.9.9", "9.10.0", True), ("9.9.9", "10.0.0", True)],
)
def test_raises_minor(current: str, proposed: str, expected: bool) -> None:
    assert raises_minor(current, proposed) is expected


def test_check_next_version_accepts_a_final_release_above_the_current() -> None:
    assert check_next_version("9.9.9a0", "9.9.9") == "9.9.9"


@pytest.mark.parametrize(
    ("proposed", "message"),
    [
        ("9.9.8", "not above the current version"),
        ("9.9.10a1", "not a final X.Y.Z release"),
        ("9.10", "not a final X.Y.Z release"),
        ("nine", "not a PEP 440 version"),
    ],
)
def test_check_next_version_refuses(proposed: str, message: str) -> None:
    with pytest.raises(VersionError, match=message):
        check_next_version("9.9.9", proposed)
