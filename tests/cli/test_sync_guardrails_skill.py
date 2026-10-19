"""``playbook sync`` writes the ``playbook-guardrails`` skill (D6, specs/prS-skills-context.md 8.4.3).

With hooks on, sync composes the skill from the on hooks' guardrail text and
writes it through the normal ``write_skill`` path to ``.opencode/skills/`` and
``.agents/skills/``; Claude Code runs every hook of the sample repo natively, so
``.claude/skills/`` gets none, and Continue keeps its rule files. With hooks off,
or with ``[hooks] advisory = false``, no copy is written, and the copies an
earlier sync wrote are settled by the skill leftover policy. Kept out of
``test_sync_hook_outputs.py``, which is past the 500-line budget already.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.lockfile.model import LockEntry, Lockfile
from coding_agent_playbook.sync import pipeline as _sync
from coding_agent_playbook.types import format_frontmatter, split_frontmatter
from tests.cli.hook_repo import CONFIG, HOOKS_ON, SETTINGS, hook_deps, make_hook_repo
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    SyntheticRepoFactory = Callable[..., Path]

# The sample hooks bind the builtin guard_x, which validate (H6) resolves
# through the handler registry: install it as a real entry point.
pytestmark = pytest.mark.usefixtures("sample_hook_handlers")

_SKILL_DIRS = tuple(
    f"{root}/playbook-guardrails"
    for root in (".claude/skills", ".opencode/skills", ".agents/skills")
)
_WRITTEN_DIRS = _SKILL_DIRS[1:]
_HOOKS_OFF = "[hooks]\nenabled = false\n"
# HOOKS_ON keeps allow_code_from, so the sample external hook still resolves.
_ADVISORY_OFF = f"{HOOKS_ON}advisory = false\n"


def _sync_repo(repo: Path, tmp_path: Path, **kwargs: Any) -> int:
    return _sync.execute(repo, git=FakeGitClient(), hook_deps=hook_deps(tmp_path / "s"), **kwargs)


def _lock_entries(repo: Path) -> list[LockEntry]:
    text = (repo / ".coding-agent-playbook.lock").read_text(encoding="utf-8")
    return Lockfile.from_dict(tomllib.loads(text)).entries


def _with_shared_skills(repo: Path, hooks_table: str = HOOKS_ON) -> None:
    """Rewrite the committed config with ``shared_skills`` enabled and ``hooks_table``."""
    adapters = CONFIG.replace('"opencode"]', '"opencode", "shared_skills"]')
    (repo / ".coding-agent-playbook.toml").write_text(f"{adapters}\n{hooks_table}", "utf-8")


def _hook_repo(root: Path, factory: SyntheticRepoFactory, hooks_table: str = HOOKS_ON) -> Path:
    repo = make_hook_repo(root, factory, hooks_table=hooks_table)
    _with_shared_skills(repo, hooks_table)
    return repo


def _skill_dirs(repo: Path) -> list[str]:
    return [rel for rel in _SKILL_DIRS if (repo / rel).exists()]


def _guardrail_rows(repo: Path) -> dict[str, tuple[str, str | None, str | None]]:
    return {
        entry.path: (entry.kind, entry.artifact_id, entry.source)
        for entry in _lock_entries(repo)
        if "playbook-guardrails" in entry.path
    }


def test_sync_writes_guardrails_skill_to_opencode_and_agents_roots_only(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    repo = _hook_repo(tmp_path / "repo", make_synthetic_repo)

    assert _sync_repo(repo, tmp_path) == 0

    assert _skill_dirs(repo) == list(_WRITTEN_DIRS)
    opencode, shared = (repo / rel / "SKILL.md" for rel in _WRITTEN_DIRS)
    assert opencode.read_bytes() == shared.read_bytes()
    text = opencode.read_text(encoding="utf-8")
    assert "## Guard X (`guard-x`)\n\nAdvice.\n" in text
    assert "(`destructive-command-guard`)" in text
    assert not (repo / ".continue" / "prompts" / "playbook-guardrails.md").exists()
    origin = ("skill", "playbook-guardrails", "coding_agent_playbook")
    assert _guardrail_rows(repo) == {f"{rel}/SKILL.md": origin for rel in _WRITTEN_DIRS}
    assert _sync_repo(repo, tmp_path, check=True) == 0


def test_sync_with_hooks_off_writes_no_guardrails_skill_and_no_section(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    fresh = _hook_repo(tmp_path / "fresh", make_synthetic_repo, _HOOKS_OFF)
    switched = _hook_repo(tmp_path / "switched", make_synthetic_repo)
    assert _sync_repo(switched, tmp_path) == 0
    assert _skill_dirs(switched), "hooks on: the skill is written first"
    _with_shared_skills(switched, _HOOKS_OFF)

    assert _sync_repo(fresh, tmp_path) == 0
    assert _sync_repo(switched, tmp_path) == 0

    for repo in (fresh, switched):
        assert _skill_dirs(repo) == [], repo.name
        assert "## Guardrails" not in (repo / "AGENTS.md").read_text(encoding="utf-8")
        assert _guardrail_rows(repo) == {}, repo.name


def test_sync_with_advisory_off_writes_no_guardrails_skill(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    """Hooks stay on, but ``[hooks] advisory = false`` leaves every hook without text."""
    repo = _hook_repo(tmp_path / "repo", make_synthetic_repo, _ADVISORY_OFF)

    assert _sync_repo(repo, tmp_path) == 0

    assert (repo / SETTINGS).is_file(), "hooks are on: Claude Code still gets its settings"
    assert _skill_dirs(repo) == []
    assert _guardrail_rows(repo) == {}
    assert not list((repo / ".continue" / "rules").glob("30-guardrail-*.md"))


def test_repo_local_guardrails_skill_replaces_the_intro_and_keeps_the_sections(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    repo = _hook_repo(tmp_path / "repo", make_synthetic_repo)
    ours = {
        "id": "playbook-guardrails",
        "name": "playbook-guardrails",
        "description": "Our guardrails. Use when a guardrail needs detail.",
    }
    skill_md = repo / "playbook" / "skills" / "playbook-guardrails" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text(format_frontmatter(ours, "\n# Our guardrails\n"), encoding="utf-8")

    assert _sync_repo(repo, tmp_path) == 0

    frontmatter, body = split_frontmatter(
        (repo / _WRITTEN_DIRS[0] / "SKILL.md").read_text(encoding="utf-8")
    )
    assert frontmatter["description"] == ours["description"]
    assert "\n# Our guardrails\n\n## " in body, "the sections follow our intro"
    assert "## Guard X (`guard-x`)\n" in body
    assert "# Playbook guardrails" not in body
    origin = ("skill", "playbook-guardrails", "<repo-local>")
    assert _guardrail_rows(repo) == {f"{rel}/SKILL.md": origin for rel in _WRITTEN_DIRS}
