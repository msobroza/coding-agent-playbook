"""``build_edition`` copies a fake tag's graded set into a scratch catalog (#281 ticket 14).

Real git, isolated by the ``real_git`` fixture, on a scratch repo: tag ``v9.9.9``
records a manifest grading the prompt ``review``; ``v9.9.7`` has no manifest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.release.edition import load_edition
from coding_agent_playbook.release.edition_build import (
    EditionBuildError,
    build_edition,
    tag_commit,
)
from coding_agent_playbook.release.manifest import (
    ManifestEntry,
    ReleaseManifest,
    release_dir,
    render_manifest,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

PROMPT = "catalog/core/prompts/review.md"
FROZEN = (
    b"---\r\nid: review\r\nname: Review\r\ndescription: R.\r\nslash: review\r\n---\r\nFrozen.\r\n"
)


def _tagged_repo(real_git: Callable[..., str], tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / PROMPT).parent.mkdir(parents=True)
    (repo / PROMPT).write_bytes(FROZEN)
    real_git("init", "-q", cwd=repo)
    real_git("add", "-A", cwd=repo)
    real_git("commit", "-q", "-m", "feat: the graded set", cwd=repo)
    real_git("tag", "v9.9.7", cwd=repo)
    entry = ManifestEntry("coding_agent_playbook", "prompt", "review", PROMPT, "d1")
    manifest = release_dir(repo / "catalog", "9.9.9") / "manifest.toml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(render_manifest(ReleaseManifest("9.9.9", "f00d", (entry,), ())), "utf-8")
    real_git("add", "-A", cwd=repo)
    real_git("commit", "-q", "-m", "chore(release): v9.9.9", cwd=repo)
    real_git("tag", "--annotate", "--message", "Release v9.9.9", "v9.9.9", cwd=repo)
    (repo / PROMPT).write_bytes(FROZEN.replace(b"Frozen", b"Current"))  # the text moved on
    return repo


def test_an_edition_is_built_byte_for_byte_from_its_tag(
    real_git: Callable[..., str], tmp_path: Path
) -> None:
    repo = _tagged_repo(real_git, tmp_path)

    root = build_edition(repo, "v9.9.9", tmp_path / "scratch")

    assert root == tmp_path / "scratch" / "editions" / "v9.9.9"
    assert (root / "core/prompts/review.md").read_bytes() == FROZEN
    assert load_edition(root).prompt("review").frontmatter.id == "review"
    assert not (repo / "catalog" / "editions").exists()


def test_a_missing_tag_has_no_commit(real_git: Callable[..., str], tmp_path: Path) -> None:
    repo = _tagged_repo(real_git, tmp_path)
    assert tag_commit(repo, "v9.9.8") is None
    with pytest.raises(EditionBuildError, match=r"no tag v9\.9\.8"):
        build_edition(repo, "v9.9.8", tmp_path / "scratch")


def test_a_tag_without_a_manifest_or_a_non_release_tag_is_refused(
    real_git: Callable[..., str], tmp_path: Path
) -> None:
    repo = _tagged_repo(real_git, tmp_path)
    with pytest.raises(EditionBuildError, match=r"has no manifest at catalog/releases/9\.9\.7"):
        build_edition(repo, "v9.9.7", tmp_path / "scratch")
    with pytest.raises(EditionBuildError, match="not a release tag"):
        build_edition(repo, "main", tmp_path / "scratch")
