"""Catalog gates on how shipped prompts declare their rules (specs/prS-skills-context.md §7.7).

``includes_rules`` is the only declaration (D15): no shipped prompt body calls
the removed ``{{ rule() }}`` helper, every listed id names a core rule, and each
listed scoped rule names the skill whose reference a command points at.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.artifacts.prompt import Prompt
from coding_agent_playbook.catalog.roots import ENGINE_PACKAGE
from coding_agent_playbook.renderer import RULE_CALL_RE
from tests._catalog import CORE_ROOT, bundled_plugin_dirs, core_rules

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog


def _shipped_prompt_files() -> list[Path]:
    """Every prompt source of a bundled layer (core, then each plugin), sorted.

    A layer's ``prompts/`` only: a skill's own ``prompts/`` folder (a vendored
    skill ships one) holds skill files, not slash-command prompts.
    """
    layers = [CORE_ROOT, *bundled_plugin_dirs()]
    return sorted(
        path
        for layer in layers
        if (layer / "prompts").is_dir()
        for path in (layer / "prompts").iterdir()
        if path.name.endswith((".md", ".md.j2"))
    )


def _shipped_prompts() -> list[Prompt]:
    return [Prompt.from_markdown(path, ENGINE_PACKAGE) for path in _shipped_prompt_files()]


def test_the_catalog_ships_prompts_with_includes_rules() -> None:
    """Guards the gates below against an empty listing (a moved prompts directory)."""
    assert any(prompt.frontmatter.includes_rules for prompt in _shipped_prompts())


@pytest.mark.parametrize("path", _shipped_prompt_files(), ids=lambda p: p.name)
def test_no_shipped_prompt_calls_rule(path: Path) -> None:
    body = Prompt.from_markdown(path, ENGINE_PACKAGE).template_body

    assert RULE_CALL_RE.search(body) is None


def test_every_shipped_includes_rules_id_names_a_core_rule() -> None:
    known = core_rules()
    unknown = {
        (prompt.frontmatter.id, rule_id)
        for prompt in _shipped_prompts()
        for rule_id in prompt.frontmatter.includes_rules
        if rule_id not in known
    }

    assert unknown == set()


def test_every_shipped_included_scoped_rule_names_a_skill() -> None:
    """A scoped rule without ``skill:`` would get no pointer line in any command."""
    rules = core_rules()
    included = {rule_id for p in _shipped_prompts() for rule_id in p.frontmatter.includes_rules}
    ownerless = {
        rule_id
        for rule_id in included
        if rules[rule_id].frontmatter.scope == "scoped" and rules[rule_id].frontmatter.skill is None
    }

    assert ownerless == set()
