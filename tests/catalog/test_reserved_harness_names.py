"""No shipped prompt slash or skill id takes a name a target harness reserves (ADR 0009, #272).

A core prompt's slash, or a skill id of core or of a bundled plugin, that equals a
harness command, a command alias or a skill a harness ships shadows the harness's
own in a synced repo: on OpenCode the project command replaces the built-in, and
on Claude Code a project skill replaces a bundled one. The reserved names are
test data, one set per harness, in ``tests/_reserved_harness_names.py``; the
repo-local authors' copy is the prompt-frontmatter rule of playbook-creator.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.artifacts.rule import Rule
from coding_agent_playbook.catalog.prompt_sets import PROMPT_SETS
from coding_agent_playbook.catalog.roots import ENGINE_PACKAGE
from coding_agent_playbook.catalog.source import _iter_skills, layer_prompts
from coding_agent_playbook.skills.naming import skill_id_of
from tests._catalog import CATALOG_ROOT, CORE_ROOT, CORE_SKILLS_ROOT, bundled_plugin_dirs
from tests._reserved_harness_names import RESERVED_HARNESS_NAMES

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

pytestmark = pytest.mark.catalog

_PROMPT_FRONTMATTER_RULE: Final = (
    CORE_SKILLS_ROOT / "playbook-creator" / "rules" / "playbook-prompt-frontmatter.md"
)

#: The harness commands the prompt-frontmatter rule must name for repo-local authors:
#: the ones spec #270 and ADR 0009 call out, and the commands all three harnesses share.
_RULE_NAMED_COMMANDS: Final = (
    "review",
    "code-review",
    "security-review",
    "init",
    "simplify",
    "run",
    "verify",
    "debug",
    "doctor",
    "loop",
    "batch",
    "diff",
    "plan",
    "agents",
    "skills",
    "compact",
    "undo",
)


@dataclass(frozen=True)
class ShippedName:
    """One name the catalog ships that a harness user can type: a prompt slash or a skill id.

    Example: ``ShippedName("prompt slash", "review-core", "core/prompts/review.md.j2")``.
    """

    kind: str
    name: str
    where: str


def _relative(path: Path | None) -> str:
    """``path`` relative to the catalog root, for a readable failure; ``"?"`` when unknown."""
    if path is None:
        return "?"
    return path.resolve().relative_to(CATALOG_ROOT.resolve()).as_posix()


def _prompt_slashes(prompts_root: Path) -> list[ShippedName]:
    """The slash of every prompt under ``prompts_root``, in every prompt set (v1 and its twins)."""
    found: dict[tuple[str, str], ShippedName] = {}
    for prompt_set in PROMPT_SETS:
        for prompt in layer_prompts(prompts_root, ENGINE_PACKAGE, prompt_set):
            where = _relative(prompt.source_path)
            found[(prompt.frontmatter.slash, where)] = ShippedName(
                "prompt slash", prompt.frontmatter.slash, where
            )
    return list(found.values())


def _skill_ids(skills_root: Path) -> list[ShippedName]:
    """The id of every skill under ``skills_root``, loaded by the engine's own skill walker."""
    return [
        ShippedName("skill id", skill_id_of(skill), _relative(skill.source_dir))
        for skill in _iter_skills(skills_root, ENGINE_PACKAGE)
    ]


def shipped_names() -> list[ShippedName]:
    """Core's prompt slashes and the skill ids of core and every bundled plugin.

    Example: ``"review-core" in {n.name for n in shipped_names()}`` -> ``True``.
    """
    names = _prompt_slashes(CORE_ROOT / "prompts") + _skill_ids(CORE_SKILLS_ROOT)
    for plugin_dir in bundled_plugin_dirs():
        names += _skill_ids(plugin_dir / "skills")
    return names


def reserved_collisions(
    shipped: Iterable[ShippedName], reserved: Mapping[str, frozenset[str]]
) -> list[str]:
    """One message per shipped name a harness reserves, naming the item, its file and the harness.

    Example::

        reserved_collisions([ShippedName("skill id", "pr", "plugins/x/skills/pr")],
                            {"Claude Code": frozenset({"pr"})})
        # ["skill id 'pr' (plugins/x/skills/pr) is reserved by Claude Code"]
    """
    return [
        f"{item.kind} {item.name!r} ({item.where}) is reserved by {harness}"
        for item in shipped
        for harness, names in reserved.items()
        if item.name in names
    ]


def test_reserved_collisions_names_the_item_and_every_harness_reserving_it() -> None:
    shipped = [
        ShippedName("prompt slash", "review", "core/prompts/review.md.j2"),
        ShippedName("skill id", "tdd", "plugins/demo/skills/tdd"),
    ]
    reserved = {"Claude Code": frozenset({"review"}), "Codex": frozenset({"review", "plan"})}

    assert reserved_collisions(shipped, reserved) == [
        "prompt slash 'review' (core/prompts/review.md.j2) is reserved by Claude Code",
        "prompt slash 'review' (core/prompts/review.md.j2) is reserved by Codex",
    ]


def test_shipped_names_cover_every_prompt_set_and_every_bundled_layer() -> None:
    # Guards the gate against passing on an empty walk: each source it reads shows up.
    by_name = {(item.kind, item.name) for item in shipped_names()}
    wheres = {item.where for item in shipped_names()}

    assert ("prompt slash", "review-core") in by_name
    assert ("prompt slash", "security-review-core") in by_name
    assert any(where.startswith("core/prompts/v2/") for where in wheres)
    assert ("skill id", "playbook-creator") in by_name
    for plugin_dir in bundled_plugin_dirs():
        assert any(where.startswith(f"plugins/{plugin_dir.name}/skills/") for where in wheres), (
            plugin_dir.name
        )


def test_reserved_names_are_kept_per_harness() -> None:
    assert set(RESERVED_HARNESS_NAMES) == {"Claude Code", "OpenCode", "Codex"}
    for harness, names in RESERVED_HARNESS_NAMES.items():
        assert {"review", "init"} <= names, harness
    assert {"code-review", "security-review", "simplify", "pr", "prototype"} <= (
        RESERVED_HARNESS_NAMES["Claude Code"]
    )
    assert "customize-opencode" in RESERVED_HARNESS_NAMES["OpenCode"]
    assert {"skill-creator", "skill-installer", "imagegen"} <= RESERVED_HARNESS_NAMES["Codex"]


def test_no_shipped_prompt_slash_or_skill_id_is_a_reserved_harness_name() -> None:
    collisions = reserved_collisions(shipped_names(), RESERVED_HARNESS_NAMES)

    assert collisions == [], "\n".join(collisions)


def test_prompt_frontmatter_rule_names_the_harness_commands_to_avoid() -> None:
    body = Rule.from_markdown(_PROMPT_FRONTMATTER_RULE, ENGINE_PACKAGE).body
    named = set(re.findall(r"`/?([a-z][a-z0-9-]*)`", body))

    missing = [name for name in _RULE_NAMED_COMMANDS if name not in named]

    assert missing == [], f"the prompt-frontmatter rule does not name {missing}"
