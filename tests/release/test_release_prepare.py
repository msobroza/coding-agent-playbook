"""``scripts/release.py prepare``: preflight, version, release files, commit, push and PR.

git, commitizen and ``playbook forge`` are one named fake (``FakeReleaseHost``)
and the catalog snapshot is a canned manifest, so no test starts a process, needs
those binaries or reads the shipped catalog.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.release.manifest import (
    ManifestEntry,
    ReleaseManifest,
    read_manifest,
    release_dir,
    render_manifest,
)
from release import COMMITIZEN_REQUIREMENT, main
from tests.release.release_fakes import BASE, PR_URL, FakeReleaseHost

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_CORE = "coding_agent_playbook"


def _entry(artifact_id: str, digest: str, kind: str = "prompt") -> ManifestEntry:
    return ManifestEntry(_CORE, kind, artifact_id, f"catalog/core/prompts/{artifact_id}.md", digest)


def _snapshot(
    graded_digest: str = "g1", other_digest: str = "o1"
) -> Callable[[str], ReleaseManifest]:
    def build(base: str) -> ReleaseManifest:
        graded = _entry("review", graded_digest)
        return ReleaseManifest("0", base, (graded,), (graded, _entry("refactor", other_digest)))

    return build


def _checkout(tmp_path: Path, version: str, previous: ReleaseManifest | None = None) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "x"\nversion = "{version}"\n', encoding="utf-8"
    )
    if previous is not None:
        target = release_dir(tmp_path / "catalog", previous.version)
        target.mkdir(parents=True)
        (target / "manifest.toml").write_text(render_manifest(previous), encoding="utf-8")
    return tmp_path


def _previous(version: str = "9.9.8") -> ReleaseManifest:
    graded = _entry("review", "g1")
    return ReleaseManifest(version, "0ld", (graded,), (graded, _entry("refactor", "o1")))


def _run(
    checkout: Path,
    host: FakeReleaseHost,
    *args: str,
    snapshot: Callable[[str], ReleaseManifest] | None = None,
) -> int:
    argv = ["prepare-checkout", "--base", BASE, *args]
    return main(argv, cwd=checkout, runner=host, snapshot=snapshot or _snapshot())


def _released(checkout: Path, version: str) -> tuple[ReleaseManifest, str]:
    target = release_dir(checkout / "catalog", version)
    return read_manifest(target / "manifest.toml"), (target / "notes.md").read_text("utf-8")


# --------------------------------------------------------------------------- #
# The first release
# --------------------------------------------------------------------------- #


def test_first_release_takes_the_explicit_version_and_opens_the_pull_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    checkout = _checkout(tmp_path, "9.9.9a0")
    host = FakeReleaseHost(log=[("feat: start (#1)", "")])

    assert _run(checkout, host, "--version", "9.9.9") == 0

    manifest, notes = _released(checkout, "9.9.9")
    assert (manifest.version, manifest.base) == ("9.9.9", BASE)
    assert notes.startswith("# Release 9.9.9\n\nFirst release.\n")
    assert "- #1" in notes
    assert 'version = "9.9.9"' in (checkout / "pyproject.toml").read_text("utf-8")
    assert host.ran("bump", "9.9.9", "--version-files-only", "--yes")
    assert host.ran("--from", COMMITIZEN_REQUIREMENT, "cz")
    assert host.ran("git", "log", "--first-parent")
    assert next(c for c in host.commands if "log" in c)[-1] == BASE  # all history
    assert host.ran("commit", "--quiet", "--message", "chore(release): v9.9.9")
    assert host.ran("push", "--force-with-lease", "origin", "HEAD:refs/heads/release/v9.9.9")
    assert host.ran("pr", "create", "--base", "main", "--title", "chore(release): v9.9.9")
    assert f"release: opened {PR_URL}" in capsys.readouterr().out


def test_first_release_without_a_version_is_refused_before_anything_is_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    checkout = _checkout(tmp_path, "9.9.9a0")
    host = FakeReleaseHost()

    assert _run(checkout, host) == 1

    assert "pass --version for the first release" in capsys.readouterr().err
    assert not (checkout / "catalog").exists()
    assert not host.ran("switch", "--force-create")


def test_the_release_commit_is_never_tagged(tmp_path: Path) -> None:
    host = FakeReleaseHost()

    _run(_checkout(tmp_path, "9.9.9a0"), host, "--version", "9.9.9")

    assert not [c for c in host.commands if c[:2] == ["git", "tag"] and "--list" not in c]
    assert not [
        c
        for c in host.commands
        if "cz" in c and "--version-files-only" not in c and "--get-next" not in c
    ]


# --------------------------------------------------------------------------- #
# Preflight refusals
# --------------------------------------------------------------------------- #


def test_a_merged_but_untagged_release_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = FakeReleaseHost(tags=["v9.9.8"])

    assert _run(_checkout(tmp_path, "9.9.9"), host) == 1

    err = capsys.readouterr().err
    assert "release v9.9.9 is merged but not tagged" in err
    assert not host.ran("bump")


def test_an_open_release_pull_request_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pulls = [{"number": 5, "head": "feature/x"}, {"number": 9, "head": "release/v9.9.9"}]
    host = FakeReleaseHost(tags=["v9.9.8"], open_pulls=pulls)

    assert _run(_checkout(tmp_path, "9.9.8", _previous()), host) == 1

    assert "release pull request #9 (release/v9.9.9) is still open" in capsys.readouterr().err


def test_a_checkout_off_the_base_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = FakeReleaseHost(head="0ther")

    assert _run(_checkout(tmp_path, "9.9.9a0"), host, "--version", "9.9.9") == 1

    assert f"not at the base {BASE}" in capsys.readouterr().err


def test_a_version_whose_tag_exists_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = FakeReleaseHost(tags=["v9.9.8", "v9.9.9"])

    assert _run(_checkout(tmp_path, "9.9.8", _previous()), host, "--version", "9.9.9") == 1

    assert "tag v9.9.9 already exists" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# The next version
# --------------------------------------------------------------------------- #


def test_commitizen_picks_the_version_when_the_graded_set_is_unchanged(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path, "9.9.8", _previous())
    host = FakeReleaseHost(tags=["v9.9.8"], cz_next={(): (0, "9.9.9\n")})

    assert _run(checkout, host, snapshot=_snapshot(other_digest="o2")) == 0

    assert host.ran("bump", "9.9.9", "--version-files-only", "--yes")
    assert not host.ran("--increment", "MINOR")
    assert next(c for c in host.commands if "log" in c)[-1] == f"v9.9.8..{BASE}"


def test_a_graded_set_change_raises_a_patch_to_a_minor(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path, "9.9.8", _previous())
    cz = {(): (0, "9.9.9\n"), ("--increment", "MINOR"): (0, "9.10.0\n")}
    host = FakeReleaseHost(tags=["v9.9.8"], cz_next=cz)

    assert _run(checkout, host, snapshot=_snapshot(graded_digest="g2")) == 0

    assert host.ran("bump", "9.10.0", "--version-files-only", "--yes")


def test_a_graded_set_change_releases_even_without_a_bump_worthy_commit(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path, "9.9.8", _previous())
    host = FakeReleaseHost(tags=["v9.9.8"], cz_next={("--increment", "MINOR"): (0, "9.10.0\n")})

    assert _run(checkout, host, snapshot=_snapshot(graded_digest="g2")) == 0

    manifest, _ = _released(checkout, "9.10.0")
    assert manifest.graded[0].digest == "g2"


def test_nothing_to_release_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    host = FakeReleaseHost(tags=["v9.9.8"])

    assert _run(_checkout(tmp_path, "9.9.8", _previous()), host) == 1

    assert "nothing to release" in capsys.readouterr().err
    assert not host.ran("switch", "--force-create")


# --------------------------------------------------------------------------- #
# The release files
# --------------------------------------------------------------------------- #


def test_notes_name_changed_artifacts_and_pull_requests_without_subjects_or_urls(
    tmp_path: Path,
) -> None:
    checkout = _checkout(tmp_path, "9.9.8", _previous())
    log = [
        ("feat(prompts)!: rename the review slash (#40)", ""),
        ("fix: typo in refactor (#41)", "Long body text."),
        ("chore: local tidy", ""),
    ]
    host = FakeReleaseHost(tags=["v9.9.8"], cz_next={(): (0, "9.10.0\n")}, log=log)

    assert _run(checkout, host, snapshot=_snapshot(other_digest="o2")) == 0

    _, notes = _released(checkout, "9.10.0")
    assert "## Breaking changes\n\n- #40\n" in notes
    assert "## Changed artifacts\n\n- prompt `refactor`\n" in notes
    assert "## Pull requests\n\n- #40\n- #41\n" in notes
    assert "typo" not in notes
    assert "rename" not in notes
    assert "://" not in notes
    assert host.ran("--body-file", str(release_dir(checkout / "catalog", "9.10.0") / "notes.md"))


# --------------------------------------------------------------------------- #
# Failure and re-run
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("step", ["commit", "push", "pr create"])
def test_a_failed_step_switches_back_to_the_base_and_drops_the_local_branch(
    tmp_path: Path, step: str, capsys: pytest.CaptureFixture[str]
) -> None:
    host = FakeReleaseHost(fail_on=step)

    assert _run(_checkout(tmp_path, "9.9.9a0"), host, "--version", "9.9.9") == 1

    assert f"{step} failed" in capsys.readouterr().err
    assert host.commands[-2] == ["git", "switch", "--detach", "--discard-changes", BASE]
    assert host.commands[-1] == ["git", "branch", "--delete", "--force", "release/v9.9.9"]


def test_a_release_commit_that_leaves_changes_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = FakeReleaseHost(status=" M stray.txt\n")

    assert _run(_checkout(tmp_path, "9.9.9a0"), host, "--version", "9.9.9") == 1

    assert "left changes behind" in capsys.readouterr().err
    assert not host.ran("push")


def test_a_rerun_after_a_failed_push_writes_the_same_files(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    _run(_checkout(first, "9.9.9a0"), FakeReleaseHost(fail_on="push"), "--version", "9.9.9")

    assert _run(_checkout(second, "9.9.9a0"), FakeReleaseHost(), "--version", "9.9.9") == 0

    assert _released(first, "9.9.9") == _released(second, "9.9.9")


def test_a_previous_release_without_a_manifest_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = FakeReleaseHost(tags=["v9.9.8"], cz_next={(): (0, "9.9.9\n")})

    assert _run(_checkout(tmp_path, "9.9.8"), host) == 1

    assert "release 9.9.8 has no manifest" in capsys.readouterr().err


def test_a_malformed_previous_manifest_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    checkout = _checkout(tmp_path, "9.9.8", _previous())
    manifest = release_dir(checkout / "catalog", "9.9.8") / "manifest.toml"
    manifest.write_text("schema_version = 7\n", encoding="utf-8")

    assert _run(checkout, FakeReleaseHost(tags=["v9.9.8"])) == 1

    assert "schema_version 7" in capsys.readouterr().err
