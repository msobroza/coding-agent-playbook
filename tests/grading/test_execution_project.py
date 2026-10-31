"""Tests for :class:`ProjectHandle` — the one-run, caching test runner (M4).

These spin up a tiny project in ``tmp_path`` and actually run the inner pytest in
a subprocess (the realistic path), so they are slower than the pure-parser tests
but still small. The inner pytest is isolated from this repo's own
``pyproject.toml`` (no ``--cov-fail-under``, no ``filterwarnings=error``) by the
handle's command construction + ``rootdir`` pinning.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import textwrap
import time
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.grading.execution_metrics.project import (
    NoSuiteResultError,
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

    calls = {"n": 0}
    real_popen = _subprocess.Popen

    def _counting_popen(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(
        "coding_agent_playbook.grading.execution_metrics.project.subprocess.Popen",
        _counting_popen,
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


@pytest.mark.parametrize(
    ("script", "timeout_s", "reason"),
    [
        ("import time; time.sleep(30)", 0.2, "it timed out after 0.2 s"),
        ("import sys; sys.exit(4)", None, "it exited 4 with no junit report"),
    ],
    ids=["timed-out", "no-junit-report"],
)
def test_a_suite_that_gives_no_result_raises_no_suite_result_error(
    tmp_path: Path, script: str, timeout_s: float | None, reason: str
) -> None:
    """Eval scoring fails every execution check on this error, quoting its ``reason``."""
    handle = ProjectHandle(
        root=tmp_path,
        test_cmd=[sys.executable, "-c", script],
        report_dir=tmp_path / "reports",
        timeout_s=timeout_s,
    )

    with pytest.raises(NoSuiteResultError) as excinfo:
        handle.run()
    assert excinfo.value.reason == reason


def test_a_command_that_cannot_start_is_not_a_no_result_error(tmp_path: Path) -> None:
    """A missing program is the environment's fault, not the suite's: a plain ``RuntimeError``."""
    handle = ProjectHandle(
        root=tmp_path,
        test_cmd=["definitely-not-a-real-program-xyz"],
        report_dir=tmp_path / "reports",
    )

    with pytest.raises(RuntimeError) as excinfo:
        handle.run()
    assert not isinstance(excinfo.value, NoSuiteResultError)


def test_the_default_command_must_leave_a_junit_report_whatever_its_exit_code(
    tmp_path: Path,
) -> None:
    """Regression: an ``os._exit(0)`` read as an empty, all-passing report (pass rate 1.0)."""
    root = tmp_path / "proj"
    _make_project(root, _TEST_PASS)
    (root / "conftest.py").write_text("import os\nos._exit(0)\n", encoding="utf-8")

    with pytest.raises(NoSuiteResultError) as excinfo:
        ProjectHandle.create(root, tmp_path / "reports").run()
    assert excinfo.value.reason == "it exited 0 with no junit report"


def test_an_explicit_command_may_exit_0_with_no_junit_report(tmp_path: Path) -> None:
    """A ``--test-cmd`` need not write junit: only the default command promises one."""
    handle = ProjectHandle.create(
        tmp_path, tmp_path / "reports", test_cmd=[sys.executable, "-c", "pass"]
    )

    assert handle.run().returncode == 0


@pytest.mark.parametrize(
    ("report", "content"),
    [
        ("junit.xml", "<oops"),
        ("coverage.xml", "<oops"),
        ("coverage.xml", '<coverage line-rate="abc"/>'),
    ],
    ids=["truncated-junit", "truncated-coverage", "coverage-bad-rate"],
)
def test_an_unreadable_report_is_no_result(tmp_path: Path, report: str, content: str) -> None:
    """Regression: a truncated report raised ``ParseError``, which aborted a whole eval record."""
    reports = tmp_path / "reports"
    junit = '<testsuite tests="1"><testcase name="t"/></testsuite>'
    script = (
        "import pathlib, sys; d = pathlib.Path(sys.argv[1]); "
        f"(d / 'junit.xml').write_text({junit!r}); (d / {report!r}).write_text({content!r})"
    )
    handle = ProjectHandle(
        root=tmp_path, test_cmd=[sys.executable, "-c", script, str(reports)], report_dir=reports
    )

    with pytest.raises(NoSuiteResultError) as excinfo:
        handle.run()
    assert excinfo.value.reason == f"its {report} report cannot be read"


def test_a_run_with_no_result_is_cached_and_never_rerun(tmp_path: Path) -> None:
    """A second ``run()`` re-raises the first failure instead of paying a timeout again."""
    runs = tmp_path / "runs.txt"
    script = f"import pathlib, sys; pathlib.Path({str(runs)!r}).open('a').write('x'); sys.exit(4)"
    handle = ProjectHandle(
        root=tmp_path, test_cmd=[sys.executable, "-c", script], report_dir=tmp_path / "reports"
    )

    with pytest.raises(NoSuiteResultError) as first:
        handle.run()
    with pytest.raises(NoSuiteResultError) as second:
        handle.run()
    assert second.value is first.value
    assert handle.no_result is first.value
    assert runs.read_text(encoding="utf-8") == "x"


def test_a_flaky_retry_with_no_result_keeps_the_best_rate_so_far(tmp_path: Path) -> None:
    """A retry that gives no result must not discard the cached run's rate and coverage."""
    reports = tmp_path / "reports"
    marker = tmp_path / "ran-once"
    junit = (
        '<testsuite tests="2"><testcase name="a"/>'
        '<testcase name="b"><failure message="x"/></testcase></testsuite>'
    )
    script = (
        "import pathlib, sys; d, m = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])\n"
        "if m.exists(): (d / 'junit.xml').unlink(); sys.exit(4)\n"
        f"m.touch(); (d / 'junit.xml').write_text({junit!r}); sys.exit(1)"
    )
    handle = ProjectHandle(
        root=tmp_path,
        test_cmd=[sys.executable, "-c", script, str(reports), str(marker)],
        report_dir=reports,
        flaky_retries=1,
    )

    assert handle.best_pass_rate() == pytest.approx(0.5)


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX")
def test_a_timed_out_suite_takes_the_processes_it_started_with_it(tmp_path: Path) -> None:
    """Regression: the timeout killed pytest only; a test's own subprocess kept running."""
    pid_file = tmp_path / "grandchild.pid"
    script = (
        "import pathlib, subprocess, sys, time; "
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid)); time.sleep(60)"
    )
    handle = ProjectHandle(
        root=tmp_path,
        test_cmd=[sys.executable, "-c", script],
        report_dir=tmp_path / "reports",
        timeout_s=5.0,
    )

    with pytest.raises(NoSuiteResultError):
        handle.run()
    pid = int(pid_file.read_text(encoding="utf-8"))
    try:
        assert not _alive(pid)
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX")
def test_an_interrupted_suite_takes_its_processes_with_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: in its own session the suite missed Ctrl-C, and only a timeout killed it."""
    started: list[subprocess.Popen[str]] = []

    class _InterruptedWait(subprocess.Popen[str]):
        def communicate(self, input: Any = None, timeout: float | None = None) -> tuple[Any, Any]:
            if self not in started:
                started.append(self)
                raise KeyboardInterrupt
            return super().communicate(input, timeout)

    monkeypatch.setattr(
        "coding_agent_playbook.grading.execution_metrics.project.subprocess.Popen", _InterruptedWait
    )
    handle = ProjectHandle(
        root=tmp_path,
        test_cmd=[sys.executable, "-c", "import time; time.sleep(60)"],
        report_dir=tmp_path / "reports",
    )

    with pytest.raises(KeyboardInterrupt):
        handle.run()
    assert started[0].returncode == -signal.SIGKILL


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX")
def test_a_group_kill_refused_by_the_os_still_ends_in_no_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: macOS refuses ``killpg`` (EPERM) once the group holds only a zombie."""

    def _refused(pid: int, sig: int) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(
        "coding_agent_playbook.grading.execution_metrics.project.os.killpg", _refused
    )
    handle = ProjectHandle(
        root=tmp_path,
        test_cmd=[sys.executable, "-c", "import time; time.sleep(60)"],
        report_dir=tmp_path / "reports",
        timeout_s=0.5,
    )

    with pytest.raises(NoSuiteResultError) as excinfo:
        handle.run()
    assert excinfo.value.reason == "it timed out after 0.5 s"


def _alive(pid: int) -> bool:
    """Whether ``pid`` still runs, after a short grace for the kernel to reap it."""
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        time.sleep(0.1)
    return True


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


# Writes whether the suite saw the caller's secret; a non-zero exit with no junit is no result.
_SECRET_PROBE = (
    "import os, pathlib; "
    "pathlib.Path(os.environ['PLAYBOOK_OUT']).write_text(str('PLAYBOOK_SECRET' in os.environ))"
)


def _secret_seen(tmp_path: Path, label: str, *, inherit_env: bool) -> str:
    """Run :data:`_SECRET_PROBE` in a handle and return whether it saw ``PLAYBOOK_SECRET``."""
    out = tmp_path / f"seen-{label}.txt"
    ProjectHandle.create(
        tmp_path,
        tmp_path / f"reports-{label}",
        test_cmd=[sys.executable, "-c", _SECRET_PROBE],
        env_overrides={"PLAYBOOK_OUT": str(out)},
        inherit_env=inherit_env,
    ).run()
    return out.read_text(encoding="utf-8")


def test_inherit_env_false_runs_with_only_the_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With ``inherit_env=False`` the caller's variables stay out; ``True`` still passes them."""
    monkeypatch.setenv("PLAYBOOK_SECRET", "1")

    assert _secret_seen(tmp_path, "isolated", inherit_env=False) == "False"
    assert _secret_seen(tmp_path, "inherited", inherit_env=True) == "True"


def test_inherit_env_defaults_to_true(tmp_path: Path) -> None:
    """The default keeps the metrics gate and the hook path inheriting the caller's environment."""
    assert ProjectHandle.create(tmp_path, tmp_path / "reports").inherit_env is True


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
