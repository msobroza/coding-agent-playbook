"""Tests for the renderer subsystem. See SPEC.md §9 and specs/prA-core-internals.md."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from jinja2 import UndefinedError

from coding_agent_playbook.renderer import (
    build_environment,
    render_artifact_body,
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
