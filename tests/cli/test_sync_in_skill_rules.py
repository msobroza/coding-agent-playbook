"""A repo-local rule in ``playbook/skills/<id>/rules/`` end to end (prU D5, L0-05 acceptance).

The directory sets membership: the rule needs no ``skill:`` to be validated,
synced into its skill's output and recorded in the lockfile, and an in-skill
rule with a core rule's id overrides that rule like any repo-local rule.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from coding_agent_playbook.commands import render as _render
from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.lockfile.model import Lockfile

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest

_SKILL_MD = (
    "---\nid: {id}\nname: {id}\ndescription: Risk model conventions.\n"
    "playbook:\n  use_when: editing a risk model\n  files: Risk model code\n---\n# {id}\n"
)
_RULE_MD = "---\nid: {id}\nname: {name}\ndescription: One line.\nscope: scoped\n---\nBody\n"


def _in_skill_rule(repo: Path, skill_id: str, rule_id: str, name: str) -> Path:
    """Write ``playbook/skills/<skill_id>/{SKILL.md,rules/<rule_id>.md}``; no ``skill:`` key."""
    skill_dir = repo / "playbook" / "skills" / skill_id
    (skill_dir / "rules").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(_SKILL_MD.format(id=skill_id), encoding="utf-8")
    rule = skill_dir / "rules" / f"{rule_id}.md"
    rule.write_text(_RULE_MD.format(id=rule_id, name=name), encoding="utf-8")
    return rule


def test_in_skill_rule_without_skill_key_is_synced_into_its_skill(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    _in_skill_rule(repo, "risk-models", "risk-naming", "Risk naming")

    assert _validate.run(argparse.Namespace(repo_root=str(repo))) == 0, capsys.readouterr().out
    assert "warning:" not in capsys.readouterr().err
    assert _sync.run(argparse.Namespace(repo_root=str(repo), check=False)) == 0

    skill_dir = repo / ".claude" / "skills" / "risk-models"
    assert (skill_dir / "references" / "risk-naming.md").is_file()
    assert not (skill_dir / "rules").exists(), "rules/ is loaded as rules, never byte-copied"
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert isinstance(lockfile, Lockfile)
    entries = {(e.path, e.kind, e.artifact_id) for e in lockfile.entries}
    assert (
        ".claude/skills/risk-models/references/risk-naming.md",
        "rule",
        "risk-naming",
    ) in entries


def test_in_skill_rule_with_a_core_id_overrides_core_and_shows_the_collision(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    rule = _in_skill_rule(repo, "risk-models", "python-typing", "Typing")
    args = argparse.Namespace(
        repo_root=str(repo), id="python-typing", format=None, show_source=True, show_rules=False
    )

    assert _render.run(args) == 0

    out = capsys.readouterr().out
    assert f"Template:  {rule}" in out
    assert "Overrides: coding_agent_playbook" in out
