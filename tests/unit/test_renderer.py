"""Tests for the renderer subsystem. See SPEC.md §9 and specs/prA-core-internals.md."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from jinja2 import UndefinedError

from coding_agent_playbook.renderer import (
    SENTINEL,
    build_environment,
    carries_engine_sentinel,
    includes_rules_appendix,
    render_artifact_body,
    render_for,
    render_string,
    with_sentinel_body,
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


# --- includes_rules appendix is decided on the template body (SPEC §6.2.5) ---

_PROMPT_FORMATS = ["prompt_continue", "prompt_claude_command", "prompt_opencode_command"]
_INLINE_FRONTMATTER = {"name": "P", "description": "D", "includes_rules": ["x"]}


@pytest.mark.parametrize("fmt", _PROMPT_FORMATS)
def test_render_for_no_appendix_when_template_inlines_an_already_rendered_rule(
    tmp_path: Path, fmt: str
) -> None:
    """Regression: sync hands render_for the RENDERED body, where the ``rule()``
    call is already expanded. Deciding on it emitted every inlined rule twice."""
    registry = StubRuleRegistry({"x": "### X\n\nrule body\n"})
    out = render_for(
        tmp_path / "p.md.j2",
        "Intro\n### X\n\nrule body\n",
        fmt,
        frontmatter=_INLINE_FRONTMATTER,
        rule_registry=registry,
        template_body='Intro\n{{ rule("x") }}\n',
    )
    assert out.count("rule body") == 1
    assert "## Reference rules" not in out


@pytest.mark.parametrize("fmt", _PROMPT_FORMATS)
def test_render_for_appends_appendix_when_template_has_no_rule_call(
    tmp_path: Path, fmt: str
) -> None:
    registry = StubRuleRegistry({"x": "### X\n\nrule body\n"})
    out = render_for(
        tmp_path / "p.md",
        "Plain body\n",
        fmt,
        frontmatter=_INLINE_FRONTMATTER,
        rule_registry=registry,
        template_body="Plain body\n",
    )
    assert out.count("rule body") == 1
    assert "## Reference rules" in out


@pytest.mark.parametrize(
    "template_body",
    [
        '{{rule("x")}}',
        "{{- rule('x') }}",
        '{{  rule ( "x" ) }}',
        '{% raw %}{{ rule("x") }}{% endraw %}',
    ],
)
def test_includes_rules_appendix_suppressed_for_any_rule_call_spelling(template_body: str) -> None:
    registry = StubRuleRegistry({"x": "### X\n\nrule body\n"})

    assert includes_rules_appendix(template_body, _INLINE_FRONTMATTER, registry) == ""


def test_includes_rules_appendix_lists_rules_for_a_template_without_calls() -> None:
    registry = StubRuleRegistry({"x": "### X\n\nrule body\n"})

    appendix = includes_rules_appendix("no calls here", _INLINE_FRONTMATTER, registry)

    assert appendix == "\n## Reference rules\n\n### X\n\nrule body\n"


# --- engine-output detection (sentinel position) ----------------------------

_BODY_FIRST = with_sentinel_body("---\ndescription: d\n---", "body\n")


@pytest.mark.parametrize(
    ("text", "after_frontmatter", "owned"),
    [
        (f"<!-- {SENTINEL} -->\n# Title\n", False, True),
        (f"<!-- {SENTINEL} -->\n---\ndescription: d\n---\nbody\n", False, True),
        (_BODY_FIRST, True, True),
        (_BODY_FIRST, False, False),
        ("\ufeff" + _BODY_FIRST, True, True),
        (f"\ufeff<!-- {SENTINEL} -->\n# Title\n", False, True),
        (f"---\ndescription: d\n---\nFiles saying {SENTINEL} are generated.\n", True, False),
        ("---\ndescription: d\n---\nbody\n", True, False),
        (f"---\ndescription: d\n---\nintro\n<!-- {SENTINEL} -->\n", True, False),
        (f"intro\n<!-- {SENTINEL} -->\n", True, False),
        (f"---\ndescription: {SENTINEL}\n---\nbody\n", True, False),
        ("", True, False),
    ],
    ids=[
        "line-1",
        "legacy-line-1-before-frontmatter",
        "first-body-line-opted-in",
        "first-body-line-not-opted-in",
        "bom-first-body-line",
        "bom-line-1",
        "first-body-line-quotes-it-in-prose",
        "no-sentinel",
        "deeper-in-body",
        "line-2-no-frontmatter",
        "inside-frontmatter",
        "empty",
    ],
)
def test_carries_engine_sentinel_only_at_the_engine_positions(
    text: str, after_frontmatter: bool, owned: bool
) -> None:
    assert carries_engine_sentinel(text, after_frontmatter=after_frontmatter) is owned


def test_opencode_command_starts_with_its_frontmatter(tmp_path: Path) -> None:
    """OpenCode's gray-matter needs ``---`` at offset 0; the sentinel follows the envelope."""
    out = render_for(
        tmp_path / "p.md",
        "Body\n",
        "prompt_opencode_command",
        frontmatter={"name": "P", "description": "D"},
    )
    assert out == f"---\ndescription: D\n---\n<!-- {SENTINEL} -->\n\nBody\n"
