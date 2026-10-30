"""The release report: what changed in a release's committed metrics (spec D4).

A pure module: it reads the committed release metrics files
(``<releases>/<version>/metrics/<target>.json``) and returns data; it plots
nothing and decides no score. :func:`load_history` validates every file, in
SemVer order. :func:`release_report` compares each target of one release with
its *baseline*: the release the gate compared it with, which the regression
check recorded as the file's ``previous`` (``annotate_release_metrics``), looked
up for the same target. Verdicts come from
``evals.release_regression.check_regressions`` against that file, so the report
and the release gate always agree. A target the release no longer has is
ignored; one whose file records no ``previous``, or names a release without a
file for the target, has no baseline and is reported without deltas or
verdicts, like a first release. The trend still covers every release.

Per task it pools passes over runs (``evals.release_metrics.entries_summary``)
and counts the verdicts; the trend holds each task's numbers in every release
up to this one, marking a release whose judge changed: its file records
``judge_change`` (it re-judged), or its judge parts differ from the target's
file in the release before it (no answers to re-judge, e.g. the first change
after v0.4.0). The
Markdown (``evals.release_report_markdown``), CSV and agreement rows render
these for the release PR and its assets.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, get_args

from packaging.version import InvalidVersion, Version

from coding_agent_playbook.evals.answers_store import judge_parts_of
from coding_agent_playbook.evals.release_metrics import entries_summary
from coding_agent_playbook.evals.release_metrics_schema import (
    JUDGE_CHANGE_KEY,
    ReleaseMetricsError,
    validate_release_metrics,
)
from coding_agent_playbook.evals.release_regression import (
    RegressionCheck,
    SampleStatus,
    check_regressions,
)
from coding_agent_playbook.evals.release_report_markdown import (
    MARKDOWN_LIMIT,
    TRUNCATION_POINTER,
    render_markdown,
)
from coding_agent_playbook.evals.release_report_rows import agreement_rows, csv_rows
from coding_agent_playbook.exit_two import ExitTwoError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

__all__ = [
    "MARKDOWN_LIMIT",
    "TRUNCATION_POINTER",
    "MetricsHistory",
    "ReleaseReport",
    "ReleaseReportError",
    "TargetReport",
    "TaskDelta",
    "TrendPoint",
    "load_history",
    "release_report",
    "target_report",
]

type MetricsFile = Mapping[str, Any]

#: The directory of a release that holds its metrics files (``scripts/release_eval.py``).
METRICS_DIRNAME: Final = "metrics"
#: Every verdict a task counts, in the order the regression check names them.
STATUSES: Final[tuple[SampleStatus, ...]] = get_args(SampleStatus.__value__)


class ReleaseReportError(ExitTwoError):
    """A release with no metrics files, or a metrics file that cannot be read.

    Example::

        >>> str(ReleaseReportError("no metrics at r/9.9.7/metrics"))
        'no metrics at r/9.9.7/metrics'
    """


@dataclass(frozen=True)
class MetricsHistory:
    """The validated metrics ``files`` under ``root``: by release (SemVer order), then by target.

    Example::

        >>> load_history(Path("catalog/releases")).releases  # doctest: +SKIP
        ('9.9.3', '9.9.4')
    """

    root: Path
    files: Mapping[str, Mapping[str, MetricsFile]]

    @property
    def releases(self) -> tuple[str, ...]:
        """Every release with a metrics file, oldest first."""
        return tuple(self.files)

    def up_to(self, version: str) -> tuple[str, ...]:
        """The releases up to and including ``version``, oldest first."""
        return tuple(r for r in self.releases if Version(r) <= Version(version))

    def baseline(self, version: str, target: str) -> MetricsFile | None:
        """The file of ``target`` in the release its ``version`` file records as ``previous``.

        ``None`` when the file records no ``previous`` (the gate compared it with
        nothing) or that release has no file for ``target``.
        """
        previous = self.files[version][target].get("previous")
        return self.files.get(str(previous), {}).get(target) if previous else None


@dataclass(frozen=True)
class TaskDelta:
    """One task of one target: pooled pass rates and means, before and now, and verdict counts.

    ``previous_*`` are ``None`` when the baseline lacks the task (or there is
    no baseline); ``counts`` maps every verdict status to its sample count.
    """

    target: str
    task: str
    previous_pass_rate: float | None
    pass_rate: float
    previous_mean: float | None
    mean: float
    counts: Mapping[str, int]


@dataclass(frozen=True)
class TrendPoint:
    """One task's pass rate and mean score in one release, and whether its judge changed."""

    release: str
    target: str
    task: str
    pass_rate: float
    mean: float
    judge_changed: bool


@dataclass(frozen=True)
class TargetReport:
    """One target's file in a release, its ``baseline`` file and the regression ``check``.

    ``baseline`` and ``check`` are ``None`` when the file records no ``previous``
    (the gate compared it with nothing) or that release has no file for the target.
    """

    target: str
    data: MetricsFile
    baseline: MetricsFile | None
    check: RegressionCheck | None

    @property
    def previous(self) -> str | None:
        """The baseline's release, else ``None``."""
        return None if self.baseline is None else str(self.baseline["release"])


@dataclass(frozen=True)
class ReleaseReport:
    """The report of ``version``: one :class:`TargetReport` per target, task deltas and trend.

    Example::

        >>> report = release_report(load_history(Path("catalog/releases")), "9.9.4")  # doctest: +SKIP
        >>> report.markdown().startswith("# Release metrics: 9.9.4")  # doctest: +SKIP
        True
    """

    version: str
    history: MetricsHistory
    targets: tuple[TargetReport, ...]
    tasks: tuple[TaskDelta, ...]
    trend: tuple[TrendPoint, ...]

    def target(self, name: str) -> TargetReport:
        """The section of target ``name``; raise :class:`ReleaseReportError` if absent."""
        for section in self.targets:
            if section.target == name:
                return section
        names = ", ".join(s.target for s in self.targets)
        raise ReleaseReportError(f"{self.version} has no target {name!r} (targets: {names})")

    def markdown(self, limit: int = MARKDOWN_LIMIT) -> str:
        """The report as Markdown, cut at a section boundary when over ``limit`` characters."""
        return render_markdown(self, limit)

    def csv_rows(self) -> list[dict[str, str]]:
        """One row per release, target and sample, up to this release (D4 columns)."""
        return csv_rows(self._history_sections())

    def agreement_rows(self) -> list[dict[str, str]]:
        """One row per task of each file with a judge change, up to this release."""
        return agreement_rows([section.data for section in self._history_sections()])

    def _history_sections(self) -> list[TargetReport]:
        """Every target of every release up to this one, each checked against its baseline."""
        history, releases = self.history, self.history.up_to(self.version)
        return [target_report(history, r, name) for r in releases for name in history.files[r]]


def load_history(releases_root: Path) -> MetricsHistory:
    """Read and validate ``<releases_root>/*/metrics/*.json``, by release then target.

    Raises :class:`ReleaseReportError` naming the file that cannot be read or
    fails the schema, or the release directory that is not a version.

    Example::

        >>> load_history(Path("catalog/releases")).files["9.9.4"].keys()  # doctest: +SKIP
        dict_keys(['claude-opus', 'opencode-qwen'])
    """
    files: dict[str, dict[str, MetricsFile]] = {}
    for path in sorted(releases_root.glob(f"*/{METRICS_DIRNAME}/*.json")):
        release = _release_of(path)
        data = _read(path)
        files.setdefault(release, {})[str(data["target"]["name"])] = data
    ordered = sorted(files, key=Version)
    return MetricsHistory(releases_root, {r: dict(sorted(files[r].items())) for r in ordered})


def release_report(history: MetricsHistory, version: str) -> ReleaseReport:
    """The report of ``version``'s targets against their baselines, with the trend up to it.

    Raises :class:`ReleaseReportError` naming the missing metrics directory and
    the versions that have one.

    Example::

        >>> release_report(history, "9.9.4").targets[0].previous  # doctest: +SKIP
        '9.9.3'
    """
    if version not in history.files:
        missing = history.root / version / METRICS_DIRNAME
        known = ", ".join(history.releases) or "none"
        raise ReleaseReportError(f"no metrics files at {missing}; releases with metrics: {known}")
    targets = tuple(target_report(history, version, name) for name in history.files[version])
    tasks = tuple(delta for section in targets for delta in _task_deltas(section))
    trend = tuple(point for s in targets for point in _trend(history, version, s.target))
    return ReleaseReport(version, history, targets, tasks, trend)


def target_report(history: MetricsHistory, version: str, target: str) -> TargetReport:
    """``target``'s file in ``version`` checked against its baseline, when it has one."""
    data = history.files[version][target]
    baseline = history.baseline(version, target)
    check = None if baseline is None else check_regressions(data, baseline)
    return TargetReport(target, data, baseline, check)


def by_task(data: MetricsFile) -> dict[str, dict[str, Mapping[str, Any]]]:
    """The file's sample entries grouped by task (``prompt_id``), tasks and samples sorted."""
    grouped: dict[str, dict[str, Mapping[str, Any]]] = {}
    for sample_id, entry in sorted(data["samples"].items()):
        grouped.setdefault(str(entry["prompt_id"]), {})[sample_id] = entry
    return dict(sorted(grouped.items()))


def pooled(entries: Mapping[str, Mapping[str, Any]]) -> tuple[float, float]:
    """The pass rate (passes over runs) and the mean of the per-sample means of ``entries``."""
    summary = entries_summary(entries)
    return _as_float(summary["pass_rate"]), _as_float(summary["mean_score"])


def _as_float(value: object) -> float:
    """A summary number as a float (``None``, the mean of no entries, as 0)."""
    if value is None:
        return 0.0
    if not isinstance(value, int | float):
        raise ReleaseReportError(f"expected a number in the summary, got {value!r}")
    return float(value)


def _task_deltas(section: TargetReport) -> list[TaskDelta]:
    previous = by_task(section.baseline) if section.baseline is not None else {}
    statuses = {v.sample_id: v.status for v in section.check.samples} if section.check else {}
    deltas = []
    for task, entries in by_task(section.data).items():
        rate, mean = pooled(entries)
        old = pooled(previous[task]) if task in previous else (None, None)
        counts = _counts([statuses[s] for s in entries if s in statuses])
        deltas.append(TaskDelta(section.target, task, old[0], rate, old[1], mean, counts))
    return deltas


def _counts(statuses: Sequence[str]) -> dict[str, int]:
    return {status: statuses.count(status) for status in STATUSES}


def _trend(history: MetricsHistory, version: str, target: str) -> list[TrendPoint]:
    points = []
    earlier: MetricsFile | None = None
    for release in history.up_to(version):
        data = history.files[release].get(target)
        if data is None:
            continue
        changed = _judge_changed(earlier, data)
        for task, entries in by_task(data).items():
            rate, mean = pooled(entries)
            points.append(TrendPoint(release, target, task, rate, mean, changed))
        earlier = data
    return points


def _judge_changed(earlier: MetricsFile | None, data: MetricsFile) -> bool:
    """Whether ``data`` re-judged, or its judge parts differ from ``earlier``'s (spec D4/D5)."""
    if isinstance(data.get(JUDGE_CHANGE_KEY), dict):
        return True
    if earlier is None:
        return False
    before, now = _judge_parts(earlier), _judge_parts(data)
    # A file without ``setup`` knows its judge model only: compare the parts both know.
    return any(before[key] != now[key] for key in before.keys() & now.keys())


def _judge_parts(data: MetricsFile) -> dict[str, object]:
    """The file's judge parts: from ``setup``, else ``target.judge_model`` alone."""
    setup = data.get("setup")
    if isinstance(setup, dict):
        return judge_parts_of(setup)
    return {"judge_model": data["target"].get("judge_model")}


def _release_of(path: Path) -> str:
    """The release a metrics file belongs to: its release directory, which must be a version."""
    release = path.parent.parent.name
    try:
        Version(release)
    except InvalidVersion as error:
        raise ReleaseReportError(
            f"{path}: release directory {release!r} is not a version"
        ) from error
    return release


def _read(path: Path) -> MetricsFile:
    """The validated metrics file at ``path``; raise naming the path when it is unusable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        validate_release_metrics(data)
    except (OSError, ValueError, ReleaseMetricsError) as error:
        raise ReleaseReportError(f"{path}: {error}") from error
    loaded: MetricsFile = data
    return loaded
