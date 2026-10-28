"""``cognitive_complexity``: complexipy per function, each side through a temporary file.

complexipy is ``FakeComplexipyRunner`` (``--plain`` rows scripted per source
text, read from the file the metric wrote) behind ``ToolSetup.runner`` or
``MetricsGateDeps.tool_runner``; no complexipy runs, except in the one smoke
test that needs it on ``PATH``.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Final

import pytest

from coding_agent_playbook.grading.metric import get_metric, static_metrics
from coding_agent_playbook.grading.parse import parse_module
from coding_agent_playbook.grading.static_metrics.cognitive import (
    CognitiveComplexityMetric,
    complexipy_argv,
    parse_complexipy_plain,
)
from coding_agent_playbook.grading.tool_runner import subprocess_tool_runner
from coding_agent_playbook.grading.types import EvalContext, Measurement, MeasureSetup, ToolSetup
from coding_agent_playbook.metrics_gate.config import MetricConfig, parse_metrics_config
from coding_agent_playbook.metrics_gate.policy import resolve_metric_selection
from coding_agent_playbook.metrics_gate.run import (
    MetricsGateDeps,
    MetricsGateRequest,
    MetricsGateResult,
    cli_tool_paths,
    run_metrics_gate,
)
from tests.fakes import FakeBaselineGit, FakeComplexipyRunner, complexipy_plain

COMPLEXIPY: Final = "/venv/bin/complexipy"
SOURCE: Final = (
    "class Box:\n    def run(self, x):\n        return x\n\n\ndef load(path):\n    return path\n"
)


def _ctx(runner: FakeComplexipyRunner, source: str = SOURCE) -> EvalContext:
    return EvalContext(
        module=parse_module(source, "src/x.py"),
        source=source,
        label="src/x.py",
        tool_paths={"complexipy": COMPLEXIPY},
        tool_setup=ToolSetup(cwd=Path("/repo"), runner=runner, timeout_s=4.0),
    )


def _values(measurements: list[Measurement]) -> dict[str, float]:
    return {m.scope_key: m.value for m in measurements}


def test_one_measurement_per_function_keyed_like_parse_module() -> None:
    runner = FakeComplexipyRunner(answers={SOURCE: {"load": 0, "Box::run": 4}})

    measured = CognitiveComplexityMetric().measure(_ctx(runner))

    assert _values(measured) == {"src/x.py::load": 0.0, "src/x.py::Box.run": 4.0}
    assert {m.evaluator for m in measured} == {"cognitive_complexity"}
    module = parse_module(SOURCE, "src/x.py")
    assert set(_values(measured)) == {fn.scope_key for fn in module.functions}


def test_argv_runs_on_the_temporary_file_in_its_own_directory() -> None:
    runner = FakeComplexipyRunner()

    CognitiveComplexityMetric().measure(_ctx(runner))

    [(argv, source, cwd, timeout_s)] = runner.calls
    assert argv == (COMPLEXIPY, *complexipy_argv("complexipy")[1:])
    assert {"--isolated", "--ignore-complexity", "--plain"} <= set(argv)
    assert (source, timeout_s) == (SOURCE, 4.0)
    assert cwd is not None and cwd != Path("/repo")
    assert not cwd.exists()  # the temporary directory (and complexipy's cache) is gone


def test_trailing_notes_are_ignored() -> None:
    runner = FakeComplexipyRunner(answers={SOURCE: {"load": 2}}, notes=True)

    assert _values(CognitiveComplexityMetric().measure(_ctx(runner))) == {"src/x.py::load": 2.0}


def test_a_shared_qualname_keeps_its_highest_value() -> None:
    stdout = b"measured.py Box::value 0\nmeasured.py Box::value 3\nmeasured.py Box::value 1\n"

    assert parse_complexipy_plain(stdout) == {"Box.value": 3}


@pytest.mark.parametrize(
    "runner",
    [FakeComplexipyRunner(returncode=1), FakeComplexipyRunner(returncode=2)],
    ids=["syntax-error", "usage-error-of-an-old-complexipy"],
)
def test_failed_call_yields_no_measurement(runner: FakeComplexipyRunner) -> None:
    assert CognitiveComplexityMetric().measure(_ctx(runner)) == []


def test_timeout_yields_no_measurement_never_zero() -> None:
    assert CognitiveComplexityMetric().measure(_ctx(FakeComplexipyRunner(timeout=True))) == []


def test_unparsed_module_runs_no_complexipy() -> None:
    runner = FakeComplexipyRunner()
    ctx = _ctx(runner)
    broken = EvalContext(
        module=None, source="def (:\n", label="src/x.py", tool_paths=ctx.tool_paths
    )

    assert CognitiveComplexityMetric().measure(broken) == []
    assert runner.calls == []


def test_unavailable_without_a_complexipy_path() -> None:
    ctx = _ctx(FakeComplexipyRunner())
    without = EvalContext(module=ctx.module, source=SOURCE, label="src/x.py")

    assert CognitiveComplexityMetric().available(ctx)
    assert not CognitiveComplexityMetric().available(without)
    assert not CognitiveComplexityMetric().runnable(MeasureSetup())
    assert CognitiveComplexityMetric().measure(without) == []


@pytest.mark.parametrize(
    ("raw", "score"), [(0, 1.0), (15, 1.0), (16, 0.99), (25, 0.9), (115, 0.0), (300, 0.0)]
)
def test_score_is_one_up_to_the_standard_15_then_drops_a_hundredth_per_point(
    raw: int, score: float
) -> None:
    assert get_metric("cognitive_complexity").score(raw) == pytest.approx(score)


def test_opt_in_only_by_name_never_through_quality() -> None:
    available = static_metrics()

    default = {m.name for m in resolve_metric_selection(available)}
    quality = {m.name for m in resolve_metric_selection(available, select=["quality"])}
    extended = {m.name for m in resolve_metric_selection(available, extend_select=["quality"])}
    by_name = resolve_metric_selection(available, select=["cognitive_complexity"])

    assert "cognitive_complexity" not in default | quality | extended
    assert [m.name for m in by_name] == ["cognitive_complexity"]


def test_cli_finds_complexipy_on_path_next_to_ruff() -> None:
    found = {"ruff": "/p/ruff", "complexipy": "/p/complexipy"}

    assert cli_tool_paths(found.get) == found
    assert cli_tool_paths({"ruff": "/p/ruff"}.get) == {"ruff": "/p/ruff"}


# --------------------------------------------------------------------------- #
# Through the gate: the standard limit, non-regression, a missing complexipy
# --------------------------------------------------------------------------- #


def _write(root: Path, rel: str, text: str) -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text, encoding="utf-8")


def _gate(
    tmp_path: Path,
    runner: FakeComplexipyRunner,
    head: dict[str, str],
    *,
    config: MetricConfig | None = None,
    tool_paths: dict[str, str] | None = None,
) -> MetricsGateResult:
    git = FakeBaselineGit(blobs={("HEAD", rel): text for rel, text in head.items()})
    request = MetricsGateRequest(
        repo_root=tmp_path,
        config=config or MetricConfig(),
        paths=(str(tmp_path),),
        baseline="git:HEAD",
        tool_paths={"complexipy": COMPLEXIPY} if tool_paths is None else tool_paths,
        select=("cognitive_complexity",),
    )
    deps = MetricsGateDeps(git_factory=lambda _timeout: git, tool_runner=runner)
    return run_metrics_gate(request, deps=deps)


def _levels(result: MetricsGateResult) -> dict[str, str]:
    return {f.scope_key: f.level for f in result.report.findings}


def _versions(tag: str) -> str:
    """A distinct source text per scripted version of ``f`` (only the text keys the fake)."""
    return f"def f(x):\n    return x  # {tag}\n"


@pytest.mark.parametrize(
    ("before", "after", "level"),
    [
        (10, 14, "ok"),  # growth up to the standard 15 is free
        (10, 15, "ok"),
        (10, 16, "fail"),  # past 15
        (20, 20, "ok"),  # legacy over the limit, unchanged: quiet
        (20, 21, "fail"),  # worse while over the limit
        (20, 18, "ok"),  # better
    ],
)
def test_nonregression_against_head(tmp_path: Path, before: int, after: int, level: str) -> None:
    base, now = _versions("base"), _versions("now")
    _write(tmp_path, "x.py", now)
    runner = FakeComplexipyRunner(answers={base: {"f": before}, now: {"f": after}})

    result = _gate(tmp_path, runner, {"x.py": base})

    assert _levels(result) == {"x.py::f": level}
    assert len(runner.calls) == 2


@pytest.mark.parametrize(("value", "level"), [(15, "ok"), (16, "fail")])
def test_a_new_function_meets_the_standard_limit(tmp_path: Path, value: int, level: str) -> None:
    _write(tmp_path, "new.py", SOURCE)
    runner = FakeComplexipyRunner(answers={SOURCE: {"load": value}})

    assert _levels(_gate(tmp_path, runner, {})) == {"new.py::load": level}


def test_a_configured_threshold_replaces_the_standard_limit(tmp_path: Path) -> None:
    _write(tmp_path, "new.py", SOURCE)
    runner = FakeComplexipyRunner(answers={SOURCE: {"load": 20, "Box::run": 26}})
    config = parse_metrics_config(
        {"thresholds": {"cognitive_complexity": {"warn": 1.0, "fail": 0.9}}}
    )

    levels = _levels(_gate(tmp_path, runner, {}, config=config))

    assert levels == {"new.py::load": "warn", "new.py::Box.run": "fail"}


def test_missing_complexipy_is_a_not_measured_note_never_a_failure(tmp_path: Path) -> None:
    _write(tmp_path, "x.py", SOURCE)
    runner = FakeComplexipyRunner()

    result = _gate(tmp_path, runner, {}, tool_paths={})

    assert (result.report.passed, result.report.findings, runner.calls) == (True, [], [])
    assert result.missing_tools == (("cognitive_complexity", "complexipy"),)


def test_fake_rows_match_the_plain_format() -> None:
    assert complexipy_plain({"Box::run": 4}) == b"measured.py Box::run 4\n"


@pytest.mark.skipif(shutil.which("complexipy") is None, reason="needs complexipy >= 8.2 on PATH")
def test_real_complexipy_scores_sonar_examples() -> None:
    """The parser against a real complexipy: SonarSource's nesting increments."""
    source = (
        "def nested(items, flag):\n"
        "    total = 0\n"
        "    for item in items:\n"  # +1
        "        if item and flag:\n"  # +2 (nesting 1), +1 (and)
        "            if item > 3:\n"  # +3 (nesting 2)
        "                total += item\n"
        "    return total\n"
    )
    complexipy = shutil.which("complexipy")
    assert complexipy is not None
    ctx = EvalContext(
        module=parse_module(source, "a.py"),
        source=source,
        label="a.py",
        tool_paths={"complexipy": complexipy},
        tool_setup=ToolSetup(runner=subprocess_tool_runner, timeout_s=30.0),
    )

    assert _values(CognitiveComplexityMetric().measure(ctx)) == {"a.py::nested": 7.0}
