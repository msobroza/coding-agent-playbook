"""Tests for ``diff_coverage``: coverage of the changed lines only (prK §F.1.1).

:func:`changed_line_coverage` is pure over a :class:`CoverageReport`, so most
cases build the report by hand. The metric reads git through the injected
``ToolSetup.git`` (a :class:`FakeGitRunner` printing a canned diff) and the suite
through a :class:`FakeProjectHandle`, so no git or pytest process ever runs.
The gate cases spy on :class:`FakeProjectFactory` to count suite runs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent_playbook.evaluators.execution.coverage_xml import CoverageReport
from coding_agent_playbook.evaluators.execution.diff_coverage import (
    DiffCoverage,
    DiffCoverageMetric,
    FileDiffCoverage,
    changed_line_coverage,
    format_ranges,
    line_ranges,
)
from coding_agent_playbook.evaluators.execution.project import RunArtifacts
from coding_agent_playbook.evaluators.metric import get_metric
from coding_agent_playbook.evaluators.metrics_gate import (
    MetricsGateDeps,
    MetricsGateRequest,
    run_metrics_gate,
)
from coding_agent_playbook.evaluators.types import EvalContext, Measurement, MetricConfig, ToolSetup
from tests.fakes import (
    FakeBaselineGit,
    FakeGitRunner,
    FakeProjectFactory,
    FakeProjectHandle,
    empty_run,
)

_ROOT = Path("/repo")


def _report(lines: dict[str, dict[int, int]]) -> CoverageReport:
    return CoverageReport(lines=lines)


def _diff(path: str, *hunks: str) -> bytes:
    body = "".join(f"{hunk}\n+x\n" for hunk in hunks)
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n{body}".encode()


# --------------------------------------------------------------------------- #
# changed_line_coverage (pure)
# --------------------------------------------------------------------------- #


def test_no_changed_executable_lines_returns_empty() -> None:
    """Changed comments and blank lines are not executable: nothing is scored."""
    report = _report({"src/a.py": {1: 1, 2: 0}})

    result = changed_line_coverage({"src/a.py": frozenset({5, 6})}, report, root=_ROOT)

    assert result == DiffCoverage()
    assert result.percent is None


def test_score_is_covered_over_executable() -> None:
    report = _report({"src/a.py": {1: 1, 2: 0, 3: 4}, "src/b.py": {1: 0, 2: 1}})
    changed = {"src/a.py": frozenset({1, 2, 3, 9}), "src/b.py": frozenset({2})}

    result = changed_line_coverage(changed, report, root=_ROOT)

    assert (result.covered, result.executable) == (3, 4)
    assert result.percent == 75.0
    assert [(item.path, item.percent) for item in result.files] == [
        ("src/a.py", pytest.approx(200 / 3)),
        ("src/b.py", 100.0),
    ]


def test_uncovered_lines_collapse_to_ranges() -> None:
    hits = {line: 0 for line in (12, 13, 14, 15, 40)} | {16: 1}
    changed = {"src/a.py": frozenset({12, 13, 14, 15, 16, 40})}

    result = changed_line_coverage(changed, _report({"src/a.py": hits}), root=_ROOT)

    assert result.files == (FileDiffCoverage("src/a.py", 6, 1, ((12, 15), (40, 40))),)
    assert format_ranges(result.files[0].uncovered) == "12-15, 40"
    assert line_ranges([3, 1, 2, 2, 7]) == ((1, 3), (7, 7))


def test_test_paths_excluded_via_TEST_PATH_GLOBS() -> None:
    report = _report({"tests/test_a.py": {1: 0}, "src/conftest.py": {1: 0}, "src/a.py": {1: 1}})
    changed = {
        "tests/test_a.py": frozenset({1}),
        "src/conftest.py": frozenset({1}),
        "src/a.py": frozenset({1}),
    }

    result = changed_line_coverage(changed, report, root=_ROOT)

    assert [item.path for item in result.files] == ["src/a.py"]
    assert result.percent == 100.0


def test_exclude_globs_are_not_scored() -> None:
    report = _report({"eval_tasks/t1/setup/app.py": {1: 0}, "src/a.py": {1: 0}})
    changed = {"eval_tasks/t1/setup/app.py": frozenset({1}), "src/a.py": frozenset({1})}

    result = changed_line_coverage(
        changed, report, root=_ROOT, exclude=("**/eval_tasks/*/setup/**",)
    )

    assert [item.path for item in result.files] == ["src/a.py"]


def test_unmeasured_files_listed_not_scored() -> None:
    report = _report({"src/a.py": {1: 1}})
    changed = {"src/a.py": frozenset({1}), "scripts/tool.py": frozenset({1, 2})}

    result = changed_line_coverage(changed, report, root=_ROOT)

    assert result.unmeasured == ("scripts/tool.py",)
    assert result.percent == 100.0


def test_source_relative_report_names_map_onto_the_repo(tmp_path: Path) -> None:
    """``--cov=src`` names files relative to ``src``; the changed paths are repo-relative."""
    report = CoverageReport(lines={"pkg/a.py": {1: 0, 2: 1}}, sources=(str(tmp_path / "src"),))

    result = changed_line_coverage({"src/pkg/a.py": frozenset({1, 2})}, report, root=tmp_path)

    assert result.files == (FileDiffCoverage("src/pkg/a.py", 2, 1, ((1, 1),)),)


# --------------------------------------------------------------------------- #
# The metric
# --------------------------------------------------------------------------- #


def _handle(
    tmp_path: Path, diff_base: str | None, coverage: CoverageReport | None = None
) -> FakeProjectHandle:
    run = empty_run()
    artifacts = RunArtifacts(run.junit, coverage or CoverageReport(), run.returncode)
    return FakeProjectHandle(
        root=tmp_path,
        test_cmd=[],
        report_dir=tmp_path / "reports",
        diff_base=diff_base,
        artifacts=artifacts,
    )


def _ctx(handle: FakeProjectHandle, git: FakeGitRunner) -> EvalContext:
    setup = ToolSetup(git=git.factory, timeout_s=3.0, exclude=("**/eval_tasks/*/setup/**",))
    return EvalContext(module=None, source="", label="suite", project=handle, tool_setup=setup)


def test_metric_descriptors() -> None:
    metric = get_metric("diff_coverage")

    assert isinstance(metric, DiffCoverageMetric)
    assert (metric.needs_project, metric.diff_based) == (True, True)
    assert metric.score(62.5) == pytest.approx(0.625)


def test_metric_measures_one_module_percentage(tmp_path: Path) -> None:
    git = FakeGitRunner(outputs={"diff": _diff("src/a.py", "@@ -0,0 +1,4 @@")})
    handle = _handle(tmp_path, "HEAD", _report({"src/a.py": {1: 1, 2: 1, 3: 0, 4: 1}}))

    measured = DiffCoverageMetric().measure(_ctx(handle, git))

    assert measured == [Measurement("diff_coverage", "suite", 75.0)]
    assert git.roots == [(tmp_path, 3.0)]
    assert git.calls[0][-3:] == ("HEAD", "--", "*.py")


def test_handle_without_diff_base_yields_empty_so_kind_new(tmp_path: Path) -> None:
    git = FakeGitRunner(outputs={"diff": _diff("src/a.py", "@@ -0,0 +1 @@")})
    handle = _handle(tmp_path, None)

    assert DiffCoverageMetric().measure(_ctx(handle, git)) == []
    assert (git.calls, handle.runs) == ([], 0)


def test_only_test_or_excluded_changes_never_run_the_suite(tmp_path: Path) -> None:
    diff = _diff("tests/test_a.py", "@@ -0,0 +1 @@") + _diff(
        "eval_tasks/t/setup/app.py", "@@ -0,0 +1 @@"
    )
    handle = _handle(tmp_path, "HEAD")

    assert DiffCoverageMetric().measure(_ctx(handle, FakeGitRunner(outputs={"diff": diff}))) == []
    assert handle.runs == 0


# --------------------------------------------------------------------------- #
# Through the gate
# --------------------------------------------------------------------------- #


def _gate(
    tmp_path: Path, factory: FakeProjectFactory, git: FakeGitRunner, *, select: tuple[str, ...]
) -> list[tuple[str, str]]:
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    request = MetricsGateRequest(
        repo_root=tmp_path,
        config=MetricConfig(mode="regression"),
        paths=(str(tmp_path / "src"),),
        baseline="git:HEAD",
        run_tests=True,
        select=select,
    )
    head = FakeBaselineGit(blobs={("HEAD", "src/a.py"): "x = 1\n"})
    deps = MetricsGateDeps(
        project_factory=factory,
        git_factory=lambda timeout_s: head,
        git_runner_factory=git.factory,
    )
    report = run_metrics_gate(request, deps=deps).report
    return [(finding.evaluator, finding.kind) for finding in report.findings]


def test_diff_based_skips_baseline_suite_run(tmp_path: Path) -> None:
    """``--select diff_coverage`` costs one suite run, in source mode, with the diff base."""
    run = empty_run()
    factory = FakeProjectFactory(
        artifacts=RunArtifacts(run.junit, _report({"src/a.py": {1: 0}}), 0)
    )
    git = FakeGitRunner(outputs={"diff": _diff("src/a.py", "@@ -1 +1 @@")})

    findings = _gate(tmp_path, factory, git, select=("diff_coverage",))

    assert [(r.root, r.diff_base, r.cov_sources) for r in factory.requests] == [
        (tmp_path, "HEAD", ("src",))
    ]
    assert [handle.runs for handle in factory.handles] == [1]
    assert findings == [("diff_coverage", "new")]


def test_testing_family_runs_the_baseline_without_a_diff_base(tmp_path: Path) -> None:
    factory = FakeProjectFactory()
    git = FakeGitRunner()

    _gate(tmp_path, factory, git, select=("testing",))

    assert [(r.root.name, r.diff_base, r.cov_sources) for r in factory.requests] == [
        (tmp_path.name, "HEAD", ("src",)),
        ("baseline-worktree", None, ("src",)),
    ]


def test_no_diff_base_keeps_the_bare_cov_command(tmp_path: Path) -> None:
    """Without a diff base ``diff_coverage`` cannot measure, so the command stays as it was."""
    factory = FakeProjectFactory()
    (tmp_path / "src").mkdir()
    request = MetricsGateRequest(
        repo_root=tmp_path, config=MetricConfig(mode="absolute"), paths=(), run_tests=True
    )

    run_metrics_gate(request, deps=MetricsGateDeps(project_factory=factory))

    assert [(r.diff_base, r.cov_sources) for r in factory.requests] == [(None, ())]


def test_json_baseline_rows_of_diff_based_metrics_are_dropped(tmp_path: Path) -> None:
    """A snapshot's old ``diff_coverage`` is relative to another base: never compared."""
    snapshot = tmp_path / "cov.json"
    snapshot.write_text(
        '{"schema": 1, "tree": null, "measurements": ['
        '{"evaluator": "diff_coverage", "scope_key": "suite", "value": 100.0}]}',
        encoding="utf-8",
    )
    run = empty_run()
    factory = FakeProjectFactory(
        artifacts=RunArtifacts(run.junit, _report({"src/a.py": {1: 1}}), 0)
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    request = MetricsGateRequest(
        repo_root=tmp_path,
        config=MetricConfig(mode="regression"),
        paths=(str(tmp_path / "src"),),
        baseline=f"json:{snapshot}",
        run_tests=True,
        select=("diff_coverage",),
        diff_base="HEAD",
    )
    git = FakeGitRunner(outputs={"diff": _diff("src/a.py", "@@ -1 +1 @@")})
    deps = MetricsGateDeps(project_factory=factory, git_runner_factory=git.factory)

    report = run_metrics_gate(request, deps=deps).report

    assert [(f.evaluator, f.value, f.kind) for f in report.findings] == [
        ("diff_coverage", 100.0, "new")
    ]
    assert [r.diff_base for r in factory.requests] == ["HEAD"]


def test_changed_lines_seam_replaces_the_git_read(tmp_path: Path) -> None:
    """A caller that already lists the change (the coverage Stop stage) skips git entirely."""
    git = FakeGitRunner(outputs={"diff": _diff("src/a.py", "@@ -0,0 +1 @@")})
    handle = _handle(tmp_path, "base0", _report({"src/a.py": {1: 1, 2: 0}}))
    asked: list[tuple[Path, str]] = []

    def listed(root: Path, base: str) -> dict[str, frozenset[int]]:
        asked.append((root, base))
        return {"src/a.py": frozenset({1, 2})}

    setup = ToolSetup(git=git.factory, changed_lines=listed)
    ctx = EvalContext(module=None, source="", label="suite", project=handle, tool_setup=setup)

    assert DiffCoverageMetric().measure(ctx) == [Measurement("diff_coverage", "suite", 50.0)]
    assert (asked, git.calls) == ([(tmp_path, "base0")], [])
