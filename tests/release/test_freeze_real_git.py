"""``release.py freeze``/``unfreeze``/``check-editions`` on a scratch repo with a fake tag (#295).

Every git command is the real one (isolated by the ``real_git`` fixture) on a
work clone of a bare ``origin``; only ``playbook forge`` is faked
(``FakeForgeOverRealGit``). The repo's catalog is tiny: one core prompt
``review`` including the rule ``typing``, one core sample ``review/pinned``,
release ``9.9.9``'s manifest grading both, and the notices the vendored rule
needs (``ATTRIBUTIONS.md`` and its skill's ``references/LICENSE.*``). Tag
``v9.9.9`` ships the frozen text (with a retired ``version`` key and CRLF
bytes); ``main`` has moved on since. The engine guard is faked
(:func:`accept_any_engine`): the engine under test is this checkout's, never the
scratch repo's, which has no ``src``.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.evals.edition_checks import edition_problems
from coding_agent_playbook.release.edition import load_edition
from coding_agent_playbook.release.manifest import (
    ManifestEntry,
    ReleaseManifest,
    release_dir,
    render_manifest,
)
from release import main as release_main
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
ATTRIBUTIONS = "catalog/core/ATTRIBUTIONS.md"
LICENSE = "catalog/core/skills/python-coding/references/LICENSE.python-best-practices"
NOTICES = {ATTRIBUTIONS: b"# Attributions\n\nCredits.\n", LICENSE: b"MIT License\r\n\r\nText.\r\n"}


def accept_any_engine(_checkout: Path, _command: str) -> None:
    """The engine guard here: the scratch repo has no ``src``, so this engine is the one."""


def main(argv: list[str], **kwargs: Any) -> int:
    return release_main(argv, engine_guard=accept_any_engine, **kwargs)


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
    for path, data in NOTICES.items():
        _write(work / path, data)
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
    for path, data in NOTICES.items():
        assert (repo.work / EDITION / path.removeprefix("catalog/")).read_bytes() == data
    assert load_edition(repo.work / EDITION).prompt("review").frontmatter.id == "review"
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


def test_check_editions_catches_a_notice_dropped_from_the_digests_and_the_edition(
    real_git: Callable[..., str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _released_repo(real_git, tmp_path)
    assert _run(repo, "freeze") == 0
    repo.merge(f"freeze/{TAG}")
    rel = LICENSE.removeprefix("catalog/")
    digests = repo.work / EDITION / "digests.toml"
    blocks = digests.read_text(encoding="utf-8").split("\n\n")
    digests.write_text("\n\n".join(b for b in blocks if rel not in b), encoding="utf-8")
    (repo.work / EDITION / rel).unlink()
    assert edition_problems(repo.work / "catalog") == []  # the offline check cannot see it
    capsys.readouterr()

    assert main(["check-editions"], cwd=repo.work) == 1

    assert f"lists no notice '{rel}'" in capsys.readouterr().err


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


def test_unfreeze_removes_the_pins_and_the_edition_byte_for_byte(
    real_git: Callable[..., str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _released_repo(real_git, tmp_path)
    unpinned = (repo.work / SAMPLE).read_bytes()
    assert _run(repo, "freeze") == 0
    repo.merge(f"freeze/{TAG}")

    assert _run(repo, "unfreeze") == 0

    repo.merge(f"unfreeze/{TAG}")
    assert not (repo.work / "catalog/editions").exists()
    assert (repo.work / SAMPLE).read_bytes() == unpinned
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


def test_freeze_checkout_refuses_an_engine_from_outside_the_checkout(
    real_git: Callable[..., str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _released_repo(real_git, tmp_path)
    argv = ["freeze-checkout", "--base", repo.run("rev-parse", "HEAD"), "--tag", TAG]

    assert release_main(argv, cwd=repo.work, runner=FakeForgeOverRealGit()) == 1

    assert "freeze-checkout imported the engine from" in capsys.readouterr().err
    assert repo.run("status", "--porcelain") == ""
    assert not (repo.work / EDITION).exists()
