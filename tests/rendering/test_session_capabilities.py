"""``framework_skill(role)`` and ``skill_active(name)`` in templates (D74; prU L0-19)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.rendering.session import RenderSession, TemplateContext

if TYPE_CHECKING:
    from coding_agent_playbook.detector.facts import Facts

_FRAMEWORK = "acme.framework"
_TEMPLATE = (
    "clarify={{ framework_skill('clarify') }};"
    "verify={{ framework_skill('verify') }};"
    "coding={{ skill_active('python-coding') }};"
    "data={{ skill_active('ml-data') }};"
    "plain={{ skill_active('notes') }}"
)


def _skill(skill_id: str, package: str, **frontmatter: Any) -> Skill:
    return Skill(
        frontmatter={"id": skill_id, "name": skill_id, "description": "d", **frontmatter},
        body="b\n",
        scripts_dir=None,
        references_dir=None,
        source_package=package,
    )


def _rule(rule_id: str, text: str, **fields: Any) -> Rule:
    frontmatter = RuleFrontmatter(id=rule_id, name=rule_id, description="d", **fields)
    return Rule(frontmatter, text, text, "{{" in text, None, "<repo-local>")


_SKILLS = [
    _skill("grill-me", _FRAMEWORK, capabilities=["clarify"]),
    _skill("python-coding", "coding_agent_playbook", playbook={"files": "Any Python file"}),
    _skill("ml-data", "coding_agent_playbook", playbook={"files": "Model code"}),
    _skill("notes", "<repo-local>"),
]
_RULES = [
    _rule("page", _TEMPLATE, scope="always"),
    _rule("typing", "T\n", scope="scoped", globs=["**/*.py"], skill="python-coding"),
    _rule(
        "pandas",
        "P\n",
        scope="scoped",
        globs=["**/*.py"],
        skill="ml-data",
        applies_if={"has_framework": ["pandas"]},
    ),
]
_CONTEXT = TemplateContext(facts=cast("Facts", {}), project_name="demo", engine_version="1")


def _render(**session_args: Any) -> str:
    session = RenderSession.open(_RULES, _CONTEXT, repo_root=Path("/nowhere"), **session_args)
    return session.render_rule(_RULES[0]).body


def test_templates_see_the_framework_roles_and_the_active_skills() -> None:
    body = _render(skills=_SKILLS, framework=_FRAMEWORK)

    assert body == "clarify=grill-me;verify=;coding=True;data=False;plain=True"


def test_without_a_framework_every_role_is_empty() -> None:
    body = _render(skills=_SKILLS, framework=None)

    assert body.startswith("clarify=;verify=;")


def test_a_session_opened_without_skills_knows_none() -> None:
    assert _render() == "clarify=;verify=;coding=False;data=False;plain=False"


_RULE_TEMPLATE = (
    "page={{ rule_active('page') }};"
    "typing={{ rule_active('typing') }};"
    "pandas={{ rule_active('pandas') }};"
    "absent={{ rule_active('absent') }}"
)


def _render_rule_flags(**session_args: Any) -> str:
    page = _rule("page", _RULE_TEMPLATE, scope="always")
    rules = [page, *_RULES[1:]]
    session = RenderSession.open(rules, _CONTEXT, repo_root=Path("/nowhere"), **session_args)
    return session.render_rule(page).body


def test_rule_active_needs_the_rule_kept_and_its_skill_rendered() -> None:
    """prU D73: a ``skill -> rule`` pointer renders only when both resolve."""
    body = _render_rule_flags(skills=_SKILLS, framework=_FRAMEWORK)

    assert body == "page=True;typing=True;pandas=False;absent=False"


def test_rule_active_is_false_for_a_skill_member_when_no_skill_renders() -> None:
    assert _render_rule_flags() == "page=True;typing=False;pandas=False;absent=False"
