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

Which metrics run is the ruff-shaped selection (prK §F.0.3 item 2): the
request's ``select`` / ``extend_select`` / ``ignore`` override ``[metrics]``'s,
key by key. A name the request itself passes is checked strictly, so naming an
execution metric without ``run_tests`` is a usage error; one only ``[metrics]``
names is dropped when the suite does not run, so the static twins
(``--no-run-tests``, the Stop stages) keep working on a config written for test
runs. Targets matching ``[metrics] exclude`` are never measured, and
``changed_only`` keeps those changed since the ``git:`` baseline.

Example::

    >>> root = Path(".")
    >>> request = MetricsGateRequest(repo_root=root, config=load_metrics_config(root))
    >>> run_metrics_gate(request).breached  # doctest: +SKIP
    False
"""

from __future__ import annotations

import shutil
import tempfile
import tomllib
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators._metrics_inputs import (
    GIT_PREFIX,
    JSON_PREFIX,
    MAX_FILE_BYTES,
    MetricsGateUsageError,
    SourceMeter,
    discover_targets,
    filter_targets,
    git_usage_error,
    measure_candidates,
    static_baseline,
    verify_git_ref,
)
from coding_agent_playbook.evaluators._metrics_suite import (
    ProjectFactory,
    gate_suite,
    run_suites,
    without_diff_based,
)
from coding_agent_playbook.evaluators.baseline_git import (
    BaselineGitError,
    SubprocessBaselineGit,
    SubprocessGitRunner,
    changed_paths,
)
from coding_agent_playbook.evaluators.check import MeasurementSet
from coding_agent_playbook.evaluators.execution.project import ProjectHandle
from coding_agent_playbook.evaluators.measurement_snapshot import (
    SnapshotError,
    read_snapshot,
    write_snapshot,
)
from coding_agent_playbook.evaluators.metric import execution_metrics, static_metrics
from coding_agent_playbook.evaluators.parse import parse_module
from coding_agent_playbook.evaluators.policy import metric_check, resolve_metric_selection
from coding_agent_playbook.evaluators.rubric import Rubric
from coding_agent_playbook.evaluators.tool_runner import MemoToolRunner, subprocess_tool_runner
from coding_agent_playbook.evaluators.types import EvalContext, MetricConfig, ToolSetup
from coding_agent_playbook.metrics_config import parse_metrics_config

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from coding_agent_playbook.evaluators.baseline_git import BaselineGit, GitRunner
    from coding_agent_playbook.evaluators.check import Check
    from coding_agent_playbook.evaluators.metric import Metric
    from coding_agent_playbook.evaluators.tool_runner import ToolRunner
    from coding_agent_playbook.evaluators.types import EvaluationReport, Measurement, Mode

#: The committed config file whose ``[metrics]`` table seeds the gate.
CONFIG_FILENAME = ".coding-agent-playbook.toml"

#: The name the Rubric carries (stable per run; the gate has one rubric).
_RUBRIC_NAME = "metrics"

__all__ = [
    "CONFIG_FILENAME",
    "MAX_FILE_BYTES",
    "MetricsGateDeps",
    "MetricsGateRequest",
    "MetricsGateResult",
    "MetricsGateUsageError",
    "build_rubric",
    "cli_tool_paths",
    "load_metrics_config",
    "run_metrics_gate",
    "tool_setup",
]


@dataclass(frozen=True)
class MetricsGateRequest:
    """One gate run: what to measure, against what, and under which policy.

    ``config`` is the ``[metrics]`` policy; ``mode`` overrides ``config.mode``
    and ``strict`` is OR-ed with ``config.strict``. ``paths`` resolve against the
    process cwd (empty = ``<repo_root>/src``, else ``repo_root``). ``baseline`` is
    ``git:<ref>``, ``json:<snapshot>`` or a directory. ``tool_paths`` fills
    :attr:`EvalContext.tool_paths` for every measurement context. A candidate or
    baseline file over ``max_file_bytes`` is never parsed (a skip note for a
    candidate, all-new for a baseline).

    ``select`` / ``extend_select`` / ``ignore`` replace their ``[metrics]`` key
    when not ``None``. ``changed_only`` needs a ``git:`` baseline.
    ``emit_measurements`` writes the raw candidate measurements there as a
    snapshot of ``snapshot_tree`` (the caller's ``HEAD^{tree}`` or fingerprint;
    ``None`` when the worktree is not one).

    ``diff_base`` is the ref diff-based metrics (``diff_coverage``) diff the
    candidate against; ``None`` takes a ``git:`` baseline's ref, so a hook
    grading against a ``json:`` snapshot passes it explicitly.
    ``[metrics] test_timeout_s`` bounds each suite run.

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
    max_file_bytes: int = MAX_FILE_BYTES
    select: tuple[str, ...] | None = None
    extend_select: tuple[str, ...] | None = None
    ignore: tuple[str, ...] | None = None
    changed_only: bool = False
    emit_measurements: Path | None = None
    snapshot_tree: str | None = None
    diff_base: str | None = None


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
    ``load_static_metrics`` lists the static metrics to select from;
    ``git_factory`` builds the git client for a ``git:`` baseline from
    ``[metrics] git_timeout_s``, and ``git_runner_factory`` the working-tree
    reader ``changed_only`` lists files with (a hook passes its ``SafeGit``).
    ``tool_runner`` runs a subprocess-backed metric's tool (a hook passes one
    over its ``ProcPort``); the gate memoizes it per run. ``which`` is how the
    CLI finds ``ruff`` for :attr:`MetricsGateRequest.tool_paths`.
    ``changed_lines`` lists the lines changed since a diff base for
    ``diff_coverage`` instead of a git read (``None``: git through
    ``git_runner_factory``); the coverage Stop stage passes its own listing.
    """

    project_factory: ProjectFactory = ProjectHandle.create
    load_static_metrics: Callable[[], list[Metric]] = static_metrics
    git_factory: Callable[[float], BaselineGit] = SubprocessBaselineGit
    git_runner_factory: Callable[[Path, float], GitRunner] = SubprocessGitRunner
    tool_runner: ToolRunner = subprocess_tool_runner
    which: Callable[[str], str | None] = shutil.which
    changed_lines: Callable[[Path, str], Mapping[str, frozenset[int]]] | None = None


@dataclass
class _Measured:
    """Everything measured for one request, before grading."""

    static: list[Metric]
    execution: list[Metric]
    candidate: list[Measurement]
    baseline: list[Measurement] | None
    skipped: list[tuple[str, str]]
    measured_count: int
    tool_paths: Mapping[str, str] = field(default_factory=dict)


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
    """Static candidate + baseline measurements, the suite when selected, then the snapshot."""
    git = deps.git_factory(request.config.git_timeout_s)
    static, execution = _selected_metrics(request, deps)
    setup = tool_setup(request, deps)
    meter = SourceMeter(static, request.tool_paths, request.max_file_bytes, setup)
    targets = _targets(request, deps, git)
    baseline = without_diff_based(_baseline(request, targets, meter, git), execution)
    candidates = measure_candidates(targets, request.repo_root, meter)
    measured = _Measured(
        static,
        execution,
        candidates.measurements,
        baseline,
        candidates.skipped,
        candidates.measured_count,
        request.tool_paths,
    )
    if measured.execution:
        suite = gate_suite(request, execution, deps.project_factory, setup)
        candidate, suite_base = run_suites(suite, request.repo_root, request.baseline, git=git)
        measured.candidate.extend(candidate)
        if suite_base:
            measured.baseline = (measured.baseline or []) + suite_base
    if request.emit_measurements is not None:
        _emit(request.emit_measurements, measured.candidate, request.snapshot_tree)
    return measured


def tool_setup(request: MetricsGateRequest, deps: MetricsGateDeps) -> ToolSetup:
    """How this run's subprocess-backed metrics run: memoized runner, repo root, ``[metrics]`` ruff.

    The memo is per run: an unchanged file's identical candidate and baseline
    text costs one ruff call. ``diff_coverage`` reads git through the same
    ``git_runner_factory`` as ``changed_only`` and skips ``[metrics] exclude``.

    Example::

        >>> tool_setup(request, MetricsGateDeps()).cwd == request.repo_root  # doctest: +SKIP
        True
    """
    return ToolSetup(
        cwd=request.repo_root,
        runner=MemoToolRunner(deps.tool_runner),
        timeout_s=request.config.git_timeout_s,
        ruff=request.config.ruff_settings,
        git=deps.git_runner_factory,
        exclude=request.config.exclude,
        changed_lines=deps.changed_lines,
    )


def cli_tool_paths(which: Callable[[str], str | None]) -> dict[str, str]:
    """The consumer-toolchain binaries ``which`` finds on ``PATH`` (``ruff``), for the CLI.

    Example::

        >>> cli_tool_paths(lambda name: None)
        {}
    """
    found = which("ruff")
    return {} if found is None else {"ruff": found}


def _selected_metrics(
    request: MetricsGateRequest, deps: MetricsGateDeps
) -> tuple[list[Metric], list[Metric]]:
    """The selected ``(static, execution)`` metrics; execution only when the suite runs."""
    available = [*deps.load_static_metrics(), *execution_metrics()]
    config = request.config
    try:
        if not request.run_tests:
            # Only the request's own names are strict: [metrics] also serves test
            # runs, so its execution metrics are dropped below, not rejected.
            requested = (*(request.select or ()), *(request.extend_select or ()))
            resolve_metric_selection(available, select=(), extend_select=requested)
        chosen = resolve_metric_selection(
            available,
            select=config.select if request.select is None else request.select,
            extend_select=_override(request.extend_select, config.extend_select),
            ignore=_override(request.ignore, config.ignore),
            run_tests=True,
        )
    except ValueError as exc:
        raise MetricsGateUsageError(str(exc)) from exc
    static = [metric for metric in chosen if not metric.needs_project]
    execution = [metric for metric in chosen if metric.needs_project and request.run_tests]
    return static, execution


def _override(
    request_value: tuple[str, ...] | None, config_value: tuple[str, ...]
) -> tuple[str, ...]:
    return config_value if request_value is None else request_value


def _targets(request: MetricsGateRequest, deps: MetricsGateDeps, git: BaselineGit) -> list[Path]:
    """Discovered targets minus ``[metrics] exclude``; only the changed ones under ``changed_only``."""
    targets = discover_targets(request.paths, request.repo_root)
    changed = _changed_files(request, deps, git) if request.changed_only else None
    return filter_targets(
        targets, request.repo_root, exclude=request.config.exclude, changed=changed
    )


def _changed_files(
    request: MetricsGateRequest, deps: MetricsGateDeps, git: BaselineGit
) -> frozenset[str]:
    """The files changed since the ``git:`` baseline, plus untracked ones (repo-relative)."""
    baseline = request.baseline or ""
    if not baseline.startswith(GIT_PREFIX):
        raise MetricsGateUsageError(
            f"--changed needs a git: baseline (--baseline git:<ref>), got {request.baseline!r}"
        )
    ref = baseline[len(GIT_PREFIX) :]
    verify_git_ref(git, request.repo_root, ref)
    runner = deps.git_runner_factory(request.repo_root, request.config.git_timeout_s)
    try:
        return changed_paths(runner, ref)
    except BaselineGitError as exc:
        raise git_usage_error(exc, f"cannot list the files changed since {ref!r}") from exc


def _baseline(
    request: MetricsGateRequest, targets: Sequence[Path], meter: SourceMeter, git: BaselineGit
) -> list[Measurement] | None:
    """The static baseline; a ``json:`` snapshot already holds every measurement."""
    if request.baseline is None:
        return None
    if request.baseline.startswith(JSON_PREFIX):
        try:
            return read_snapshot(Path(request.baseline[len(JSON_PREFIX) :]))
        except SnapshotError as exc:
            raise MetricsGateUsageError(str(exc)) from exc
    return static_baseline(request.baseline, targets, request.repo_root, meter, git)


def _emit(path: Path, measurements: Sequence[Measurement], tree: str | None) -> None:
    try:
        write_snapshot(path, measurements, tree=tree)
    except OSError as exc:
        raise MetricsGateUsageError(f"cannot write --emit-measurements {path}: {exc}") from exc


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
    (``ctx.module`` for static, ``ctx.project`` for execution, the measuring
    ``tool_paths`` for ``ruff_violations``). A parsed empty
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
        tool_paths=measured.tool_paths,
    )
