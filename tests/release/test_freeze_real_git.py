"""``release.py freeze``/``unfreeze``/``check-editions`` on a scratch repo with a fake tag (#295).

Every git command is the real one (isolated by the ``real_git`` fixture) on a
work clone of a bare ``origin``; only ``playbook forge`` is faked
(``FakeForgeOverRealGit``). The repo's catalog is tiny: one core prompt
``review`` including the rule ``typing``, one core sample ``review/pinned``, and
release ``9.9.9``'s manifest grading both. Tag ``v9.9.9`` ships the frozen text
(with a retired ``version`` key and CRLF bytes); ``main`` has moved on since.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.edition_checks import edition_problems
from coding_agent_playbook.release.manifest import (
    ManifestEntry,
    ReleaseManifest,
    release_dir,
    render_manifest,
)
from release import main
from tests.edition_fixtures import write_sample
from tests.release.release_fakes import PR_URL, FakeForgeOverRealGit

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest

TAG = "v9.9.9"
PROMPT = "catalog/core/prompts/review.md"
RULE = "catalog/core/skills/python-coding/rules/typing.md"
SAMPLE = "catalog/core/eval_samples/review/pinned/sample.toml"
EDITION = f"catalog/editions/{TAG}"
FROZEN_PROMPT = (
    b"---\r\nid: review\r\nname: Review\r\ndescription: Review code.\r\nslash: review\r\n"
    b"version: 3\r\nincludes_rules:\r\n  - typing\r\n---\r\nFrozen review prompt.\r\n"
)
RULE_TEXT = "---\nid: typing\nname: Typing\ndescription: Type all.\nscope: always\n---\nType.\n"


@dataclass(frozen=True)
class Repo:
    work: Path
    git: Callable[..., str]

    def run(self, *args: str) -> str:
        return self.git(*args, cwd=self.work)

    def commit_all(self, message: str) -> str:
        self.run("add", "-A")
        self.run("commit", "-q", "-m", message)
        self.run("push", "-q", "origin", "HEAD:refs/heads/main")
        return self.run("rev-parse", "HEAD")

    def merge(self, branch: str) -> str:
        """Fast-forward ``main`` to ``origin/<branch>``, as merging its pull request does."""
        self.run("fetch", "-q", "origin")
        self.run("switch", "-q", "--detach", f"origin/{branch}")
        self.run("push", "-q", "origin", "HEAD:refs/heads/main")
        return self.run("rev-parse", "HEAD")


def _released_repo(real_git: Callable[..., str], tmp_path: Path) -> Repo:
    remote, work = tmp_path / "origin.git", tmp_path / "work"
    real_git("init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    real_git("init", "-q", "-b", "main", str(work), cwd=tmp_path)
    real_git("remote", "add", "origin", str(remote), cwd=work)
    repo = Repo(work, real_git)
    _write(work / PROMPT, FROZEN_PROMPT)
    _write(work / RULE, RULE_TEXT.encode())
    write_sample(work / "catalog/core", edition=None)
    base = repo.commit_all("feat: the graded set")
    graded = (
        ManifestEntry("coding_agent_playbook", "prompt", "review", PROMPT, "d1"),
        ManifestEntry("coding_agent_playbook", "rule", "typing", RULE, "d2"),
    )
    manifest = render_manifest(ReleaseManifest("9.9.9", base, graded, ()))
    _write(release_dir(work / "catalog", "9.9.9") / "manifest.toml", manifest.encode())
    repo.commit_all("chore(release): v9.9.9")
    repo.run("tag", "--annotate", "--message", "Release v9.9.9", TAG)
    _write(work / PROMPT, FROZEN_PROMPT.replace(b"Frozen", b"Current"))
    repo.commit_all("feat: improve the review prompt")
    return repo


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _run(repo: Repo, command: str, host: FakeForgeOverRealGit | None = None) -> int:
    argv = [f"{command}-checkout", "--base", repo.run("rev-parse", "HEAD"), "--tag", TAG]
    return main(argv, cwd=repo.work, runner=host or FakeForgeOverRealGit())


def test_freeze_copies_the_tag_pins_the_sample_and_opens_a_pull_request(
    real_git: Callable[..., str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _released_repo(real_git, tmp_path)
    base = repo.run("rev-parse", "HEAD")
    host = FakeForgeOverRealGit()

    assert _run(repo, "freeze", host) == 0

    assert f"release: opened {PR_URL}" in capsys.readouterr().out
    (create,) = host.created()
    assert create[create.index("--title") + 1] == f"chore(evals): freeze edition {TAG}"
    assert repo.run("rev-parse", "HEAD") == base  # back at the base, tree clean, no branch
    assert repo.run("status", "--porcelain") == ""
    assert repo.run("branch", "--list", f"freeze/{TAG}") == ""
    repo.merge(f"freeze/{TAG}")
    catalog = repo.work / "catalog"
    assert (repo.work / EDITION / "core/prompts/review.md").read_bytes() == FROZEN_PROMPT
    assert (catalog / "editions/README.md").is_file()
    sample = tomllib.loads((repo.work / SAMPLE).read_text(encoding="utf-8"))
    assert sample["edition"] == TAG
    assert edition_problems(catalog) == []


def test_check_editions_passes_on_a_frozen_edition_and_fails_on_a_hand_edit(
    real_git: Callable[..., str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _released_repo(real_git, tmp_path)
    assert _run(repo, "freeze") == 0
    repo.merge(f"freeze/{TAG}")
    capsys.readouterr()

    assert main(["check-editions"], cwd=repo.work) == 0
    assert "every edition file equals its tag's blob" in capsys.readouterr().out

    edited = repo.work / EDITION / "core/prompts/review.md"
    edited.write_bytes(FROZEN_PROMPT + b"A hand edit.\r\n")

    assert main(["check-editions"], cwd=repo.work) == 1
    err = capsys.readouterr().err
    assert str(edited) in err
    assert f"edit the current text in {PROMPT} instead" in err


def test_freeze_again_before_the_merge_reuses_the_open_pull_request(
    real_git: Callable[..., str], tmp_path: Path
) -> None:
    repo = _released_repo(real_git, tmp_path)
    assert _run(repo, "freeze") == 0
    url = "https://forge.example/pulls/12"
    host = FakeForgeOverRealGit(open_pulls=[{"head": f"freeze/{TAG}", "url": url}])

    assert _run(repo, "freeze", host) == 0

    assert host.created() == []
    repo.merge(f"freeze/{TAG}")
    assert edition_problems(repo.work / "catalog") == []


def test_unfreeze_removes_the_pins_and_the_edition(
    real_git: Callable[..., str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _released_repo(real_git, tmp_path)
    assert _run(repo, "freeze") == 0
    repo.merge(f"freeze/{TAG}")

    assert _run(repo, "unfreeze") == 0

    repo.merge(f"unfreeze/{TAG}")
    assert not (repo.work / "catalog/editions").exists()
    assert "edition" not in tomllib.loads((repo.work / SAMPLE).read_text(encoding="utf-8"))
    assert _run(repo, "unfreeze") == 1
    assert f"nothing to unfreeze: no edition {TAG}" in capsys.readouterr().err


def test_freeze_refuses_a_missing_tag_and_a_tag_without_a_manifest(
    real_git: Callable[..., str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _released_repo(real_git, tmp_path)
    base = repo.run("rev-parse", "HEAD")
    argv = ["freeze-checkout", "--base", base, "--tag"]

    assert main([*argv, "v9.9.8"], cwd=repo.work, runner=FakeForgeOverRealGit()) == 1
    assert "no tag v9.9.8" in capsys.readouterr().err

    repo.run("tag", "v9.9.7", "HEAD~2")
    assert main([*argv, "v9.9.7"], cwd=repo.work, runner=FakeForgeOverRealGit()) == 1
    assert "has no manifest at catalog/releases/9.9.7/manifest.toml" in capsys.readouterr().err
    assert repo.run("status", "--porcelain") == ""
    assert repo.run("rev-parse", "HEAD") == base
