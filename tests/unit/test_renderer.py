"""Tests for the renderer subsystem. See SPEC.md §9 and specs/prA-core-internals.md."""

from __future__ import annotations

import tomllib
from importlib import metadata
from pathlib import Path
from typing import Any

import pytest
from jinja2 import StrictUndefined, UndefinedError
from jinja2.exceptions import SecurityError
from jinja2.sandbox import ImmutableSandboxedEnvironment, SandboxedEnvironment
from packaging.requirements import Requirement
from packaging.version import Version

from coding_agent_playbook.renderer import (
    SENTINEL,
    TemplateSecurityError,
    appendix_rule_ids,
    build_environment,
    render_artifact_body,
    render_for,
    render_sandboxed,
    render_string,
)


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


def test_has_ml_dep_helper_true_when_present(tmp_path: Path) -> None:
    env = build_environment([tmp_path])
    env.globals["_facts"] = {"ml_stack": {"torch": "2.3.0"}}
    template = '{% if has_ml_dep("torch") %}yes{% endif %}'
    assert render_string(template, {}, env=env) == "yes"


def test_has_ml_dep_helper_false_when_absent(tmp_path: Path) -> None:
    env = build_environment([tmp_path])
    env.globals["_facts"] = {"ml_stack": {}}
    template = '{% if has_ml_dep("torch") %}yes{% endif %}'
    assert render_string(template, {}, env=env) == ""


def test_has_ml_dep_helper_does_not_read_frameworks(tmp_path: Path) -> None:
    # has_ml_dep reads facts["ml_stack"], not facts["frameworks"].
    env = build_environment([tmp_path])
    env.globals["_facts"] = {"frameworks": {"torch": "2.3.0"}}
    template = '{% if has_ml_dep("torch") %}yes{% endif %}'
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
        "scope": "scoped",
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
    assert "alwaysApply: false" in out
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


def test_render_for_continue_rule_drops_globs_when_always_apply(tmp_path: Path) -> None:
    """When scope=always, alwaysApply=true, globs is not emitted
    (Continue semantics — globs is meaningful only with alwaysApply=false)."""
    out = render_for(
        tmp_path / "rule.md.j2",
        "body",
        "continue_rule",
        frontmatter={
            "id": "x",
            "name": "X",
            "description": "x",
            "scope": "always",
            "globs": ["**/*.py"],
        },
    )
    assert "alwaysApply: true" in out
    assert "globs:" not in out


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


# --- Task B.4 step 3: prompt_continue / prompt_claude_command /
#     prompt_opencode_command + includes_rules appendix --------------------


def test_render_for_prompt_continue_with_includes_rules_appendix(tmp_path: Path) -> None:
    frontmatter = {
        "id": "review-code",
        "name": "Review code",
        "description": "Review a diff for safety.",
        "slash": "/review",
        "includes_rules": ["x"],
    }
    body = "Review the diff.\n"
    registry = StubRuleRegistry({"x": "### X\n\nrule body\n"})
    out = render_for(
        tmp_path / "prompts" / "review-code.md",
        body,
        "prompt_continue",
        frontmatter=frontmatter,
        rule_registry=registry,
    )
    assert "name: Review code" in out
    assert "description: Review a diff for safety." in out
    assert "invokable: true" in out
    assert "Review the diff." in out
    assert "## Reference rules" in out
    assert "### X" in out
    assert "rule body" in out
    assert SENTINEL in out


def test_render_for_prompt_continue_no_appendix_when_inline_rule_call(
    tmp_path: Path,
) -> None:
    frontmatter = {
        "id": "review-code",
        "name": "Review code",
        "description": "Review a diff for safety.",
        "slash": "/review",
        "includes_rules": ["x"],
    }
    # Body already references the rule inline — author placed it themselves.
    body = 'Read this rule: {{ rule("x") }}\nThen review.\n'
    registry = StubRuleRegistry({"x": "### X\n\nrule body\n"})
    out = render_for(
        tmp_path / "prompts" / "review-code.md",
        body,
        "prompt_continue",
        frontmatter=frontmatter,
        rule_registry=registry,
    )
    assert "## Reference rules" not in out
    assert "Then review." in out


def test_render_for_prompt_opencode_command_single_arg_substitution(
    tmp_path: Path,
) -> None:
    frontmatter = {
        "id": "review",
        "name": "Review",
        "description": "Review.",
        "slash": "/review",
        "input_variables": [{"name": "target", "description": "what to review"}],
    }
    body = "Please review {{ target }} carefully.\n"
    out = render_for(
        tmp_path / "prompts" / "review.md",
        body,
        "prompt_opencode_command",
        frontmatter=frontmatter,
    )
    assert "$ARGUMENTS" in out
    assert "{{ target }}" not in out
    assert "description: Review." in out


def test_render_for_prompt_opencode_command_multi_arg_substitution(
    tmp_path: Path,
) -> None:
    frontmatter = {
        "id": "compare",
        "name": "Compare",
        "description": "Compare two things.",
        "slash": "/compare",
        "input_variables": [
            {"name": "a", "description": "first"},
            {"name": "b", "description": "second"},
        ],
    }
    body = "Compare {{ a }} with {{ b }}.\n"
    out = render_for(
        tmp_path / "prompts" / "compare.md",
        body,
        "prompt_opencode_command",
        frontmatter=frontmatter,
    )
    assert "$1" in out
    assert "$2" in out
    assert "{{ a }}" not in out
    assert "{{ b }}" not in out


def test_render_for_prompt_claude_command_emits_title_and_body(tmp_path: Path) -> None:
    frontmatter = {
        "id": "review",
        "name": "Review",
        "description": "Review a diff.",
        "slash": "/review",
    }
    body = "Step 1: read the diff.\n"
    out = render_for(
        tmp_path / "prompts" / "review.md",
        body,
        "prompt_claude_command",
        frontmatter=frontmatter,
    )
    assert "# Review" in out
    assert "Step 1: read the diff." in out


def test_render_for_prompt_opencode_command_escapes_special_description(
    tmp_path: Path,
) -> None:
    """A description containing a colon or quote must produce valid YAML
    (code-quality review I4 — was using raw f-string)."""
    import yaml as _yaml

    out = render_for(
        tmp_path / "prompt.md.j2",
        "hello",
        "prompt_opencode_command",
        frontmatter={"description": 'has: colons and "quotes"'},
    )
    # Reparse and check we get the original description back
    parts = out.split("---\n", 2)
    parsed = _yaml.safe_load(parts[1])
    assert parsed["description"] == 'has: colons and "quotes"'


# --- Task B.6 / code-quality review I6: full-string equality tests --------


def test_render_for_continue_rule_exact_output(tmp_path: Path) -> None:
    """Locks the exact output shape of continue_rule to catch whitespace
    regressions (code-quality review I6)."""
    out = render_for(
        tmp_path / "rule.md.j2",
        "body line 1\nbody line 2\n",
        "continue_rule",
        frontmatter={
            "id": "py-typing",
            "name": "Py typing",
            "description": "Type hints",
            "scope": "scoped",
            "globs": ["**/*.py"],
        },
    )
    expected = (
        f"<!-- {SENTINEL} -->\n"
        "---\n"
        "name: Py typing\n"
        "description: Type hints\n"
        "alwaysApply: false\n"
        "globs:\n"
        "- '**/*.py'\n"
        "---\n"
        "body line 1\nbody line 2\n"
    )
    assert out == expected


def test_render_for_claude_md_section_exact_output(tmp_path: Path) -> None:
    """Locks the exact output shape of claude_md_section to catch whitespace
    regressions (code-quality review I6)."""
    out = render_for(
        tmp_path / "rule.md",
        "body line 1\nbody line 2\n",
        "claude_md_section",
        frontmatter={
            "id": "x",
            "name": "X",
            "description": "d",
            "scope": "scoped",
            "globs": ["**/*.py"],
        },
    )
    expected = "## X\n\n*Applies to: `**/*.py`*\n\nbody line 1\nbody line 2\n\n---\n"
    assert out == expected


def test_render_for_prompt_continue_exact_output(tmp_path: Path) -> None:
    """Locks the exact output shape of prompt_continue (no includes_rules)
    to catch whitespace regressions (code-quality review I6)."""
    out = render_for(
        tmp_path / "prompt.md.j2",
        "body line 1\nbody line 2\n",
        "prompt_continue",
        frontmatter={"name": "P", "description": "D"},
    )
    expected = (
        f"<!-- {SENTINEL} -->\n"
        "---\n"
        "name: P\n"
        "description: D\n"
        "invokable: true\n"
        "---\n"
        "body line 1\nbody line 2\n"
    )
    assert out == expected


def test_render_for_prompt_continue_no_appendix_when_all_fragments_empty(
    tmp_path: Path,
) -> None:
    """When includes_rules is set but every rule's applies_if evaluates false
    (registry returns ""), no Reference rules section is emitted
    (code-quality review M5)."""
    registry = StubRuleRegistry({"foo": "", "bar": ""})
    out = render_for(
        tmp_path / "prompt.md.j2",
        "body",
        "prompt_continue",
        frontmatter={
            "name": "P",
            "description": "D",
            "includes_rules": ["foo", "bar"],
        },
        rule_registry=registry,
    )
    assert "## Reference rules" not in out


# --- prK §P1: sandboxed Jinja environment -----------------------------------

#: Classic template-injection escapes from a template to Python internals.
_SANDBOX_ESCAPES = (
    pytest.param('{{ lipsum.__globals__["os"].__name__ }}', id="lipsum.__globals__"),
    pytest.param("{{ cycler.__init__.__globals__.os.name }}", id="cycler.__init__.__globals__"),
    pytest.param("{{ ''.__class__.__mro__[1].__subclasses__() }}", id="str.__class__.__mro__"),
)


@pytest.mark.parametrize("is_prompt_context", [False, True], ids=["rule-env", "prompt-env"])
def test_build_environment_is_sandboxed(tmp_path: Path, is_prompt_context: bool) -> None:
    registry = StubRuleRegistry({}) if is_prompt_context else None
    env = build_environment([tmp_path], is_prompt_context=is_prompt_context, rule_registry=registry)
    assert isinstance(env, SandboxedEnvironment)
    # Mutable sandbox on purpose: the escape-to-``os`` threat does not need the
    # immutable variant, which would also reject in-template list/dict mutation.
    assert not isinstance(env, ImmutableSandboxedEnvironment)


def test_sandboxed_environment_keeps_render_options(tmp_path: Path) -> None:
    env = build_environment([tmp_path])
    assert env.autoescape is False
    assert env.keep_trailing_newline is True
    assert env.trim_blocks is True
    assert env.lstrip_blocks is True
    assert env.undefined is StrictUndefined


@pytest.mark.parametrize("template", _SANDBOX_ESCAPES)
def test_sandbox_blocks_globals_escape(tmp_path: Path, template: str) -> None:
    env = build_environment([tmp_path])
    with pytest.raises(SecurityError):
        render_string(template, {}, env=env)


def test_sandbox_allows_in_template_list_mutation(tmp_path: Path) -> None:
    env = build_environment([tmp_path])
    template = "{% set seen = [] %}{{ seen.append('a') or seen | join(',') }}"
    assert render_string(template, {}, env=env) == "a"


def test_render_sandboxed_names_the_source_on_a_violation(tmp_path: Path) -> None:
    """jinja2's bare ``SecurityError`` becomes ``TemplateSecurityError`` naming the file."""
    env = build_environment([tmp_path])
    with pytest.raises(TemplateSecurityError) as caught:
        render_sandboxed(
            '{{ lipsum.__globals__["os"] }}', {}, env=env, source="playbook/rules/x.md.j2"
        )
    assert caught.value.source == "playbook/rules/x.md.j2"
    assert "unsafe" in caught.value.detail
    assert str(caught.value).startswith("playbook/rules/x.md.j2: template rejected")
    assert render_sandboxed("{{ x }}", {"x": "ok"}, env=env, source="s") == "ok"


def test_appendix_rule_ids_follow_includes_rules_unless_body_inlines_them() -> None:
    assert appendix_rule_ids(["a", "b"], "Refactor.\n") == ["a", "b"]
    assert appendix_rule_ids(["a"], "{{ rule('a') }}\n") == []
    assert appendix_rule_ids([], "body") == []


#: The jinja2 release closing the published sandbox escapes (CVE-2024-56326,
#: fixed in 3.1.5; CVE-2025-27516, fixed in 3.1.6). Keep in step with the
#: ``jinja2>=`` floor in ``pyproject.toml`` (SPEC §9.3, §17).
_JINJA_SANDBOX_FLOOR = Version("3.1.6")


def test_jinja_version_has_sandbox_fixes() -> None:
    """The sandbox is the security boundary for agent-writable templates (prK §P1)."""
    assert Version(metadata.version("jinja2")) >= _JINJA_SANDBOX_FLOOR


def test_pyproject_pins_the_jinja_sandbox_floor() -> None:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    dependencies = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["dependencies"]
    [jinja] = [Requirement(dep) for dep in dependencies if dep.startswith("jinja2")]
    assert jinja.specifier.contains(str(_JINJA_SANDBOX_FLOOR))
    assert not jinja.specifier.contains("3.1.5")
