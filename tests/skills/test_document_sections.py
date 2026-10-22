"""The emitted skill sections (specs/prS-skills-context.md 6.4.4, 6.8.3).

The frontmatter and body a skill with member rules is written with, its
``## Rules`` index, the member rule files and the ``## Where guidance
lives`` section. Expected texts are the spec's worked examples, copied
verbatim. Split from ``test_document.py`` (the descriptions) to keep each
test module under 300 lines.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.artifacts.member_reference import MemberReference
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.skills.document import (
    WhereEntry,
    emitted_body,
    emitted_frontmatter,
    render_member_reference,
    rules_index,
    skill_catalog_block,
    where_entry,
    where_guidance_section,
)
from coding_agent_playbook.skills.playbook_block import playbook_block

TYPING_DESCRIPTION = (
    "Prefer a concrete type or a Protocol to Any, write X | None, and take abstract "
    "read-only types as inputs."
)
DI_DESCRIPTION = (
    "Pass I/O collaborators in as parameters; pick concrete implementations in one "
    "composition root per entry point."
)
TOOLING_FILES = "Tool configuration and framework wiring"


def _member(rule_id: str, name: str, description: str) -> MemberReference:
    return MemberReference(rule_id, name, description, 50, ("**/*.py",), "text\n", "pkg")


MEMBERS = (
    _member("python-dependency-injection", "Dependency injection", DI_DESCRIPTION),
    _member("python-typing", "Typing", TYPING_DESCRIPTION),
)


def _python_coding(*members: MemberReference, **playbook: str) -> Skill:
    """python-coding with ``members``; ``playbook`` replaces the default block."""
    frontmatter = {
        "id": "python-coding",
        "name": "python-coding",
        "description": "Library-agnostic Python conventions.",
        "playbook": playbook or {"use_when": "editing Python code", "files": "Any Python file"},
    }
    return Skill(frontmatter, "\n# Python coding\n\nIntro.\n", None, None, "pkg", members)


def test_emitted_frontmatter_strips_playbook_and_composes_description() -> None:
    emitted = emitted_frontmatter(_python_coding(*MEMBERS))
    assert emitted == {
        "id": "python-coding",
        "name": "python-coding",
        "description": (
            "Library-agnostic Python conventions. Covers Dependency injection, Typing. "
            "Use when editing Python code."
        ),
    }
    assert list(emitted) == ["id", "name", "description"]


def test_emitted_frontmatter_of_a_plain_skill_is_the_authored_mapping() -> None:
    authored = {"id": "brainstorming", "description": "You MUST use this.", "license": "MIT"}
    plugin = Skill(dict(authored), "body\n", None, None, "superpowers")
    emitted = emitted_frontmatter(plugin)
    assert emitted == authored
    assert emitted is not plugin.frontmatter
    assert emitted_body(plugin) == "body\n"


def test_emitted_body_appends_rules_index_after_authored_body() -> None:
    assert emitted_body(_python_coding(*MEMBERS)) == (
        "\n# Python coding\n\nIntro.\n\n"
        "## Rules\n\n"
        "Each file under rules/ is one rule. Open only the ones the current task needs.\n\n"
        "- [python-dependency-injection](rules/python-dependency-injection.md) — "
        f"Dependency injection: {DI_DESCRIPTION}\n"
        f"- [python-typing](rules/python-typing.md) — Typing: {TYPING_DESCRIPTION}\n"
    )


def test_rules_index_line_links_rule_id_with_name_and_description() -> None:
    index = rules_index(MEMBERS[1:])
    assert index.splitlines()[-1] == (
        "- [python-typing](rules/python-typing.md) — Typing: Prefer a concrete type or a "
        "Protocol to Any, write X | None, and take abstract read-only types as inputs."
    )
    assert rules_index(()) == ""


def test_render_member_reference_with_and_without_globs() -> None:
    body = "\n# Python typing conventions\n\nType hints.\n"
    assert render_member_reference("python-typing", ["**/*.py"], body) == (
        "*Rule `python-typing`; applies to `**/*.py`.*\n\n"
        "# Python typing conventions\n\nType hints.\n"
    )
    assert render_member_reference("pytest", ["tests/**", "**/conftest.py"], "# T\n") == (
        "*Rule `pytest`; applies to `tests/**`, `**/conftest.py`.*\n\n# T\n"
    )
    assert render_member_reference("python-idioms", [], "# Idioms") == (
        "*Rule `python-idioms`.*\n\n# Idioms\n"
    )


def test_where_guidance_section_sorted_by_skill_id_with_lint_line() -> None:
    entries = [
        WhereEntry("python-tooling", TOOLING_FILES),
        WhereEntry("python-coding", "Any Python file"),
        WhereEntry("ml-data", "Code that loads or saves models, checkpoints or caches"),
        WhereEntry("python-testing", "Test files and conftest.py"),
    ]
    assert where_guidance_section(entries) == (
        "## Where guidance lives\n\n"
        "Detailed conventions live in skills. Before you edit one of these files, load its "
        "skill and open the rules its index lists.\n\n"
        "- Code that loads or saves models, checkpoints or caches: skill `ml-data`\n"
        "- Any Python file: skill `python-coding`\n"
        "- Test files and conftest.py: skill `python-testing`\n"
        f"- {TOOLING_FILES}: skill `python-tooling`\n\n"
        "Lint feedback names a rule id; that rule's file in the skill's rules/ has the fix.\n\n"
        "---\n"
    )


def test_where_guidance_section_is_empty_without_entries() -> None:
    assert where_guidance_section([]) == ""


def test_where_entry_is_none_without_members_or_files() -> None:
    assert where_entry(_python_coding(*MEMBERS)) == WhereEntry("python-coding", "Any Python file")
    assert where_entry(_python_coding()) is None
    assert where_entry(_python_coding(*MEMBERS, use_when="editing Python code")) is None


@pytest.mark.parametrize(
    ("playbook", "expected"),
    [
        ({"use_when": " editing code ", "files": "Any file"}, ("editing code", "Any file")),
        ({"use_when": 42, "files": "   "}, (None, None)),
        ("yes", (None, None)),
        (None, (None, None)),
    ],
)
def test_skill_catalog_block_reads_absent_or_malformed_keys_as_none(
    playbook: object, expected: tuple[str | None, str | None]
) -> None:
    frontmatter = {"id": "x"} if playbook is None else {"id": "x", "playbook": playbook}
    block = skill_catalog_block(Skill(frontmatter, "", None, None, "pkg"))
    assert (block.use_when, block.files) == expected


@pytest.mark.parametrize(
    ("playbook", "expected"),
    [
        ({"use_when": "x", "sections": []}, {"use_when": "x", "sections": []}),
        ("yes", {}),
        (None, {}),
    ],
)
def test_playbook_block_reads_an_absent_or_non_mapping_block_as_empty(
    playbook: object, expected: dict[str, object]
) -> None:
    frontmatter = {"id": "x"} if playbook is None else {"id": "x", "playbook": playbook}

    assert playbook_block(Skill(frontmatter, "", None, None, "pkg")) == expected
