"""End-to-end ``playbook sync`` of member rules as skill references (specs/prS-skills-context.md 6.8.9).

A synthetic repo holds a repo-local skill with a ``playbook:`` block and two
repo-local scoped rules naming it, one gated on the ``click`` framework. Sync
writes each active member as ``references/<rule-id>.md`` in every skill root,
records it in the lockfile as ``kind = "rule"``, and settles the references of
members that turn off (and the whole skill once none is on) by the lockfile
leftover policy. Assertions stay on the test's own skill: core skills may sit
next to it in every root. A skill whose composed description cannot fit 300
characters aborts every mode before the first write.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.sources.filesystem import FileSystemStateSource
from coding_agent_playbook.types import split_frontmatter
from tests.fakes import FakeGitClient, pre_gate_validate
from tests.member_skill_samples import (
    skill_tree_bytes,
    write_repo_member_rule,
    write_repo_member_skill,
)
from tests.plugins.superpowers_expectations import NATIVE_SKILL_ROOTS

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.lockfile import LockEntry

_SKILL = "risk-models"
_UNGATED, _GATED = "risk-naming", "risk-click"

_CONFIG = """\
schema_version = 1
adapters_enabled = ["continue", "claude_code", "opencode", "shared_skills"]
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


def _ns(repo: Path, *, check: bool = False) -> argparse.Namespace:
    return argparse.Namespace(repo_root=str(repo), check=check)


def _repo(
    tmp_path: Path,
    make_synthetic_repo: Callable[..., Path],
    *,
    ungated: bool = True,
    description: str = "Conventions for the risk models.",
) -> Path:
    """The synthetic repo with ``click`` declared, so both members start active."""
    repo = make_synthetic_repo(
        tmp_path, config_text=_CONFIG, pyproject_extras={"dependencies": ["click"]}
    )
    write_repo_member_skill(repo, _SKILL, description=description)
    if ungated:
        write_repo_member_rule(repo, _UNGATED, skill_id=_SKILL, priority=60)
    write_repo_member_rule(repo, _GATED, skill_id=_SKILL, priority=40, framework_gate="click")
    return repo


def _drop_click(repo: Path) -> None:
    pyproject = repo / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    pyproject.write_text(text.replace('["click"]', "[]"), encoding="utf-8")


def _lock_entries(repo: Path) -> dict[str, LockEntry]:
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    return {entry.path: entry for entry in lockfile.entries}


def test_sync_writes_member_references_to_every_skill_root_byte_identically(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo)

    assert _sync.run(_ns(repo)) == 0

    trees = [skill_tree_bytes(repo / root / _SKILL) for root in NATIVE_SKILL_ROOTS]
    assert all(tree == trees[0] for tree in trees[1:])
    assert set(trees[0]) == {"SKILL.md", f"references/{_GATED}.md", f"references/{_UNGATED}.md"}
    reference = trees[0][f"references/{_UNGATED}.md"].decode("utf-8")
    assert reference == (
        f"*Rule `{_UNGATED}`; applies to `src/risk/**/*.py`.*\n\n"
        f"# {_UNGATED}\n\nApplies in synthetic.\n"
    )
    frontmatter, body = split_frontmatter(trees[0]["SKILL.md"].decode("utf-8"))
    assert frontmatter["description"] == (
        "Conventions for the risk models. Covers Risk click, Risk naming. "
        "Use when changing a risk model."
    )
    assert "playbook" not in frontmatter
    assert f"- [{_GATED}](references/{_GATED}.md) — Risk click:" in body
    # Continue gets the members as rule files, never the skill as a prompt (E4).
    assert not (repo / ".continue" / "prompts" / f"{_SKILL}.md").exists()
    assert (repo / ".continue" / "rules" / f"60-{_UNGATED}.md").is_file()


def test_sync_gates_the_skill_off_and_removes_pristine_output_when_no_member_is_active(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo, ungated=False)
    assert _sync.run(_ns(repo)) == 0
    assert all((repo / root / _SKILL / "SKILL.md").is_file() for root in NATIVE_SKILL_ROOTS)

    _drop_click(repo)
    assert _sync.run(_ns(repo)) == 0

    for root in NATIVE_SKILL_ROOTS:
        assert not (repo / root / _SKILL).exists(), root
    assert not any(f"/{_SKILL}/" in path for path in _lock_entries(repo))


def test_sync_removes_the_reference_of_a_deactivated_member(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo)
    assert _sync.run(_ns(repo)) == 0

    _drop_click(repo)
    assert _sync.run(_ns(repo)) == 0

    for root in NATIVE_SKILL_ROOTS:
        tree = skill_tree_bytes(repo / root / _SKILL)
        assert set(tree) == {"SKILL.md", f"references/{_UNGATED}.md"}, root
        assert _GATED not in tree["SKILL.md"].decode("utf-8")
    assert not any(path.endswith(f"/{_GATED}.md") for path in _lock_entries(repo))


def test_lockfile_records_member_references_with_rule_provenance(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo)

    assert _sync.run(_ns(repo)) == 0

    entries = _lock_entries(repo)
    # NATIVE_SKILL_ROOTS lists the roots of these three adapters, in this order.
    for root, adapter in zip(
        NATIVE_SKILL_ROOTS, ("claude_code", "opencode", "shared_skills"), strict=True
    ):
        reference = entries[f"{root}/{_SKILL}/references/{_UNGATED}.md"]
        assert (reference.kind, reference.artifact_id) == ("rule", _UNGATED)
        assert (reference.source, reference.adapter) == ("<repo-local>", adapter)
        skill_md = entries[f"{root}/{_SKILL}/SKILL.md"]
        assert (skill_md.kind, skill_md.artifact_id, skill_md.adapter) == ("skill", _SKILL, adapter)


def test_sync_check_is_clean_after_sync(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo)
    assert _sync.run(_ns(repo)) == 0
    capsys.readouterr()

    assert _sync.run(_ns(repo, check=True)) == 0
    assert "No drift" in capsys.readouterr().out

    reference = repo / NATIVE_SKILL_ROOTS[0] / _SKILL / "references" / f"{_UNGATED}.md"
    reference.write_text("edited by hand\n", encoding="utf-8")
    assert _sync.run(_ns(repo, check=True)) == 1
    assert f"{NATIVE_SKILL_ROOTS[0]}/{_SKILL}/references/{_UNGATED}.md" in capsys.readouterr().out


def test_gitignore_covers_member_references_through_their_skill_directory(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    """``[output] commit = false`` (the default): one managed line per skill directory (6.7)."""
    repo = _repo(tmp_path, make_synthetic_repo)

    assert _sync.run(_ns(repo)) == 0

    lines = (repo / ".gitignore").read_text(encoding="utf-8").splitlines()
    for root in NATIVE_SKILL_ROOTS:
        assert f"/{root}/{_SKILL}/" in lines, root
    assert not any("/references/" in line for line in lines)


# 283 chars: with one Covers name and the Use-when tail the description is 345 (over 300).
_OVERFLOWING_DESCRIPTION = (
    "Conventions for every risk model, its inputs and its calibration data. " * 4
).strip()


@pytest.mark.parametrize(
    "mode",
    [{}, {"check": True}, {"check_staged": True}],
    ids=["write", "check", "check-staged"],
)
def test_sync_aborts_before_any_write_when_a_composed_description_cannot_fit(
    tmp_path: Path,
    make_synthetic_repo: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
    mode: dict[str, bool],
) -> None:
    """Regression: the description was first composed inside ``write_skill``, mid-dispatch.

    So the overflow escaped as a traceback after earlier adapters had written
    ``AGENTS.md`` and commands, with no lockfile saved. The gate is stubbed
    (V11 would refuse this skill in write and ``--check`` mode); ``--check-staged``
    never runs it.
    """
    repo = _repo(tmp_path, make_synthetic_repo, description=_OVERFLOWING_DESCRIPTION)
    before = skill_tree_bytes(repo)  # every file in the repo, by relative path
    git = FakeGitClient(staged=["AGENTS.md"])

    rc = _sync.execute(
        repo,
        check=mode.get("check", False),
        check_staged=mode.get("check_staged", False),
        git=git,
        validate=pre_gate_validate,
    )

    assert rc == 1

    err = capsys.readouterr().err
    assert f"error: skills/{_SKILL} (<repo-local>): the composed description is " in err
    assert "over the 300-char limit even when the Covers clause names one member" in err
    assert err.rstrip().endswith("error: playbook sync aborted; no files were written.")
    assert "Traceback" not in err
    assert skill_tree_bytes(repo) == before
