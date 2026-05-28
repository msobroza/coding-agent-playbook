"""Tests for the OpenCode adapter (SPEC.md §10.6)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.adapters.opencode_adapter import OpenCodeAdapter
from coding_agent_playbook.types import (
    Prompt,
    PromptFrontmatter,
    Rule,
    RuleFrontmatter,
    Skill,
)

if TYPE_CHECKING:
    from pathlib import Path


def _make_rule(
    *,
    rule_id: str = "python-typing",
    name: str = "Python typing standards",
    description: str = "Type hints everywhere",
    scope: str = "scoped",
    globs: list[str] | None = None,
    priority: int = 50,
    body: str = "# Python typing\n\nUse type hints.\n",
) -> Rule:
    fm = RuleFrontmatter(
        id=rule_id,
        name=name,
        description=description,
        scope=scope,  # type: ignore[arg-type]
        globs=list(globs) if globs is not None else [],
        priority=priority,
    )
    return Rule(
        frontmatter=fm,
        body=body,
        template_body=body,
        is_templated=False,
        source_path=None,
        source_package="test",
    )


def _make_prompt(
    *,
    prompt_id: str = "generate-tests",
    name: str = "Generate tests",
    description: str = "Generate pytest tests for the provided code",
    slash: str = "generate-tests",
    input_variables: list[dict[str, str]] | None = None,
    includes_rules: list[str] | None = None,
    body: str = "Task: generate tests for {{ target }}.\n",
) -> Prompt:
    fm = PromptFrontmatter(
        id=prompt_id,
        name=name,
        description=description,
        slash=slash,
        input_variables=list(input_variables) if input_variables is not None else [],
        includes_rules=list(includes_rules) if includes_rules is not None else [],
    )
    return Prompt(
        frontmatter=fm,
        body=body,
        template_body=body,
        is_templated=False,
        source_path=None,
        source_package="test",
    )


def _make_skill(
    *,
    skill_id: str = "demo-skill",
    name: str = "Demo skill",
    description: str = "A demo skill",
    body: str = "Skill body.\n",
) -> Skill:
    return Skill(
        frontmatter={
            "id": skill_id,
            "name": name,
            "description": description,
            "slash": skill_id,
        },
        body=body,
        scripts_dir=None,
        references_dir=None,
        source_package="test",
    )


def test_write_rule_returns_empty_list_and_creates_no_files(tmp_path: Path) -> None:
    """OpenCode reads AGENTS.md natively, so the adapter does not write rules."""
    rule = _make_rule()
    adapter = OpenCodeAdapter()
    written = adapter.write_rule(rule, repo_root=tmp_path)
    assert written == []
    # The adapter must not touch the .opencode tree just because a rule was offered.
    assert not (tmp_path / ".opencode").exists()
    # Nor the AGENTS.md path — that belongs to the sibling adapter.
    assert not (tmp_path / "AGENTS.md").exists()


def test_write_skill_returns_empty_list_and_creates_no_files(tmp_path: Path) -> None:
    """OpenCode reads .claude/skills/ natively, so the adapter does not write skills."""
    skill = _make_skill()
    adapter = OpenCodeAdapter()
    written = adapter.write_skill(skill, repo_root=tmp_path)
    assert written == []
    # The adapter must not touch the .opencode tree just because a skill was offered.
    assert not (tmp_path / ".opencode").exists()
    # Nor the .claude tree — that belongs to the Claude Code adapter.
    assert not (tmp_path / ".claude").exists()
