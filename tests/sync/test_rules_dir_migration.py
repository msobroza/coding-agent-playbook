"""Member rules move from ``<skill>/references/<id>.md`` to ``<skill>/rules/<id>.md`` (prU D5).

ADR 0005: the rendered skill gets the source's ``rules/`` directory and
``references/`` is left to free-form documents. An engine before prU wrote each
member rule as ``<root>/<skill>/references/<id>.md`` (lockfile ``kind = rule``).
The first sync after the upgrade writes ``rules/<id>.md`` and settles the old
copies through the lockfile leftover policy (SPEC §4.2 step 9): pristine copies
are deleted, an edited copy is kept and owned like any other leftover.

``_rewind_to_references_layout`` turns a repo synced by this engine into the
state the previous engine left: the same member bytes and lockfile rows, spelled
under ``references/``.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.sync import pipeline as _sync
from tests._catalog import CORE_SKILLS_ROOT
from tests.fakes import FakeGitClient
from tests.plugins.superpowers_expectations import consumer_config

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest

    MakeRepo = Callable[..., Path]

_SKILL_ROOTS = (".claude/skills", ".opencode/skills", ".agents/skills")
_SKILL = "python-coding"
_EDITED_MEMBER = "python-typing"


def _config(*, commit: bool = False) -> str:
    base = consumer_config(overlays=[], adapters=("claude_code", "opencode", "shared_skills"))
    return f"{base}\n[output]\ncommit = {str(commit).lower()}\n"


def _rule_rows(repo: Path) -> dict[str, str]:
    """``{lockfile path: kind}`` for every row under a skill root."""
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    return {
        entry.path: entry.kind
        for entry in lockfile.entries
        if entry.path.startswith(tuple(f"{root}/" for root in _SKILL_ROOTS))
    }


def _old_spelling(path: str) -> str:
    """``.claude/skills/s/rules/x.md`` -> ``.claude/skills/s/references/x.md``."""
    return path.replace("/rules/", "/references/", 1)


def _move_rules_dir_back(rules_dir: Path) -> None:
    """Move every file of a skill's ``rules/`` into its ``references/``, then drop ``rules/``."""
    old_dir = rules_dir.parent / "references"
    old_dir.mkdir(exist_ok=True)
    for member in sorted(rules_dir.iterdir()):
        shutil.move(member, old_dir / member.name)
    rules_dir.rmdir()


def _rewind_to_references_layout(repo: Path) -> None:
    """Leave ``repo`` as an engine before prU synced it: members under ``references/``."""
    for root in _SKILL_ROOTS:
        for rules_dir in sorted((repo / root).glob("*/rules")):
            _move_rules_dir_back(rules_dir)
    state = FileSystemStateSource(repo_root=repo)
    lockfile = state.load_lockfile()
    assert lockfile is not None
    for entry in lockfile.entries:
        if entry.kind == "rule" and "/rules/" in entry.path:
            entry.path = _old_spelling(entry.path)
    state.save_lockfile(lockfile)


def _synced_then_rewound(repo: Path) -> tuple[Path, set[str]]:
    """Sync, record the member rows, then rewind to the old layout."""
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    members = {path for path, kind in _rule_rows(repo).items() if kind == "rule"}
    assert members, "the synthetic repo must activate at least one member rule"
    _rewind_to_references_layout(repo)
    return repo, members


def test_resync_moves_pristine_member_copies_to_rules(
    tmp_path: Path, make_synthetic_repo: MakeRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, members = _synced_then_rewound(make_synthetic_repo(tmp_path, config_text=_config()))
    assert all("/rules/" in path for path in members)
    capsys.readouterr()

    assert _sync.execute(repo, git=FakeGitClient()) == 0

    rows = _rule_rows(repo)
    assert {path for path, kind in rows.items() if kind == "rule"} == members
    for path in members:
        assert (repo / path).is_file(), path
        assert not (repo / _old_spelling(path)).exists(), path
    assert not [path for path, kind in rows.items() if "/references/" in path and kind == "rule"]
    # No member copy stays in references/: it holds exactly the files the catalog
    # skill ships there (today its license copies).
    shipped = sorted(p.name for p in (CORE_SKILLS_ROOT / _SKILL / "references").iterdir())
    assert shipped, "the catalog skill ships its license copies under references/"
    for root in _SKILL_ROOTS:
        left = sorted(p.name for p in (repo / root / _SKILL / "references").iterdir())
        assert left == shipped, root
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0


def test_edited_old_member_copy_is_kept_and_reported_under_commit_true(
    tmp_path: Path, make_synthetic_repo: MakeRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, _ = _synced_then_rewound(make_synthetic_repo(tmp_path, config_text=_config(commit=True)))
    edited_rel = f".claude/skills/{_SKILL}/references/{_EDITED_MEMBER}.md"
    edited = repo / edited_rel
    edited.write_text("# my notes\n", encoding="utf-8")
    capsys.readouterr()

    assert _sync.execute(repo, git=FakeGitClient()) == 0

    err = capsys.readouterr().err
    assert "note: kept output" in err
    assert edited_rel in err
    assert edited.read_text(encoding="utf-8") == "# my notes\n"
    assert (repo / f".claude/skills/{_SKILL}/rules/{_EDITED_MEMBER}.md").is_file()
    pristine = repo / f".opencode/skills/{_SKILL}/references/{_EDITED_MEMBER}.md"
    assert not pristine.exists()
    assert edited_rel in _rule_rows(repo)
