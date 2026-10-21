"""Framework capability tags on skills (D74, D77; prU L0-19)."""

from __future__ import annotations

from typing import Any

import pytest

from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.skills.capabilities import (
    CAPABILITY_ROLES,
    capability_problems,
    format_role_map,
    framework_role_map,
)
from coding_agent_playbook.skills.document import emitted_frontmatter

_PKG = "acme.framework"


def _skill(skill_id: str, package: str = _PKG, **frontmatter: Any) -> Skill:
    return Skill(
        frontmatter={"id": skill_id, "name": skill_id, "description": "d", **frontmatter},
        body="b\n",
        scripts_dir=None,
        references_dir=None,
        source_package=package,
    )


def test_roles_are_the_d74_roles_in_order() -> None:
    assert CAPABILITY_ROLES == (
        "clarify",
        "clarify_with_docs",
        "spec",
        "plan",
        "tdd",
        "debug",
        "review",
        "verify",
    )


def test_framework_role_map_reads_only_the_framework_package_tags() -> None:
    skills = [
        _skill("diagnose", capabilities=["debug"]),
        _skill("grill", capabilities=["clarify"]),
        _skill("core-skill", package="coding_agent_playbook", capabilities=["tdd"]),
        _skill("plain"),
    ]

    assert framework_role_map(skills, _PKG) == {"clarify": "grill", "debug": "diagnose"}
    assert framework_role_map(skills, None) == {}


def test_capability_problems_reject_unknown_roles_shapes_and_duplicates() -> None:
    skills = [
        _skill("a", capabilities=["tdd", "deploy"]),
        _skill("b", capabilities=["tdd"]),
        _skill("c", capabilities="debug"),
        _skill("other", package="elsewhere", capabilities=["nonsense"]),
    ]

    assert capability_problems(skills, _PKG) == [
        (
            "a",
            "capabilities has unknown role 'deploy'; known roles: " + ", ".join(CAPABILITY_ROLES),
        ),
        ("b", "capabilities role 'tdd' is already declared by skill 'a'; one skill per role"),
        ("c", "capabilities must be a list of role names, got 'debug'"),
    ]


def test_format_role_map() -> None:
    line = format_role_map("mattpocock", {"clarify": "grill-me", "debug": "diagnosing-bugs"})

    assert line == "framework mattpocock: clarify -> grill-me, debug -> diagnosing-bugs"
    assert format_role_map("bare", {}) == "framework bare: (no capabilities declared)"


def test_the_capabilities_key_is_never_written_out() -> None:
    skill = _skill("grill", capabilities=["clarify"])

    assert "capabilities" not in emitted_frontmatter(skill)


_EXPECTED_ROLE_MAPS = {
    "coding_agent_playbook.plugins.mattpocock_skills": {
        "clarify": "grill-me",
        "clarify_with_docs": "grill-with-docs",
        "spec": "to-spec",
        "plan": "to-tickets",
        "tdd": "tdd",
        "debug": "diagnosing-bugs",
        "review": "two-axis-review",
    },
    "coding_agent_playbook.plugins.superpowers": {
        "clarify": "brainstorming",
        "plan": "writing-plans",
        "tdd": "test-driven-development",
        "debug": "systematic-debugging",
        "review": "requesting-code-review",
        "verify": "verification-before-completion",
    },
}


@pytest.mark.catalog
@pytest.mark.parametrize("package", sorted(_EXPECTED_ROLE_MAPS))
def test_bundled_frameworks_tag_the_d74_skills(tmp_path: Any, package: str) -> None:
    skills = FileSystemArtifactSource(repo_root=tmp_path, overlay_packages=[package]).list_skills()

    assert capability_problems(skills, package) == []
    assert framework_role_map(skills, package) == _EXPECTED_ROLE_MAPS[package]
