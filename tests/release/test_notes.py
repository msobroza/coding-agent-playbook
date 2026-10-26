"""``release.notes``: pull request numbers, a breaking section and artifact ids, nothing else."""

from __future__ import annotations

from coding_agent_playbook.release.changes import ArtifactChanges
from coding_agent_playbook.release.manifest import ManifestEntry
from coding_agent_playbook.release.notes import (
    CommitMessage,
    PullRequestRef,
    pull_requests,
    render_notes,
)


def test_pull_requests_reads_squash_and_merge_subjects_and_skips_the_rest() -> None:
    commits = [
        CommitMessage("feat(sync): name changed guidance (#309)"),
        CommitMessage("Merge pull request #266 from me/branch", "feat: x"),
        CommitMessage("fix: a local commit without a pull request"),
    ]

    assert pull_requests(commits) == [PullRequestRef(266), PullRequestRef(309)]


def test_a_bang_header_or_a_breaking_footer_marks_the_pull_request_breaking() -> None:
    commits = [
        CommitMessage("feat(catalog)!: drop version (#306)"),
        CommitMessage("refactor: move x (#7)", "Body.\n\nBREAKING CHANGE: x moved"),
        CommitMessage("fix: y (#8)", "mentions BREAKING CHANGE: mid-line? no, at line start"),
    ]

    assert pull_requests(commits) == [
        PullRequestRef(7, breaking=True),
        PullRequestRef(8, breaking=False),
        PullRequestRef(306, breaking=True),
    ]


def _entry(kind: str, artifact_id: str, layer: str = "coding_agent_playbook") -> ManifestEntry:
    return ManifestEntry(layer, kind, artifact_id, f"catalog/x/{artifact_id}", "d")


def test_notes_list_artifact_ids_and_pull_request_numbers_only() -> None:
    changes = ArtifactChanges(
        added=(_entry("skill", "tdd", "coding_agent_playbook.plugins.mattpocock_skills"),),
        changed=(_entry("prompt", "review"),),
        removed=(),
    )
    pulls = [PullRequestRef(301), PullRequestRef(306, breaking=True)]

    notes = render_notes("9.9.9", previous="9.9.8", changes=changes, pulls=pulls)

    assert notes == (
        "# Release 9.9.9\n\nChanges since 9.9.8.\n\n"
        "## Breaking changes\n\n- #306\n\n"
        "## Changed artifacts\n\n- prompt `review`\n\n"
        "## Added artifacts\n\n- skill `tdd` (mattpocock_skills)\n\n"
        "## Removed artifacts\n\nNone.\n\n"
        "## Pull requests\n\n- #301\n- #306\n"
    )
    assert "http" not in notes


def test_first_release_notes_have_no_artifact_diff() -> None:
    notes = render_notes("9.9.9", previous=None, changes=None, pulls=[PullRequestRef(1)])

    assert notes == (
        "# Release 9.9.9\n\nFirst release.\n\n"
        "## Breaking changes\n\nNone.\n\n## Pull requests\n\n- #1\n"
    )
