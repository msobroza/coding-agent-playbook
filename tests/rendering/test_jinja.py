"""Tests for the sandboxed Jinja environment (SPEC §9.3) and the rendering package boundary."""

from __future__ import annotations

import tomllib
from importlib import metadata
from pathlib import Path

import pytest
from jinja2 import StrictUndefined, UndefinedError
from jinja2.exceptions import SecurityError
from jinja2.sandbox import ImmutableSandboxedEnvironment, SandboxedEnvironment
from packaging.requirements import Requirement
from packaging.version import Version

from coding_agent_playbook.rendering.jinja import (
    TemplateSecurityError,
    build_environment,
    jinja_syntax_error,
    render_artifact_body,
    render_sandboxed,
    render_string,
)
from tests.engine_modules import engine_module
from tests.import_probe import new_modules_after

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


_ANYIO_TEMPLATE = '{% if has_dependency("anyio") %}yes{% else %}no{% endif %}'


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        ({"dependencies": {"anyio": ">=4"}}, "yes"),
        ({"dev_dependencies": {"anyio": ">=4"}}, "yes"),
        ({"dependencies": {"AnyIO": ">=4"}}, "yes"),  # PEP 503-normalized
        ({"dependencies": {"trio": ">=0.25"}}, "no"),
        ({}, "no"),  # no dependency facts: no 'is defined' guard needed
    ],
    ids=["runtime", "dev", "pep503", "other", "no-facts"],
)
def test_has_dependency_helper_reads_runtime_and_dev_dependencies(
    tmp_path: Path, facts: dict[str, object], expected: str
) -> None:
    env = build_environment([tmp_path])
    env.globals["_facts"] = facts
    assert render_string(_ANYIO_TEMPLATE, {}, env=env) == expected


_AT_LEAST_311 = '{% if python_at_least("3.11") %}new{% else %}old{% endif %}'


@pytest.mark.parametrize(
    ("version", "expected"),
    [("3.9", "old"), ("3.10", "old"), ("3.11", "new"), ("3.12", "new"), ("3.13", "new")],
)
def test_python_at_least_compares_versions_numerically(
    tmp_path: Path, version: str, expected: str
) -> None:
    env = build_environment([tmp_path])
    env.globals["_facts"] = {"python_version": version}
    assert render_string(_AT_LEAST_311, {}, env=env) == expected


def test_python_at_least_is_false_when_python_version_is_undefined(tmp_path: Path) -> None:
    env = build_environment([tmp_path])
    env.globals["_facts"] = {}
    assert render_string(_AT_LEAST_311, {}, env=env) == "old"


def test_python_at_least_is_false_without_any_facts(tmp_path: Path) -> None:
    env = build_environment([tmp_path])
    assert render_string(_AT_LEAST_311, {}, env=env) == "old"


def test_has_ml_dep_helper_does_not_read_frameworks(tmp_path: Path) -> None:
    # has_ml_dep reads facts["ml_stack"], not facts["frameworks"].
    env = build_environment([tmp_path])
    env.globals["_facts"] = {"frameworks": {"torch": "2.3.0"}}
    template = '{% if has_ml_dep("torch") %}yes{% endif %}'
    assert render_string(template, {}, env=env) == ""


@pytest.mark.parametrize("search_dirs", [[], ["prompts"]], ids=["bare", "loader"])
def test_rule_helper_is_undefined_in_every_environment(
    tmp_path: Path, search_dirs: list[str]
) -> None:
    """Regression (D15): ``rule()`` is gone, so a rule, prompt or hook body calling it fails."""
    env = build_environment([tmp_path / name for name in search_dirs])
    with pytest.raises(UndefinedError, match="'rule' is undefined"):
        render_string('{{ rule("foo") }}', {}, env=env)


# --- prK §P1: sandboxed Jinja environment -----------------------------------

#: Classic template-injection escapes from a template to Python internals.
_SANDBOX_ESCAPES = (
    pytest.param('{{ lipsum.__globals__["os"].__name__ }}', id="lipsum.__globals__"),
    pytest.param("{{ cycler.__init__.__globals__.os.name }}", id="cycler.__init__.__globals__"),
    pytest.param("{{ ''.__class__.__mro__[1].__subclasses__() }}", id="str.__class__.__mro__"),
)


def test_build_environment_is_sandboxed(tmp_path: Path) -> None:
    env = build_environment([tmp_path])
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


def test_jinja_syntax_error_names_the_parse_error() -> None:
    found = jinja_syntax_error("{% if x %}unclosed\n")

    assert found is not None
    assert found.startswith("Unexpected end of template.")


@pytest.mark.parametrize(
    "template",
    ["{{ project_name }} {% if x %}ok{% endif %}\n", '{{ lipsum.__globals__["os"] }}'],
    ids=["valid", "escape-parses"],
)
def test_jinja_syntax_error_is_none_for_a_template_that_parses(template: str) -> None:
    """Parse only, ``playbook validate``'s check: an escape parses, the sandbox stops it later."""
    assert jinja_syntax_error(template) is None


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


# --- the package boundary ----------------------------------------------------

_RENDERING_MODULES = ("jinja", "formats", "rule_registry", "prompt_rule_delivery", "session")


def test_rendering_never_imports_the_sync_context() -> None:
    """``rendering`` sits below ``adapters``: it never loads validation, commands or sync.

    The sync context (``SyncContext``, ``validation.context``) once supplied
    ``template_source``; ``rendering.rule_registry`` now takes it from the stdlib
    leaf ``artifacts.identity`` (H11), so no rendering module reaches back up.
    ``rendering.session`` takes the ``Config`` its context reads, never the context.
    """
    loaded = new_modules_after(
        "; ".join(
            f"import {engine_module(f'coding_agent_playbook.rendering.{name}')}"
            for name in _RENDERING_MODULES
        )
    )

    for package in ("validation", "commands", "sync"):
        prefix = engine_module(f"coding_agent_playbook.{package}")
        assert [name for name in loaded if name == prefix or name.startswith(f"{prefix}.")] == []
