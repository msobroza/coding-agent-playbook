"""The ``playbook-creator`` core skill follows the playbook-layer gate (prU D70, D75, D78(18)).

Every member gates on ``playbook_layer``, so sync writes the skill only in a repo
with a layer of its own: the authoring probe (the reference probe plus an empty
``playbook/``) gets it, the standard reference probe does not. The engine-only
rule also needs ``catalog/core``, so it renders in the engine checkout and not
in a consumer repo. The opening rule asks for missing inputs through the enabled
framework's clarify skill, or directly without one (D74, D75).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

import pytest

import coding_agent_playbook
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.detector.facts import detect
from coding_agent_playbook.detector.predicate import evaluate_predicate
from coding_agent_playbook.rendering.session import RenderSession, TemplateContext
from tests._catalog import REPO_ROOT, core_rules
from tests.plugins.superpowers_expectations import NATIVE_SKILL_ROOTS

if TYPE_CHECKING:
    from coding_agent_playbook.detector.facts import Facts

pytestmark = pytest.mark.catalog

_SKILL: Final = "playbook-creator"
_WHERE_LINE: Final = "skill `playbook-creator`"
_ENGINE_ONLY: Final = "playbook-engine-catalog-gate"
_ASK: Final = "playbook-ask-for-missing-inputs"
_FRAMEWORK: Final = "acme.framework"


def _emitted_roots(repo: Path) -> list[str]:
    """The native skill roots of ``repo`` that hold ``playbook-creator/SKILL.md``."""
    return [root for root in NATIVE_SKILL_ROOTS if (repo / root / _SKILL / "SKILL.md").is_file()]


def _agents_md(repo: Path) -> str:
    return (repo / "AGENTS.md").read_text(encoding="utf-8")


def test_authoring_probe_emits_playbook_creator(authoring_probe_repo: Path) -> None:
    assert _emitted_roots(authoring_probe_repo) == list(NATIVE_SKILL_ROOTS)
    assert _WHERE_LINE in _agents_md(authoring_probe_repo)


def test_standard_probe_does_not_emit_playbook_creator(reference_probe_repo: Path) -> None:
    assert _emitted_roots(reference_probe_repo) == []
    assert _WHERE_LINE not in _agents_md(reference_probe_repo)


def test_engine_only_rule_stays_out_of_a_consumer_layer(authoring_probe_repo: Path) -> None:
    """D78(18): a consumer repo's ``playbook/`` gets every member but the engine gate."""
    rules_dir = authoring_probe_repo / ".claude" / "skills" / _SKILL / "rules"
    written = sorted(path.name for path in rules_dir.iterdir())
    assert f"{_ASK}.md" in written
    assert f"{_ENGINE_ONLY}.md" not in written


def test_engine_only_rule_applies_in_the_engine_checkout() -> None:
    gate = core_rules()[_ENGINE_ONLY].frontmatter.applies_if
    assert evaluate_predicate(gate, detect(REPO_ROOT), repo_root=REPO_ROOT)


def _clarify_skill(skill_id: str) -> Skill:
    return Skill(
        frontmatter={
            "id": skill_id,
            "name": skill_id,
            "description": "fake clarify skill",
            "capabilities": ["clarify"],
        },
        body="fake body\n",
        scripts_dir=None,
        references_dir=None,
        source_package=_FRAMEWORK,
    )


def _render_ask(clarify: str | None) -> str:
    """The opening rule as sync renders it with a framework whose clarify skill is ``clarify``."""
    skills = [] if clarify is None else [_clarify_skill(clarify)]
    context = TemplateContext(
        facts=cast("Facts", {"playbook_layer": True}),
        project_name="demo",
        engine_version=coding_agent_playbook.__version__,
    )
    framework = None if clarify is None else _FRAMEWORK
    session = RenderSession.open((), context, repo_root=Path(), skills=skills, framework=framework)
    return session.render_rule(core_rules()[_ASK]).body


@pytest.mark.parametrize("clarify", ["grill-me", "brainstorming"])
def test_ask_rule_names_the_framework_clarify_skill(clarify: str) -> None:
    body = _render_ask(clarify)

    assert f"the {clarify} skill" in body, body
    assert "ask the user directly" not in body, body


def test_ask_rule_asks_directly_without_a_framework() -> None:
    body = _render_ask(None)

    assert "ask the user directly" in body, body
    assert "grill-me" not in body and "brainstorming" not in body, body
