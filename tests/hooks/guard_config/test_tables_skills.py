"""skill-nudge's per-skill glob table, derived at sync (specs/prS-skills-context.md 8.5.2).

``compile_guard_config`` groups the globs of the member rules this sync renders by
the skill that owns them (ADR 0001), so the runtime can name the skill that covers
an edited file without importing the catalog; ``test_compile`` pins the grouping
(``test_compile_derives_skill_globs_from_rendered_member_rules``).

Spec 8.8 puts ``test_skill_nudge_config_is_derived_and_replaces_a_layer_value``
in the guard_config writer's main test file; it lives here, next to the table it
renders, to keep that file within the size cap.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.hooks.guard_config._tables_skills import SKILL_NUDGE_HOOK_ID
from tests.hook_samples import resolved_hook
from tests.hooks.guard_config.compile_kit import compiled_document, request_for

if TYPE_CHECKING:
    from pathlib import Path


def test_skill_nudge_config_is_derived_and_replaces_a_layer_value(repo: Path) -> None:
    """A layer's ``skills`` (no schema declares it) never survives: sync's table wins."""
    layered = {"skills": [{"id": "rogue", "globs": ["**"]}], "keep": True}
    nudge = resolved_hook(SKILL_NUDGE_HOOK_ID, events=("post_tool_use",), config=layered)
    fm = RuleFrontmatter(
        id="pytest",
        name="pytest",
        description="d",
        scope="scoped",
        globs=["tests/**/*.py"],
        skill="python-testing",
    )
    rule = Rule(fm, "Body.\n", "Body.\n", False, None, "coding_agent_playbook")
    request = dataclasses.replace(
        request_for(repo, [nudge, resolved_hook("guard-x")]), rules=[rule]
    )

    hooks = compiled_document(request)["hooks"]

    assert hooks[SKILL_NUDGE_HOOK_ID]["handlers"]["post_tool_use"]["config"] == {
        "keep": True,
        "skills": [{"id": "python-testing", "globs": ["tests/**/*.py"]}],
    }
    assert "skills" not in hooks["guard-x"]["handlers"]["pre_tool_use"]["config"]
