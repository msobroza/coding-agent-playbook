"""Hooks on + a symlinked skills root: ``sync --check`` agrees with write mode (SPEC §12.3).

Regression: with ``.claude/skills -> ../.agents/skills`` write mode recorded the
``guard_config.json`` ``protected`` rows through the repo's symlink
(``.agents/skills/<id>/…``) while the ``--check`` scratch, where
``.claude/skills`` is a real directory, recorded ``.claude/skills/<id>/…``. So
``sync --check`` reported ``guard_config.json`` as drift right after a clean
sync, and no sync could clear it.
"""

from __future__ import annotations

import json
import shutil
import sys
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.sync import pipeline as _sync
from tests.cli.hook_repo import GUARD_CONFIG, hook_deps, make_hook_repo
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

pytestmark = [
    pytest.mark.usefixtures("sample_hook_handlers"),
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks"),
]

_SKILL = "demo-skill"


def _sync_repo(repo: Path, tmp_path: Path, **kwargs: Any) -> int:
    kwargs.setdefault("git", FakeGitClient())
    kwargs.setdefault("hook_deps", hook_deps(tmp_path / "state"))
    return _sync.execute(repo, **kwargs)


def _repo_with_linked_skills_root(tmp_path: Path, make_synthetic_repo: Callable[..., Path]) -> Path:
    """The hook repo plus one skill, its Claude skills root linked into ``.agents/skills``."""
    repo = make_hook_repo(tmp_path / "repo", make_synthetic_repo)
    skill_dir = repo / "playbook" / "skills" / _SKILL
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nid: {_SKILL}\nname: {_SKILL}\ndescription: A demo skill\n---\nDo it.\n"
    )
    (repo / ".agents" / "skills").mkdir(parents=True)
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "skills").symlink_to("../.agents/skills", target_is_directory=True)
    return repo


def _protected_paths(repo: Path) -> set[str]:
    config = json.loads((repo / GUARD_CONFIG).read_text(encoding="utf-8"))
    return {row["path"] for row in config["protected"]["entries"]}


def test_check_reports_no_drift_right_after_a_sync(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_linked_skills_root(tmp_path, make_synthetic_repo)
    assert _sync_repo(repo, tmp_path) == 0
    capsys.readouterr()

    assert _sync_repo(repo, tmp_path, check=True) == 0, capsys.readouterr().out


def test_protected_rows_name_the_resolved_skill_path_like_the_lockfile(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = _repo_with_linked_skills_root(tmp_path, make_synthetic_repo)
    assert _sync_repo(repo, tmp_path) == 0

    paths = _protected_paths(repo)

    assert f".agents/skills/{_SKILL}/SKILL.md" in paths
    assert f".claude/skills/{_SKILL}/SKILL.md" not in paths


def test_check_survives_a_looping_link_inside_a_skill_dir(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression (Python 3.12, where ``Path.resolve()`` raises on a symlink loop): the
    protected rows map each scratch path onto the repo through its links, and a loop
    there crashed ``sync --check``."""
    repo = make_hook_repo(tmp_path / "repo", make_synthetic_repo)
    source = repo / "playbook" / "skills" / _SKILL
    (source / "scripts").mkdir(parents=True)
    (source / "SKILL.md").write_text(
        f"---\nid: {_SKILL}\nname: {_SKILL}\ndescription: A demo skill\n---\nDo it.\n"
    )
    (source / "scripts" / "run.sh").write_text("echo hi\n")
    assert _sync_repo(repo, tmp_path) == 0
    scripts = repo / ".claude" / "skills" / _SKILL / "scripts"
    shutil.rmtree(scripts)
    scripts.symlink_to("scripts")

    assert _sync_repo(repo, tmp_path, check=True) == 1
    assert _sync_repo(repo, tmp_path) == 0
    capsys.readouterr()
    assert _sync_repo(repo, tmp_path, check=True) == 0, capsys.readouterr().out


def test_check_reports_no_drift_with_a_symlinked_scanned_dir(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """``output_dirs`` follows the same rule: ``.claude/commands`` linked elsewhere."""
    repo = make_hook_repo(tmp_path / "repo", make_synthetic_repo)
    (repo / "tools" / "claude-commands").mkdir(parents=True)
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "commands").symlink_to("../tools/claude-commands", target_is_directory=True)
    assert _sync_repo(repo, tmp_path) == 0
    capsys.readouterr()

    assert _sync_repo(repo, tmp_path, check=True) == 0, capsys.readouterr().out


def test_check_reports_no_drift_with_aliased_skills_roots(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Two adapters' skills roots on one real directory: write mode writes one file
    per skill (one ``composite`` row), the scratch writes two; both must agree."""
    repo = _repo_with_linked_skills_root(tmp_path, make_synthetic_repo)
    (repo / ".opencode").mkdir(exist_ok=True)
    (repo / ".opencode" / "skills").symlink_to("../.agents/skills", target_is_directory=True)
    assert _sync_repo(repo, tmp_path) == 0
    capsys.readouterr()

    assert _sync_repo(repo, tmp_path, check=True) == 0, capsys.readouterr().out


def test_check_reports_no_drift_with_a_scanned_dir_linked_out_of_the_repo(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """SPEC §12.3's ``.claude/commands -> ../shared-commands``: the row is dropped in both modes."""
    repo = make_hook_repo(tmp_path / "repo", make_synthetic_repo)
    outside = tmp_path / "shared-commands"
    outside.mkdir()
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "commands").symlink_to(outside, target_is_directory=True)
    assert _sync_repo(repo, tmp_path) == 0
    capsys.readouterr()

    assert _sync_repo(repo, tmp_path, check=True) == 0, capsys.readouterr().out
