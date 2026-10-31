"""Unit tests of the ``setup/`` snapshot and of the scratch repo written from it.

The end-to-end regressions (the catalog written by the agent or its suite, the
baseline suite run once before any agent) are in ``test_scoring_tamper.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.run.harness_runner import materialize
from coding_agent_playbook.evals.run.scoring_suite import UnscorableSuiteError
from coding_agent_playbook.evals.run.setup_baseline import (
    CatalogSetupChangedError,
    SetupBaseline,
    UnexpectedSetupEntryError,
    first_setup_change,
    require_catalog_unchanged,
    take_setup_snapshot,
)
from tests.evals.test_harness_runner import _make_sample, _make_setup

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def _tree_bytes(root: Path) -> dict[str, bytes]:
    """Every entry under ``root``, hidden ones included: a file's bytes, a directory's ``b"/"``."""
    found: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        found[rel] = b"/" if path.is_dir() else path.read_bytes()
    return found


# --------------------------------------------------------------------------- #
# take_setup_snapshot / first_setup_change
# --------------------------------------------------------------------------- #


def test_a_snapshot_holds_every_regular_file_by_relative_path(tmp_path: Path) -> None:
    setup = tmp_path / "setup"
    (setup / "pkg").mkdir(parents=True)
    (setup / "mod.py").write_bytes(b"a")
    (setup / "pkg" / "b.py").write_bytes(b"b")
    (setup / ".hidden").write_bytes(b"h")

    snapshot = take_setup_snapshot(setup)

    assert dict(snapshot.files) == {".hidden": b"h", "mod.py": b"a", "pkg/b.py": b"b"}
    assert snapshot.digest == take_setup_snapshot(setup).digest


def test_a_missing_setup_dir_gives_an_empty_snapshot(tmp_path: Path) -> None:
    snapshot = take_setup_snapshot(tmp_path / "absent")

    assert dict(snapshot.files) == {}
    assert snapshot.digest == take_setup_snapshot(tmp_path / "also-absent").digest


def test_a_symlink_in_setup_is_refused_by_name(tmp_path: Path) -> None:
    setup = tmp_path / "setup"
    setup.mkdir()
    (setup / "link.py").symlink_to(tmp_path / "elsewhere.py")

    with pytest.raises(UnexpectedSetupEntryError, match=r"link\.py in setup/ is neither") as raised:
        take_setup_snapshot(setup)
    assert raised.value.rel_path == "link.py"
    assert isinstance(raised.value, ValueError)


def test_the_snapshot_writes_the_same_files_back(tmp_path: Path) -> None:
    setup = tmp_path / "setup"
    (setup / "pkg").mkdir(parents=True)
    (setup / "pkg" / "b.py").write_bytes(b"b")

    written = take_setup_snapshot(setup).write_tree(tmp_path / "copy")

    assert _tree_bytes(written) == _tree_bytes(setup)


@pytest.mark.parametrize(
    ("edit", "expected"),
    [
        (lambda s: (s / "mod.py").write_bytes(b"edited"), "mod.py"),
        (lambda s: (s / "new.py").write_bytes(b"new"), "new.py"),
        (lambda s: (s / "test_mod.py").unlink(), "test_mod.py"),
        (lambda s: (s / "aa.py").symlink_to(s / "mod.py"), "aa.py"),
        (lambda s: None, None),
    ],
    ids=["rewritten", "added", "removed", "symlink", "unchanged"],
)
def test_first_setup_change_names_the_first_changed_path(
    tmp_path: Path, edit: Callable[[Path], object], expected: str | None
) -> None:
    _make_setup(tmp_path)
    setup = tmp_path / "setup"
    snapshot = take_setup_snapshot(setup)

    edit(setup)

    assert first_setup_change(snapshot, setup) == expected


# --------------------------------------------------------------------------- #
# materialize builds the scratch repo from the snapshot
# --------------------------------------------------------------------------- #


def test_materialize_builds_the_scratch_repo_from_the_snapshot(tmp_path: Path) -> None:
    """Every trial starts from the bytes read before any agent ran, not the live catalog."""
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir)
    snapshot = take_setup_snapshot(sample.setup_dir)
    (sample.setup_dir / "mod.py").write_text("edited after the snapshot\n", encoding="utf-8")
    (sample.setup_dir / "planted.py").write_text("x = 1\n", encoding="utf-8")

    baseline = materialize(sample, tmp_path / "scratch", snapshot=snapshot)

    scratch = {k: v for k, v in _tree_bytes(baseline.repo_root).items() if not k.startswith(".git")}
    assert scratch == dict(snapshot.files)


def test_a_changed_catalog_setup_is_unscorable_naming_the_sample_and_path(tmp_path: Path) -> None:
    _make_setup(tmp_path)
    setup = tmp_path / "setup"
    baseline = SetupBaseline("t-x", setup, take_setup_snapshot(setup))
    require_catalog_unchanged(baseline)
    (setup / "test_mod.py").write_text("edited\n", encoding="utf-8")

    with pytest.raises(CatalogSetupChangedError, match=r"of t-x .* first at test_mod\.py"):
        require_catalog_unchanged(baseline)
    assert issubclass(CatalogSetupChangedError, UnscorableSuiteError)
