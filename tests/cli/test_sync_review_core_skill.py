"""``playbook sync`` writes the review prompt as the ``review-core`` skill Codex reads (#274).

Codex receives no prompts, so with ``shared_skills`` on, sync renders the review
prompt into ``.agents/skills/review-core/`` (rules inlined, no command
frontmatter), records it in the lockfile and settles it like any skill once the
adapter is off. No other core prompt becomes a skill there.

Claude Code does not read ``.agents/skills/``, and its output is byte-identical
with the adapter on or off. OpenCode scans that root too, but adds no command for
a skill whose name a command already holds: OpenCode v1.19.4,
``packages/opencode/src/command/index.ts``, ``Command.state`` registers config
commands first and its skills loop opens with ``if (commands[item.name])
continue``. So OpenCode keeps one review entry, the ``/review-core`` command its
adapter writes, which the last test pins on the engine side.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.config.files import FileSystemStateSource
from tests.conftest import _DEFAULT_CONFIG
from tests.plugins.superpowers_expectations import NATIVE_SKILL_ROOTS

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    SyntheticRepoFactory = Callable[..., Path]

pytestmark = pytest.mark.catalog

_HARNESSES: Final = '["claude_code", "opencode"]'
_WITH_SHARED: Final = '["claude_code", "opencode", "shared_skills"]'
_SKILL_DIR: Final = ".agents/skills/review-core"
#: A heading only the current review text has (the former v2 set, ADR 0012), not v1.
_CURRENT_TEXT_HEADING: Final = "## Skills for this task"


def _ns(repo: Path) -> argparse.Namespace:
    return argparse.Namespace(repo_root=str(repo), check=False)


def _config(adapters: str) -> str:
    default = _DEFAULT_CONFIG.replace('["continue", "claude_code", "opencode"]', adapters)
    assert default != _DEFAULT_CONFIG, "the default adapters line moved; update this test"
    return default


def _synced(root: Path, factory: SyntheticRepoFactory, config_text: str) -> Path:
    root.mkdir()
    repo = factory(root, config_text=config_text)
    assert _sync.run(_ns(repo)) == 0
    return repo


def _lock_rows(repo: Path, needle: str) -> dict[str, tuple[str, str | None]]:
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    return {e.path: (e.kind, e.artifact_id) for e in lockfile.entries if needle in e.path}


def _tree(repo: Path, top: str) -> dict[str, bytes]:
    return {
        p.relative_to(repo).as_posix(): p.read_bytes()
        for p in sorted((repo / top).rglob("*"))
        if p.is_file()
    }


def test_sync_writes_the_current_review_prompt_as_the_review_core_skill(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    repo = _synced(tmp_path / "repo", make_synthetic_repo, _config(_WITH_SHARED))

    frontmatter, body = split_frontmatter(
        (repo / _SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    )
    assert frontmatter["name"] == "review-core"
    assert "slash" not in frontmatter
    assert "allowed-tools" not in frontmatter
    assert body.lstrip().startswith("<!--")
    assert "# Review" in body
    assert "## Reference rules" in body
    assert _CURRENT_TEXT_HEADING in body
    assert _lock_rows(repo, f"{_SKILL_DIR}/") == {f"{_SKILL_DIR}/SKILL.md": ("prompt", "review")}


def test_no_other_core_prompt_becomes_a_shared_skill(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    """Every other ``.agents/skills/`` dir is a skill some native skill root also gets."""
    repo = _synced(tmp_path / "repo", make_synthetic_repo, _config(_WITH_SHARED))

    shared = {p.name for p in (repo / ".agents/skills").iterdir()}
    native = {
        p.name
        for root in NATIVE_SKILL_ROOTS
        if root != ".agents/skills" and (repo / root).is_dir()
        for p in (repo / root).iterdir()
    }
    assert shared - native == {"review-core"}
    commands = {p.stem for p in (repo / ".claude/commands").glob("*.md")}
    assert shared & commands == {"review-core"}


def test_the_review_core_skill_is_settled_once_the_adapter_is_off(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    repo = _synced(tmp_path / "repo", make_synthetic_repo, _config(_WITH_SHARED))
    assert (repo / _SKILL_DIR / "SKILL.md").is_file()

    (repo / ".coding-agent-playbook.toml").write_text(_config(_HARNESSES), encoding="utf-8")
    assert _sync.run(_ns(repo)) == 0

    assert not (repo / _SKILL_DIR).exists()
    assert _lock_rows(repo, _SKILL_DIR) == {}


def test_claude_code_and_opencode_output_is_unchanged_by_the_review_core_skill(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    """OpenCode keeps one review entry: its ``/review-core`` command, no skill copy."""
    without = _synced(tmp_path / "without", make_synthetic_repo, _config(_HARNESSES))
    with_shared = _synced(tmp_path / "with", make_synthetic_repo, _config(_WITH_SHARED))

    for top in (".claude", ".opencode"):
        assert _tree(with_shared, top) == _tree(without, top), top
    assert (with_shared / ".opencode/command/review-core.md").is_file()
    assert not (with_shared / ".opencode/skills/review-core").exists()
    assert not (with_shared / ".claude/skills/review-core").exists()
