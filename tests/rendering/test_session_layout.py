"""Templates receive the resolved document layout as ``layout`` (D71; prU L0-23)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.config.model import Config, ProjectMeta
from coding_agent_playbook.rendering.session import RenderSession, TemplateContext

if TYPE_CHECKING:
    from coding_agent_playbook.detector.facts import Facts

_TEMPLATE = "specs={{ layout.specs }};plans={{ layout.plans }};glossary={{ layout.glossary }}"


def _render(config: Config) -> str:
    rule = Rule(
        RuleFrontmatter(id="page", name="page", description="d", scope="always"),
        _TEMPLATE,
        _TEMPLATE,
        True,
        None,
        "<repo-local>",
    )
    context = TemplateContext.for_config(config, cast("Facts", {}))
    session = RenderSession.open([rule], context, repo_root=Path("/nowhere"))
    return session.render_rule(rule).body


def test_templates_see_the_configured_layout_with_defaults_for_the_rest() -> None:
    config = Config(1, ProjectMeta("x", "python-library"), "1", layout={"specs": "specs"})

    assert _render(config) == "specs=specs;plans=docs/plans;glossary=CONTEXT.md"


def test_without_a_layout_table_templates_see_the_d60_defaults() -> None:
    config = Config(1, ProjectMeta("x", "python-library"), "1")

    assert _render(config) == "specs=docs/specs;plans=docs/plans;glossary=CONTEXT.md"


def test_a_context_built_by_hand_carries_the_defaults() -> None:
    context = TemplateContext(facts=cast("Facts", {}), project_name="demo", engine_version="1")

    assert context.as_dict()["layout"] == {
        "glossary": "CONTEXT.md",
        "context_map": "CONTEXT-MAP.md",
        "adr": "docs/adr",
        "architecture": "docs/architecture.md",
        "specs": "docs/specs",
        "plans": "docs/plans",
        "research": "docs/research",
        "agents": "docs/agents",
        "scratch": ".scratch",
    }
