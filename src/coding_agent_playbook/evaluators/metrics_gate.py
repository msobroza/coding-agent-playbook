"""The ``playbook metrics`` gate as a library call (prK §F.0.3 item 1, Track Pb P-D3).

:func:`run_metrics_gate` discovers the target files, measures them and their
baseline, optionally runs the suite, and grades everything through one
:class:`~coding_agent_playbook.evaluators.rubric.Rubric` of metric-backed checks
(one per gated metric, built by the shared
:func:`~coding_agent_playbook.evaluators.policy.metric_check` factory). It never
prints, never parses argv and never imports ``cli.py``, argparse or jinja2, so
the Stop stages can call it in-process; ``commands/metrics.py`` is the thin CLI
over it and its output is pinned byte for byte by goldens.

Running the suite is the explicit :attr:`MetricsGateRequest.run_tests` field,
never inferred from ``[metrics] run_tests``, and
:attr:`MetricsGateRequest.test_cmd` is exactly what runs: an agent can edit
``[metrics] test_cmd``, so only the CLI resolves it into a request.

Example::

    >>> root = Path(".")
    >>> request = MetricsGateRequest(repo_root=root, config=load_metrics_config(root))
    >>> run_metrics_gate(request).breached  # doctest: +SKIP
    False
"""

from __future__ import annotations

import tempfile
import tomllib
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.config import parse_metrics_config
from coding_agent_playbook.evaluators._metrics_inputs import (
    MetricsGateUsageError,
    ProjectFactory,
    SourceMeter,
    SuiteRun,
    discover_targets,
    measure_candidates,
    static_baseline,
    suite_baseline,
)
from coding_agent_playbook.evaluators.baseline_git import SubprocessBaselineGit
from coding_agent_playbook.evaluators.check import MeasurementSet
from coding_agent_playbook.evaluators.execution.project import ProjectHandle
from coding_agent_playbook.evaluators.metric import execution_metrics, static_metrics
from coding_agent_playbook.evaluators.parse import parse_module
from coding_agent_playbook.evaluators.policy import metric_check
from coding_agent_playbook.evaluators.rubric import Rubric
from coding_agent_playbook.evaluators.types import EvalContext, MetricConfig

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from coding_agent_playbook.evaluators.baseline_git import BaselineGit
    from coding_agent_playbook.evaluators.check import Check
    from coding_agent_playbook.evaluators.metric import Metric
    from coding_agent_playbook.evaluators.types import EvaluationReport, Measurement, Mode

#: The committed config file whose ``[metrics]`` table seeds the gate.
CONFIG_FILENAME = ".coding-agent-playbook.toml"

#: The name the Rubric carries (stable per run; the gate has one rubric).
_RUBRIC_NAME = "metrics"

__all__ = [
    "CONFIG_FILENAME",
    "MetricsGateDeps",
    "MetricsGateRequest",
    "MetricsGateResult",
    "MetricsGateUsageError",
    "build_rubric",
    "load_metrics_config",
    "run_metrics_gate",
]


@dataclass(frozen=True)
class MetricsGateRequest:
    """One gate run: what to measure, against what, and under which policy.

    ``config`` is the ``[metrics]`` policy; ``mode`` overrides ``config.mode``
    and ``strict`` is OR-ed with ``config.strict``. ``paths`` resolve against the
    process cwd (empty = ``<repo_root>/src``, else ``repo_root``). ``baseline`` is
    ``git:<ref>`` or a directory. ``tool_paths`` fills
    :attr:`EvalContext.tool_paths` for every measurement context.

    Example::

        >>> MetricsGateRequest(repo_root=Path("."), config=MetricConfig()).run_tests
        False
    """

    repo_root: Path
    config: MetricConfig
    paths: tuple[str, ...] = ()
    baseline: str | None = None
    mode: Mode | None = None
    strict: bool = False
    run_tests: bool = False
    test_cmd: tuple[str, ...] | None = None
    tool_paths: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MetricsGateResult:
    """The graded report plus what the CLI prints around it.

    ``config`` is the effective policy (request overrides applied, mode degraded
    to ``absolute`` without a baseline, which ``note`` explains). ``skipped``
    lists ``(label, reason)`` for each candidate that was not measured.

    Example::

        >>> result = run_metrics_gate(request)  # doctest: +SKIP
        >>> result.breached and result.config.fail_on_breach  # the CLI's exit 1
        True
    """

    report: EvaluationReport
    config: MetricConfig
    note: str | None
    skipped: tuple[tuple[str, str], ...]
    measured_count: int

    @property
    def breached(self) -> bool:
        """True when the report did not pass; ``config.fail_on_breach`` decides the exit code."""
        return not self.report.passed


@dataclass(frozen=True)
class MetricsGateDeps:
    """The gate's replaceable collaborators (tests inject named fakes here).

    ``project_factory`` builds the handle a suite run executes;
    ``load_static_metrics`` lists the static metrics to measure; ``git_factory``
    builds the git client for a ``git:`` baseline from ``[metrics] git_timeout_s``.
    """

    project_factory: ProjectFactory = ProjectHandle.create
    load_static_metrics: Callable[[], list[Metric]] = static_metrics
    git_factory: Callable[[float], BaselineGit] = SubprocessBaselineGit


@dataclass
class _Measured:
    """Everything measured for one request, before grading."""

    static: list[Metric]
    execution: list[Metric]
    candidate: list[Measurement]
    baseline: list[Measurement] | None
    skipped: list[tuple[str, str]]
    measured_count: int


def load_metrics_config(repo_root: Path) -> MetricConfig:
    """Parse ``[metrics]`` from ``<repo_root>/.coding-agent-playbook.toml`` if present.

    Only the committed file is read: ``[metrics]`` is team policy, so a personal
    ``.local.toml`` never loosens it. Malformed TOML or an invalid ``[metrics]``
    value raises :class:`MetricsGateUsageError` (the CLI's exit 2).

    Example::

        >>> load_metrics_config(Path("/no/such/repo"))
        MetricConfig(mode='regression', fail_on_breach=True, strict=False, ...)
    """
    config_path = repo_root / CONFIG_FILENAME
    if not config_path.is_file():
        return MetricConfig()
    try:
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
        return parse_metrics_config(data.get("metrics", {}))
    except tomllib.TOMLDecodeError as exc:
        raise MetricsGateUsageError(f"malformed {CONFIG_FILENAME}: {exc}") from exc
    except ValueError as exc:
        raise MetricsGateUsageError(
            f"invalid [metrics] config in {CONFIG_FILENAME}: {exc}"
        ) from exc


def run_metrics_gate(
    request: MetricsGateRequest, *, deps: MetricsGateDeps | None = None
) -> MetricsGateResult:
    """Measure and grade ``request``; raises :class:`MetricsGateUsageError` on bad input.

    ``fail_fast`` is off: the gate wants the complete report (every breach
    surfaced), not a short-circuit.

    Example::

        >>> config = MetricConfig(mode="absolute")
        >>> run_metrics_gate(MetricsGateRequest(Path("."), config, paths=("src",)))  # doctest: +SKIP
        MetricsGateResult(report=EvaluationReport(...), ...)
    """
    measured = _measure(request, deps if deps is not None else MetricsGateDeps())
    config, note = _effective_config(request)
    report = _grade(measured, config, request.repo_root)
    return MetricsGateResult(
        report=report,
        config=config,
        note=note,
        skipped=tuple(measured.skipped),
        measured_count=measured.measured_count,
    )


def _measure(request: MetricsGateRequest, deps: MetricsGateDeps) -> _Measured:
    """Static candidate + baseline measurements, then the suite when requested."""
    git = deps.git_factory(request.config.git_timeout_s)
    static = deps.load_static_metrics()
    meter = SourceMeter(static, request.tool_paths)
    targets = discover_targets(request.paths, request.repo_root)
    baseline = (
        None
        if request.baseline is None
        else static_baseline(request.baseline, targets, request.repo_root, meter, git)
    )
    candidates = measure_candidates(targets, request.repo_root, meter)
    measured = _Measured(
        static, [], candidates.measurements, baseline, candidates.skipped, candidates.measured_count
    )
    if request.run_tests:
        measured.execution = execution_metrics()
        _measure_suites(request, measured, deps.project_factory, git)
    return measured


def _measure_suites(
    request: MetricsGateRequest, measured: _Measured, factory: ProjectFactory, git: BaselineGit
) -> None:
    """Run the suite once on the candidate and, with a baseline, once on the baseline."""
    test_cmd = None if request.test_cmd is None else list(request.test_cmd)
    suite = SuiteRun(measured.execution, test_cmd, factory, request.tool_paths)
    with tempfile.TemporaryDirectory(prefix="playbook-metrics-") as tmp:
        work_dir = Path(tmp)
        measured.candidate.extend(suite.measure(request.repo_root, work_dir / "candidate-reports"))
        if request.baseline is not None:
            exec_baseline = suite_baseline(
                request.baseline, request.repo_root, suite, work_dir, git
            )
            measured.baseline = (measured.baseline or []) + exec_baseline


def _effective_config(request: MetricsGateRequest) -> tuple[MetricConfig, str | None]:
    """Request overrides config; ``regression``/``both`` without a baseline become ``absolute``."""
    mode = request.mode or request.config.mode
    strict = request.config.strict or request.strict
    note: str | None = None
    if request.baseline is None and mode in ("regression", "both"):
        note = f"no --baseline given; '{mode}' mode falls back to 'absolute'."
        mode = "absolute"
    return replace(request.config, mode=mode, strict=strict), note


def build_rubric(metrics: Sequence[Metric], config: MetricConfig) -> Rubric:
    """One metric-backed :class:`Check` per metric, in order, as the gate's :class:`Rubric`.

    Each check comes from the shared ``metric_check`` factory (the eval-task
    compiler uses the same one): ``config``'s per-metric override when present,
    else the metric's ported default. Unknown metric names get no check.

    Example::

        >>> build_rubric(static_metrics(), MetricConfig(mode="absolute")).name
        'metrics'
    """
    checks: list[Check] = []
    for metric in metrics:
        check = metric_check(metric.name, config)
        if check is not None:
            checks.append(check)
    return Rubric(checks, name=_RUBRIC_NAME)


def _grade(measured: _Measured, config: MetricConfig, repo_root: Path) -> EvaluationReport:
    """Grade the pre-built measurements; nothing is re-measured here."""
    rubric = build_rubric([*measured.static, *measured.execution], config)
    measurements = MeasurementSet(measured.candidate, measured.baseline)
    with ExitStack() as stack:
        ctx = _grading_ctx(measured, repo_root, stack)
        return rubric.evaluate(ctx, measurements, strict=config.strict, fail_fast=False)


def _grading_ctx(measured: _Measured, repo_root: Path, stack: ExitStack) -> EvalContext:
    """An :class:`EvalContext` whose slots satisfy the metric checks' availability.

    The metric-backed checks gate availability on the slot the metric does
    (``ctx.module`` for static, ``ctx.project`` for execution). A parsed empty
    module and a lazy :class:`ProjectHandle` flip them on; the handle only runs
    pytest when :meth:`ProjectHandle.run` is called, which grading never does,
    and its throwaway report dir is removed when ``stack`` exits. The
    measurements ride along so a nested rubric could self-measure.
    """
    module = parse_module("", _RUBRIC_NAME) if measured.static else None
    project = None
    if measured.execution:
        report_dir = Path(
            stack.enter_context(tempfile.TemporaryDirectory(prefix="playbook-metrics-avail-"))
        )
        project = ProjectHandle.create(repo_root, report_dir)
    return EvalContext(
        module=module,
        source="",
        label=_RUBRIC_NAME,
        project=project,
        candidate_measurements=measured.candidate,
        baseline_measurements=measured.baseline,
    )
