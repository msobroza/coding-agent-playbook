"""``render_artifacts`` composes skills from member rules (specs/prS-skills-context.md 6.4.3).

The sync's render step hands the adapters composed skills: a skill with a
``playbook:`` block carries its active member rules, rendered, and is dropped
when none is active. When member rules are active but no enabled adapter
delivers them, it prints one ``warning:`` line on stderr. A composed
description that cannot fit 300 characters raises before any adapter runs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.skills.document import DescriptionOverflowError
from coding_agent_playbook.sync.render import (
    SkillDescriptionOverflowError,
    render_artifacts,
    report_description_overflow,
)
from coding_agent_playbook.validation.context import SyncContext
from tests.member_skill_samples import write_repo_member_rule, write_repo_member_skill

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_CONFIG = """\
schema_version = 1
adapters_enabled = {adapters}
overlays_enabled = []

[project]
name = "synthetic"
kind = "python-library"

[engine]
version = "0.1.0a0"

[storage]
artifact_source = "filesystem"
state_source = "filesystem"
"""


def _repo(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], adapters: str = '["claude_code"]'
) -> Path:
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG.format(adapters=adapters))
    write_repo_member_skill(repo)
    write_repo_member_rule(repo, "risk-naming", priority=60)
    write_repo_member_rule(repo, "risk-click", priority=40, framework_gate="click")
    return repo


def _skill(repo: Path, skill_id: str = "risk-models") -> list[str]:
    """The member rule ids of ``skill_id`` as rendered, or ``[]`` when it is not written."""
    skills = render_artifacts(SyncContext.from_repo(repo)).skills
    found = [skill for skill in skills if skill.frontmatter.get("id") == skill_id]
    return [member.rule_id for skill in found for member in skill.member_references]


def test_render_artifacts_attaches_only_the_active_members_rendered(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo)

    skills = render_artifacts(SyncContext.from_repo(repo)).skills

    [skill] = [s for s in skills if s.frontmatter.get("id") == "risk-models"]
    [member] = skill.member_references
    assert member.rule_id == "risk-naming"  # risk-click needs click, absent here
    assert "Applies in synthetic." in member.text  # the Jinja-rendered body


def test_render_artifacts_drops_the_skill_without_an_active_member(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo)
    (repo / "playbook" / "rules" / "risk-naming.md.j2").unlink()

    assert _skill(repo) == []


def test_render_artifacts_orders_members_by_priority(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo)
    pyproject = repo / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8").replace(
            "dependencies = []", 'dependencies = ["click"]'
        ),
        encoding="utf-8",
    )

    assert _skill(repo) == ["risk-click", "risk-naming"]


def test_render_artifacts_warns_when_no_enabled_adapter_delivers_member_rules(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo, adapters="[]")

    render_artifacts(SyncContext.from_repo(repo))

    # Core skills with members join the list once core ships them, so pin the ends.
    [line] = capsys.readouterr().err.splitlines()
    assert line.startswith(
        "warning: no enabled adapter delivers scoped rules (only agents_md is on); skill"
    )
    assert "risk-models" in line
    assert line.endswith(
        "no assistant: add claude_code, opencode or shared_skills to adapters_enabled"
    )


def test_render_artifacts_prints_no_warning_with_a_skill_adapter(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo)

    render_artifacts(SyncContext.from_repo(repo))

    assert "warning:" not in capsys.readouterr().err


# 287 chars: with one Covers name and the Use-when tail the description is 339 (over 300).
_OVERFLOWING_DESCRIPTION = ("Risk conventions. " * 16).strip()


def test_render_artifacts_raises_when_a_composed_description_cannot_fit(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    """Regression: the overflow first surfaced inside ``write_skill``, mid-dispatch."""
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG.format(adapters='["claude_code"]'))
    write_repo_member_skill(repo, description=_OVERFLOWING_DESCRIPTION)
    write_repo_member_rule(repo, "risk-naming")

    with pytest.raises(SkillDescriptionOverflowError) as raised:
        render_artifacts(SyncContext.from_repo(repo))

    assert raised.value.subject == "skills/risk-models (<repo-local>)"
    assert raised.value.overflow.length == 339
    assert raised.value.overflow.text.endswith(
        "Covers Risk naming. Use when changing a risk model."
    )
    assert str(raised.value).startswith("skills/risk-models (<repo-local>): the composed ")


def test_render_artifacts_leaves_a_long_description_without_members_as_authored(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    """A skill without ``playbook:`` is never composed, so no length limit applies to it."""
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG.format(adapters='["claude_code"]'))
    skill_dir = repo / "playbook" / "skills" / "long-notes"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nid: long-notes\nname: long-notes\ndescription: {_OVERFLOWING_DESCRIPTION * 2}\n"
        "---\n# Notes\n",
        encoding="utf-8",
    )

    skills = render_artifacts(SyncContext.from_repo(repo)).skills

    [skill] = [s for s in skills if s.frontmatter.get("id") == "long-notes"]
    assert skill.frontmatter["description"] == _OVERFLOWING_DESCRIPTION * 2


def test_report_description_overflow_prints_the_skill_and_the_outcome(
    capsys: pytest.CaptureFixture[str],
) -> None:
    overflow = DescriptionOverflowError("X. Covers Y. Use when Z.")
    exc = SkillDescriptionOverflowError("skills/x (pkg)", overflow)

    assert report_description_overflow(exc, outcome="playbook sync aborted.") == 1

    first, second = capsys.readouterr().err.splitlines()
    assert first == f"error: skills/x (pkg): {overflow}"
    assert second == "error: playbook sync aborted."
