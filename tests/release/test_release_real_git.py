"""``scripts/release.py`` against a real git and a real bare ``origin`` (PR #314 review).

``FakeTagHost`` answers what the tests assume git prints; these tests pin what
git really prints. Two findings motivated them: ``git ls-remote`` with an exact
ref pattern omits the peeled ``^{}`` line (so a pushed annotated tag looked like
it pointed elsewhere), and a release whose base moved needs a recovery that
``prepare`` accepts. commitizen and ``playbook forge`` stay faked
(``FakeCzForgeOverRealGit``); every git command is the real one, isolated by
the ``real_git`` fixture.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from coding_agent_playbook.release.manifest import (
    ReleaseManifest,
    parse_manifest,
    release_dir,
    render_manifest,
)
from release import Completed, main, run_process

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from pathlib import Path

    import pytest

PR_URL = "https://forge.example/pulls/88"


@dataclass
class FakeCzForgeOverRealGit:
    """Real git for ``git …``; ``cz bump <v> --version-files-only`` and ``forge pr`` faked."""

    commands: list[list[str]] = field(default_factory=list)

    def __call__(
        self, argv: Sequence[str], *, cwd: Path, env: Mapping[str, str] | None = None
    ) -> Completed:
        command = list(argv)
        self.commands.append(command)
        if "cz" in command:
            return self._cz_bump(command[-3], cwd)
        if "forge" in command:
            return Completed(0, "[]" if "list" in command else f"{PR_URL}\n")
        return run_process(command, cwd=cwd, env=env)

    @staticmethod
    def _cz_bump(version: str, cwd: Path) -> Completed:
        pyproject = cwd / "pyproject.toml"
        text = pyproject.read_text(encoding="utf-8")
        pyproject.write_text(
            re.sub(r'(?m)^version = ".*"$', f'version = "{version}"', text, count=1),
            encoding="utf-8",
        )
        return Completed(0)


@dataclass(frozen=True)
class Repo:
    """A work clone of a bare ``origin``, with a ``git(*args) -> stdout`` helper."""

    work: Path
    git: Callable[..., str]

    def commit(self, message: str, *, version: str | None = None, base: str | None = None) -> str:
        """Commit (and push to ``main``) a change; ``version`` bumps it, with a manifest on ``base``."""
        if version is None:
            (self.work / "notes.txt").write_text(message, encoding="utf-8")
        else:
            _write_version(self.work, version)
            target = release_dir(self.work / "catalog", version)
            target.mkdir(parents=True, exist_ok=True)
            manifest = ReleaseManifest(version, base or self.head(), (), ())
            (target / "manifest.toml").write_text(render_manifest(manifest), encoding="utf-8")
        self.git("add", "-A", cwd=self.work)
        self.git("commit", "-q", "-m", message, cwd=self.work)
        self.git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=self.work)
        return self.head()

    def head(self) -> str:
        return self.git("rev-parse", "HEAD", cwd=self.work).strip()

    def tag(self, *args: str, runner: object = run_process) -> int:
        return main(["tag", *args], cwd=self.work, runner=runner)  # type: ignore[arg-type]


def _write_version(work: Path, version: str) -> None:
    (work / "pyproject.toml").write_text(
        f'[project]\nname = "x"\nversion = "{version}"\n', encoding="utf-8"
    )


def _repo(real_git: Callable[..., str], tmp_path: Path) -> Repo:
    remote, work = tmp_path / "origin.git", tmp_path / "work"
    real_git("init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    real_git("init", "-q", "-b", "main", str(work), cwd=tmp_path)
    real_git("remote", "add", "origin", str(remote), cwd=work)
    _write_version(work, "0.9.0")
    real_git("add", "-A", cwd=work)
    real_git("commit", "-q", "-m", "chore: start", cwd=work)
    real_git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=work)
    return Repo(work, real_git)


def test_a_pushed_annotated_tag_makes_every_later_run_a_no_op(
    real_git: Callable[..., str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(real_git, tmp_path)
    release = repo.commit("chore(release): v1.0.9", version="1.0.9")

    assert repo.tag("--tested-commit", release) == 0
    assert f"tagged v1.0.9 at {release}" in capsys.readouterr().out
    assert repo.git("cat-file", "-t", "refs/tags/v1.0.9", cwd=repo.work).strip() == "tag"

    assert repo.tag("--tested-commit", release) == 0  # the same commit, re-run
    assert f"v1.0.9 already points at {release}" in capsys.readouterr().out

    later = repo.commit("feat: later")
    assert repo.tag("--tested-commit", later) == 0  # the next push to main
    assert repo.tag() == 0  # the manual fallback
    out = capsys.readouterr().out
    assert out.count(f"v1.0.9 already points at {release}") == 2


def test_a_release_whose_base_moved_is_superseded_by_prepare_version_then_tagged(
    real_git: Callable[..., str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(real_git, tmp_path)
    first = repo.commit("chore(release): v0.9.1", version="0.9.1")
    assert repo.tag("--tested-commit", first) == 0
    prepared_on = repo.head()
    repo.commit("feat: merged while the release pull request was open")
    stale = repo.commit("chore(release): v1.0.9", version="1.0.9", base=prepared_on)

    assert repo.tag("--tested-commit", stale) == 1
    assert "prepare --version" in capsys.readouterr().err

    host = FakeCzForgeOverRealGit()
    argv = ["prepare-checkout", "--base", stale]
    assert main(argv, cwd=repo.work, runner=host, snapshot=_empty_snapshot) == 1
    assert "pass --version, higher than 1.0.9" in capsys.readouterr().err

    assert (
        main([*argv, "--version", "1.1.0"], cwd=repo.work, runner=host, snapshot=_empty_snapshot)
        == 0
    )
    assert f"release: opened {PR_URL}" in capsys.readouterr().out

    repo.git("fetch", "-q", "origin", cwd=repo.work)
    repo.git("push", "-q", "origin", "origin/release/v1.1.0:refs/heads/main", cwd=repo.work)
    merged = repo.git("rev-parse", "origin/release/v1.1.0", cwd=repo.work).strip()
    manifest = parse_manifest(
        repo.git("show", f"{merged}:catalog/releases/1.1.0/manifest.toml", cwd=repo.work)
    )
    notes = repo.git("show", f"{merged}:catalog/releases/1.1.0/notes.md", cwd=repo.work)
    assert manifest.base == stale
    assert "Changes since 0.9.1." in notes

    assert repo.tag("--tested-commit", merged) == 0
    assert f"tagged v1.1.0 at {merged}" in capsys.readouterr().out
    assert repo.git("tag", "--list", "v1.0.9", cwd=repo.work).strip() == ""


def _empty_snapshot(base: str) -> ReleaseManifest:
    return ReleaseManifest("0", base, (), ())
