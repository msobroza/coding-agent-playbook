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

from coding_agent_playbook.evaluators.execution.project import (
    ProjectHandle,
    default_test_cmd,
    import_roots,
)

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


# --------------------------------------------------------------------------- #
# prK §F.1.1: timeout, environment, interpreter and --cov sources
# --------------------------------------------------------------------------- #


def test_timeout_maps_to_runtime_error(tmp_path: Path) -> None:
    handle = ProjectHandle(
        root=tmp_path,
        test_cmd=[sys.executable, "-c", "import time; time.sleep(30)"],
        report_dir=tmp_path / "reports",
        timeout_s=0.2,
    )

    with pytest.raises(RuntimeError, match=r"timed out after 0\.2s"):
        handle.run()


def test_env_overrides_passed_to_subprocess(tmp_path: Path) -> None:
    """The overrides sit on top of the inherited environment (``PATH`` survives)."""
    out = tmp_path / "env.txt"
    script = (
        "import os, pathlib; "
        "pathlib.Path(os.environ['PLAYBOOK_OUT']).write_text("
        "os.environ['COVERAGE_FILE'] + '|' + str(bool(os.environ.get('PATH'))))"
    )
    handle = ProjectHandle.create(
        tmp_path,
        tmp_path / "reports",
        test_cmd=[sys.executable, "-c", script],
        env_overrides={"PLAYBOOK_OUT": str(out), "COVERAGE_FILE": "/state/.coverage"},
    )

    assert handle.run().returncode == 0
    assert out.read_text(encoding="utf-8") == "/state/.coverage|True"


def test_default_test_cmd_unchanged_without_kwargs(tmp_path: Path) -> None:
    reports = tmp_path / "reports"

    assert default_test_cmd(reports) == [
        sys.executable,
        "-m",
        "pytest",
        f"--junitxml={reports / 'junit.xml'}",
        "--cov",
        f"--cov-report=xml:{reports / 'coverage.xml'}",
        f"--cov-config={reports / 'coveragerc'}",
        "-o",
        "addopts=",
        "-p",
        "no:cacheprovider",
        "-q",
    ]


def test_default_test_cmd_python_and_cov_sources_argv(tmp_path: Path) -> None:
    reports = tmp_path / "reports"

    argv = default_test_cmd(reports, python="/proj/.venv/bin/python", cov_sources=["src", "lib"])

    assert argv[:3] == ["/proj/.venv/bin/python", "-m", "pytest"]
    assert "--cov" not in argv
    assert argv[4:6] == ["--cov=src", "--cov=lib"]
    assert argv[6:] == default_test_cmd(reports)[5:]


def test_create_threads_diff_base_timeout_python_and_sources(tmp_path: Path) -> None:
    handle = ProjectHandle.create(
        tmp_path,
        tmp_path / "reports",
        diff_base="HEAD",
        timeout_s=300.0,
        python="py",
        cov_sources=["src"],
    )

    assert (handle.diff_base, handle.timeout_s, handle.env_overrides) == ("HEAD", 300.0, {})
    assert handle.test_cmd[:5] == ["py", "-m", "pytest", handle.test_cmd[3], "--cov=src"]
    # An explicit command runs exactly as given.
    explicit = ProjectHandle.create(tmp_path, tmp_path / "r2", test_cmd=["make"], python="py")
    assert explicit.test_cmd == ["make"]


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        (["src/pkg/__init__.py"], ("src",)),
        (["src/tool.py"], ("src",)),
        (["pkg/__init__.py", "src/README.md"], (".",)),
        (["mod.py"], (".",)),
    ],
    ids=["src-package", "src-module", "src-without-python", "flat"],
)
def test_import_roots(tmp_path: Path, files: list[str], expected: tuple[str, ...]) -> None:
    for rel in files:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("", encoding="utf-8")

    assert import_roots(tmp_path) == expected
