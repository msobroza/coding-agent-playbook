"""Tests for the Continue adapter (PR B Track 6). SPEC §10.2."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from coding_agent_playbook.adapters.continue_adapter import ContinueAdapter
from coding_agent_playbook.renderer import SENTINEL
from coding_agent_playbook.types import Prompt, PromptFrontmatter, Rule, RuleFrontmatter

if TYPE_CHECKING:
    from pathlib import Path


class _StubRegistry:
    """In-memory ``RuleRegistry`` used by the Continue adapter tests."""

    def __init__(self, fragments: dict[str, str]) -> None:
        self._fragments = fragments

    def render_for_inclusion(self, rule_id: str, context: dict[str, Any]) -> str:
        return self._fragments.get(rule_id, "")


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
            globs=list(globs) if globs is not None else [],
            priority=priority,
        ),
        body=body,
        template_body=body,
        is_templated=False,
        source_path=None,
        source_package="coding_agent_playbook",
    )


# --- Task 6.2: write_rule -------------------------------------------------


def test_continue_write_rule_creates_file_with_sentinel(tmp_path: Path) -> None:
    rule = _make_rule(rule_id="x", priority=50, globs=["**/*.py"])
    adapter = ContinueAdapter()
    written = adapter.write_rule(rule, repo_root=tmp_path)
    expected = tmp_path / ".continue" / "rules" / "50-x.md"
    assert written == [expected]
    content = expected.read_text(encoding="utf-8")
    assert SENTINEL in content.split("\n", 1)[0]
    assert "name: Python typing standards" in content
    assert "alwaysApply: false" in content
    assert "**/*.py" in content


def test_continue_write_rule_zero_pads_priority(tmp_path: Path) -> None:
    """Priority must format as two-digit zero-padded for stable lex sort."""
    rule = _make_rule(rule_id="early", priority=5)
    written = ContinueAdapter().write_rule(rule, repo_root=tmp_path)
    assert written == [tmp_path / ".continue" / "rules" / "05-early.md"]


def test_continue_write_rule_creates_parent_directory(tmp_path: Path) -> None:
    """write_rule must create .continue/rules/ if it does not already exist."""
    rule = _make_rule(rule_id="x", priority=50)
    assert not (tmp_path / ".continue").exists()
    ContinueAdapter().write_rule(rule, repo_root=tmp_path)
    assert (tmp_path / ".continue" / "rules").is_dir()


def test_continue_write_rule_always_scope_drops_globs(tmp_path: Path) -> None:
    """A scope=always rule must render alwaysApply: true with no globs (renderer
    contract — Continue treats globs as meaningful only when alwaysApply=false)."""
    rule = _make_rule(rule_id="x", scope="always", globs=["**/*.py"])
    written = ContinueAdapter().write_rule(rule, repo_root=tmp_path)
    content = written[0].read_text(encoding="utf-8")
    assert "alwaysApply: true" in content
    assert "globs:" not in content


# --- Task 6.3: write_prompt -----------------------------------------------


def _make_prompt(
    *,
    prompt_id: str = "generate-tests",
    name: str = "Generate tests",
    description: str = "Generate pytest tests",
    slash: str = "generate-tests",
    includes_rules: list[str] | None = None,
    body: str = "# Generate tests\n\nWrite tests.\n",
) -> Prompt:
    return Prompt(
        frontmatter=PromptFrontmatter(
            id=prompt_id,
            name=name,
            description=description,
            slash=slash,
            includes_rules=list(includes_rules) if includes_rules is not None else [],
        ),
        body=body,
        template_body=body,
        is_templated=False,
        source_path=None,
        source_package="coding_agent_playbook",
    )


def test_continue_write_prompt_creates_file_with_sentinel(tmp_path: Path) -> None:
    prompt = _make_prompt(slash="generate-tests")
    adapter = ContinueAdapter()
    written = adapter.write_prompt(prompt, repo_root=tmp_path)
    expected = tmp_path / ".continue" / "prompts" / "generate-tests.md"
    assert written == [expected]
    content = expected.read_text(encoding="utf-8")
    assert SENTINEL in content.split("\n", 1)[0]
    assert "name: Generate tests" in content
    assert "description: Generate pytest tests" in content
    assert "invokable: true" in content


def test_continue_write_prompt_creates_parent_directory(tmp_path: Path) -> None:
    """write_prompt must create .continue/prompts/ if it does not already exist."""
    prompt = _make_prompt(slash="x")
    assert not (tmp_path / ".continue").exists()
    ContinueAdapter().write_prompt(prompt, repo_root=tmp_path)
    assert (tmp_path / ".continue" / "prompts").is_dir()


def test_continue_write_prompt_no_appendix_without_registry(tmp_path: Path) -> None:
    """When the adapter is constructed without a rule_registry, includes_rules
    is declarative-only and no '## Reference rules' appendix is appended."""
    prompt = _make_prompt(includes_rules=["x"])
    adapter = ContinueAdapter()
    written = adapter.write_prompt(prompt, repo_root=tmp_path)
    content = written[0].read_text(encoding="utf-8")
    assert "## Reference rules" not in content


def test_continue_write_prompt_renders_includes_rules_appendix(tmp_path: Path) -> None:
    """When constructed with a registry, the includes_rules appendix is emitted."""
    prompt = _make_prompt(includes_rules=["x"])
    registry = _StubRegistry({"x": "### X\n\nrule body\n"})
    adapter = ContinueAdapter(rule_registry=registry)
    written = adapter.write_prompt(prompt, repo_root=tmp_path)
    content = written[0].read_text(encoding="utf-8")
    assert "## Reference rules" in content
    assert "### X" in content
    assert "rule body" in content
