"""Tests for the one measuring pass, ``grading/measuring.py`` (specs/prT-package-layout.md B.11).

Eval scoring and the metrics gate both measure through this module: ``python_files`` is
the one ``IGNORED_DIRS`` walk, ``measure_tree`` the per-file loop with its byte cap and
hostile-source handling, ``measure_suite`` the suite loop, and ``measured_metrics`` the
names that decide, at grade time, whether a metric-backed check is available.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.checks.files import FileExistsCheck
from coding_agent_playbook.evals.judge import StubJudge
from coding_agent_playbook.grading.check import MeasurementSet, NonRegressionCheck, ThresholdCheck
from coding_agent_playbook.grading.compose import AllOf, AnyOf, Not
from coding_agent_playbook.grading.execution_metrics.coverage_xml import CoverageReport
from coding_agent_playbook.grading.execution_metrics.junit import JunitSummary
from coding_agent_playbook.grading.execution_metrics.project import RunArtifacts
from coding_agent_playbook.grading.judge_metric import JudgeMetric
from coding_agent_playbook.grading.measuring import (
    SourceMeter,
    decode_source_blob,
    iter_checks,
    measure_files,
    measure_suite,
    measure_tree,
    measured_metrics,
    python_files,
    referenced_metrics,
)
from coding_agent_playbook.grading.metric import Metric, execution_metrics, get_metric
from coding_agent_playbook.grading.normalizer import Identity
from coding_agent_playbook.grading.rubric import Rubric
from coding_agent_playbook.grading.scope import Scope
from coding_agent_playbook.grading.types import EvalContext, Measurement, MeasureSetup
from tests.fakes import NO_OP_SUITE_CMD, FakeProjectHandle

if TYPE_CHECKING:
    from pathlib import Path


def _write(root: Path, rel: str, text: str = "x = 1\n") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _rel(paths: list[Path], root: Path) -> list[str]:
    return [path.relative_to(root).as_posix() for path in paths]


@dataclass
class UnlaunchableProjectHandle(FakeProjectHandle):
    """A handle whose suite cannot be launched, as when pytest is missing."""

    def _run_once(self) -> RunArtifacts:
        raise RuntimeError(f"could not run the test command {self.test_cmd!r}")


def _handle(root: Path, run: RunArtifacts) -> FakeProjectHandle:
    return FakeProjectHandle(
        root=root, test_cmd=list(NO_OP_SUITE_CMD), report_dir=root / "reports", artifacts=run
    )


class _OwnToolMetric(Metric):
    """A stand-in out-of-tree metric that needs a tool of its own and says so in ``runnable``."""

    name = "own_tool_metric"
    scope = Scope.FILE
    normalizer = Identity()

    def runnable(self, setup: MeasureSetup) -> bool:
        return "own-tool" in setup.tool_paths

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return [Measurement(evaluator=self.name, scope_key=ctx.label, value=1.0)]


def _grading_ctx(measured: set[str] | frozenset[str]) -> EvalContext:
    return EvalContext(module=None, source="", label="rubric", measured_metrics=frozenset(measured))


def _cc_meter(setup: MeasureSetup | None = None) -> SourceMeter:
    return SourceMeter([get_metric("cyclomatic_complexity")], setup or MeasureSetup())


def test_python_files_skip_dot_and_ignored_dirs(tmp_path: Path) -> None:
    kept = ("a.py", "pkg/b.py", "pkg/sub/c.py")
    dropped = (
        ".hidden/d.py",
        "build/e.py",
        "venv/f.py",
        "node_modules/g.py",
        "pkg/__pycache__/h.py",
    )
    for rel in (*kept, *dropped, "pkg/notes.txt"):
        _write(tmp_path, rel)

    assert _rel(python_files(tmp_path), tmp_path) == list(kept)


def test_python_files_keep_paths_under_the_given_root(tmp_path: Path) -> None:
    real = tmp_path / "real"
    _write(real, "pkg/a.py")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    assert python_files(link) == [link / "pkg" / "a.py"]


def test_measure_tree_labels_are_root_relative_posix(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/deep/mod.py", "def f():\n    return 1\n")

    tree = measure_tree(tmp_path, _cc_meter())

    assert [row.scope_key for row in tree.measurements] == ["pkg/deep/mod.py::f"]
    assert (tree.skipped, tree.measured_count) == ((), 1)


def test_measure_tree_skips_an_unparseable_file_with_a_reason(tmp_path: Path) -> None:
    _write(tmp_path, "broken.py", "def oops(:\n    pass\n")
    _write(tmp_path, "ok.py", "def f():\n    return 1\n")

    tree = measure_tree(tmp_path, _cc_meter())

    assert tree.skipped == (("broken.py", "unparseable (invalid syntax)"),)
    assert [row.scope_key for row in tree.measurements] == ["ok.py::f"]
    assert tree.measured_count == 1


def test_measure_tree_skips_a_file_over_the_byte_cap(tmp_path: Path) -> None:
    _write(tmp_path, "big.py", "#" * 65)

    tree = measure_tree(tmp_path, _cc_meter(MeasureSetup(max_file_bytes=64)))

    assert tree.skipped == (("big.py", "too large (65 bytes, over the 64-byte cap)"),)
    assert (tree.measurements, tree.measured_count) == ((), 0)


def test_measure_files_label_each_file_as_given(tmp_path: Path) -> None:
    path = _write(tmp_path, "a.py", "def f():\n    return 1\n")

    tree = measure_files([(path, "src/pkg/a.py")], _cc_meter())

    assert [row.scope_key for row in tree.measurements] == ["src/pkg/a.py::f"]


@pytest.mark.parametrize(
    ("body", "cap"),
    [(b"x = '\xff'\n", 1000), (b"def oops(:\n", 1000), (b"#" * 65, 64)],
    ids=["not-utf8", "unparseable", "over-cap"],
)
def test_measure_file_or_drop_counts_a_bad_baseline_file_as_all_new(
    tmp_path: Path, body: bytes, cap: int
) -> None:
    path = tmp_path / "base.py"
    path.write_bytes(body)

    assert _cc_meter(MeasureSetup(max_file_bytes=cap)).measure_file_or_drop(path, "base.py") == []


def test_measure_file_or_drop_measures_a_good_baseline_file(tmp_path: Path) -> None:
    path = _write(tmp_path, "base.py", "def f():\n    return 1\n")

    rows = _cc_meter().measure_file_or_drop(path, "base.py")

    assert [(row.scope_key, row.value) for row in rows] == [("base.py::f", 1.0)]


def test_decode_source_blob_normalizes_newlines_and_refuses_non_utf8() -> None:
    assert decode_source_blob(b"a = 1\r\nb = 2\rc = 3\n") == "a = 1\nb = 2\nc = 3\n"
    assert decode_source_blob(b"x = '\xff'\n") is None
    assert decode_source_blob(b"#" * 65, max_file_bytes=64) is None


def test_measured_metrics_drop_ruff_without_a_ruff_path() -> None:
    metrics = [get_metric("wmc"), get_metric("ruff_violations")]

    assert measured_metrics(metrics, MeasureSetup()) == {"wmc"}
    with_ruff = MeasureSetup(tool_paths={"ruff": "/usr/bin/ruff"})
    assert measured_metrics(metrics, with_ruff) == {"wmc", "ruff_violations"}


def test_measured_metrics_never_list_a_judged_metric() -> None:
    judged = Rubric.of(("clarity", 1.0), name="quality")
    metrics = [JudgeMetric("names are clear"), judged, get_metric("dit")]

    assert measured_metrics(metrics, MeasureSetup()) == {"dit"}


def test_a_metric_check_is_available_iff_its_metric_was_measured() -> None:
    check = ThresholdCheck(get_metric("wmc"), fail=0.5)

    assert check.available(_grading_ctx({"wmc"})) is True
    assert check.available(_grading_ctx(set())) is False


def test_a_judged_metric_check_asks_its_judge_not_the_pass() -> None:
    check = ThresholdCheck(JudgeMetric("names are clear"), fail=0.5)
    promised = _grading_ctx({"judge:names-are-clear"})

    assert check.available(promised) is False
    assert check.available(replace(promised, judge=StubJudge())) is True


def test_a_metric_check_over_zero_files_grades_vacuously(tmp_path: Path) -> None:
    static = [get_metric("cyclomatic_complexity")]
    tree = measure_tree(tmp_path, SourceMeter(static, MeasureSetup()))
    ctx = _grading_ctx(measured_metrics(static, MeasureSetup()))

    rubric = Rubric([NonRegressionCheck(static[0], fail=0.25)])
    report = rubric.evaluate(ctx, MeasurementSet(list(tree.measurements)))

    [check] = report.checks
    assert (check.status, check.passed, check.score, check.subresults) == ("run", True, None, ())


@pytest.mark.parametrize(
    ("tool_paths", "expected"),
    [({}, ("skipped", 0, [])), ({"own-tool": "/opt/own-tool"}, ("run", 1, ["a.py"]))],
    ids=["tool-missing", "tool-present"],
)
def test_a_metric_check_is_skipped_when_its_metric_refuses_the_setup_in_runnable(
    tmp_path: Path, tool_paths: dict[str, str], expected: tuple[str, int, list[str]]
) -> None:
    _write(tmp_path, "a.py")
    metric, setup = _OwnToolMetric(), MeasureSetup(tool_paths=tool_paths)
    tree = measure_tree(tmp_path, SourceMeter([metric], setup))
    ctx = _grading_ctx(measured_metrics([metric], setup))

    rubric = Rubric([ThresholdCheck(metric, fail=0.5)])
    report = rubric.evaluate(ctx, MeasurementSet(list(tree.measurements)))

    [check] = report.checks
    measured = [row.scope_key for row in tree.measurements]
    assert (check.status, len(check.subresults), measured) == expected


def test_measure_suite_runs_the_suite_once_for_every_execution_metric(tmp_path: Path) -> None:
    run = RunArtifacts(
        junit=JunitSummary(passed=3, failed=1, errors=0, skipped=0, total=4),
        coverage=CoverageReport(per_file={"a.py": 50.0}, total=50.0),
        returncode=1,
    )
    handle = _handle(tmp_path, run)

    rows = measure_suite(handle, execution_metrics(), MeasureSetup())

    assert handle.runs == 1
    assert sorted((row.evaluator, row.scope_key, row.value) for row in rows) == [
        ("coverage", "a.py", 50.0),
        ("coverage", "suite", 50.0),
        ("test_pass_rate", "suite", 0.75),
    ]


def test_measure_suite_raises_what_an_unlaunchable_suite_raises(tmp_path: Path) -> None:
    handle = UnlaunchableProjectHandle(
        root=tmp_path, test_cmd=["no-such-pytest"], report_dir=tmp_path / "reports"
    )

    with pytest.raises(RuntimeError, match="no-such-pytest"):
        measure_suite(handle, execution_metrics(), MeasureSetup())


def test_referenced_metrics_walk_composers_and_dedupe_by_name() -> None:
    cc, wmc = get_metric("cyclomatic_complexity"), get_metric("wmc")
    checks = [
        AllOf(ThresholdCheck(cc), Not(NonRegressionCheck(wmc))),
        AnyOf(ThresholdCheck(get_metric("cyclomatic_complexity")), FileExistsCheck("a.py")),
    ]

    assert [metric.name for metric in referenced_metrics(checks)] == [
        "cyclomatic_complexity",
        "wmc",
    ]


def test_referenced_metrics_descend_into_a_nested_rubric_only_when_asked() -> None:
    inner = Rubric([ThresholdCheck(get_metric("dit"), fail=0.5)], name="inner")
    checks = [ThresholdCheck(inner, fail=0.5)]

    assert [metric.name for metric in referenced_metrics(checks)] == ["inner"]
    assert [metric.name for metric in referenced_metrics(checks, nested=True)] == ["inner", "dit"]


def test_iter_checks_descends_composers_and_a_rubric_metrics_checks() -> None:
    """Every node, a ``[rubric]`` group's bound file check included (hole 2's freeze input)."""
    bound = FileExistsCheck("tests/test_a.py")
    group = ThresholdCheck(Rubric([AllOf(bound)], name="group"), fail=0.5)
    negated = FileExistsCheck("b.py")
    checks = [AnyOf(Not(negated), group)]

    walked = list(iter_checks(checks))

    assert walked[0] is checks[0]
    assert {id(c) for c in (negated, group, bound)} <= {id(c) for c in walked}
    assert len(walked) == 6


def test_iter_checks_visits_a_rubric_that_nests_itself_once() -> None:
    loop = Rubric([], name="loop")
    leaf = FileExistsCheck("a.py")
    loop.checks.extend([ThresholdCheck(loop, fail=0.5), leaf])

    assert [c for c in iter_checks([ThresholdCheck(loop, fail=0.5)]) if c is leaf] == [leaf]


def test_referenced_metrics_visit_a_rubric_that_nests_itself_once() -> None:
    loop = Rubric([], name="loop")
    loop.checks.append(ThresholdCheck(loop, fail=0.5))

    assert [metric.name for metric in referenced_metrics(loop.checks, nested=True)] == ["loop"]
