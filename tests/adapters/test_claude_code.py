"""Tests for the Claude Code adapter (PR B Track 7)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.adapters.claude_code_adapter import ClaudeCodeAdapter
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
    return Rule(
        frontmatter=RuleFrontmatter(
            id=rule_id,
            name=name,
            description=description,
            scope=scope,  # type: ignore[arg-type]
            globs=globs or [],
            priority=priority,
        ),
        body=body,
        template_body=body,
        is_templated=False,
        source_path=None,
        source_package="test",
    )


def _make_prompt(
    *,
    prompt_id: str = "review",
    name: str = "Review",
    description: str = "Review code",
    slash: str = "review",
    body: str = "# Review\n\nReview the diff.\n",
    includes_rules: list[str] | None = None,
    input_variables: list[dict[str, object]] | None = None,
) -> Prompt:
    return Prompt(
        frontmatter=PromptFrontmatter(
            id=prompt_id,
            name=name,
            description=description,
            slash=slash,
            includes_rules=includes_rules or [],
            input_variables=input_variables or [],
        ),
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
    body: str = "# Demo skill\n\nDo the thing.\n",
    scripts_dir: Path | None = None,
    references_dir: Path | None = None,
) -> Skill:
    return Skill(
        frontmatter={"id": skill_id, "name": name, "description": description},
        body=body,
        scripts_dir=scripts_dir,
        references_dir=references_dir,
        source_package="test",
    )


def test_claude_code_adapter_is_adapter_subclass():
    assert issubclass(ClaudeCodeAdapter, Adapter)
    assert ClaudeCodeAdapter.name == "claude_code"


def test_claude_code_adapter_instantiates_with_empty_buffer():
    adapter = ClaudeCodeAdapter()
    assert adapter._buffered_rules == []


def test_claude_code_write_rule_buffers_does_not_write(tmp_path):
    rule = _make_rule(rule_id="x", priority=50, globs=["**/*.py"])
    adapter = ClaudeCodeAdapter()
    written = adapter.write_rule(rule, repo_root=tmp_path)
    assert written == []
    # No .claude/ directory or files were created.
    assert not (tmp_path / ".claude").exists()
    # The rule was buffered for finalize() to compose.
    assert len(adapter._buffered_rules) == 1
    priority, rule_id, rendered_section = adapter._buffered_rules[0]
    assert priority == 50
    assert rule_id == "x"
    # Rendered section is a claude_md_section: ## heading, optional applies-to,
    # body, separator.
    assert "## Python typing standards" in rendered_section
    assert "*Applies to: `**/*.py`*" in rendered_section


def test_claude_code_write_rule_appends_to_buffer_in_call_order(tmp_path):
    adapter = ClaudeCodeAdapter()
    adapter.write_rule(_make_rule(rule_id="a", priority=10, name="A"), tmp_path)
    adapter.write_rule(_make_rule(rule_id="b", priority=20, name="B"), tmp_path)
    assert [item[:2] for item in adapter._buffered_rules] == [(10, "a"), (20, "b")]
