"""``render_artifacts`` composes skills from member rules (specs/prS-skills-context.md 6.4.3).

The sync's render step hands the adapters composed skills: a skill with a
``playbook:`` block carries its active member rules, rendered, and is dropped
when none is active. When member rules are active but no enabled adapter
delivers them, it prints one ``warning:`` line on stderr.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.commands._sync_render import render_artifacts
from coding_agent_playbook.orchestrator import SyncContext
from tests.member_skill_samples import write_repo_member_rule, write_repo_member_skill

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest

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
