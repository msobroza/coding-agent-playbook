"""``scripts/release.py tag``: an annotated, immutable tag on exactly the release commit.

By hand (no flag) it reads CI on the release commit through ``gh``; the CI tag
job passes ``--tested-commit $GITHUB_SHA`` instead, since that job runs only
after the tests passed on that commit. git and ``gh`` are the named fake
``FakeTagHost``, so no test starts a process or touches a real tag.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from coding_agent_playbook.release.manifest import ReleaseManifest, render_manifest
from coding_agent_playbook.release.tagging import TEST_JOB
from release import main
from tests.release.release_fakes import FakeCommit, FakeTagHost

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

VERSION = "9.9.9"
TAG = f"v{VERSION}"
LATER = "1a7e" * 10
RELEASE = "re1e" * 10
BASE = "ba5e" * 10
OLDER = "01de" * 10
GREEN = json.dumps(
    {"jobs": [{"name": f"{TEST_JOB} (3.12)", "status": "completed", "conclusion": "success"}]}
)
RED = json.dumps(
    {"jobs": [{"name": f"{TEST_JOB} (3.12)", "status": "completed", "conclusion": "failure"}]}
)


def _manifest(base: str = BASE) -> str:
    return render_manifest(ReleaseManifest(VERSION, base, (), ()))


def _host(*, base: str = BASE, version: str = VERSION, **kwargs: object) -> FakeTagHost:
    """main: a later commit, the release commit, its parent at the previous version."""
    history = [
        FakeCommit(LATER, version),
        FakeCommit(RELEASE, version, _manifest(base)),
        FakeCommit(BASE, "9.9.8"),
        FakeCommit(OLDER, "9.9.7"),
    ]
    return FakeTagHost(history=history, **kwargs)  # type: ignore[arg-type]


def _tag(host: FakeTagHost, tmp_path: Path, *args: str) -> int:
    return main(["tag", *args], cwd=tmp_path, runner=host)


def _tagged(host: FakeTagHost) -> bool:
    return host.ran("git", "tag", "--annotate")


def _pushed(host: FakeTagHost) -> bool:
    return any(command[:2] == ["git", "push"] for command in host.commands)


def test_tag_creates_an_annotated_tag_on_the_release_commit_and_pushes_it_explicitly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = _host(jobs=GREEN)

    assert _tag(host, tmp_path) == 0

    assert host.commands[0] == ["git", "fetch", "--tags", "origin"]
    tag = next(c for c in host.commands if c[:2] == ["git", "tag"])
    assert tag[-2:] == [TAG, RELEASE]  # the release commit, not origin/main's head
    assert "--annotate" in tag
    assert host.ran("git", "push", "origin", f"refs/tags/{TAG}:refs/tags/{TAG}")
    assert not any("-f" in c or "--force" in c for c in host.commands)
    assert host.ran("gh", "run", "list", "--commit", RELEASE)
    assert f"tagged {TAG} at {RELEASE}" in capsys.readouterr().out


def test_tag_refuses_when_the_parent_is_not_the_recorded_base(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = _host(base=OLDER, jobs=GREEN)

    assert _tag(host, tmp_path) == 1

    assert "re-run prepare" in capsys.readouterr().err
    assert not _tagged(host)
    assert not _pushed(host)


def test_tag_refuses_when_ci_on_the_release_commit_is_red(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = _host(jobs=RED)

    assert _tag(host, tmp_path) == 1

    assert f"CI on {RELEASE} is not green" in capsys.readouterr().err
    assert not _tagged(host)
    assert not _pushed(host)


def test_tag_is_a_no_op_when_the_tag_already_points_at_the_release_commit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = _host(remote_tags={TAG: RELEASE}, local_tags={TAG: RELEASE})

    assert _tag(host, tmp_path) == 0

    assert f"{TAG} already points at {RELEASE}" in capsys.readouterr().out
    assert not _tagged(host)
    assert not _pushed(host)


def test_tag_refuses_when_the_tag_points_elsewhere(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = _host(remote_tags={TAG: LATER}, local_tags={TAG: LATER}, jobs=GREEN)

    assert _tag(host, tmp_path) == 1

    assert "never moved" in capsys.readouterr().err
    assert not _tagged(host)
    assert not _pushed(host)


def test_tag_only_pushes_a_local_annotated_tag_already_at_the_release_commit(
    tmp_path: Path,
) -> None:
    host = _host(local_tags={TAG: RELEASE}, jobs=GREEN)

    assert _tag(host, tmp_path) == 0

    assert not _tagged(host)
    assert host.remote_tags == {TAG: RELEASE}


def test_tag_refuses_a_release_commit_without_its_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = _host(jobs=GREEN)
    host.history[1] = FakeCommit(RELEASE, VERSION)

    assert _tag(host, tmp_path) == 1

    assert f"catalog/releases/{VERSION}/manifest.toml" in capsys.readouterr().err
    assert not _tagged(host)


def test_tag_has_nothing_to_do_on_a_pre_release_version(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = _host(version="9.9.9a0")

    assert _tag(host, tmp_path) == 0

    assert "nothing to tag" in capsys.readouterr().out
    assert not _tagged(host)


def test_a_failed_push_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    host = _host(jobs=GREEN, fail_on="git push")

    assert _tag(host, tmp_path) == 1

    assert "git push origin" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# The CI tag job: --tested-commit
# --------------------------------------------------------------------------- #


def test_the_ci_job_tags_its_own_commit_without_asking_the_forge(tmp_path: Path) -> None:
    host = _host()
    host.history.pop(0)  # the push's commit is the release commit

    assert _tag(host, tmp_path, "--tested-commit", RELEASE) == 0

    assert host.remote_tags == {TAG: RELEASE}
    assert not any(command[0] == "gh" for command in host.commands)
    assert not host.ran("rev-parse", "--verify", "origin/main^{commit}")


def test_the_ci_job_leaves_a_release_commit_it_did_not_test_to_that_commits_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = _host()

    assert _tag(host, tmp_path, "--tested-commit", LATER) == 0

    assert f"not this run's commit {LATER}" in capsys.readouterr().out
    assert not _tagged(host)
    assert not _pushed(host)
