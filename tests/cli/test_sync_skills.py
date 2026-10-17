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
from coding_agent_playbook.lockfile import compute_hash
from coding_agent_playbook.sources.filesystem import FileSystemStateSource
from tests.fakes import FakeGitClient, pre_gate_validate

if TYPE_CHECKING:
    from collections.abc import Callable
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


def _lock_paths(repo: Path) -> set[str]:
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    return {entry.path for entry in lockfile.entries}


def _write_legacy_skill_md(repo: Path, rel: str, text: str) -> None:
    """Rewrite ``rel`` as a pre-v0.15 engine did (no sentinel) and record its hash in
    the lockfile, as that engine's sync would have — the legacy claim's proof."""
    (repo / rel).write_text(text)
    state = FileSystemStateSource(repo_root=repo)
    lockfile = state.load_lockfile()
    assert lockfile is not None
    entry = lockfile.find(rel)
    assert entry is not None
    entry.sha256 = compute_hash((repo / rel).read_bytes())
    state.save_lockfile(lockfile)


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
    assert {f"{root}/query-db/SKILL.md" for root in _SKILL_ROOTS} <= _lock_paths(repo)


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
    for generated in ("AGENTS.md", ".claude/CLAUDE.md", ".claude/rules/coding-agent-playbook.md"):
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
    # Check modes decide ownership against the real tree, like write mode:
    # no false drift, and the user's own files are never "generated output".
    assert _sync.run(_ns(repo, check=True)) == 0
    staged = [".opencode/skills/query-db/notes.md", ".opencode/skills/query-db/SKILL.md"]
    assert _sync.execute(repo, check_staged=True, git=FakeGitClient(staged=staged)) == 0
    assert "/.opencode/skills/query-db/" not in (repo / ".gitignore").read_text()


def test_sync_takes_over_legacy_sentinel_less_claude_skill(tmp_path, make_synthetic_repo):
    """Upgrade path: the old ClaudeCodeAdapter wrote ``SKILL.md`` with no sentinel; the
    lockfile proves the engine wrote it, so the next sync re-owns it and the leftover
    policy cleans the stale script the engine wrote — while a file the user added
    (never in the lockfile) survives."""
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG_WITH_SHARED_SKILLS)
    source = _write_repo_local_skill(repo, "query-db")
    (source / "scripts" / "stale.py").write_text("old\n")
    assert _sync.run(_ns(repo)) == 0
    (source / "scripts" / "stale.py").unlink()
    legacy_dir = repo / ".claude" / "skills" / "query-db"
    _write_legacy_skill_md(
        repo, ".claude/skills/query-db/SKILL.md", "---\nid: query-db\n---\nlegacy body\n"
    )
    (legacy_dir / "notes.md").write_text("mine\n")

    assert _sync.run(_ns(repo)) == 0

    assert not (legacy_dir / "scripts" / "stale.py").exists()
    assert (legacy_dir / "notes.md").read_text() == "mine\n"
    shared = _skill_tree(repo / "shared_skills" / "query-db")
    assert _skill_tree(legacy_dir) == {**shared, "notes.md": b"mine\n"}


def test_sync_never_reclaims_an_adopted_leftover(tmp_path, make_synthetic_repo, capsys):
    """Regression: a removed skill's edited leftovers stay listed in the lockfile; when
    the id came back, that listing re-claimed the dir the user had adopted (sentinel-less
    ``SKILL.md``) and silently overwrote their files. Only unchanged bytes prove a claim."""
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG_WITH_SHARED_SKILLS)
    source = _write_repo_local_skill(repo, "query-db")
    saved = _skill_tree(source)
    assert _sync.run(_ns(repo)) == 0
    shutil.rmtree(source)
    adopted = repo / ".claude" / "skills" / "query-db"
    (adopted / "SKILL.md").write_text("MY OWN INSTRUCTIONS\n")
    (adopted / "scripts" / "run.py").write_text("print('mine')\n")
    assert _sync.run(_ns(repo)) == 0  # both kept as edited leftovers
    before = _skill_tree(adopted)
    for rel, content in saved.items():  # the canonical id comes back
        (source / rel).parent.mkdir(parents=True, exist_ok=True)
        (source / rel).write_bytes(content)
    capsys.readouterr()

    assert _sync.run(_ns(repo)) == 0

    assert _skill_tree(adopted) == before
    assert f"not writing {adopted}" in capsys.readouterr().err
    assert (repo / "shared_skills" / "query-db" / "scripts" / "run.py").is_file()
    assert _sync.run(_ns(repo, check=True)) == 0


def test_sync_check_names_the_blocker_of_a_refused_swap(tmp_path, make_synthetic_repo, capsys):
    """A file/folder swap blocked by a file ``playbook sync`` did not write is one of the
    two documented exceptions to check-mode parity (a file under a link leading out of
    its skill dir is the other): ``--check`` keeps failing until the user moves the
    file, so it says so instead of "run 'playbook sync'" (SPEC §12.3)."""
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG_WITH_SHARED_SKILLS)
    source = _write_repo_local_skill(repo, "query-db")
    (source / "references" / "api").mkdir(parents=True)
    (source / "references" / "api" / "v1.md").write_text("nested\n")
    assert _sync.run(_ns(repo)) == 0
    (repo / "shared_skills" / "query-db" / "references" / "api" / "mine.md").write_text("mine\n")
    shutil.rmtree(source / "references" / "api")
    (source / "references" / "api").write_text("flat\n")
    assert _sync.run(_ns(repo)) == 0
    capsys.readouterr()

    assert _sync.run(_ns(repo, check=True)) == 1

    out = capsys.readouterr().out
    assert "shared_skills/query-db/references/api is in the way" in out
    assert "move those\n    files" in out
    for root in (".claude/skills", ".opencode/skills"):  # unblocked roots were swapped
        assert (repo / root / "query-db" / "references" / "api").read_text() == "flat\n"


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


def _rename_skill_id_case_and_sync(
    tmp_path: Path,
    make_synthetic_repo: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> str:
    """Sync ``id: Demo``, rename it to ``id: demo``, sync again; return that sync's stdout.

    The first sync bypasses the validate gate (``id: Demo`` breaks the Agent
    Skills name rule): it models output a pre-gate engine wrote (prK §P P8).

    Asserts the FS-independent contract: ``--check`` reports drift (no crash)
    before the second sync, every root then holds exactly one fresh ``demo/``,
    and ``--check`` is clean afterwards.
    """
    # Continue is on too: its degraded prompt (``.continue/prompts/<id>.md``) goes
    # through the ABC's sentinel cleanup, which must compare identity, not spelling.
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG_WITH_SHARED_SKILLS)
    source = _write_repo_local_skill(repo, "Demo")
    # ``id: Demo`` fails validate, which now gates sync: seed pre-gate output.
    assert _sync.execute(repo, validate=pre_gate_validate) == 0
    skill_md = source / "SKILL.md"
    skill_md.write_text(skill_md.read_text().replace("id: Demo", "id: demo"))
    capsys.readouterr()

    assert _sync.run(_ns(repo, check=True)) == 1
    capsys.readouterr()
    assert _sync.run(_ns(repo)) == 0
    out: str = capsys.readouterr().out

    for root in _SKILL_ROOTS:
        assert [entry.name for entry in (repo / root).iterdir()] == ["demo"], root
        assert (repo / root / "demo" / "scripts" / "run.py").is_file(), root
        assert (repo / root / "demo" / "SKILL.md").read_text().startswith("---\nname: demo\n")
    assert not any("/Demo/" in path for path in _lock_paths(repo))
    gitignore = (repo / ".gitignore").read_text()
    assert "/Demo/" not in gitignore
    assert _sync.run(_ns(repo, check=True)) == 0
    return out


def test_sync_case_only_id_rename_on_case_insensitive_fs(tmp_path, make_synthetic_repo, capsys):
    """Default macOS APFS / Windows: renaming ``id: Demo`` to ``id: demo`` must keep the
    skill in every root. The old lockfile entry ``Demo/scripts/run.py`` names the very
    file just written as ``demo/scripts/run.py`` (same inode), so the leftover policy
    must not delete fresh output (regression: it compared path strings)."""
    if not _fs_is_case_insensitive(tmp_path):
        pytest.skip("needs a case-insensitive filesystem")
    out = _rename_skill_id_case_and_sync(tmp_path, make_synthetic_repo, capsys)
    assert re.search(r", 0 removed$", out, re.MULTILINE)  # renamed in place, nothing stale


def test_sync_case_only_id_rename_cleans_old_dir_on_case_sensitive_fs(
    tmp_path, make_synthetic_repo, capsys
):
    """Linux: ``Demo/`` and ``demo/`` are different dirs, so the old one is a pristine
    leftover and is deleted (3 roots x SKILL.md + run.py), its dir pruned; plus
    Continue's stale ``Demo.md`` prompt (sentinel cleanup)."""
    if _fs_is_case_insensitive(tmp_path):
        pytest.skip("needs a case-sensitive filesystem")
    out = _rename_skill_id_case_and_sync(tmp_path, make_synthetic_repo, capsys)
    assert re.search(r", 7 removed$", out, re.MULTILINE)
    assert not (tmp_path / ".continue" / "prompts" / "Demo.md").exists()  # repo is tmp_path


# --- check-mode parity: a completed sync leaves nothing for --check to flag ---
#
# Each scenario builds a repo state (running earlier syncs as needed) and returns
# the git client to use. The property: after a successful write-mode sync,
# ``--check`` exits 0 and ``--check-staged`` with nothing generated staged exits
# 0 — i.e. the check modes make exactly write mode's ownership decisions.


def _sync_ok(repo: Path, git: FakeGitClient) -> None:
    assert _sync.execute(repo, git=git) == 0


def _scenario_fresh_skill(repo: Path) -> FakeGitClient:
    _write_repo_local_skill(repo, "query-db")
    return FakeGitClient()


def _scenario_colliding_user_dir(repo: Path) -> FakeGitClient:
    _write_repo_local_skill(repo, "query-db")
    user_dir = repo / ".opencode" / "skills" / "query-db"
    user_dir.mkdir(parents=True)
    (user_dir / "SKILL.md").write_text("---\nname: query-db\ndescription: mine\n---\nmine\n")
    (user_dir / "notes.md").write_text("notes\n")
    return FakeGitClient()


def _scenario_symlinked_skill_dir(repo: Path) -> FakeGitClient:
    if sys.platform == "win32":
        pytest.skip("POSIX symlinks")
    _write_repo_local_skill(repo, "query-db")
    target = repo / "shared_skills" / "hand-written"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("---\nname: hand-written\ndescription: d\n---\nmine\n")
    (repo / "shared_skills" / "query-db").symlink_to(target, target_is_directory=True)
    return FakeGitClient()


def _scenario_plain_file_at_skill_path(repo: Path) -> FakeGitClient:
    _write_repo_local_skill(repo, "query-db")
    blocker = repo / ".claude" / "skills" / "query-db"
    blocker.parent.mkdir(parents=True)
    blocker.write_text("not a dir\n")
    return FakeGitClient()


def _scenario_removed_skill(repo: Path) -> FakeGitClient:
    git = FakeGitClient()
    source = _write_repo_local_skill(repo, "query-db")
    _sync_ok(repo, git)
    shutil.rmtree(source)
    return git


def _scenario_removed_skill_with_edited_leftover(repo: Path) -> FakeGitClient:
    git = _scenario_removed_skill(repo)
    (repo / "shared_skills" / "query-db" / "scripts" / "run.py").write_text("edited\n")
    return git


def _scenario_removed_skill_with_user_file(repo: Path) -> FakeGitClient:
    git = _scenario_removed_skill(repo)
    (repo / ".claude" / "skills" / "query-db" / "notes.md").write_text("mine\n")
    return git


def _scenario_removed_skill_with_tracked_leftover(repo: Path) -> FakeGitClient:
    _scenario_removed_skill(repo)
    return FakeGitClient(tracked={".opencode/skills/query-db/SKILL.md"})


def _scenario_script_dropped_from_live_skill(repo: Path) -> FakeGitClient:
    git = FakeGitClient()
    source = _write_repo_local_skill(repo, "query-db")
    (source / "scripts" / "old.py").write_text("old\n")
    _sync_ok(repo, git)
    (source / "scripts" / "old.py").unlink()
    (repo / ".claude" / "skills" / "query-db" / "scripts" / "old.py").write_text("edited\n")
    return git


def _scenario_case_only_rename(repo: Path) -> FakeGitClient:
    git = FakeGitClient()
    skill_md = _write_repo_local_skill(repo, "Demo") / "SKILL.md"
    # ``id: Demo`` fails validate, which now gates sync: seed pre-gate output.
    assert _sync.execute(repo, git=git, validate=pre_gate_validate) == 0
    skill_md.write_text(skill_md.read_text().replace("id: Demo", "id: demo"))
    return git


def _scenario_legacy_sentinel_less(repo: Path) -> FakeGitClient:
    git = FakeGitClient()
    _write_repo_local_skill(repo, "query-db")
    _sync_ok(repo, git)
    _write_legacy_skill_md(repo, ".claude/skills/query-db/SKILL.md", "---\nid: query-db\n---\nx\n")
    return git


def _scenario_sentinel_stripped_by_user(repo: Path) -> FakeGitClient:
    """Listed in the lockfile but no longer engine bytes: the user's now, never re-claimed."""
    git = FakeGitClient()
    _write_repo_local_skill(repo, "query-db")
    _sync_ok(repo, git)
    (repo / ".claude" / "skills" / "query-db" / "SKILL.md").write_text("mine\n")
    return git


def _scenario_symlinked_skills_root_removed_skill(repo: Path) -> FakeGitClient:
    if sys.platform == "win32":
        pytest.skip("POSIX symlinks")
    (repo / ".agents" / "skills").mkdir(parents=True)
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "skills").symlink_to("../.agents/skills", target_is_directory=True)
    return _scenario_removed_skill(repo)


def _with_harness(repo: Path) -> None:
    config = repo / ".coding-agent-playbook.toml"
    config.write_text(config.read_text().replace('"shared_skills"]', '"agent_harness"]'))


def _scenario_harness_removed_skill(repo: Path) -> FakeGitClient:
    _with_harness(repo)
    return _scenario_removed_skill(repo)


def _scenario_harness_removed_skill_edited_leftover(repo: Path) -> FakeGitClient:
    _with_harness(repo)
    git = _scenario_removed_skill(repo)
    (repo / "skills" / "query-db" / "scripts" / "run.py").write_text("edited\n")
    return git


def _scenario_harness_case_only_rename(repo: Path) -> FakeGitClient:
    _with_harness(repo)
    return _scenario_case_only_rename(repo)


def _scenario_reference_folder_becomes_file(repo: Path) -> FakeGitClient:
    git = FakeGitClient()
    source = _write_repo_local_skill(repo, "query-db")
    (source / "references" / "api").mkdir(parents=True)
    (source / "references" / "api" / "v1.md").write_text("nested\n")
    _sync_ok(repo, git)
    shutil.rmtree(source / "references" / "api")
    (source / "references" / "api").write_text("flat\n")
    return git


def _scenario_removed_skill_without_lockfile(repo: Path) -> FakeGitClient:
    git = _scenario_removed_skill(repo)
    (repo / ".coding-agent-playbook.lock").unlink()
    return git


_PARITY_SCENARIOS = {
    "fresh-skill": _scenario_fresh_skill,
    "colliding-user-dir": _scenario_colliding_user_dir,
    "symlinked-skill-dir": _scenario_symlinked_skill_dir,
    "plain-file-at-skill-path": _scenario_plain_file_at_skill_path,
    "removed-skill": _scenario_removed_skill,
    "removed-skill-edited-leftover": _scenario_removed_skill_with_edited_leftover,
    "removed-skill-user-file": _scenario_removed_skill_with_user_file,
    "removed-skill-tracked-leftover": _scenario_removed_skill_with_tracked_leftover,
    "script-dropped-from-live-skill": _scenario_script_dropped_from_live_skill,
    "case-only-rename": _scenario_case_only_rename,
    "legacy-sentinel-less": _scenario_legacy_sentinel_less,
    "sentinel-stripped-by-user": _scenario_sentinel_stripped_by_user,
    "symlinked-skills-root-removed-skill": _scenario_symlinked_skills_root_removed_skill,
    "harness-removed-skill": _scenario_harness_removed_skill,
    "harness-removed-skill-edited-leftover": _scenario_harness_removed_skill_edited_leftover,
    "harness-case-only-rename": _scenario_harness_case_only_rename,
    "reference-folder-becomes-file": _scenario_reference_folder_becomes_file,
    "removed-skill-without-lockfile": _scenario_removed_skill_without_lockfile,
}


@pytest.mark.parametrize("scenario", list(_PARITY_SCENARIOS), ids=list(_PARITY_SCENARIOS))
def test_check_modes_agree_with_a_completed_sync(
    scenario: str, tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG_WITH_SHARED_SKILLS)
    git = _PARITY_SCENARIOS[scenario](repo)

    assert _sync.execute(repo, git=git) == 0

    assert _sync.execute(repo, check=True, git=git) == 0
    for staged in ([], ["src/app.py", "playbook/skills/notes.md"]):
        staged_git = FakeGitClient(tracked=git.tracked, staged=staged)
        assert _sync.execute(repo, check_staged=True, git=staged_git) == 0, staged
