"""Tests for :class:`ProjectHandle` — the one-run, caching test runner (M4).

These spin up a tiny project in ``tmp_path`` and actually run the inner pytest in
a subprocess (the realistic path), so they are slower than the pure-parser tests
but still small. The inner pytest is isolated from this repo's own
``pyproject.toml`` (no ``--cov-fail-under``, no ``filterwarnings=error``) by the
handle's command construction + ``rootdir`` pinning.
"""

from __future__ import annotations

import sys
import textwrap
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evaluators.execution.project import ProjectHandle

if TYPE_CHECKING:
    from pathlib import Path

# A minimal package + a passing test that exercises one of two branches, giving
# a known, stable coverage figure for ``mod.py``.
_MOD = textwrap.dedent(
    """\
    def add(a, b):
        return a + b


    def sub(a, b):
        return a - b
    """
)

_TEST_PASS = textwrap.dedent(
    """\
    from mod import add


    def test_add():
        assert add(1, 2) == 3
    """
)

_TEST_FAIL = textwrap.dedent(
    """\
    from mod import add


    def test_add_ok():
        assert add(1, 2) == 3


    def test_add_broken():
        assert add(1, 2) == 99
    """
)


def _make_project(root: Path, test_source: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "mod.py").write_text(_MOD, encoding="utf-8")
    (root / "test_mod.py").write_text(test_source, encoding="utf-8")


def test_run_passing_suite_reports_all_passed(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    _make_project(root, _TEST_PASS)
    handle = ProjectHandle.create(root, tmp_path / "reports")
    artifacts = handle.run()
    assert artifacts.returncode == 0
    assert artifacts.junit.total == 1
    assert artifacts.junit.passed == 1
    assert artifacts.junit.pass_rate() == 1.0
    # mod.py coverage is known: add() is hit, sub() is not -> partial.
    assert "mod.py" in artifacts.coverage.per_file
    assert 0.0 < artifacts.coverage.per_file["mod.py"] < 100.0


def test_run_failing_suite_nonzero_and_failure_counted(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    _make_project(root, _TEST_FAIL)
    handle = ProjectHandle.create(root, tmp_path / "reports")
    artifacts = handle.run()
    assert artifacts.returncode != 0
    assert artifacts.junit.total == 2
    assert artifacts.junit.failed == 1
    assert artifacts.junit.pass_rate() == 0.5


def test_run_is_cached_single_subprocess(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling ``run()`` twice executes the suite exactly once (cached)."""
    root = tmp_path / "proj"
    _make_project(root, _TEST_PASS)
    handle = ProjectHandle.create(root, tmp_path / "reports")

    import subprocess as _subprocess
    from typing import Any

    calls = {"n": 0}
    real_run = _subprocess.run

    def _counting_run(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        return real_run(*args, **kwargs)

    monkeypatch.setattr(
        "coding_agent_playbook.evaluators.execution.project.subprocess.run",
        _counting_run,
    )
    first = handle.run()
    second = handle.run()
    assert first is second
    assert calls["n"] == 1


def test_missing_pytest_raises_clear_error(tmp_path: Path) -> None:
    """A test command whose program is not runnable surfaces a clear error."""
    root = tmp_path / "proj"
    _make_project(root, _TEST_PASS)
    handle = ProjectHandle(
        root=root,
        test_cmd=["definitely-not-a-real-program-xyz", "--version"],
        report_dir=tmp_path / "reports",
    )
    with pytest.raises(RuntimeError) as exc:
        handle.run()
    assert "pytest" in str(exc.value).lower() or "run" in str(exc.value).lower()


def test_default_command_includes_junit_and_cov(tmp_path: Path) -> None:
    handle = ProjectHandle.create(tmp_path / "proj", tmp_path / "reports")
    joined = " ".join(handle.test_cmd)
    assert "pytest" in joined
    assert "--junitxml" in joined
    assert "--cov" in joined


def test_nonzero_exit_without_junit_raises(tmp_path: Path) -> None:
    """A command that launches but exits non-zero writing *no* junit (e.g. a
    collection crash) is a runtime error, not silently treated as all-passed.

    This also exercises the empty-report fallbacks in ``_read_junit`` /
    ``_read_coverage`` (no XML files written).
    """
    root = tmp_path / "proj"
    root.mkdir()
    handle = ProjectHandle(
        root=root,
        test_cmd=[sys.executable, "-c", "import sys; sys.exit(2)"],
        report_dir=tmp_path / "reports",
    )
    with pytest.raises(RuntimeError) as exc:
        handle.run()
    assert "runnable" in str(exc.value).lower() or "no junit" in str(exc.value).lower()


def test_no_tests_collected_exit5_is_not_an_error(tmp_path: Path) -> None:
    """Exit code 5 (pytest: no tests collected) yields an empty, valid result
    (pass rate 1.0), not a runtime error."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "mod.py").write_text(_MOD, encoding="utf-8")  # module, but no tests
    handle = ProjectHandle.create(root, tmp_path / "reports")
    artifacts = handle.run()
    assert artifacts.junit.total == 0
    assert artifacts.junit.pass_rate() == 1.0
