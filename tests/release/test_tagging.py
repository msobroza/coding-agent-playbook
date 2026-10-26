"""``release.tagging``: which commit a release tag goes on, and when tagging refuses.

The decisions are pure: the release commit from the first-parent revisions of
``pyproject.toml``, the base check against the release's manifest, the test
jobs' verdict and what to do with the tag given where it already points.
"""

from __future__ import annotations

import json

import pytest

from coding_agent_playbook.release.manifest import ReleaseManifest
from coding_agent_playbook.release.tagging import (
    TEST_JOB,
    BaseMoved,
    Revision,
    TagAction,
    TagRefusal,
    TagState,
    check_base,
    check_tests_passed,
    find_release_commit,
    parse_jobs,
    tag_action,
    taggable,
)

VERSION = "9.9.9"
RELEASE = "re1e" * 10
BASE = "ba5e" * 10
OTHER = "07e7" * 10


def _manifest(base: str = BASE, version: str = VERSION) -> ReleaseManifest:
    return ReleaseManifest(version, base, (), ())


# --------------------------------------------------------------------------- #
# taggable: only a final X.Y.Z version is ever tagged
# --------------------------------------------------------------------------- #


def test_a_final_version_is_taggable_and_a_pre_release_is_not() -> None:
    assert taggable(VERSION)
    assert not taggable("9.9.9a0")
    assert not taggable("9.9")


# --------------------------------------------------------------------------- #
# find_release_commit: the commit that introduced the version, never HEAD
# --------------------------------------------------------------------------- #


def test_the_release_commit_is_the_one_that_introduced_the_version() -> None:
    revisions = [
        Revision("later" * 8, VERSION),  # a later dependency bump keeps the version
        Revision(RELEASE, VERSION),
        Revision(OTHER, "9.9.8"),
        Revision("older" * 8, "9.9.7"),
    ]

    assert find_release_commit(VERSION, revisions) == RELEASE


def test_the_walk_stops_at_the_previous_version() -> None:
    def revisions() -> object:
        yield Revision(RELEASE, VERSION)
        yield Revision(OTHER, "9.9.8")
        raise AssertionError("read past the previous version")

    assert find_release_commit(VERSION, revisions()) == RELEASE  # type: ignore[arg-type]


def test_a_commit_without_a_readable_version_ends_the_walk() -> None:
    revisions = [Revision(RELEASE, VERSION), Revision(OTHER, None)]

    assert find_release_commit(VERSION, revisions) == RELEASE


def test_no_revision_at_the_version_is_a_refusal() -> None:
    with pytest.raises(TagRefusal, match=r"no first-parent commit .* 9\.9\.9"):
        find_release_commit(VERSION, [Revision(OTHER, "9.9.8")])


def test_a_version_that_never_changed_is_a_refusal() -> None:
    with pytest.raises(TagRefusal, match="never changed"):
        find_release_commit(VERSION, [Revision(RELEASE, VERSION), Revision(OTHER, VERSION)])


# --------------------------------------------------------------------------- #
# check_base: the release commit's parent is the base prepare recorded
# --------------------------------------------------------------------------- #


def test_a_parent_equal_to_the_recorded_base_passes() -> None:
    check_base(VERSION, RELEASE, BASE, _manifest())


def test_a_base_mismatch_is_a_refusal_naming_both_commits() -> None:
    with pytest.raises(BaseMoved, match=f"{OTHER}.*{BASE}.*prepare --version"):
        check_base(VERSION, RELEASE, OTHER, _manifest())


def test_a_manifest_of_another_version_is_a_refusal() -> None:
    with pytest.raises(TagRefusal, match=r"records version 9\.9\.8"):
        check_base(VERSION, RELEASE, BASE, _manifest(version="9.9.8"))


# --------------------------------------------------------------------------- #
# check_tests_passed: every test job on the release commit succeeded
# --------------------------------------------------------------------------- #


def _jobs(*rows: tuple[str, str, str]) -> str:
    jobs = [{"name": n, "status": s, "conclusion": c} for n, s, c in rows]
    return json.dumps({"jobs": jobs})


def test_green_test_jobs_pass_whatever_the_other_jobs_say() -> None:
    jobs = parse_jobs(
        _jobs(
            (f"{TEST_JOB} (3.12)", "completed", "success"),
            (f"{TEST_JOB} (3.13)", "completed", "success"),
            ("tag-release", "completed", "failure"),
        )
    )

    check_tests_passed(RELEASE, jobs)


def test_a_red_test_job_is_a_refusal() -> None:
    jobs = parse_jobs(
        _jobs(
            (f"{TEST_JOB} (3.12)", "completed", "success"),
            (f"{TEST_JOB} (3.13)", "completed", "failure"),
        )
    )

    with pytest.raises(TagRefusal, match=r"test \(3\.13\) .*failure"):
        check_tests_passed(RELEASE, jobs)


def test_a_running_test_job_is_a_refusal() -> None:
    jobs = parse_jobs(_jobs((f"{TEST_JOB} (3.12)", "in_progress", "")))

    with pytest.raises(TagRefusal, match="in_progress"):
        check_tests_passed(RELEASE, jobs)


def test_no_test_job_is_a_refusal() -> None:
    with pytest.raises(TagRefusal, match="no test job"):
        check_tests_passed(RELEASE, parse_jobs(_jobs(("wheel-smoke", "completed", "success"))))


def test_jobs_text_of_the_wrong_shape_is_a_refusal() -> None:
    with pytest.raises(TagRefusal, match="expected"):
        parse_jobs('{"runs": []}')


# --------------------------------------------------------------------------- #
# tag_action: idempotent and immutable
# --------------------------------------------------------------------------- #


def test_no_tag_anywhere_creates_it() -> None:
    assert tag_action(VERSION, RELEASE, TagState(remote=None, local=None)) is TagAction.CREATE


def test_a_remote_tag_at_the_release_commit_is_a_no_op() -> None:
    state = TagState(remote=RELEASE, local=None)

    assert tag_action(VERSION, RELEASE, state) is TagAction.NONE


def test_a_local_annotated_tag_at_the_release_commit_is_only_pushed() -> None:
    state = TagState(remote=None, local=RELEASE, local_annotated=True)

    assert tag_action(VERSION, RELEASE, state) is TagAction.PUSH


def test_a_remote_tag_elsewhere_is_a_refusal() -> None:
    with pytest.raises(TagRefusal, match=f"v9.9.9 already points at {OTHER}.*never moved"):
        tag_action(VERSION, RELEASE, TagState(remote=OTHER, local=OTHER))


def test_a_local_tag_elsewhere_is_a_refusal() -> None:
    with pytest.raises(TagRefusal, match=f"local tag v9.9.9 points at {OTHER}"):
        tag_action(VERSION, RELEASE, TagState(remote=None, local=OTHER, local_annotated=True))


def test_a_local_lightweight_tag_is_a_refusal() -> None:
    with pytest.raises(TagRefusal, match="lightweight"):
        tag_action(VERSION, RELEASE, TagState(remote=None, local=RELEASE, local_annotated=False))
