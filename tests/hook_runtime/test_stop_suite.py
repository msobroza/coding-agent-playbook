"""The shared Stop suite run through the pinned stage runner (specs/prK-hook-pack.md §F.1.2).

``PinnedSuiteHandle`` runs the ``coverage`` record's command through the
``StageRunner`` (``FakeStageRunner`` here, which writes the reports a real
pytest would), parses junit and coverage XML from the report dir, and turns
every run without a report into ``SuiteUnavailable``: never green.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.hook_runtime.stop.runner import ToolRun
from coding_agent_playbook.hook_runtime.stop.suite import (
    PYTEST_COV_ADVICE,
    SuiteSpec,
    SuiteUnavailable,
    pinned_suite_handle,
    suite_env,
)
from tests.hook_runtime.fakes import FakeStageRunner

if TYPE_CHECKING:
    from pathlib import Path

    from tests.hook_runtime.fakes import StageCall

RECORD_ARGS: Final = ("-m", "pytest", "-o", "addopts=", "-p", "no:cacheprovider", "-q")
JUNIT: Final = (
    '<testsuite><testcase name="a"/><testcase name="b"><failure message="x"/></testcase>'
    "</testsuite>"
)
COVERAGE: Final = (
    '<coverage line-rate="0.5"><sources><source>{root}/src</source></sources><packages>'
    '<package><classes><class filename="pkg/a.py"><lines><line number="1" hits="1"/>'
    '<line number="2" hits="0"/></lines></class></classes></package></packages></coverage>'
)


def _spec(tmp_path: Path) -> SuiteSpec:
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    report_dir = tmp_path / "state" / "suite" / "tree"
    env = suite_env({"PATH": "/usr/bin"}, report_dir)
    return SuiteSpec(root, report_dir, "project_python", RECORD_ARGS, env, 300.0)


def _flag(call: StageCall, prefix: str) -> str:
    return next(arg.removeprefix(prefix) for arg in call.args if arg.startswith(prefix))


def _pytest(call: StageCall, root: Path, returncode: int = 1) -> ToolRun:
    """What pytest-cov writes: junit and Cobertura XML at the paths the args name."""
    from pathlib import Path

    Path(_flag(call, "--junitxml=")).write_text(JUNIT, encoding="utf-8")
    Path(_flag(call, "--cov-report=xml:")).write_text(COVERAGE.format(root=root), "utf-8")
    return ToolRun("project_python", returncode, b"FAILED tests/test_a.py::b - x\n1 failed\n")


def test_run_goes_through_the_pinned_runner_with_reports_and_env(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    runner = FakeStageRunner()
    runner.answer("project_python", lambda call: _pytest(call, spec.root))

    artifacts = pinned_suite_handle(spec, runner).run()

    (call,) = runner.calls
    assert call.args[: len(RECORD_ARGS)] == RECORD_ARGS
    assert "--cov=src" in call.args
    assert call.args[-1] == f"--cov-config={spec.report_dir / 'coveragerc'}"
    assert call.env == {
        "PATH": "/usr/bin",
        "COVERAGE_FILE": str(spec.report_dir / ".coverage"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    assert (artifacts.returncode, artifacts.junit.failed, artifacts.junit.total) == (1, 1, 2)
    assert artifacts.coverage.lines == {"pkg/a.py": {1: 1, 2: 0}}
    assert (spec.report_dir / "coveragerc").read_text(encoding="utf-8") == "[run]\n"


def test_run_is_cached_one_run_per_handle(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    runner = FakeStageRunner()
    runner.answer("project_python", lambda call: _pytest(call, spec.root))
    handle = pinned_suite_handle(spec, runner)

    assert handle.run() is handle.run()
    assert len(runner.calls) == 1
    assert b"FAILED" in handle.output


@pytest.mark.parametrize(
    ("run", "category", "advice"),
    [
        (
            ToolRun("project_python", 4, b"", b"error: unrecognized arguments: --cov=src\n"),
            "toolchain_missing",
            PYTEST_COV_ADVICE,
        ),
        (ToolRun("project_python", 2, b"collection crashed\n"), "crash", ""),
        (ToolRun("project_python", skip_category="timeout"), "timeout", ""),
        (
            ToolRun("project_python", skip_category="tool_changed", advice="re-sync"),
            "tool_changed",
            "re-sync",
        ),
    ],
    ids=["no-pytest-cov", "no-junit", "timeout", "pin-changed"],
)
def test_runs_without_a_report_are_unavailable(
    tmp_path: Path, run: ToolRun, category: str, advice: str
) -> None:
    runner = FakeStageRunner()
    runner.answer("project_python", lambda call: run)

    with pytest.raises(SuiteUnavailable) as caught:
        pinned_suite_handle(_spec(tmp_path), runner).run()

    assert (caught.value.category, caught.value.advice) == (category, advice)
