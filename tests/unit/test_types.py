"""Tests for canonical types and markdown round-trip (PR 2). SPEC §6.6."""

from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent_playbook.types import (
    Prompt,
    PromptFrontmatter,
    Rule,
    RuleFrontmatter,
    Skill,
    format_frontmatter,
    split_frontmatter,
)

RULE_MD = """\
---
id: python-typing
name: Python typing standards
description: Type hints everywhere
scope: scoped
globs:
  - "**/*.py"
applies_if:
  python_version: ">=3.11"
tags: [language, python]
---
# Python typing standards

Body line.
"""

PROMPT_MD = """\
---
id: generate-tests
name: Generate tests
description: Generate pytest tests
slash: generate-tests
includes_rules:
  - python-typing
  - pytest
---
# Task: generate tests

Body.
"""


def _make_rule() -> Rule:
    return Rule(
        frontmatter=RuleFrontmatter(
            id="python-typing",
            name="Python typing standards",
            description="Type hints everywhere",
            scope="scoped",
            globs=["**/*.py"],
            applies_if={"python_version": ">=3.11"},
            tags=["language", "python"],
        ),
        body="# Body\n",
        template_body="# Body\n",
        is_templated=False,
        source_path=Path("rules/typing.md"),
        source_package="coding_agent_playbook",
    )


# ---------------------------------------------------------------------------
# split_frontmatter
# ---------------------------------------------------------------------------


def test_split_frontmatter_parses_mapping_and_body():
    data, body = split_frontmatter(RULE_MD)
    assert data["id"] == "python-typing"
    assert body.startswith("# Python typing standards")


def test_split_frontmatter_requires_opening_fence():
    with pytest.raises(ValueError, match="frontmatter fence"):
        split_frontmatter("no frontmatter here")


def test_split_frontmatter_requires_closing_fence():
    with pytest.raises(ValueError, match="unterminated"):
        split_frontmatter("---\nid: x\nstill open\n")


def test_split_frontmatter_rejects_non_mapping():
    with pytest.raises(ValueError, match="YAML mapping"):
        split_frontmatter("---\n- a\n- b\n---\nbody\n")


def test_split_frontmatter_rejects_indented_closing_fence():
    """An indented '---' inside a YAML multi-line scalar must not be treated
    as the closing fence (bug_006 — round-trip regression)."""
    text = (
        "---\n"
        "id: x\n"
        "name: x\n"
        "description: 'line one\n"
        "\n"
        "  ---\n"
        "\n"
        "  line two'\n"
        "scope: scoped\n"
        "---\n"
        "body\n"
    )
    data, body = split_frontmatter(text)
    assert data["description"] == "line one\n---\nline two"
    assert body == "body\n"


# ---------------------------------------------------------------------------
# format_frontmatter round-trip
# ---------------------------------------------------------------------------


def test_frontmatter_text_roundtrip():
    data, body = split_frontmatter(RULE_MD)
    reparsed, reparsed_body = split_frontmatter(format_frontmatter(data, body))
    assert reparsed == data
    assert reparsed_body == body


# ---------------------------------------------------------------------------
# Rule and RuleFrontmatter
# ---------------------------------------------------------------------------


def test_rule_from_markdown_reads_fields(tmp_path):
    path = tmp_path / "typing.md.j2"
    path.write_text(RULE_MD, encoding="utf-8")
    rule = Rule.from_markdown(path, "coding_agent_playbook")
    assert rule.frontmatter.id == "python-typing"
    assert rule.frontmatter.scope == "scoped"
    assert rule.frontmatter.priority == 50  # default applied
    assert rule.is_templated is True
    assert rule.body == rule.template_body
    assert rule.source_package == "coding_agent_playbook"


def test_plain_md_is_not_templated(tmp_path):
    path = tmp_path / "typing.md"
    path.write_text(RULE_MD, encoding="utf-8")
    assert Rule.from_markdown(path, "pkg").is_templated is False


def test_rule_dict_roundtrip():
    rule = _make_rule()
    assert Rule.from_dict(rule.to_dict()) == rule


def test_rule_markdown_roundtrip(tmp_path):
    path = tmp_path / "rule.md.j2"
    path.write_text(RULE_MD, encoding="utf-8")
    rule = Rule.from_markdown(path, "pkg")
    path.write_text(rule.to_markdown(), encoding="utf-8")  # same path → same source_path
    assert Rule.from_markdown(path, "pkg") == rule


def test_rule_markdown_roundtrip_with_horizontal_rule_in_description(tmp_path):
    """Rule with a '---' line inside its description round-trips through markdown
    (bug_006 — the round-trip contract from SPEC §6.6.3)."""
    rule = Rule(
        frontmatter=RuleFrontmatter(
            id="x",
            name="x",
            description="line one\n---\nline two",
            scope="scoped",
        ),
        body="body\n",
        template_body="body\n",
        is_templated=False,
        source_path=tmp_path / "rule.md",
        source_package="pkg",
    )
    path = tmp_path / "rule.md"
    path.write_text(rule.to_markdown(), encoding="utf-8")
    assert Rule.from_markdown(path, "pkg") == rule


def test_rule_frontmatter_coerces_none_to_defaults():
    """YAML 'globs:' (blank) parses as None; the dataclass must coerce that
    back to the declared default so the field type holds (bug_001)."""
    fm = RuleFrontmatter(
        id="x",
        name="x",
        description="x",
        scope="scoped",
        version=None,  # type: ignore[arg-type]
        globs=None,  # type: ignore[arg-type]
        applies_if=None,  # type: ignore[arg-type]
        priority=None,  # type: ignore[arg-type]
        tags=None,  # type: ignore[arg-type]
    )
    assert fm.version == 1
    assert fm.globs == []
    assert fm.applies_if == {}
    assert fm.priority == 50
    assert fm.tags == []


def test_rule_markdown_roundtrip_with_blank_optional_fields(tmp_path):
    """A rule authored with blank 'globs:' / 'priority:' lines round-trips
    through markdown (bug_001 — SPEC §6.6.3 contract)."""
    text = (
        "---\n"
        "id: x\n"
        "name: x\n"
        "description: x\n"
        "scope: scoped\n"
        "globs:\n"
        "priority:\n"
        "tags:\n"
        "---\n"
        "body\n"
    )
    path = tmp_path / "rule.md"
    path.write_text(text, encoding="utf-8")
    rule = Rule.from_markdown(path, "pkg")
    assert rule.frontmatter.globs == []
    assert rule.frontmatter.priority == 50
    assert rule.frontmatter.tags == []
    path.write_text(rule.to_markdown(), encoding="utf-8")
    assert Rule.from_markdown(path, "pkg") == rule


# ---------------------------------------------------------------------------
# Prompt and PromptFrontmatter
# ---------------------------------------------------------------------------


def test_prompt_dict_roundtrip():
    prompt = Prompt(
        frontmatter=PromptFrontmatter(
            id="generate-tests",
            name="Generate tests",
            description="Generate pytest tests",
            slash="generate-tests",
            includes_rules=["python-typing", "pytest"],
            eval_tasks=["generate-tests-happy-path"],
        ),
        body="# Task\n",
        template_body="# Task\n",
        is_templated=False,
        source_path=None,
        source_package="pkg",
    )
    assert Prompt.from_dict(prompt.to_dict()) == prompt


def test_prompt_markdown_roundtrip(tmp_path):
    path = tmp_path / "generate-tests.md.j2"
    path.write_text(PROMPT_MD, encoding="utf-8")
    prompt = Prompt.from_markdown(path, "pkg")
    assert prompt.frontmatter.slash == "generate-tests"
    assert prompt.frontmatter.includes_rules == ["python-typing", "pytest"]
    path.write_text(prompt.to_markdown(), encoding="utf-8")
    assert Prompt.from_markdown(path, "pkg") == prompt


def test_prompt_frontmatter_coerces_none_to_defaults():
    """Same coercion contract for PromptFrontmatter (bug_001)."""
    fm = PromptFrontmatter(
        id="x",
        name="x",
        description="x",
        slash="x",
        version=None,  # type: ignore[arg-type]
        applies_if=None,  # type: ignore[arg-type]
        input_variables=None,  # type: ignore[arg-type]
        includes_rules=None,  # type: ignore[arg-type]
        eval_tasks=None,  # type: ignore[arg-type]
    )
    assert fm.version == 1
    assert fm.applies_if == {}
    assert fm.input_variables == []
    assert fm.includes_rules == []
    assert fm.eval_tasks == []


# ---------------------------------------------------------------------------
# Skill
# ---------------------------------------------------------------------------


def test_skill_to_prompt_deferred_to_pr6():
    skill = Skill(
        frontmatter={"name": "demo"},
        body="b",
        scripts_dir=None,
        references_dir=None,
        source_package="pkg",
    )
    with pytest.raises(NotImplementedError):
        skill.to_prompt()


def test_skill_dict_roundtrip():
    skill = Skill(
        frontmatter={"name": "demo"},
        body="b",
        scripts_dir=Path("skills/demo/scripts"),
        references_dir=None,
        source_package="pkg",
    )
    assert Skill.from_dict(skill.to_dict()) == skill


def test_skill_to_dict_does_not_alias_frontmatter():
    """to_dict must return a snapshot; mutating it must not mutate the Skill
    (bug_002 — matches the Rule/Prompt detached-snapshot contract)."""
    skill = Skill(
        frontmatter={"name": "demo"},
        body="b",
        scripts_dir=None,
        references_dir=None,
        source_package="pkg",
    )
    data = skill.to_dict()
    assert data["frontmatter"] is not skill.frontmatter
    data["frontmatter"]["injected"] = True
    assert "injected" not in skill.frontmatter


def test_skill_from_dict_does_not_alias_frontmatter():
    """from_dict must detach from its input; mutating the dict must not
    mutate the resulting Skill (bug_002)."""
    payload = {
        "frontmatter": {"name": "demo"},
        "body": "b",
        "scripts_dir": None,
        "references_dir": None,
        "source_package": "pkg",
    }
    skill = Skill.from_dict(payload)
    payload["frontmatter"]["injected"] = True
    assert "injected" not in skill.frontmatter
