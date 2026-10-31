"""Regression tests: an agent cannot game scoring by editing what scoring trusts.

Each test stands an agent in with a :class:`FakeRunner` mutation that edits the
candidate tree and then reaches for the grading inputs: the ``setup/`` baseline
that ``file_unchanged`` and the baseline suite compare against, or the files the
file checks read, which the scoring suite runs agent code beside. The agent and
its suite run as the engine's user, so the catalog ``setup/`` and the engine's
temp dirs are writable to them.
"""

from __future__ import annotations

import os
import tempfile
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.evals.run.fake_runner import FakeRunner, write_files
from coding_agent_playbook.evals.run.harness_runner import materialize
from coding_agent_playbook.evals.sample import EvalSample
from coding_agent_playbook.exit_two import ExitTwoError
from coding_agent_playbook.grading.execution_metrics.project import ProjectHandle
from tests.evals.test_harness_runner import (
    _LONG_FN,
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


def _restore_conftest(rel: str, original: str) -> str:
    """A ``conftest.py`` that writes ``original`` back to ``rel`` once the session ends."""
    return (
        "from pathlib import Path\n\n\n"
        "def pytest_sessionfinish(session, exitstatus):\n"
        f"    (Path(__file__).parent / {rel!r}).write_text({original!r}, encoding='utf-8')\n"
    )


def test_a_suite_that_restores_an_edited_file_fails_file_unchanged(tmp_path: Path) -> None:
    """Regression: file checks graded the tree after the suite, which had put the bytes back."""
    files = {
        "mod.py": _REFACTORED,
        "test_refactor.py": _TEST_OK,
        "conftest.py": _restore_conftest("mod.py", _LONG_FN),
    }
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_unchanged_and_green_gate())

    result = FakeRunner(write_files(files)).run_sample(sample, tmp_path / "scratch")

    unchanged = _check(result.report, "file_unchanged:mod.py")
    assert (unchanged.passed, unchanged.status) == (False, "run")
    assert result.passed is False


def test_file_checks_ignore_files_the_suite_creates(tmp_path: Path) -> None:
    """A file a test writes during the suite is not one the agent left behind."""
    writer = (
        "from pathlib import Path\n\n\n"
        "def test_writes():\n"
        "    (Path(__file__).parent / 'out.txt').write_text('made by the suite')\n"
    )
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    gate = {
        "expr": "made and suite_green",
        "bind": {
            "made": {"check": "file_exists", "path": "out.txt"},
            "suite_green": {"check": "tests_pass"},
        },
    }
    sample = _make_sample(sample_dir, gate=gate)

    result = FakeRunner(write_files({"test_out.py": writer})).run_sample(
        sample, tmp_path / "scratch"
    )

    assert _check(result.report, "file_exists:out.txt").passed is False
    assert (tmp_path / "scratch" / "out.txt").is_file()  # the suite did write it


@pytest.fixture
def private_tmpdir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A temp dir of this test's own, for the engine and its suite alike.

    Why: the conftests below glob the temp dir for the engine's dirs, and under
    ``-n`` the shared one holds other tests' trees too.
    """
    private = tmp_path / "tmp"
    private.mkdir()
    monkeypatch.setenv("TMPDIR", str(private))
    monkeypatch.setattr(tempfile, "tempdir", str(private))
    return private


def _glob_writer_conftest(pattern: str, rel: str, text: str) -> str:
    """A ``conftest.py`` that writes ``text`` to ``rel`` in every temp dir matching ``pattern``."""
    return (
        "import glob, os, tempfile\n"
        f"for d in glob.glob(os.path.join(tempfile.gettempdir(), {pattern!r})):\n"
        f"    with open(os.path.join(d, {rel!r}), 'w') as fh:\n"
        f"        fh.write({text!r})\n"
    )


def test_a_suite_that_rewrites_the_frozen_file_inputs_still_fails_file_unchanged(
    private_tmpdir: Path, tmp_path: Path
) -> None:
    """Regression: the frozen copy sat in ``$TMPDIR/playbook-eval-graded-*/tree`` during the suite.

    A ``conftest.py`` wrote the original bytes into it, so ``file_unchanged``
    graded the forgery and passed.
    """
    files = {
        "test_mod.py": "def test_other():\n    pass\n",
        "conftest.py": _glob_writer_conftest(
            "playbook-eval-graded-*/tree", "test_mod.py", _TEST_OK
        ),
    }
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    gate = {
        "expr": "same and suite_green",
        "bind": {
            "same": {"check": "file_unchanged", "path": "test_mod.py"},
            "suite_green": {"check": "tests_pass"},
        },
    }
    sample = _make_sample(sample_dir, gate=gate)

    result = FakeRunner(write_files(files)).run_sample(sample, tmp_path / "scratch")

    assert _check(result.report, "file_unchanged:test_mod.py").passed is False
    assert result.passed is False


def test_a_suite_that_blanks_the_frozen_test_files_is_still_caught_by_rule_4(
    private_tmpdir: Path, tmp_path: Path
) -> None:
    """Regression: rule 4 read ``$TMPDIR/playbook-eval-tests-*/tree``, which the suite could blank.

    A test file that the conftest kept from collection then defined no tests.
    """
    conftest = "collect_ignore = ['test_hidden.py']\n" + _glob_writer_conftest(
        "playbook-eval-tests-*/tree", "test_hidden.py", ""
    )
    files = {
        "mod.py": _REFACTORED,
        "test_hidden.py": "def test_hidden():\n    assert False\n",
        "conftest.py": conftest,
    }
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    gate = {"expr": "suite_green", "bind": {"suite_green": {"check": "tests_pass"}}}
    sample = _make_sample(sample_dir, gate=gate)

    result = FakeRunner(write_files(files)).run_sample(sample, tmp_path / "scratch")

    check = _check(result.report, "threshold:test_pass_rate")
    assert check.passed is False
    assert "test file(s) define tests that never ran: test_hidden.py" in check.detail
    assert result.passed is False


# --------------------------------------------------------------------------- #
# The catalog setup/ baseline: read once before any agent, never trusted after
# --------------------------------------------------------------------------- #


def _tree_bytes(root: Path) -> dict[str, bytes]:
    """Every entry under ``root``, hidden ones included: a file's bytes, a directory's ``b"/"``."""
    return {
        path.relative_to(root).as_posix(): b"/" if path.is_dir() else path.read_bytes()
        for path in sorted(root.rglob("*"))
    }


def _three_trial_sample(sample_dir: Path) -> EvalSample:
    """A ``tests_pass`` sample whose ``[aggregate]`` runs three trials."""
    data: dict[str, Any] = {
        "id": "t-three",
        "description": "three trials",
        "verdict": {"trial": "gate"},
        "gate": {"expr": "suite_green", "bind": {"suite_green": {"check": "tests_pass"}}},
        "aggregate": {
            "expr": "rel",
            "bind": {"rel": {"metric": "pass_pow_k", "k": 3, "over": "verdict", "fail": 0.5}},
        },
    }
    return EvalSample.from_dict(
        data, source_path=sample_dir / "sample.toml", prompt_id="refactor", source_package="<test>"
    )


def _record_suite_roots(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Every root a scoring suite runs in, in order (the real run still happens)."""
    roots: list[Path] = []
    real = ProjectHandle._run_once

    def _spy(self: ProjectHandle) -> Any:
        roots.append(self.root)
        return real(self)

    monkeypatch.setattr(ProjectHandle, "_run_once", _spy)
    return roots


def _refactor(scratch: Path) -> None:
    (scratch / "mod.py").write_text(_REFACTORED, encoding="utf-8")


def test_the_baseline_suite_runs_once_per_sample_before_any_agent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: the baseline suite ran per trial, in a copy made after the candidate's suite.

    A process the candidate's suite left behind could rewrite that copy before the
    baseline suite ran in it (a skip there exempted the candidate's own skip), and
    every trial paid one more suite run.
    """
    roots = _record_suite_roots(monkeypatch)
    suites_before_each_agent: list[int] = []

    def _agent(scratch: Path) -> None:
        suites_before_each_agent.append(len(roots))
        _refactor(scratch)

    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    scratch = tmp_path / "scratch"
    result = FakeRunner(_agent).run_sample(_three_trial_sample(sample_dir), scratch)

    assert result.passed is True
    assert suites_before_each_agent == [1, 2, 3]
    assert [root.is_relative_to(scratch) for root in roots] == [False, True, True, True]


def test_run_sample_leaves_the_catalog_setup_byte_and_file_identical(tmp_path: Path) -> None:
    """No ``__pycache__``, ``.pytest_cache`` or ``.coverage`` reaches the catalog ``setup/``."""
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    before = _tree_bytes(sample_dir)

    FakeRunner(_refactor).run_sample(_three_trial_sample(sample_dir), tmp_path / "scratch")

    assert _tree_bytes(sample_dir) == before


def _catalog_writer_conftest(rel: str) -> str:
    """A ``conftest.py`` that copies its tree's ``rel`` over the catalog ``setup/``'s."""
    return (
        "import pathlib, shutil\n"
        "here = pathlib.Path(__file__).parent\n"
        "for parent in here.parents:\n"
        "    setup = parent / 'sample' / 'setup'\n"
        "    if setup.is_dir():\n"
        f"        shutil.copyfile(here / {rel!r}, setup / {rel!r})\n"
        "        break\n"
    )


def _same_and_green_gate(path: str) -> dict[str, Any]:
    return {
        "expr": "same and suite_green",
        "bind": {
            "same": {"check": "file_unchanged", "path": path},
            "suite_green": {"check": "tests_pass"},
        },
    }


def test_a_suite_that_writes_the_catalog_setup_makes_the_sample_unscorable(
    tmp_path: Path,
) -> None:
    """Regression: the suite rewrote the catalog ``setup/``, so ``file_unchanged`` compared edits.

    The baseline suite then ran the poisoned files, and the user's checkout was
    left dirty for every later trial and sample.
    """
    files = {
        "test_mod.py": "def test_other():\n    pass\n",
        "conftest.py": _catalog_writer_conftest("test_mod.py"),
    }
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, gate=_same_and_green_gate("test_mod.py"))

    with pytest.raises(ExitTwoError) as raised:
        FakeRunner(write_files(files)).run_sample(sample, tmp_path / "scratch")

    assert type(raised.value).__name__ == "CatalogSetupChangedError"
    message = str(raised.value)
    assert f"of t-fixture ({sample_dir / 'setup'})" in message
    assert "first at test_mod.py" in message and "git checkout" in message


def test_file_unchanged_grades_the_setup_read_before_the_agent_ran(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With the catalog check off, an edited catalog still never becomes the baseline."""
    monkeypatch.setattr(
        "coding_agent_playbook.evals.run.scoring.require_catalog_unchanged",
        lambda _baseline: None,
        raising=False,
    )
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    gate = {"expr": "same", "bind": {"same": {"check": "file_unchanged", "path": "mod.py"}}}
    sample = _make_sample(sample_dir, gate=gate)

    def _edit_both(scratch: Path) -> None:
        _refactor(scratch)
        (sample_dir / "setup" / "mod.py").write_text(_REFACTORED, encoding="utf-8")

    result = FakeRunner(_edit_both).run_sample(sample, tmp_path / "scratch")

    assert _check(result.report, "file_unchanged:mod.py").passed is False
    assert result.passed is False


def test_an_agent_that_writes_the_catalog_setup_makes_the_sample_unscorable(
    tmp_path: Path,
) -> None:
    """The agent itself can run Python: a write during its run stops the sample, suite or not."""
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    gate = {"expr": "same", "bind": {"same": {"check": "file_unchanged", "path": "mod.py"}}}
    sample = _make_sample(sample_dir, gate=gate)

    def _remove_from_catalog(scratch: Path) -> None:
        os.remove(sample_dir / "setup" / "mod.py")

    with pytest.raises(ExitTwoError, match=r"first at mod\.py") as raised:
        FakeRunner(_remove_from_catalog).run_sample(sample, tmp_path / "scratch")
    assert type(raised.value).__name__ == "CatalogSetupChangedError"
