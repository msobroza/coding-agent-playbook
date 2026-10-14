"""End-to-end opt-in sync of the bundled ``superpowers`` pack (SPEC §11.5).

Drives ``playbook sync`` / ``playbook validate`` / ``playbook sync --check`` on a
synthetic consumer repo the same way ``tests/cli/`` does, and checks that the
pack lands natively under ``.claude/skills/<id>/`` byte-faithfully (body,
``references/`` incl. the MIT notice, executable ``scripts/``), degrades to
Continue prompts, and writes nothing when the consumer has not opted in. It also
pins §11.5 "Opting out and overriding": opting out removes every synced pack
skill directory on the next sync (``sync --check`` reports them stale until
then) but keeps a file the consumer added inside one; a ``SKILL.md``-only
override removes the pack's ``scripts/`` and ``references/``; and an override
that ships only some of the pack skill's references removes the rest. The
mutating scenarios build their own repos so the module-scoped
``synced_pack_repo`` fixture stays read-only.
"""

from __future__ import annotations

import argparse
import os
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.packs.superpowers import PACK_NAME
from coding_agent_playbook.types import split_frontmatter
from tests.packs.superpowers_expectations import (
    EXPECTED_LICENSE_COPIES,
    EXPECTED_SCRIPTS,
    EXPECTED_SKILL_IDS,
    PACK_ROOT,
    SKILLS_ROOT,
    consumer_config,
    write_consumer_repo,
)

if TYPE_CHECKING:
    from pathlib import Path


def _ns(repo: Path, *, check: bool = False) -> argparse.Namespace:
    return argparse.Namespace(repo_root=str(repo), check=check)


@pytest.fixture(scope="module")
def synced_pack_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A consumer repo opted into the pack, after one successful ``playbook sync``.

    Module-scoped: one sync serves every read-only check below (``sync --check``
    renders into its own scratch copy and ``validate`` writes nothing).
    """
    repo = write_consumer_repo(tmp_path_factory.mktemp("pack-consumer"), overlays=[PACK_NAME])
    assert _sync.run(_ns(repo)) == 0
    return repo


def _relative_files(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())


@pytest.mark.parametrize("skill_id", sorted(EXPECTED_SKILL_IDS))
def test_sync_writes_skill_md_faithfully(synced_pack_repo: Path, skill_id: str) -> None:
    written = synced_pack_repo / ".claude" / "skills" / skill_id / "SKILL.md"
    source = SKILLS_ROOT / skill_id / "SKILL.md"
    written_fm, written_body = split_frontmatter(written.read_text(encoding="utf-8"))
    source_fm, source_body = split_frontmatter(source.read_text(encoding="utf-8"))
    assert written_fm == source_fm
    assert written_fm["id"] == skill_id
    # The adapter re-dumps the YAML frontmatter but must pass the body through
    # untouched — the port's whole point is upstream fidelity.
    assert written_body == source_body


@pytest.mark.parametrize("skill_id", sorted(EXPECTED_SKILL_IDS))
def test_sync_copies_supporting_dirs_byte_for_byte(synced_pack_repo: Path, skill_id: str) -> None:
    for subdir in ("references", "scripts"):
        source_dir = SKILLS_ROOT / skill_id / subdir
        if not source_dir.is_dir():
            continue
        target_dir = synced_pack_repo / ".claude" / "skills" / skill_id / subdir
        assert _relative_files(target_dir) == _relative_files(source_dir)
        for rel in _relative_files(source_dir):
            assert (target_dir / rel).read_bytes() == (source_dir / rel).read_bytes(), rel


@pytest.mark.parametrize("license_copy", sorted(EXPECTED_LICENSE_COPIES))
def test_synced_skill_carries_the_mit_notice(synced_pack_repo: Path, license_copy: str) -> None:
    # MIT requires the notice in every copy; the consumer repo is one.
    synced = synced_pack_repo / ".claude" / "skills" / license_copy
    assert synced.read_bytes() == (PACK_ROOT / "LICENSE").read_bytes()


@pytest.mark.parametrize("script", sorted(EXPECTED_SCRIPTS))
def test_synced_scripts_stay_executable(synced_pack_repo: Path, script: str) -> None:
    synced = synced_pack_repo / ".claude" / "skills" / script
    assert synced.is_file()
    assert os.access(synced, os.X_OK), f"{script} lost its executable bit in sync"


def test_continue_degrades_each_skill_to_a_prompt(synced_pack_repo: Path) -> None:
    prompts_dir = synced_pack_repo / ".continue" / "prompts"
    missing = sorted(sid for sid in EXPECTED_SKILL_IDS if not (prompts_dir / f"{sid}.md").is_file())
    assert not missing, f"Continue prompts missing for {missing}"


def test_validate_passes_with_pack_enabled(
    synced_pack_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = _validate.run(_ns(synced_pack_repo))
    assert rc == 0, capsys.readouterr().out


def test_sync_check_reports_no_drift_after_sync(
    synced_pack_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    assert _sync.run(_ns(synced_pack_repo, check=True)) == 0, capsys.readouterr().out


def test_sync_without_overlay_writes_no_pack_skills(tmp_path: Path) -> None:
    repo = write_consumer_repo(tmp_path, overlays=[])
    assert _sync.run(_ns(repo)) == 0
    skills_dir = repo / ".claude" / "skills"
    written = {path.name for path in skills_dir.iterdir()} if skills_dir.is_dir() else set()
    assert written.isdisjoint(EXPECTED_SKILL_IDS)


def test_opting_out_removes_the_synced_pack_skills(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = write_consumer_repo(tmp_path, overlays=[PACK_NAME])
    assert _sync.run(_ns(repo)) == 0
    (repo / ".coding-agent-playbook.toml").write_text(
        consumer_config(overlays=[]), encoding="utf-8"
    )
    capsys.readouterr()

    # Before the next sync, --check reports every pack skill file as stale.
    assert _sync.run(_ns(repo, check=True)) == 1
    out = capsys.readouterr().out
    for skill_id in sorted(EXPECTED_SKILL_IDS):
        assert f"  .claude/skills/{skill_id}/SKILL.md\n    Stale:" in out, skill_id
        assert f"  .claude/skills/{skill_id}/references/LICENSE\n    Stale:" in out, skill_id
    for script in sorted(EXPECTED_SCRIPTS):
        assert f"  .claude/skills/{script}\n    Stale:" in out, script

    assert _sync.run(_ns(repo)) == 0
    skills_dir = repo / ".claude" / "skills"
    left = {path.name for path in skills_dir.iterdir()} if skills_dir.is_dir() else set()
    assert left.isdisjoint(EXPECTED_SKILL_IDS), sorted(left & EXPECTED_SKILL_IDS)
    prompts_dir = repo / ".continue" / "prompts"
    assert not any((prompts_dir / f"{sid}.md").exists() for sid in EXPECTED_SKILL_IDS)
    capsys.readouterr()
    assert _sync.run(_ns(repo, check=True)) == 0, capsys.readouterr().out


def test_opting_out_keeps_a_file_the_consumer_added_to_a_pack_skill(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The adapter reports every file under a copied references/ dir; only the
    # pack's own files are engine output, so the consumer's notes survive.
    repo = write_consumer_repo(tmp_path, overlays=[PACK_NAME])
    assert _sync.run(_ns(repo)) == 0
    notes = repo / ".claude" / "skills" / "brainstorming" / "references" / "our-team-notes.md"
    notes.write_text("How our team brainstorms.\n", encoding="utf-8")
    assert _sync.run(_ns(repo)) == 0
    (repo / ".coding-agent-playbook.toml").write_text(
        consumer_config(overlays=[]), encoding="utf-8"
    )
    capsys.readouterr()

    assert _sync.run(_ns(repo)) == 0

    assert notes.read_text(encoding="utf-8") == "How our team brainstorms.\n"
    assert _relative_files(notes.parents[1]) == ["references/our-team-notes.md"]
    assert "warning:" not in capsys.readouterr().err


def _write_override(repo: Path, skill_id: str, references: dict[str, str]) -> None:
    """A repo-local ``playbook/skills/<skill_id>/`` overriding the pack skill."""
    override = repo / "playbook" / "skills" / skill_id
    (override / "references").mkdir(parents=True)
    (override / "SKILL.md").write_text(
        f"---\nid: {skill_id}\nname: {skill_id}\n"
        "description: Our house process\n---\nDo it our way.\n",
        encoding="utf-8",
    )
    for name, content in references.items():
        (override / "references" / name).write_text(content, encoding="utf-8")


def test_a_skill_md_only_override_removes_the_pack_scripts_and_references(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = write_consumer_repo(tmp_path, overlays=[PACK_NAME])
    assert _sync.run(_ns(repo)) == 0
    synced = repo / ".claude" / "skills" / "systematic-debugging"
    assert (synced / "scripts" / "find-polluter.sh").is_file()
    assert (synced / "references" / "root-cause-tracing.md").is_file()
    _write_override(repo, "systematic-debugging", references={})

    assert _sync.run(_ns(repo)) == 0

    assert _relative_files(synced) == ["SKILL.md"]
    assert synced.joinpath("SKILL.md").read_text(encoding="utf-8").endswith("Do it our way.\n")
    capsys.readouterr()
    assert _sync.run(_ns(repo, check=True)) == 0, capsys.readouterr().out


def test_an_override_shipping_fewer_references_removes_the_pack_only_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = write_consumer_repo(tmp_path, overlays=[PACK_NAME])
    assert _sync.run(_ns(repo)) == 0
    synced = repo / ".claude" / "skills" / "systematic-debugging"
    _write_override(repo, "systematic-debugging", references={"root-cause-tracing.md": "Ours.\n"})
    capsys.readouterr()

    # Before the sync, --check reports the pack-only references as stale.
    assert _sync.run(_ns(repo, check=True)) == 1
    out = capsys.readouterr().out
    assert "  .claude/skills/systematic-debugging/references/defense-in-depth.md\n    Stale:" in out
    assert "references/root-cause-tracing.md\n    Stale:" not in out

    assert _sync.run(_ns(repo)) == 0

    assert _relative_files(synced) == ["SKILL.md", "references/root-cause-tracing.md"]
    assert (synced / "references" / "root-cause-tracing.md").read_text(encoding="utf-8") == (
        "Ours.\n"
    )
    capsys.readouterr()
    assert _sync.run(_ns(repo, check=True)) == 0, capsys.readouterr().out
