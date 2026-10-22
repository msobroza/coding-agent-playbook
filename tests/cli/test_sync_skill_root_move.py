"""End-to-end: the shared skill root moves from ``shared_skills/`` to ``.agents/skills/``.

SPEC v0.21 (specs/prS-skills-context.md section 5.6). An engine before v0.21
wrote the ``shared_skills`` adapter's copies to ``shared_skills/<id>/``. The
adapter declares that tree as a retired output location, so the first sync
after an upgrade settles it by the leftover policy (SPEC §4.2 step 9): pristine,
untracked files are deleted and the tree pruned; edited or tracked files are
kept and owned (reported on stderr when tracked, and every kept file under
``commit = true``; an edited, untracked copy gets no notice, spec P1-8); files
no lockfile lists are never touched.

``_rewind_to_shared_skills_root`` turns a repo synced by this engine into the
state the previous engine left: the same bytes, lockfile rows and managed
``.gitignore`` entries, spelled under ``shared_skills/``.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.generated_output.gitignore import (
    BLOCK_END,
    BLOCK_START,
    apply_managed_block,
)
from coding_agent_playbook.sync import pipeline as _sync
from tests._catalog import core_skill_ids
from tests.cli.test_sync_skills import _lock_paths, _skill_tree, _write_repo_local_skill
from tests.fakes import FakeGitClient
from tests.plugins.superpowers_expectations import EXPECTED_SKILL_IDS, PLUGIN_NAME, consumer_config

if TYPE_CHECKING:
    from collections.abc import Callable

    MakeRepo = Callable[..., Path]

_OLD_ROOT = "shared_skills"
_NEW_ROOT = ".agents/skills"
_SKILL_ROOTS = (".claude/skills", ".opencode/skills", _NEW_ROOT)
#: The python-coding members active on the synthetic repo (requires-python >=3.12, no
#: dependencies): every member but python-retries-and-timeouts, which needs an HTTP client.
_SYNTHETIC_PYTHON_CODING_MEMBERS = (
    "python-abstract-inputs",
    "python-async",
    "python-async-fanout",
    "python-async-generators",
    "python-async-tasks",
    "python-classes-and-protocols",
    "python-closures-and-partial",
    "python-comments-why",
    "python-context-managers",
    "python-custom-context-managers",
    "python-custom-exceptions",
    "python-data-shapes",
    "python-dataclass-post-init",
    "python-decorators",
    "python-dependency-injection",
    "python-docstrings",
    "python-early-return",
    "python-enums",
    "python-error-boundaries",
    "python-error-handling",
    "python-error-messages-with-context",
    "python-frozen-dataclasses",
    "python-function-signatures",
    "python-hide-internal-state",
    "python-idioms",
    "python-match-destructuring",
    "python-match-fallback",
    "python-meaningful-names",
    "python-no-global-singletons",
    "python-parameterized-queries",
    "python-performance-idioms",
    "python-properties",
    "python-protocols",
    "python-pure-core",
    "python-small-units",
    "python-type-aliases",
    "python-typing",
)
#: Every file the pre-v0.21 engine left under ``shared_skills/`` for ``_synced_then_rewound``:
#: query-db's two, the core python-coding skill with one rule file per active member and its
#: two upstream license copies (D19), and python-tooling with its one ungated member (no
#: framework, no uv.lock).
_OLD_TREE_FILES = frozenset(
    {
        "query-db/SKILL.md",
        "query-db/scripts/run.py",
        "python-coding/SKILL.md",
        *(f"python-coding/rules/{rule_id}.md" for rule_id in _SYNTHETIC_PYTHON_CODING_MEMBERS),
        "python-coding/references/LICENSE.python-best-practices",
        "python-coding/references/LICENSE.python-clean-architecture",
        "python-tooling/SKILL.md",
        "python-tooling/rules/python-static-checks.md",
    }
)

needs_posix_symlinks = pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")


def _config(
    *,
    adapters: tuple[str, ...] = ("claude_code", "opencode", "shared_skills"),
    overlays: tuple[str, ...] = (),
    commit: bool = False,
) -> str:
    """A committed config text; the adapters default to the v0.21 ``init`` default."""
    base = consumer_config(overlays=list(overlays), adapters=adapters)
    return f"{base}\n[output]\ncommit = {str(commit).lower()}\n"


def _managed_block(repo: Path) -> list[str]:
    """The entries of the managed ``.gitignore`` block; ``[]`` when there is none."""
    gitignore = repo / ".gitignore"
    lines = gitignore.read_text().splitlines() if gitignore.is_file() else []
    if BLOCK_START not in lines:
        return []
    return lines[lines.index(BLOCK_START) + 1 : lines.index(BLOCK_END)]


def _old_spelling(path: str) -> str:
    """``path`` as the previous engine spelled it (``.agents/skills/x`` -> ``shared_skills/x``)."""
    return re.sub(rf"^(/?){re.escape(_NEW_ROOT)}/", rf"\g<1>{_OLD_ROOT}/", path)


def _rewind_to_shared_skills_root(repo: Path) -> None:
    """Leave ``repo`` as an engine before v0.21 synced it: shared skills in ``shared_skills/``."""
    (repo / _OLD_ROOT).mkdir()
    for skill_dir in sorted((repo / _NEW_ROOT).iterdir()):
        shutil.move(skill_dir, repo / _OLD_ROOT / skill_dir.name)
    shutil.rmtree(repo / ".agents")
    state = FileSystemStateSource(repo_root=repo)
    lockfile = state.load_lockfile()
    assert lockfile is not None
    for entry in lockfile.entries:
        entry.path = _old_spelling(entry.path)
    state.save_lockfile(lockfile)
    entries = _managed_block(repo)
    if entries:
        apply_managed_block(repo / ".gitignore", sorted(_old_spelling(e) for e in entries))


def _synced_then_rewound(repo: Path) -> Path:
    """Sync a repo-local ``query-db`` skill, then rewind to the pre-v0.21 root."""
    _write_repo_local_skill(repo, "query-db")
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    _rewind_to_shared_skills_root(repo)
    return repo


def test_first_sync_after_upgrade_moves_pristine_shared_skills_tree(
    tmp_path: Path, make_synthetic_repo: MakeRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _synced_then_rewound(make_synthetic_repo(tmp_path, config_text=_config()))
    old_root = repo / _OLD_ROOT
    old_files = {p.relative_to(old_root).as_posix() for p in old_root.rglob("*") if p.is_file()}
    assert old_files == _OLD_TREE_FILES
    capsys.readouterr()

    assert _sync.execute(repo, git=FakeGitClient()) == 0

    # The move removes the whole pristine old tree, so the removed count is every file in it.
    assert re.search(rf", {len(_OLD_TREE_FILES)} removed$", capsys.readouterr().out, re.MULTILINE)
    assert not (repo / _OLD_ROOT).exists()
    moved = repo / _NEW_ROOT / "query-db"
    assert _skill_tree(moved) == _skill_tree(repo / ".claude" / "skills" / "query-db")
    assert (moved / "SKILL.md").read_bytes() == (
        repo / ".claude" / "skills" / "query-db" / "SKILL.md"
    ).read_bytes()
    assert not [path for path in _lock_paths(repo) if path.startswith(f"{_OLD_ROOT}/")]
    block = _managed_block(repo)
    assert "/.agents/skills/query-db/" in block
    assert not [entry for entry in block if entry.startswith(f"/{_OLD_ROOT}/")]


def test_check_before_the_move_reports_the_old_tree_as_orphans(
    tmp_path: Path, make_synthetic_repo: MakeRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _synced_then_rewound(make_synthetic_repo(tmp_path, config_text=_config()))
    capsys.readouterr()

    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 1

    out = capsys.readouterr().out
    assert "  .agents/skills/query-db/SKILL.md\n    Missing on disk;" in out
    assert "  shared_skills/query-db/SKILL.md\n    Orphaned generated file;" in out
    assert "  .gitignore\n    Managed block is missing or stale" in out
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0


def test_edited_shared_skills_file_is_kept_owned_and_ignored(
    tmp_path: Path, make_synthetic_repo: MakeRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _synced_then_rewound(make_synthetic_repo(tmp_path, config_text=_config()))
    edited = repo / _OLD_ROOT / "query-db" / "scripts" / "run.py"
    edited.write_text("print('edited')\n")
    capsys.readouterr()

    assert _sync.execute(repo, git=FakeGitClient()) == 0

    # P1-8 (no new notice): under commit = false an edited, untracked copy is kept
    # silently, as the README and MIGRATION say; only tracked files are reported.
    assert f"{_OLD_ROOT}/" not in capsys.readouterr().err
    assert edited.read_text() == "print('edited')\n"
    assert not (repo / _OLD_ROOT / "query-db" / "SKILL.md").exists()
    assert f"{_OLD_ROOT}/query-db/scripts/run.py" in _lock_paths(repo)
    assert f"/{_OLD_ROOT}/query-db/scripts/run.py" in _managed_block(repo)
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0


def test_tracked_tree_is_kept_and_reported_under_commit_true(
    tmp_path: Path, make_synthetic_repo: MakeRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _synced_then_rewound(make_synthetic_repo(tmp_path, config_text=_config(commit=True)))
    tracked = {f"{_OLD_ROOT}/query-db/SKILL.md", f"{_OLD_ROOT}/query-db/scripts/run.py"}
    capsys.readouterr()

    assert _sync.execute(repo, git=FakeGitClient(tracked=set(tracked))) == 0

    err = capsys.readouterr().err
    assert "note: kept output" in err
    for rel in sorted(tracked):
        assert (repo / rel).is_file(), rel
        assert rel in err
    assert (repo / _NEW_ROOT / "query-db" / "SKILL.md").is_file()


def test_user_authored_shared_skills_dir_is_never_touched(
    tmp_path: Path, make_synthetic_repo: MakeRepo
) -> None:
    repo = _synced_then_rewound(make_synthetic_repo(tmp_path, config_text=_config()))
    mine = repo / _OLD_ROOT / "mine" / "SKILL.md"
    mine.parent.mkdir()
    mine.write_bytes(b"---\nname: mine\ndescription: hand-written\n---\nmine\n")

    assert _sync.execute(repo, git=FakeGitClient()) == 0

    assert mine.read_bytes() == b"---\nname: mine\ndescription: hand-written\n---\nmine\n"
    assert not (repo / _OLD_ROOT / "query-db").exists()
    assert not [entry for entry in _managed_block(repo) if entry.startswith(f"/{_OLD_ROOT}/")]


def test_sync_writes_no_loose_file_at_any_skill_root(
    tmp_path: Path, make_synthetic_repo: MakeRepo
) -> None:
    """OpenCode v2 loads any root-level ``*.md`` in a skill root as a skill (section 5.4.5)."""
    adapters = ("claude_code", "opencode", "shared_skills", "continue")
    config = _config(adapters=adapters, overlays=(PLUGIN_NAME,))
    repo = make_synthetic_repo(tmp_path, config_text=config)
    _write_repo_local_skill(repo, "query-db")

    assert _sync.execute(repo, git=FakeGitClient()) == 0

    for root in _SKILL_ROOTS:
        children = sorted((repo / root).iterdir())
        assert all(child.is_dir() for child in children), root
        # query-db + the superpowers skills, next to the core skills that apply here.
        not_core = {c.name for c in children if c.name not in core_skill_ids()}
        assert not_core == {"query-db", *EXPECTED_SKILL_IDS}, root
    for path in _lock_paths(repo):
        for root in _SKILL_ROOTS:
            below = Path(path).relative_to(root).parts if path.startswith(f"{root}/") else ()
            assert len(below) != 1, path


@needs_posix_symlinks
def test_agents_skills_linked_to_claude_skills_survives_removing_every_skill(
    tmp_path: Path, make_synthetic_repo: MakeRepo
) -> None:
    """Regression (section 5.4.3): ``.claude/skills`` was pruned through the link and dangled."""
    repo = make_synthetic_repo(tmp_path, config_text=_config())
    (repo / ".claude" / "skills").mkdir(parents=True)
    (repo / ".agents").mkdir()
    (repo / _NEW_ROOT).symlink_to("../.claude/skills", target_is_directory=True)
    source = _write_repo_local_skill(repo, "query-db")
    git = FakeGitClient()
    assert _sync.execute(repo, git=git) == 0
    assert _sync.execute(repo, check=True, git=git) == 0

    shutil.rmtree(source)
    assert _sync.execute(repo, git=git) == 0

    claude_skills = repo / ".claude" / "skills"
    assert claude_skills.is_dir() and not claude_skills.is_symlink()
    assert (repo / _NEW_ROOT).resolve() == claude_skills.resolve()
    assert _sync.execute(repo, check=True, git=git) == 0


@needs_posix_symlinks
def test_claude_skills_linked_to_agents_skills_has_one_lock_row_per_file(
    tmp_path: Path, make_synthetic_repo: MakeRepo
) -> None:
    """``claude_code`` and ``shared_skills`` write the same physical files: one row each."""
    repo = make_synthetic_repo(tmp_path, config_text=_config())
    (repo / _NEW_ROOT).mkdir(parents=True)
    (repo / ".claude").mkdir()
    (repo / ".claude" / "skills").symlink_to("../.agents/skills", target_is_directory=True)
    _write_repo_local_skill(repo, "query-db")
    git = FakeGitClient()

    assert _sync.execute(repo, git=git) == 0

    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    rows = [entry.path for entry in lockfile.entries]
    for rel in ("SKILL.md", "scripts/run.py"):
        assert rows.count(f"{_NEW_ROOT}/query-db/{rel}") == 1, rel
    assert not [row for row in rows if row.startswith(".claude/skills/")]
    assert _sync.execute(repo, check=True, git=git) == 0
    assert _sync.execute(repo, check_staged=True, git=FakeGitClient(staged=[])) == 0
