"""Unit tests for the ``sync --check`` scratch-copy policy (specs/prK-lifecycle-hooks.md §P P2(b)).

``ScratchCopyPolicy`` is the ``ignore=`` callable of the scratch ``copytree``;
these tests call it directly on a real temp tree (no copy involved). The
end-to-end behaviour through ``playbook sync --check`` lives in
``tests/cli/test_sync.py``.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands._sync_scratch import SCRATCH_IGNORE_NAMES, ScratchCopyPolicy
from coding_agent_playbook.detector import _IGNORE_DIRS

if TYPE_CHECKING:
    from pathlib import Path

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")


def _touch(root: Path, *rels: str) -> None:
    for rel in rels:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x\n", encoding="utf-8")


def _ignored(policy: ScratchCopyPolicy, directory: Path) -> set[str]:
    names = sorted(entry.name for entry in directory.iterdir())
    return policy(str(directory), names)


def test_scratch_ignore_names_extend_detector_ignore_dirs() -> None:
    expected = _IGNORE_DIRS | {".ruff_cache", ".pytest_cache", "dist", "build"}
    assert expected == SCRATCH_IGNORE_NAMES


def test_policy_skips_ignored_names_and_secret_paths(tmp_path: Path) -> None:
    _touch(tmp_path, ".venv/x", ".git/HEAD", "build/x", ".env", "id_rsa", "deploy.pem")
    _touch(tmp_path, ".env.example", "id_rsa.pub", "credentials.py", "README.md", "src/app.py")
    assert _ignored(ScratchCopyPolicy(tmp_path), tmp_path) == {
        ".venv",
        ".git",
        "build",
        ".env",
        "id_rsa",
        "deploy.pem",
    }


def test_policy_never_prunes_canonical_sources(tmp_path: Path) -> None:
    """``playbook/`` is the sync's input: name and secret rules do not apply there."""
    _touch(tmp_path, "playbook/skills/build/SKILL.md", "playbook/rules/handling-credentials.md")
    _touch(tmp_path, "playbook/skills/x/scripts/__pycache__/m.pyc")
    policy = ScratchCopyPolicy(tmp_path)
    assert _ignored(policy, tmp_path / "playbook" / "skills") == set()
    assert _ignored(policy, tmp_path / "playbook" / "rules") == set()
    assert _ignored(policy, tmp_path / "playbook" / "skills" / "x" / "scripts") == set()
    assert policy.skipped == set()


def test_policy_records_skipped_paths_and_covers_descendants(tmp_path: Path) -> None:
    _touch(tmp_path, ".claude/skills/x/scripts/__pycache__/m.pyc", "build/out.txt")
    policy = ScratchCopyPolicy(tmp_path)
    _ignored(policy, tmp_path)
    _ignored(policy, tmp_path / ".claude" / "skills" / "x" / "scripts")
    assert policy.skipped == {"build", ".claude/skills/x/scripts/__pycache__"}
    assert policy.covers(".claude/skills/x/scripts/__pycache__/m.pyc")
    assert policy.covers("build")
    assert not policy.covers(".claude/skills/x/scripts/run.sh")
    assert not policy.covers("buildx/out.txt")


@posix_only
def test_policy_symlink_inside_repo_is_copied(tmp_path: Path) -> None:
    _touch(tmp_path, "docs/inside.md")
    (tmp_path / "alias.md").symlink_to(tmp_path / "docs" / "inside.md")
    (tmp_path / "docs-link").symlink_to(tmp_path / "docs", target_is_directory=True)
    assert _ignored(ScratchCopyPolicy(tmp_path), tmp_path) == set()


@posix_only
def test_policy_skips_outside_dangling_excluded_and_ancestor_links(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _touch(tmp_path, "home/.ssh/id_rsa", "home/notes.txt", "repo/.env", "repo/.venv/x")
    (repo / "ssh").symlink_to(tmp_path / "home" / ".ssh", target_is_directory=True)
    (repo / "notes.txt").symlink_to(tmp_path / "home" / "notes.txt")
    (repo / "dangling").symlink_to(repo / "missing")
    (repo / "settings.txt").symlink_to(repo / ".env")
    (repo / "env").symlink_to(repo / ".venv", target_is_directory=True)
    (repo / "loop").symlink_to(repo, target_is_directory=True)
    assert _ignored(ScratchCopyPolicy(repo), repo) == {
        ".env",
        ".venv",
        "ssh",
        "notes.txt",
        "dangling",
        "settings.txt",
        "env",
        "loop",
    }
