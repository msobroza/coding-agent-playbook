"""The catalog snapshot read from the real catalog: every artifact reaches a page.

Counts come from the engine's own readers, so a new skill, rule, prompt or hook
the snapshot drops fails here rather than vanishing from the site.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from catalog_pages import HOOK_FAMILY_TITLES, render_pages
from catalog_snapshot import CatalogSnapshot, load_snapshot
from coding_agent_playbook.catalog.roots import bundled_plugins
from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from tests._catalog import REPO_ROOT

if TYPE_CHECKING:
    from coding_agent_playbook.artifacts.rule import Rule


@pytest.fixture(scope="module")
def snapshot() -> CatalogSnapshot:
    return load_snapshot(REPO_ROOT)


@pytest.fixture(scope="module")
def rules() -> list[Rule]:
    source = FileSystemArtifactSource(repo_root=REPO_ROOT, overlay_packages=bundled_plugins())
    return source.list_rules()


def test_every_member_rule_is_listed_once_on_its_skill_page(
    snapshot: CatalogSnapshot, rules: list[Rule]
) -> None:
    listed = [
        rule.id
        for skill in (*snapshot.core_skills, *(s for p in snapshot.plugins for s in p.skills))
        for section in skill.sections
        for rule in section.rules
    ]

    members = sorted(r.frontmatter.id for r in rules if r.frontmatter.skill is not None)
    assert sorted(listed) == members


def test_every_always_rule_is_listed_on_core_or_its_plugin(
    snapshot: CatalogSnapshot, rules: list[Rule]
) -> None:
    listed = [r.id for r in snapshot.always_rules]
    listed += [r.id for plugin in snapshot.plugins for r in plugin.always_rules]

    always = sorted(r.frontmatter.id for r in rules if r.frontmatter.scope == "always")
    assert sorted(listed) == always


def test_every_skill_of_core_and_the_bundled_plugins_gets_listed(
    snapshot: CatalogSnapshot,
) -> None:
    source = FileSystemArtifactSource(repo_root=REPO_ROOT, overlay_packages=bundled_plugins())
    listed = [s.id for s in snapshot.core_skills]
    listed += [s.id for plugin in snapshot.plugins for s in plugin.skills]

    assert sorted(listed) == sorted(str(s.frontmatter["id"]) for s in source.list_skills())


def test_every_hook_family_has_a_title(snapshot: CatalogSnapshot) -> None:
    # A new family directory renders under a title made from its name; give it a
    # real one in HOOK_FAMILY_TITLES (and in docs/hooks.md) instead.
    assert {hook.family for hook in snapshot.hooks} == set(HOOK_FAMILY_TITLES)


def test_each_bundled_plugin_carries_its_credit_and_framework_name(
    snapshot: CatalogSnapshot,
) -> None:
    assert [p.layer for p in snapshot.plugins] == bundled_plugins()
    for plugin in snapshot.plugins:
        assert "MIT" in plugin.credit, plugin.layer
        assert plugin.name, plugin.layer


def test_prompts_list_both_prompt_sets(snapshot: CatalogSnapshot) -> None:
    assert snapshot.prompts
    assert all(prompt.prompt_sets == ("v1", "v2") for prompt in snapshot.prompts)


def test_source_paths_are_repo_relative(snapshot: CatalogSnapshot) -> None:
    paths = [s.source_path for s in snapshot.core_skills] + [
        p.source_path for p in snapshot.plugins
    ]

    assert all(path.startswith("catalog/") for path in paths), paths


def test_the_real_catalog_renders(snapshot: CatalogSnapshot) -> None:
    pages = render_pages(snapshot, source_tree_url="https://example.test/tree/main/")

    assert len(pages) == len(snapshot.core_skills) + len(snapshot.plugins) + 3
