"""Skill-listing budget: core plus EACH bundled plugin within the listing cap (prU D18, D54, D59).

specs/prT-mattpocock-skills.md section 7.5: prS D5 as amended by D31. The test
measures what the engine itself would list, per layer, with the engine's own
functions (E13): core's rule skills (shipped by ticket 10, #72) are counted at the
longest description sync composes for them, every plugin skill at its authored one.
With every member active the Domino skills are counted too, so the cap is D59's
Domino one (7,500); without them it is D54's 7,000.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.catalog.layers import ENGINE_PACKAGE
from coding_agent_playbook.catalog.resolve import OverlayResolver
from coding_agent_playbook.catalog.roots import bundled_plugins
from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.skills.document import emitted_frontmatter
from coding_agent_playbook.skills.membership import compose_skills
from coding_agent_playbook.skills.naming import skill_id_of
from tests._budget_probe import DOMINO_LISTING_MAX_CHARS, LISTING_MAX_CHARS
from tests.plugins.mattpocock_skills._expectations import PLUGIN_NAME, present_skill_ids

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill

pytestmark = pytest.mark.catalog


def _of_layer[Artifact: (Rule, Skill)](items: list[Artifact], label: str) -> list[Artifact]:
    """The artifacts whose ``source_package`` is ``label``."""
    return [item for item in items if item.source_package == label]


def listing_chars(plugin: str, repo_root: Path) -> dict[str, int]:
    """Emitted description length per skill id for core plus ``plugin``, every member rule active.

    Example: ``sum(listing_chars(PLUGIN_NAME, tmp_path).values())`` -> 4,542 at T10b (core 762, plugin 3,780).
    """
    source = FileSystemArtifactSource(repo_root=repo_root, overlay_packages=[plugin])
    resolver = OverlayResolver()
    skills = resolver.resolve_skills(
        _of_layer(source.list_skills(), ENGINE_PACKAGE),
        [_of_layer(source.list_skills(), plugin)],
        [],
    )
    rules = resolver.resolve_rules(
        _of_layer(source.list_rules(), ENGINE_PACKAGE), [_of_layer(source.list_rules(), plugin)], []
    )
    composed = compose_skills(skills, rules, rules)  # all members active: the longest descriptions
    return {skill_id_of(s): len(str(emitted_frontmatter(s)["description"])) for s in composed}


def listing_cap(skill_ids: Iterable[str]) -> int:
    """D59's Domino cap once a Domino skill is listed, else D54's: ``listing_cap(["forge"])`` -> 7000."""
    domino = any(skill_id.startswith("domino-") for skill_id in skill_ids)
    return DOMINO_LISTING_MAX_CHARS if domino else LISTING_MAX_CHARS


@pytest.mark.parametrize("plugin", bundled_plugins())
def test_core_plus_each_bundled_plugin_listing_within_the_listing_cap_d18(
    plugin: str, tmp_path: Path
) -> None:
    chars = listing_chars(plugin, tmp_path)
    assert sum(chars.values()) <= listing_cap(chars), sorted(chars.items(), key=lambda kv: -kv[1])


def test_listing_cap_is_the_domino_one_only_with_a_domino_skill() -> None:
    assert listing_cap(["forge", "python-coding"]) == LISTING_MAX_CHARS
    assert listing_cap(["forge", "domino-jobs"]) == DOMINO_LISTING_MAX_CHARS


def test_budget_counts_every_present_plugin_skill(tmp_path: Path) -> None:
    source = FileSystemArtifactSource(repo_root=tmp_path, overlay_packages=[PLUGIN_NAME])
    plugin_ids = {skill_id_of(s) for s in _of_layer(source.list_skills(), PLUGIN_NAME)}
    measured = set(listing_chars(PLUGIN_NAME, tmp_path))
    assert plugin_ids == set(present_skill_ids())
    assert plugin_ids <= measured, f"not measured: {sorted(plugin_ids - measured)}"


def test_budget_counts_every_core_skill(tmp_path: Path) -> None:
    """Core's skills are in the sum, so the budget is core plus the plugin, never the plugin alone."""
    source = FileSystemArtifactSource(repo_root=tmp_path, overlay_packages=[])
    core_ids = {skill_id_of(s) for s in _of_layer(source.list_skills(), ENGINE_PACKAGE)}
    measured = set(listing_chars(PLUGIN_NAME, tmp_path))
    assert core_ids, "no core skill found under the engine layer"
    assert core_ids <= measured, f"core skills not measured: {sorted(core_ids - measured)}"
