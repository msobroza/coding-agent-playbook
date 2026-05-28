"""Tests for the AGENTS.md adapter (PR B, Track 8).

The AGENTS.md adapter is unique among the four built-ins:

- It is *rules-only*: ``write_prompt`` and ``write_skill`` are no-ops because
  AGENTS.md is a single repo-root file that aggregates rule sections.
- It is *single-file*: cleanup_stale is a one-path check rather than the
  shared directory-walking default — see Task 8.4.
- It *always runs*, regardless of which other adapters are enabled; the
  orchestrator enforces that contract in PR 10, but the tests here only
  exercise the adapter's own behaviour.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from coding_agent_playbook.adapters.agents_md_adapter import AgentsMdAdapter
from coding_agent_playbook.renderer import SENTINEL
from coding_agent_playbook.types import (
    Prompt,
    PromptFrontmatter,
    Rule,
    RuleFrontmatter,
    Skill,
)


def _make_rule(
    *,
    rule_id: str = "python-typing",
    name: str = "Python typing standards",
    description: str = "Type hints everywhere",
    scope: str = "scoped",
    globs: list[str] | None = None,
    priority: int = 50,
    body: str = "Use type hints everywhere.\n",
) -> Rule:
    """Build a Rule instance with already-rendered body for adapter round-trip."""
    frontmatter = RuleFrontmatter(
        id=rule_id,
        name=name,
        description=description,
        scope=scope,  # type: ignore[arg-type]
        globs=globs or [],
        priority=priority,
    )
    return Rule(
        frontmatter=frontmatter,
        body=body,
        template_body=body,
        is_templated=False,
        source_path=None,
        source_package="test-pkg",
    )


def _make_prompt(
    *,
    prompt_id: str = "review-code",
    name: str = "Review code",
    description: str = "Review a diff for safety.",
    slash: str = "review",
    body: str = "Review the diff.\n",
) -> Prompt:
    """Build a Prompt instance with already-rendered body."""
    frontmatter = PromptFrontmatter(
        id=prompt_id,
        name=name,
        description=description,
        slash=slash,
    )
    return Prompt(
        frontmatter=frontmatter,
        body=body,
        template_body=body,
        is_templated=False,
        source_path=None,
        source_package="test-pkg",
    )


def _make_skill(
    *,
    skill_id: str = "demo-skill",
    name: str = "Demo skill",
    description: str = "A demo skill",
    body: str = "Do the thing.\n",
) -> Skill:
    """Build a Skill instance with already-rendered body."""
    frontmatter: dict[str, Any] = {
        "id": skill_id,
        "name": name,
        "description": description,
    }
    return Skill(
        frontmatter=frontmatter,
        body=body,
        scripts_dir=None,
        references_dir=None,
        source_package="test-pkg",
    )


# --- Task 8.2: write_rule buffers; write_prompt/write_skill are no-ops -----


def test_agents_md_write_rule_buffers_does_not_write(tmp_path: Path) -> None:
    rule = _make_rule(rule_id="py-typing", priority=50)
    adapter = AgentsMdAdapter()
    written = adapter.write_rule(rule, repo_root=tmp_path)
    assert written == []
    # No filesystem side effects until finalize() runs.
    assert not (tmp_path / "AGENTS.md").exists()
    assert len(adapter._buffered_rules) == 1
    priority, rule_id, rendered = adapter._buffered_rules[0]
    assert priority == 50
    assert rule_id == "py-typing"
    # Rendered section uses the shared agents_md_section format (== claude_md_section)
    assert "## Python typing standards" in rendered
    assert "Use type hints everywhere." in rendered


def test_agents_md_write_rule_buffers_multiple_rules(tmp_path: Path) -> None:
    adapter = AgentsMdAdapter()
    adapter.write_rule(_make_rule(rule_id="a", priority=10, name="A rule"), tmp_path)
    adapter.write_rule(_make_rule(rule_id="b", priority=20, name="B rule"), tmp_path)
    assert len(adapter._buffered_rules) == 2
    # Buffer preserves insertion order; finalize will sort.
    assert [entry[1] for entry in adapter._buffered_rules] == ["a", "b"]
    assert not (tmp_path / "AGENTS.md").exists()


def test_agents_md_write_prompt_is_noop(tmp_path: Path) -> None:
    prompt = _make_prompt()
    adapter = AgentsMdAdapter()
    written = adapter.write_prompt(prompt, repo_root=tmp_path)
    assert written == []
    # No file under any plausible per-harness directory.
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / ".continue").exists()
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".opencode").exists()


def test_agents_md_write_skill_is_noop(tmp_path: Path) -> None:
    skill = _make_skill()
    adapter = AgentsMdAdapter()
    written = adapter.write_skill(skill, repo_root=tmp_path)
    assert written == []
    # Notably, this does NOT call Skill.to_prompt() (which would raise on the
    # current branch). AGENTS.md is rules-only — skills route through the
    # Claude Code adapter's native skill directory writer.
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / ".claude").exists()


def test_agents_md_write_rule_does_not_emit_sentinel_in_section(tmp_path: Path) -> None:
    # The sentinel belongs on the composite AGENTS.md file (finalize), not on
    # individual section fragments — otherwise finalize would have to strip it.
    rule = _make_rule()
    adapter = AgentsMdAdapter()
    adapter.write_rule(rule, repo_root=tmp_path)
    _, _, rendered = adapter._buffered_rules[0]
    assert SENTINEL not in rendered
