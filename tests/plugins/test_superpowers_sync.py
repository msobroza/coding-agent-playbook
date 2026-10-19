"""End-to-end opt-in sync of the bundled ``superpowers`` pack (SPEC §11.5).

Drives ``playbook sync`` / ``playbook validate`` / ``playbook sync --check`` on a
synthetic consumer repo the same way ``tests/cli/`` does, and checks that the
pack lands natively and byte-identically under every native skill root
(``.claude/skills/``, ``.opencode/skills/``, ``.agents/skills/``): ``SKILL.md``
with the sentinel as its first body line and the vendored body after it,
``references/`` incl. the MIT notice, executable ``scripts/``. It also checks the
degraded Continue prompts and that nothing is written without the opt-in.

The read-only checks share the module-scoped ``synced_pack_repo`` fixture, which
never shells out to git (``FakeGitClient``). The mutating scenarios pin §11.5
"Opting out and overriding" under the lockfile leftover policy (§4.2 step 9):
each builds its own consumer repo as a **real** git repo in a hermetic git
environment, because inside a git work tree the policy fails closed unless git
confirms a leftover is untracked; this exercises the tracked/untracked decision
end to end. Opting out removes all 15 pack skill dirs from every root but keeps
a file the consumer added and a file the consumer edited; a ``SKILL.md``-only
override removes the pack's ``scripts/`` and ``references/``; an override that
ships only some of the references removes the pack-only files. One scenario
enables the opt-in ``agent_harness`` adapter: its ``skills/<id>/`` copies, the
script flags in ``.playbook/manifest.toml``, and their removal on opt-out.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.harness.manifest import read_manifest
from coding_agent_playbook.renderer import SENTINEL
from tests.fakes import FakeGitClient
from tests.plugins.superpowers_expectations import (
    EXPECTED_LICENSE_COPIES,
    EXPECTED_SCRIPTS,
    EXPECTED_SKILL_IDS,
    NATIVE_SKILL_ROOTS,
    PLUGIN_NAME,
    PLUGIN_ROOT,
    SKILL_ADAPTERS,
    SKILLS_ROOT,
    consumer_config,
    write_consumer_repo,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

#: What the ``SkillWriter`` puts between the frontmatter and the vendored body:
#: the sentinel HTML comment as the first body line, then one blank separator
#: line (SPEC §6.3; ``harness.emitter.with_sentinel_body``).
_SENTINEL_BODY_PREFIX = f"<!-- {SENTINEL} -->\n\n"

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _ns(repo: Path, *, check: bool = False) -> argparse.Namespace:
    return argparse.Namespace(repo_root=str(repo), check=check)


def _git(repo: Path, *args: str) -> str:
    """Run ``git`` in ``repo`` (call only under the ``hermetic_git_env`` fixture)."""
    proc = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, timeout=10
    )
    return proc.stdout


@pytest.fixture(scope="module")
def synced_pack_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A consumer repo opted into the pack, after one successful ``playbook sync``.

    Module-scoped: one sync serves every read-only check below (``sync --check``
    renders into its own scratch dir and ``validate`` writes nothing). A first
    sync has no leftovers to judge, so a ``FakeGitClient`` stands in for git.
    """
    repo = write_consumer_repo(tmp_path_factory.mktemp("pack-consumer"), overlays=[PLUGIN_NAME])
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    return repo


@pytest.fixture
def git_pack_repo(tmp_path: Path, hermetic_git_env: None) -> Path:
    """A real git consumer repo opted into the pack: synced, sources committed.

    The generated output is gitignored by the managed block, so ``git add -A``
    commits only the sources and every synced pack file stays untracked. Inside
    a git work tree the leftover policy deletes a leftover only once git
    confirms that, so these scenarios exercise the real tracked/untracked call.
    """
    return _init_git_pack_repo(tmp_path, adapters=SKILL_ADAPTERS)


def _init_git_pack_repo(repo: Path, *, adapters: tuple[str, ...]) -> Path:
    """Write, ``git init``, sync and commit the sources of an opted-in consumer repo."""
    write_consumer_repo(repo, overlays=[PLUGIN_NAME], adapters=adapters)
    _git(repo, "init", "-q")
    assert _sync.run(_ns(repo)) == 0
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-verify", "-m", "sources")
    return repo


def _relative_files(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())


def _skill_tree(skill_dir: Path) -> dict[str, bytes]:
    return {rel: (skill_dir / rel).read_bytes() for rel in _relative_files(skill_dir)}


def _pack_skill_dirs_left(repo: Path, root: str) -> set[str]:
    skills_dir = repo / root
    found = {path.name for path in skills_dir.iterdir()} if skills_dir.is_dir() else set()
    return found & EXPECTED_SKILL_IDS


def _lock_paths(repo: Path) -> set[str]:
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    return {entry.path for entry in lockfile.entries}


def _opt_out(repo: Path, *, adapters: tuple[str, ...] = SKILL_ADAPTERS) -> None:
    (repo / ".coding-agent-playbook.toml").write_text(
        consumer_config(overlays=[], adapters=adapters), encoding="utf-8"
    )


def _source_body(skill_id: str) -> str:
    """The vendored ``SKILL.md`` body (frontmatter stripped) of a pack skill."""
    return split_frontmatter((SKILLS_ROOT / skill_id / "SKILL.md").read_text(encoding="utf-8"))[1]


# --- read-only: what an opted-in sync writes -----------------------------------


@pytest.mark.parametrize("skill_id", sorted(EXPECTED_SKILL_IDS))
def test_sync_writes_skill_md_faithfully(synced_pack_repo: Path, skill_id: str) -> None:
    text = (synced_pack_repo / ".claude" / "skills" / skill_id / "SKILL.md").read_text("utf-8")
    source = SKILLS_ROOT / skill_id / "SKILL.md"
    written_fm, written_body = split_frontmatter(text)
    source_fm, source_body = split_frontmatter(source.read_text(encoding="utf-8"))
    # The SkillWriter puts ``name`` (= id) first and keeps every other key.
    assert text.startswith(f"---\nname: {skill_id}\n")
    assert written_fm == source_fm
    assert written_fm["id"] == skill_id
    # Exactly the sentinel line is added; the vendored body after it is
    # untouched, since the port's whole point is upstream fidelity.
    assert written_body.startswith(_SENTINEL_BODY_PREFIX)
    assert written_body.removeprefix(_SENTINEL_BODY_PREFIX) == source_body


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


@pytest.mark.parametrize("skill_id", sorted(EXPECTED_SKILL_IDS))
def test_every_native_root_holds_a_byte_identical_copy(
    synced_pack_repo: Path, skill_id: str
) -> None:
    claude, *others = (
        _skill_tree(synced_pack_repo / root / skill_id) for root in NATIVE_SKILL_ROOTS
    )
    assert "SKILL.md" in claude
    for root, tree in zip(NATIVE_SKILL_ROOTS[1:], others, strict=True):
        assert tree == claude, f"{root}/{skill_id} differs from .claude/skills/{skill_id}"


@pytest.mark.parametrize("root", NATIVE_SKILL_ROOTS)
@pytest.mark.parametrize("license_copy", sorted(EXPECTED_LICENSE_COPIES))
def test_synced_skill_carries_the_mit_notice(
    synced_pack_repo: Path, root: str, license_copy: str
) -> None:
    # MIT requires the notice in every copy; each synced skill dir is one.
    synced = synced_pack_repo / root / license_copy
    assert synced.read_bytes() == (PLUGIN_ROOT / "LICENSE").read_bytes()


@pytest.mark.parametrize("root", NATIVE_SKILL_ROOTS)
@pytest.mark.parametrize("script", sorted(EXPECTED_SCRIPTS))
def test_synced_scripts_stay_executable(synced_pack_repo: Path, root: str, script: str) -> None:
    synced = synced_pack_repo / root / script
    assert synced.is_file()
    assert os.access(synced, os.X_OK), f"{root}/{script} lost its executable bit in sync"


@pytest.mark.parametrize("skill_id", sorted(EXPECTED_SKILL_IDS))
def test_continue_degrades_each_skill_to_a_prompt(synced_pack_repo: Path, skill_id: str) -> None:
    prompt = synced_pack_repo / ".continue" / "prompts" / f"{skill_id}.md"
    text = prompt.read_text(encoding="utf-8")
    # Line 1 is what lets Continue's cleanup_stale remove the prompt on opt-out.
    assert SENTINEL in text.split("\n", 1)[0]
    # Skill.to_prompt carries the vendored SKILL.md body unchanged.
    assert text.endswith(_source_body(skill_id))


def test_pack_skill_dirs_are_gitignored_in_every_root(synced_pack_repo: Path) -> None:
    # Generated output is local-only by default (SPEC §5.3): one collapsed
    # entry per skill directory in the managed block.
    gitignore = (synced_pack_repo / ".gitignore").read_text(encoding="utf-8")
    for root in NATIVE_SKILL_ROOTS:
        for skill_id in sorted(EXPECTED_SKILL_IDS):
            assert f"\n/{root}/{skill_id}/\n" in gitignore, f"{root}/{skill_id}"


def test_validate_passes_with_pack_enabled(
    synced_pack_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = _validate.run(_ns(synced_pack_repo))
    assert rc == 0, capsys.readouterr().out


def test_sync_check_reports_no_drift_after_sync(
    synced_pack_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    rc = _sync.execute(synced_pack_repo, check=True, git=FakeGitClient())
    assert rc == 0, capsys.readouterr().out


def test_sync_without_overlay_writes_no_pack_skills(tmp_path: Path) -> None:
    repo = write_consumer_repo(tmp_path, overlays=[])
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    for root in NATIVE_SKILL_ROOTS:
        assert not _pack_skill_dirs_left(repo, root), root


# --- mutating: opting out and overriding (real git, SPEC §11.5) ---------------


@needs_git
def test_opting_out_removes_the_pack_skills_from_every_root(
    git_pack_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = git_pack_repo
    _opt_out(repo)
    capsys.readouterr()

    # Before the next sync, --check sees the managed block go stale.
    assert _sync.run(_ns(repo, check=True)) == 1
    assert "  .gitignore\n    Managed block is missing or stale" in capsys.readouterr().out

    assert _sync.run(_ns(repo)) == 0
    for root in NATIVE_SKILL_ROOTS:
        assert not _pack_skill_dirs_left(repo, root), root
    prompts_dir = repo / ".continue" / "prompts"
    assert not any((prompts_dir / f"{sid}.md").exists() for sid in EXPECTED_SKILL_IDS)
    gitignore = (repo / ".gitignore").read_text(encoding="utf-8")
    assert not any(f"/{sid}/" in gitignore for sid in EXPECTED_SKILL_IDS)
    assert not any(sid in path for path in _lock_paths(repo) for sid in EXPECTED_SKILL_IDS)
    capsys.readouterr()
    assert _sync.run(_ns(repo, check=True)) == 0, capsys.readouterr().out


@needs_git
def test_opting_out_keeps_a_consumer_added_and_a_consumer_edited_file(
    git_pack_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = git_pack_repo
    # Never written by sync, so never in the lockfile: the consumer's own file.
    notes = repo / ".claude" / "skills" / "brainstorming" / "references" / "our-team-notes.md"
    notes.write_text("How our team brainstorms.\n", encoding="utf-8")
    # A sync while still opted in rewrites the copied references/ dir; the
    # consumer's file next to the pack's must not become engine output.
    assert _sync.run(_ns(repo)) == 0
    assert not any("our-team-notes" in path for path in _lock_paths(repo))
    assert "our-team-notes" not in (repo / ".gitignore").read_text(encoding="utf-8")
    # Written by sync but edited since: no longer pristine, so it is kept.
    # (Edited only now: a rewritten SKILL.md makes the dir the consumer's at
    # the next opted-in sync, which is a different scenario.)
    edited = repo / ".agents" / "skills" / "writing-plans" / "SKILL.md"
    edited.write_text("Our own planning notes.\n", encoding="utf-8")
    _opt_out(repo)
    capsys.readouterr()

    assert _sync.run(_ns(repo)) == 0

    assert "warning:" not in capsys.readouterr().err
    assert notes.read_text(encoding="utf-8") == "How our team brainstorms.\n"
    assert _relative_files(notes.parents[1]) == ["references/our-team-notes.md"]
    assert edited.read_text(encoding="utf-8") == "Our own planning notes.\n"
    assert _relative_files(edited.parent) == ["SKILL.md"]
    for root in (".claude/skills", ".opencode/skills"):
        assert not (repo / root / "writing-plans").exists(), root
    # The edited leftover stays engine-owned (lockfile + managed block); the
    # consumer's file never was.
    assert ".agents/skills/writing-plans/SKILL.md" in _lock_paths(repo)
    gitignore = (repo / ".gitignore").read_text(encoding="utf-8")
    assert "\n/.agents/skills/writing-plans/\n" in gitignore
    assert "our-team-notes" not in gitignore


def _write_override(repo: Path, skill_id: str, references: dict[str, str]) -> None:
    """A repo-local ``playbook/skills/<skill_id>/`` overriding the pack skill."""
    override = repo / "playbook" / "skills" / skill_id
    override.mkdir(parents=True)
    if references:  # an empty mapping ships no references/ dir at all
        (override / "references").mkdir()
    (override / "SKILL.md").write_text(
        f"---\nid: {skill_id}\nname: {skill_id}\n"
        "description: Our house process\n---\nDo it our way.\n",
        encoding="utf-8",
    )
    for name, content in references.items():
        (override / "references" / name).write_text(content, encoding="utf-8")


@needs_git
def test_a_skill_md_only_override_removes_the_pack_scripts_and_references(
    git_pack_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = git_pack_repo
    synced = repo / ".claude" / "skills" / "systematic-debugging"
    assert (synced / "scripts" / "find-polluter.sh").is_file()
    assert (synced / "references" / "root-cause-tracing.md").is_file()
    _write_override(repo, "systematic-debugging", references={})

    assert _sync.run(_ns(repo)) == 0

    for root in NATIVE_SKILL_ROOTS:
        override_out = repo / root / "systematic-debugging"
        assert _relative_files(override_out) == ["SKILL.md"], root
        assert override_out.joinpath("SKILL.md").read_text("utf-8").endswith("Do it our way.\n")
    capsys.readouterr()
    assert _sync.run(_ns(repo, check=True)) == 0, capsys.readouterr().out


@needs_git
def test_an_override_shipping_fewer_references_removes_the_pack_only_files(
    git_pack_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = git_pack_repo
    _write_override(repo, "systematic-debugging", references={"root-cause-tracing.md": "Ours.\n"})

    assert _sync.run(_ns(repo)) == 0

    for root in NATIVE_SKILL_ROOTS:
        override_out = repo / root / "systematic-debugging"
        expected = ["SKILL.md", "references/root-cause-tracing.md"]
        assert _relative_files(override_out) == expected, root
        ours = override_out / "references" / "root-cause-tracing.md"
        assert ours.read_text(encoding="utf-8") == "Ours.\n", root
    capsys.readouterr()
    assert _sync.run(_ns(repo, check=True)) == 0, capsys.readouterr().out


# --- opt-in agent_harness adapter (SPEC §11.5.1) ---------------------------------


@needs_git
def test_agent_harness_renders_the_pack_and_opting_out_removes_it(
    tmp_path: Path, hermetic_git_env: None
) -> None:
    adapters = (*SKILL_ADAPTERS, "agent_harness")
    repo = _init_git_pack_repo(tmp_path, adapters=adapters)

    for skill_id in sorted(EXPECTED_SKILL_IDS):
        harness, claude = (
            _skill_tree(repo / root / skill_id) for root in ("skills", ".claude/skills")
        )
        # The harness SKILL.md has its own frontmatter (no ``id``), but the
        # same sentinel body line and vendored body; everything else is identical.
        _, body = split_frontmatter(harness.pop("SKILL.md").decode("utf-8"))
        assert body == _SENTINEL_BODY_PREFIX + _source_body(skill_id), skill_id
        claude.pop("SKILL.md")
        assert harness == claude, f"skills/{skill_id} differs from .claude/skills/{skill_id}"
        # MIT: the notice travels into the harness copy too.
        assert harness["references/LICENSE"] == (PLUGIN_ROOT / "LICENSE").read_bytes(), skill_id
    manifest = read_manifest(repo)
    assert manifest is not None
    flagged = {
        script.path for entry in manifest.entries for script in entry.scripts if script.executable
    }
    for script in sorted(EXPECTED_SCRIPTS):
        assert os.access(repo / "skills" / script, os.X_OK), script
        assert f"skills/{script}" in flagged, script

    _opt_out(repo, adapters=adapters)
    assert _sync.run(_ns(repo)) == 0

    for root in ("skills", *NATIVE_SKILL_ROOTS):
        assert not _pack_skill_dirs_left(repo, root), root
