"""The sync summary line over two lockfiles' artifact digests (``sync._guidance_changes``)."""

from __future__ import annotations

from coding_agent_playbook.lockfile.model import ArtifactDigest, Lockfile
from coding_agent_playbook.sync._guidance_changes import (
    NO_GUIDANCE_CHANGED,
    GuidanceChanges,
    guidance_changes,
)


def _lock(*records: tuple[str, str, str]) -> Lockfile:
    return Lockfile(2, "0", "", artifacts=[ArtifactDigest(*record) for record in records])


def test_no_previous_lockfile_makes_every_artifact_new() -> None:
    current = _lock(("rule", "b", "1"), ("prompt", "a", "2"))

    assert guidance_changes(None, current) == GuidanceChanges(new=("prompt:a", "rule:b"))


def test_new_changed_and_removed_are_told_apart() -> None:
    previous = _lock(("rule", "kept", "1"), ("rule", "edited", "1"), ("hook", "gone", "1"))
    current = _lock(("rule", "kept", "1"), ("rule", "edited", "2"), ("skill", "added", "1"))

    changes = guidance_changes(previous, current)

    assert changes == GuidanceChanges(
        new=("skill:added",), changed=("rule:edited",), removed=("hook:gone",)
    )
    assert changes.line() == (
        "Guidance changed: new skill:added; changed rule:edited; removed hook:gone"
    )


def test_identical_digests_print_no_guidance_changed() -> None:
    same = _lock(("rule", "a", "1"))

    assert guidance_changes(same, same).line() == NO_GUIDANCE_CHANGED
