"""Tests for the renderer subsystem. See SPEC.md §9 and specs/prA-core-internals.md."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from jinja2 import UndefinedError

from coding_agent_playbook.renderer import (
    SENTINEL,
    build_environment,
    render_artifact_body,
    render_for,
    render_string,
)

if TYPE_CHECKING:
    from pathlib import Path


class StubRuleRegistry:
    """In-memory ``RuleRegistry`` used by the renderer tests."""

    def __init__(self, fragments: dict[str, str]) -> None:
        self._fragments = fragments

    def render_for_inclusion(self, rule_id: str, context: dict[str, Any]) -> str:
        return self._fragments.get(rule_id, "")


# --- Task B.2: build_environment + extension dispatch ---------------------


def test_plain_md_body_returned_verbatim(tmp_path: Path) -> None:
    body_file = tmp_path / "body.md"
    body_file.write_text("Hello {{ name }} — no Jinja here.\n", encoding="utf-8")
    env = build_environment([tmp_path])
    assert render_artifact_body(body_file, {"name": "World"}, env=env) == (
        "Hello {{ name }} — no Jinja here.\n"
    )


def test_md_j2_body_substitutes_variables(tmp_path: Path) -> None:
    template = tmp_path / "greeting.md.j2"
    template.write_text("Hello {{ name }}\n", encoding="utf-8")
    env = build_environment([tmp_path])
    assert render_artifact_body(template, {"name": "World"}, env=env) == "Hello World\n"


def test_strict_undefined_raises_on_typo(tmp_path: Path) -> None:
    template = tmp_path / "typo.md.j2"
    template.write_text("{{ python_versoin }}\n", encoding="utf-8")
    env = build_environment([tmp_path])
    with pytest.raises(UndefinedError):
        render_artifact_body(template, {"python_version": "3.12"}, env=env)


# --- Task B.3: has_framework + rule helpers --------------------------------


def test_has_framework_helper_true_when_present(tmp_path: Path) -> None:
    env = build_environment([tmp_path])
    env.globals["_facts"] = {"frameworks": {"fastapi": "0.115.0"}}
    template = '{% if has_framework("fastapi") %}yes{% endif %}'
    assert render_string(template, {}, env=env) == "yes"


def test_has_framework_helper_false_when_absent(tmp_path: Path) -> None:
    env = build_environment([tmp_path])
    env.globals["_facts"] = {"frameworks": {}}
    template = '{% if has_framework("fastapi") %}yes{% endif %}'
    assert render_string(template, {}, env=env) == ""


def test_rule_helper_registered_in_prompt_env(tmp_path: Path) -> None:
    registry = StubRuleRegistry({"foo": "### Foo\n\nbody of foo\n"})
    env = build_environment([tmp_path], is_prompt_context=True, rule_registry=registry)
    assert render_string('{{ rule("foo") }}', {}, env=env) == "### Foo\n\nbody of foo\n"


def test_rule_helper_not_registered_in_rule_env(tmp_path: Path) -> None:
    env = build_environment([tmp_path])
    with pytest.raises(UndefinedError):
        render_string('{{ rule("foo") }}', {}, env=env)


def test_rule_helper_requires_registry_in_prompt_env(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="rule_registry"):
        build_environment([tmp_path], is_prompt_context=True)


# --- Task B.4 step 1: continue_rule + alias resolution + unknown-format ----


def test_render_for_continue_rule(tmp_path: Path) -> None:
    frontmatter = {
        "id": "py-typing",
        "name": "Python typing",
        "description": "Always use type hints.",
        "scope": "always",
        "globs": ["**/*.py"],
        "version": 1,
        "priority": 50,
        "tags": ["python"],
        "applies_if": {},
    }
    body = "Use type hints everywhere.\n"
    out = render_for(
        tmp_path / "rules" / "py-typing.md",
        body,
        "continue_rule",
        frontmatter=frontmatter,
    )
    assert SENTINEL in out
    assert "alwaysApply: true" in out
    assert "name: Python typing" in out
    assert "description: Always use type hints." in out
    assert "globs:" in out
    # Continue-shaped frontmatter must NOT include canonical-only keys.
    assert "id:" not in out
    assert "version:" not in out
    assert "scope:" not in out
    assert "priority:" not in out
    assert "tags:" not in out
    assert "applies_if:" not in out
    assert out.endswith(body)


def test_render_for_continue_rule_scoped(tmp_path: Path) -> None:
    frontmatter = {
        "id": "fastapi-routers",
        "name": "FastAPI routers",
        "description": "Use APIRouter for grouping endpoints.",
        "scope": "scoped",
        "globs": ["src/**/routers/*.py"],
    }
    body = "Group endpoints with APIRouter.\n"
    out = render_for(
        tmp_path / "rules" / "fastapi-routers.md",
        body,
        "continue_rule",
        frontmatter=frontmatter,
    )
    assert "alwaysApply: false" in out
    assert "src/**/routers/*.py" in out


def test_format_alias_resolution(tmp_path: Path) -> None:
    frontmatter = {
        "id": "x",
        "name": "X",
        "description": "x",
        "scope": "always",
        "globs": [],
    }
    body = "body\n"
    via_alias = render_for(tmp_path / "x.md", body, "continue", frontmatter=frontmatter)
    via_full = render_for(tmp_path / "x.md", body, "continue_rule", frontmatter=frontmatter)
    assert via_alias == via_full


def test_unknown_format_raises_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bogus"):
        render_for(
            tmp_path / "x.md",
            "body\n",
            "bogus",
            frontmatter={"id": "x", "name": "X", "description": "x", "scope": "always"},
        )


# --- Task B.4 step 2: claude_md_section + agents_md_section ----------------


def test_render_for_claude_md_section_scoped(tmp_path: Path) -> None:
    frontmatter = {
        "id": "fastapi-routers",
        "name": "FastAPI routers",
        "description": "Use APIRouter for grouping endpoints.",
        "scope": "scoped",
        "globs": ["src/**/routers/*.py"],
    }
    body = "Group endpoints with APIRouter.\n"
    out = render_for(
        tmp_path / "rules" / "fastapi-routers.md",
        body,
        "claude_md_section",
        frontmatter=frontmatter,
    )
    assert "## FastAPI routers" in out
    assert "*Applies to: `src/**/routers/*.py`*" in out
    assert "Group endpoints with APIRouter." in out
    assert out.rstrip().endswith("---")


def test_render_for_claude_md_section_always(tmp_path: Path) -> None:
    frontmatter = {
        "id": "py-typing",
        "name": "Python typing",
        "description": "Always use type hints.",
        "scope": "always",
        "globs": [],
    }
    body = "Use type hints everywhere.\n"
    out = render_for(
        tmp_path / "rules" / "py-typing.md",
        body,
        "claude_md_section",
        frontmatter=frontmatter,
    )
    assert "## Python typing" in out
    assert "Applies to:" not in out
    assert "Use type hints everywhere." in out
    assert out.rstrip().endswith("---")


def test_render_for_agents_md_section_identical_to_claude(tmp_path: Path) -> None:
    frontmatter = {
        "id": "fastapi-routers",
        "name": "FastAPI routers",
        "description": "Use APIRouter for grouping endpoints.",
        "scope": "scoped",
        "globs": ["src/**/routers/*.py"],
    }
    body = "Group endpoints with APIRouter.\n"
    claude_out = render_for(
        tmp_path / "rules" / "fastapi-routers.md",
        body,
        "claude_md_section",
        frontmatter=frontmatter,
    )
    agents_out = render_for(
        tmp_path / "rules" / "fastapi-routers.md",
        body,
        "agents_md_section",
        frontmatter=frontmatter,
    )
    assert claude_out == agents_out
