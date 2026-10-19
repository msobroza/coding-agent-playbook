"""The skill writer's member references (specs/prS-skills-context.md 6.4.5, 6.8.4).

A skill with member rules is written with the composed frontmatter (the
catalog-only ``playbook:`` block stripped), the authored body plus the generated
``## References`` index, and one ``references/<rule-id>.md`` per active member,
byte-identical in every skill root. Split from ``test_skill_writer.py``, which
is already over 900 lines.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.adapters._skill_writer import (
    SKILL_FILENAME,
    SkillWriter,
    render_skill_md,
)
from coding_agent_playbook.renderer import SENTINEL
from coding_agent_playbook.skills.document import references_index
from coding_agent_playbook.types import Skill, split_frontmatter
from tests.member_skill_samples import (
    sample_member_reference,
    sample_member_skill,
    skill_tree_bytes,
)
from tests.plugins.superpowers_expectations import NATIVE_SKILL_ROOTS

if TYPE_CHECKING:
    from coding_agent_playbook.artifacts.member_reference import MemberReference

_TYPING = sample_member_reference("python-typing", name="Typing", priority=50)
_DI = sample_member_reference(
    "python-dependency-injection",
    name="Dependency injection",
    description="Pass I/O collaborators in as parameters.",
    priority=40,
    body="# Dependency injection\n\nInject collaborators.\n",
)


def _write(skill: Skill, repo: Path, root: str = ".claude/skills") -> list[Path]:
    return SkillWriter(Path(root)).write(skill, repo)


def test_write_emits_member_references_and_index(tmp_path: Path) -> None:
    skill = sample_member_skill("python-coding", _DI, _TYPING)

    written = _write(skill, tmp_path)

    skill_dir = tmp_path / ".claude" / "skills" / "python-coding"
    references = skill_dir / "references"
    assert written == [
        skill_dir / SKILL_FILENAME,
        references / "python-dependency-injection.md",
        references / "python-typing.md",
    ]
    assert (references / "python-typing.md").read_bytes() == _TYPING.text.encode("utf-8")
    assert (references / "python-dependency-injection.md").read_bytes() == _DI.text.encode()
    skill_md = (skill_dir / SKILL_FILENAME).read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(skill_md)
    assert frontmatter["description"] == (
        "Library-agnostic Python conventions. Covers Dependency injection, Typing. "
        "Use when editing Python code."
    )
    index = references_index(skill.member_references)
    assert body.endswith(f"Pick the reference the task needs.\n\n{index}")
    assert "playbook" not in frontmatter


def test_member_reference_bytes_identical_across_writer_roots(tmp_path: Path) -> None:
    skill = sample_member_skill("python-coding", _DI, _TYPING)

    for root in NATIVE_SKILL_ROOTS:
        _write(skill, tmp_path, root)

    trees = [skill_tree_bytes(tmp_path / root / "python-coding") for root in NATIVE_SKILL_ROOTS]
    assert len(trees) >= 3
    assert all(tree == trees[0] for tree in trees[1:])
    assert set(trees[0]) == {
        "SKILL.md",
        "references/python-dependency-injection.md",
        "references/python-typing.md",
    }


@pytest.mark.parametrize("members", [(_TYPING,), ()], ids=["with-members", "without-members"])
def test_render_skill_md_never_emits_the_playbook_block(
    members: tuple[MemberReference, ...],
) -> None:
    skill = sample_member_skill("python-coding", *members)

    text = render_skill_md(skill)

    frontmatter, _body = split_frontmatter(text)
    assert "playbook" not in frontmatter
    assert "use_when" not in text
    assert list(frontmatter) == ["name", "id", "description"]


def test_render_skill_md_of_a_plain_skill_is_unchanged() -> None:
    """Regression (plugin skills byte-identical): no members, no ``playbook`` block."""
    plain = Skill(
        {"id": "brainstorming", "name": "Brainstorming", "description": "Use when ideating."},
        "# Brainstorming\n\nAsk one question at a time.\n",
        None,
        None,
        "superpowers",
    )

    assert render_skill_md(plain) == (
        "---\n"
        "name: brainstorming\n"
        "id: brainstorming\n"
        "description: Use when ideating.\n"
        "---\n"
        f"<!-- {SENTINEL} -->\n"
        "\n"
        "# Brainstorming\n\nAsk one question at a time.\n"
    )


def test_hand_written_references_are_copied_next_to_member_references(tmp_path: Path) -> None:
    handwritten = tmp_path / "src-refs"
    handwritten.mkdir()
    (handwritten / "guide.md").write_bytes(b"# Guide\n")
    skill = sample_member_skill("python-coding", _TYPING, references_dir=handwritten)

    written = _write(skill, tmp_path / "repo")

    references = tmp_path / "repo" / ".claude" / "skills" / "python-coding" / "references"
    assert written[1:] == [references / "guide.md", references / "python-typing.md"]
    assert (references / "guide.md").read_bytes() == b"# Guide\n"


def test_rewrite_replaces_the_member_reference_an_earlier_write_left(tmp_path: Path) -> None:
    _write(sample_member_skill("python-coding", _TYPING), tmp_path)
    edited = dataclasses.replace(_TYPING, text="*Rule `python-typing`.*\n\nNew text.\n")

    _write(sample_member_skill("python-coding", edited), tmp_path)

    reference = tmp_path / ".claude/skills/python-coding/references/python-typing.md"
    assert reference.read_text(encoding="utf-8") == edited.text


def test_member_reference_blocked_by_user_directory_is_skipped_with_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skill = sample_member_skill("python-coding", _DI, _TYPING)
    _write(skill, tmp_path)
    blocked = tmp_path / ".claude/skills/python-coding/references/python-typing.md"
    blocked.unlink()
    blocked.mkdir()
    (blocked / "notes.md").write_bytes(b"my notes\n")  # no lockfile lists it

    written = _write(skill, tmp_path)

    assert blocked not in written
    assert (blocked / "notes.md").read_bytes() == b"my notes\n"
    assert blocked.parent / "python-dependency-injection.md" in written
    err = capsys.readouterr().err
    assert f"not writing {blocked}" in err
    assert "is in the way" in err


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
def test_member_reference_behind_a_link_leaving_the_skill_dir_is_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression (PR #38 guard): a member reference is never written through such a link."""
    skill = sample_member_skill("python-coding", _TYPING)
    _write(skill, tmp_path / "repo")  # the engine owns the skill dir from here
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    skill_dir = tmp_path / "repo" / ".claude" / "skills" / "python-coding"
    shutil.rmtree(skill_dir / "references")
    (skill_dir / "references").symlink_to(outside, target_is_directory=True)

    written = _write(skill, tmp_path / "repo")

    assert written == [skill_dir / SKILL_FILENAME]
    assert list(outside.iterdir()) == []
    assert (skill_dir / "references").is_symlink()
    assert "leading outside the skill directory" in capsys.readouterr().err
