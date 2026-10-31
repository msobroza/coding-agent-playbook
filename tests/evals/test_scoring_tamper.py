"""Regression tests: an agent cannot game scoring by editing what scoring trusts.

Each test stands an agent in with a :class:`FakeRunner` mutation that edits the
candidate tree and then reaches for the grading inputs: the ``setup/`` baseline
that ``file_unchanged`` and the baseline suite compare against.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from coding_agent_playbook.evals.run.fake_runner import FakeRunner
from coding_agent_playbook.evals.run.harness_runner import materialize
from tests.evals.test_harness_runner import (
    _REFACTORED,
    _TEST_OK,
    _check,
    _make_sample,
    _make_setup,
)

if TYPE_CHECKING:
    from pathlib import Path

#: Where materialize used to keep its writable baseline copy, beside the agent's cwd.
_OLD_SNAPSHOT_SUFFIX = "__setup_baseline"


def _unchanged_and_green_gate() -> dict[str, Any]:
    """``mod.py`` must stay as ``setup/`` has it, and every test must pass."""
    return {
        "expr": "src_unchanged and suite_green",
        "bind": {
            "src_unchanged": {"check": "file_unchanged", "path": "mod.py"},
            "suite_green": {"check": "tests_pass"},
        },
    }


def _old_snapshot(scratch: Path) -> Path:
    """The sibling directory the old baseline snapshot lived in."""
    return scratch.parent / f"{scratch.name}{_OLD_SNAPSHOT_SUFFIX}"


def test_an_agent_that_edits_the_baseline_snapshot_still_fails_file_unchanged(
    tmp_path: Path,
) -> None:
    """Regression: the baseline snapshot sat beside the agent's cwd, so editing both passed."""

    def _edit_both(scratch: Path) -> None:
        (scratch / "mod.py").write_text(_REFACTORED, encoding="utf-8")
        snapshot = _old_snapshot(scratch)
        snapshot.mkdir(parents=True, exist_ok=True)
        (snapshot / "mod.py").write_text(_REFACTORED, encoding="utf-8")

    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_unchanged_and_green_gate())

    result = FakeRunner(_edit_both).run_sample(sample, tmp_path / "scratch")

    assert _check(result.report, "file_unchanged:mod.py").passed is False
    assert result.passed is False


def test_an_agent_that_poisons_the_baseline_suite_leaves_the_sample_scorable(
    tmp_path: Path,
) -> None:
    """Regression: a ``conftest.py`` planted in the snapshot made every trial unscorable."""

    def _poison(scratch: Path) -> None:
        (scratch / "test_more.py").write_text(_TEST_OK, encoding="utf-8")
        snapshot = _old_snapshot(scratch)
        snapshot.mkdir(parents=True, exist_ok=True)
        (snapshot / "conftest.py").write_text("raise SystemExit\n", encoding="utf-8")

    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    gate = {"expr": "suite_green", "bind": {"suite_green": {"check": "tests_pass"}}}
    sample = _make_sample(sample_dir, gate=gate)

    result = FakeRunner(_poison).run_sample(sample, tmp_path / "scratch")

    assert result.passed is True


def test_materialize_builds_no_baseline_copy_beside_the_scratch_repo(tmp_path: Path) -> None:
    """The baseline is the catalog ``setup/``; no agent-reachable copy is made."""
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_unchanged_and_green_gate())
    scratch = tmp_path / "scratch"

    materialize(sample, scratch)

    assert not _old_snapshot(scratch).exists()
