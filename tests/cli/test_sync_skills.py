"""End-to-end ``playbook sync`` tests for native skills (SPEC §6.3, §10.8).

A repo-local skill must land byte-identically in all three native skill roots
(``.claude/skills``, ``.opencode/skills``, ``shared_skills``), survive
``sync --check`` without drift, and be cleaned from all three when removed.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.sources.filesystem import FileSystemStateSource

if TYPE_CHECKING:
    from pathlib import Path

_SKILL_ROOTS = (".claude/skills", ".opencode/skills", "shared_skills")

_CONFIG_WITH_SHARED_SKILLS = """\
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


def _write_repo_local_skill(repo: Path, skill_id: str) -> Path:
    skill_dir = repo / "playbook" / "skills" / skill_id
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nid: {skill_id}\nname: Display Name\ndescription: Query helper\n---\n"
        "Use scripts/run.py to run the query.\n",
        encoding="utf-8",
    )
    (skill_dir / "scripts" / "run.py").write_text("print('query')\n", encoding="utf-8")
    return skill_dir


def _skill_tree(skill_dir: Path) -> dict[str, bytes]:
    return {
        path.relative_to(skill_dir).as_posix(): path.read_bytes()
        for path in sorted(skill_dir.rglob("*"))
        if path.is_file()
    }


def test_sync_writes_skill_to_all_three_roots_byte_identically(tmp_path, make_synthetic_repo):
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG_WITH_SHARED_SKILLS)
    _write_repo_local_skill(repo, "query-db")

    assert _sync.run(_ns(repo)) == 0

    trees = [_skill_tree(repo / root / "query-db") for root in _SKILL_ROOTS]
    assert trees[0] == trees[1] == trees[2]
    assert set(trees[0]) == {"SKILL.md", "scripts/run.py"}
    assert trees[0]["SKILL.md"].startswith(b"---\nname: query-db\n")
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    lock_paths = {entry.path for entry in lockfile.entries}
    assert {f"{root}/query-db/SKILL.md" for root in _SKILL_ROOTS} <= lock_paths


def test_sync_check_reports_no_drift_after_sync_and_flags_edits(
    tmp_path, make_synthetic_repo, capsys
):
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG_WITH_SHARED_SKILLS)
    _write_repo_local_skill(repo, "query-db")
    assert _sync.run(_ns(repo)) == 0
    capsys.readouterr()

    assert _sync.run(_ns(repo, check=True)) == 0
    assert "No drift" in capsys.readouterr().out

    (repo / "shared_skills" / "query-db" / "scripts" / "run.py").write_text("tampered\n")
    assert _sync.run(_ns(repo, check=True)) == 1
    assert "shared_skills/query-db/scripts/run.py" in capsys.readouterr().out


def test_sync_removes_deleted_skill_from_all_three_roots(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG_WITH_SHARED_SKILLS)
    source = _write_repo_local_skill(repo, "query-db")
    user_skill = repo / ".claude" / "skills" / "hand-written" / "SKILL.md"
    user_skill.parent.mkdir(parents=True)
    user_skill.write_text("---\nname: hand-written\ndescription: d\n---\nmine\n")
    assert _sync.run(_ns(repo)) == 0

    shutil.rmtree(source)
    capsys.readouterr()
    assert _sync.run(_ns(repo)) == 0

    for root in _SKILL_ROOTS:
        assert not (repo / root / "query-db").exists(), root
    # 3 roots x (SKILL.md + scripts/run.py) + Continue's degraded prompt copy —
    # anchored, so "17 removed" (cleanup eating fresh output) cannot pass.
    assert re.search(r", 7 removed$", capsys.readouterr().out, re.MULTILINE)
    assert not (repo / ".continue" / "prompts" / "query-db.md").exists()
    assert user_skill.is_file()
    for generated in ("AGENTS.md", ".claude/CLAUDE.md"):
        assert (repo / generated).is_file(), generated


def test_sync_without_shared_skills_adapter_skips_hub(tmp_path, make_synthetic_repo):
    """``shared_skills`` is opt-out: drop it from adapters_enabled and no hub is written."""
    repo = make_synthetic_repo(tmp_path)  # default fixture config omits shared_skills
    _write_repo_local_skill(repo, "query-db")

    assert _sync.run(_ns(repo)) == 0

    assert (repo / ".claude" / "skills" / "query-db" / "SKILL.md").is_file()
    assert (repo / ".opencode" / "skills" / "query-db" / "SKILL.md").is_file()
    assert not (repo / "shared_skills").exists()


# --- review-finding regressions -----------------------------------------------


def _fs_is_case_insensitive(probe_dir: Path) -> bool:
    probe = probe_dir / "CaseProbe"
    probe.mkdir()
    try:
        return (probe_dir / "caseprobe").exists()
    finally:
        probe.rmdir()


def test_sync_never_touches_user_authored_skill_dir_with_colliding_id(
    tmp_path, make_synthetic_repo, capsys
):
    """A hand-written ``.opencode/skills/query-db/`` keeps every file; the other roots
    still get the canonical skill, and ``sync --check`` sees no drift."""
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG_WITH_SHARED_SKILLS)
    _write_repo_local_skill(repo, "query-db")
    user_dir = repo / ".opencode" / "skills" / "query-db"
    (user_dir / "scripts").mkdir(parents=True)
    (user_dir / "SKILL.md").write_text("---\nname: query-db\ndescription: mine\n---\nmine\n")
    (user_dir / "scripts" / "helper.py").write_text("print('mine')\n")
    (user_dir / "notes.md").write_text("notes\n")
    before = _skill_tree(user_dir)

    assert _sync.run(_ns(repo)) == 0
    assert _sync.run(_ns(repo)) == 0

    assert _skill_tree(user_dir) == before
    captured = capsys.readouterr()
    assert re.search(r", 0 removed$", captured.out, re.MULTILINE)
    assert f"not writing {user_dir}" in captured.err
    for root in (".claude/skills", "shared_skills"):
        assert (repo / root / "query-db" / "scripts" / "run.py").is_file(), root
    assert _sync.run(_ns(repo, check=True)) == 0


def test_sync_takes_over_legacy_sentinel_less_claude_skill(tmp_path, make_synthetic_repo):
    """Upgrade path: the old ClaudeCodeAdapter wrote ``SKILL.md`` with no sentinel; the
    lockfile proves the engine wrote it, so the next sync re-owns and cleans it."""
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG_WITH_SHARED_SKILLS)
    _write_repo_local_skill(repo, "query-db")
    assert _sync.run(_ns(repo)) == 0
    legacy_dir = repo / ".claude" / "skills" / "query-db"
    (legacy_dir / "SKILL.md").write_text("---\nid: query-db\n---\nlegacy body\n")
    (legacy_dir / "scripts" / "stale.py").write_text("old\n")

    assert _sync.run(_ns(repo)) == 0

    assert _skill_tree(legacy_dir) == _skill_tree(repo / "shared_skills" / "query-db")


def test_sync_with_relative_repo_root_keeps_fresh_skill_output(
    tmp_path, make_synthetic_repo, monkeypatch, capsys
):
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG_WITH_SHARED_SKILLS)
    _write_repo_local_skill(repo, "query-db")
    monkeypatch.chdir(repo.parent)
    relative = argparse.Namespace(repo_root=repo.name, check=False)

    assert _sync.run(relative) == 0
    assert _sync.run(relative) == 0

    assert re.search(r", 0 removed$", capsys.readouterr().out, re.MULTILINE)
    for root in _SKILL_ROOTS:
        assert (repo / root / "query-db" / "scripts" / "run.py").is_file(), root


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_sync_and_check_survive_read_only_source_script(tmp_path, make_synthetic_repo):
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG_WITH_SHARED_SKILLS)
    source = _write_repo_local_skill(repo, "query-db")
    (source / "scripts" / "run.py").chmod(0o555)

    assert _sync.run(_ns(repo)) == 0
    assert _sync.run(_ns(repo)) == 0
    assert _sync.run(_ns(repo, check=True)) == 0


def test_sync_check_and_sync_handle_reference_folder_becoming_a_file(
    tmp_path, make_synthetic_repo, capsys
):
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG_WITH_SHARED_SKILLS)
    source = _write_repo_local_skill(repo, "query-db")
    (source / "references" / "api").mkdir(parents=True)
    (source / "references" / "api" / "v1.md").write_text("nested\n")
    assert _sync.run(_ns(repo)) == 0
    shutil.rmtree(source / "references" / "api")
    (source / "references" / "api").write_text("flat\n")
    capsys.readouterr()

    assert _sync.run(_ns(repo, check=True)) == 1  # drift reported, no crash
    assert _sync.run(_ns(repo)) == 0
    assert _sync.run(_ns(repo, check=True)) == 0

    for root in _SKILL_ROOTS:
        api = repo / root / "query-db" / "references" / "api"
        assert api.is_file(), root
        assert api.read_text() == "flat\n"


def test_sync_case_only_id_rename_on_case_insensitive_fs(tmp_path, make_synthetic_repo, capsys):
    """Default macOS APFS / Windows: renaming ``id: Demo`` to ``id: demo`` must keep the
    skill in every root, and ``sync --check`` must report drift instead of crashing."""
    if not _fs_is_case_insensitive(tmp_path):
        pytest.skip("needs a case-insensitive filesystem")
    # Native skill roots only: Continue's degraded prompt copy goes through the ABC's
    # path-spelling cleanup, a separate pre-existing case-rename limitation.
    skill_roots_only = _CONFIG_WITH_SHARED_SKILLS.replace('"continue", ', "")
    repo = make_synthetic_repo(tmp_path, config_text=skill_roots_only)
    source = _write_repo_local_skill(repo, "Demo")
    assert _sync.run(_ns(repo)) == 0
    skill_md = source / "SKILL.md"
    skill_md.write_text(skill_md.read_text().replace("id: Demo", "id: demo"))
    capsys.readouterr()

    assert _sync.run(_ns(repo, check=True)) == 1
    assert _sync.run(_ns(repo)) == 0

    for root in _SKILL_ROOTS:
        assert [entry.name for entry in (repo / root).iterdir()] == ["demo"], root
        assert (repo / root / "demo" / "scripts" / "run.py").is_file(), root
    assert _sync.run(_ns(repo, check=True)) == 0
