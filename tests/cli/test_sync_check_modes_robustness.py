"""Regressions for ``playbook sync --check`` / ``--check-staged`` robustness.

- The check modes render into an empty scratch dir instead of copying the
  working tree, so dangling symlinks, unreadable directories and FIFOs cannot
  crash the pre-commit guard.
- Scratch paths are mapped back onto the real tree, so a symlinked output dir
  yields the same managed-block entries as write mode.
- An unimportable overlay package fails every mode loudly instead of silently
  rendering without it (the remote-hook venv scenario).
- A decomposed (NFD) generated name is still caught when git stages it in NFC.
"""

from __future__ import annotations

import os
import sys
import unicodedata
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import sync as _sync
from tests.conftest import _DEFAULT_CONFIG
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

_SKILL = "demo"
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX filesystem features")


def _add_skill(repo: Path) -> None:
    skill_dir = repo / "playbook" / "skills" / _SKILL
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nid: {_SKILL}\nname: {_SKILL}\ndescription: A demo skill\n---\nDo it.\n"
    )


@pytest.fixture
def repo(tmp_path: Path, make_synthetic_repo: Callable[..., Path]) -> Path:
    built = make_synthetic_repo(tmp_path, rules=[("style-guide", "Use spaces.\n")])
    _add_skill(built)
    return built


# --------------------------------------------------------------------------- #
# Symlinked output directory
# --------------------------------------------------------------------------- #


@pytest.fixture
def symlinked_skills(repo: Path) -> Path:
    """``.claude/skills -> ../.agents/skills`` (a shared-skills layout)."""
    (repo / ".agents" / "skills").mkdir(parents=True)
    (repo / ".claude").mkdir()
    (repo / ".claude" / "skills").symlink_to("../.agents/skills", target_is_directory=True)
    return repo


@posix_only
def test_check_agrees_with_write_mode_through_a_symlinked_output_dir(
    symlinked_skills: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = symlinked_skills
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert f"\n/.agents/skills/{_SKILL}/\n" in (repo / ".gitignore").read_text()
    capsys.readouterr()
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0
    assert "No drift" in capsys.readouterr().out


@posix_only
def test_check_staged_catches_output_staged_through_its_real_path(
    symlinked_skills: Path,
) -> None:
    repo = symlinked_skills
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    git = FakeGitClient(staged=[f".agents/skills/{_SKILL}/SKILL.md"])
    assert _sync.execute(repo, check_staged=True, git=git) == 1


# --------------------------------------------------------------------------- #
# Hostile working-tree entries
# --------------------------------------------------------------------------- #


@pytest.fixture
def hostile_tree(repo: Path) -> Iterator[Path]:
    """A dangling venv interpreter symlink, a 0o000 data dir and a FIFO."""
    (repo / ".venv" / "bin").mkdir(parents=True)
    (repo / ".venv" / "bin" / "python").symlink_to(repo / "no-such-python")
    locked = repo / "pgdata"
    locked.mkdir()
    (locked / "PG_VERSION").write_text("16\n")
    os.mkfifo(repo / "events.fifo")
    locked.chmod(0o000)
    yield repo
    locked.chmod(0o755)


@posix_only
@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads 0o000")
def test_check_modes_survive_unreadable_and_special_entries(
    hostile_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = hostile_tree
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0
    assert _sync.execute(repo, check_staged=True, git=FakeGitClient(staged=["src/a.py"])) == 0
    staged = FakeGitClient(staged=["AGENTS.md"])
    capsys.readouterr()
    assert _sync.execute(repo, check_staged=True, git=staged) == 1
    assert "  AGENTS.md\n" in capsys.readouterr().out


def test_check_staged_never_writes_into_the_repo(repo: Path) -> None:
    before = sorted(path.relative_to(repo) for path in repo.rglob("*"))
    assert _sync.execute(repo, check_staged=True, git=FakeGitClient(staged=["AGENTS.md"])) == 1
    assert sorted(path.relative_to(repo) for path in repo.rglob("*")) == before


# --------------------------------------------------------------------------- #
# Overlay / adapter availability
# --------------------------------------------------------------------------- #

_MISSING_OVERLAY_CONFIG = _DEFAULT_CONFIG.replace(
    "overlays_enabled = []", 'overlays_enabled = ["no_such_overlay_pkg"]'
)


def _with_missing_overlay(repo: Path, *, commit: bool = False) -> None:
    extra = "\n[output]\ncommit = true\n" if commit else ""
    (repo / ".coding-agent-playbook.toml").write_text(_MISSING_OVERLAY_CONFIG + extra)


def test_write_mode_refuses_when_an_overlay_is_not_importable(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _with_missing_overlay(repo)
    assert _sync.execute(repo, git=FakeGitClient()) == 1
    err = capsys.readouterr().err
    assert "no_such_overlay_pkg" in err
    assert "additional_dependencies" in err
    assert not (repo / "AGENTS.md").exists()
    assert not (repo / ".gitignore").exists()
    assert not (repo / ".coding-agent-playbook.lock").exists()


def test_existing_output_is_untouched_when_an_overlay_goes_missing(repo: Path) -> None:
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    snapshot = {p: p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    _with_missing_overlay(repo)
    assert _sync.execute(repo, git=FakeGitClient()) == 1
    changed = {p for p in snapshot if p.read_bytes() != snapshot[p]}
    assert changed == {repo / ".coding-agent-playbook.toml"}


@pytest.mark.parametrize("mode", [{"check": True}, {"check_staged": True}])
def test_check_modes_refuse_when_an_overlay_is_not_importable(
    repo: Path, mode: dict[str, bool], capsys: pytest.CaptureFixture[str]
) -> None:
    _with_missing_overlay(repo)
    git = FakeGitClient(staged=["src/a.py"])
    assert (
        _sync.execute(
            repo,
            git=git,
            check=mode.get("check", False),
            check_staged=mode.get("check_staged", False),
        )
        == 1
    )
    assert "no_such_overlay_pkg" in capsys.readouterr().err


def test_check_staged_stays_a_noop_under_commit_true(repo: Path) -> None:
    _with_missing_overlay(repo, commit=True)
    git = FakeGitClient(staged=["AGENTS.md"])
    assert _sync.execute(repo, check_staged=True, git=git) == 0
    assert git.calls == []


def test_importable_overlay_without_artifacts_is_fine(
    repo: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An overlay package whose ``resources/`` holds no artifacts (yet) is usable.

    (A package with no ``resources/`` directory at all, like ``json``, is not an
    overlay package: the shared preflight refuses it, see test_unusable_overlays.)
    """
    site = tmp_path_factory.mktemp("site")
    (site / "empty_overlay_pkg" / "resources").mkdir(parents=True)
    (site / "empty_overlay_pkg" / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(site))
    config = _DEFAULT_CONFIG.replace(
        "overlays_enabled = []", 'overlays_enabled = ["empty_overlay_pkg"]'
    )
    (repo / ".coding-agent-playbook.toml").write_text(config)
    assert _sync.execute(repo, git=FakeGitClient()) == 0


def test_missing_adapter_only_warns(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = _DEFAULT_CONFIG.replace('"opencode"]', '"opencode", "codex"]')
    (repo / ".coding-agent-playbook.toml").write_text(config)
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert "warning: enabled adapter(s) not installed, skipped: codex" in capsys.readouterr().err
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0


# --------------------------------------------------------------------------- #
# Unicode normalisation
# --------------------------------------------------------------------------- #


def test_nfd_prompt_name_is_ignored_and_guarded_in_nfc(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    nfd = unicodedata.normalize("NFD", "café")
    nfc = unicodedata.normalize("NFC", "café")
    repo = make_synthetic_repo(tmp_path, prompts=[("cafe", {"slash": nfd, "body": "Hi.\n"})])
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert f"\n/.claude/commands/{nfc}.md\n" in (repo / ".gitignore").read_text()
    staged = FakeGitClient(staged=[f".claude/commands/{nfc}.md"])
    assert _sync.execute(repo, check_staged=True, git=staged) == 1
