"""The release bundle's charts (spec D5); ``scripts/release_report.py`` imports this only for charts.

matplotlib is not an engine dependency: this module imports it at the top, so
importing it without matplotlib raises ``ImportError`` and the bundle script
names ``--no-charts``. Charts follow the repo's dataviz conventions: one hue per
job (blue for the new release and gray for the previous one in the paired task
bars; a blue-red diverging scale with a gray midpoint for sample deltas, every
cell labelled; one categorical hue per target in the trend, in a fixed order),
no dual axis, labels in neutral ink, and a legend whenever there are two or more
series. A release with no baseline gets no delta chart.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Final, cast

import matplotlib

matplotlib.use("Agg")  # headless: CI runners and scripts have no display

import matplotlib.pyplot as plt  # after the backend is chosen
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.lines import Line2D

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.evals.release_report import ReleaseReport, TaskDelta

TASK_DELTAS: Final = "task-deltas.png"
SAMPLE_DELTAS: Final = "sample-deltas.png"
TASK_TREND: Final = "task-trend.png"

INK: Final = "#0b0b0b"
INK_SECONDARY: Final = "#52514e"
SURFACE: Final = "#fcfcfb"
GRID: Final = "#e1e0d9"
NEW_BLUE: Final = "#2a78d6"
PREVIOUS_GRAY: Final = "#a9a8a0"
MIDPOINT_GRAY: Final = "#f0efec"
DIVERGING: Final = ("#c23a39", MIDPOINT_GRAY, "#1c5cab")  # worse, unchanged, better
#: The categorical order: a target's hue follows its name's place in the release, never its rank.
SERIES: Final = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6")
DPI: Final = 150
TREND_COLUMNS: Final = 3
JUDGE_CHANGE_LABEL: Final = "judge change"

_STYLE: Final = {
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "text.color": INK,
    "axes.labelcolor": INK_SECONDARY,
    "axes.edgecolor": GRID,
    "xtick.color": INK_SECONDARY,
    "ytick.color": INK_SECONDARY,
    "font.size": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
}


def write_charts(report: ReleaseReport, out: Path) -> list[Path]:
    """Write the release's charts into ``out``; return the files written.

    The two delta charts are left out when no target has a baseline (or no
    sample was compared); the trend is always written.

    Example::

        >>> [p.name for p in write_charts(report, Path("bundle"))]  # doctest: +SKIP
        ['task-deltas.png', 'sample-deltas.png', 'task-trend.png']
    """
    # matplotlib's stubs key rc_context by a Literal of rc names, which a plain
    # dict never matches; Any type-checks with and without matplotlib installed.
    with plt.rc_context(cast("Any", _STYLE)):
        written = [
            _task_deltas(report, out / TASK_DELTAS),
            _sample_deltas(report, out / SAMPLE_DELTAS),
            _task_trend(report, out / TASK_TREND),
        ]
    return [path for path in written if path is not None]


def _save(figure: Any, path: Path) -> Path:
    figure.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(figure)
    return path


def _task_deltas(report: ReleaseReport, path: Path) -> Path | None:
    """Per target with a baseline: paired horizontal bars, previous (gray) vs new (blue)."""
    sections = [s for s in report.targets if s.previous is not None]
    if not sections:
        return None
    rows = max(len(_tasks_of(report, s.target)) for s in sections)
    size = (5.2 * len(sections), 0.55 * rows + 1.4)
    figure, axes = plt.subplots(1, len(sections), figsize=size, squeeze=False)
    for axis, section in zip(axes[0], sections, strict=True):
        _paired_bars(axis, _tasks_of(report, section.target))
        axis.set_title(f"{section.target}: {section.previous} → {report.version}", loc="left")
    _legend(figure, [(PREVIOUS_GRAY, "previous release"), (NEW_BLUE, report.version)])
    return _save(figure, path)


def _tasks_of(report: ReleaseReport, target: str) -> list[TaskDelta]:
    return [task for task in report.tasks if task.target == target]


def _paired_bars(axis: Any, tasks: list[TaskDelta]) -> None:
    height = 0.38
    for row, task in enumerate(reversed(tasks)):
        _bar(axis, row + height / 2, task.previous_pass_rate, PREVIOUS_GRAY, height)
        _bar(axis, row - height / 2, task.pass_rate, NEW_BLUE, height)
    axis.set_yticks(range(len(tasks)), [task.task for task in reversed(tasks)])
    axis.set_xlim(0, 1.15)
    axis.set_xlabel("pass rate")
    axis.tick_params(axis="y", length=0)
    axis.xaxis.grid(visible=True, color=GRID, linewidth=0.6)
    axis.set_axisbelow(True)


def _bar(axis: Any, y: float, value: float | None, color: str, height: float) -> None:
    """One bar with its value at the end; a task the baseline lacks says so."""
    if value is None:
        axis.text(0.01, y, "not in baseline", va="center", fontsize=7, color=INK_SECONDARY)
        return
    axis.barh(y, value, height=height * 0.92, color=color)
    axis.text(value + 0.01, y, f"{value:.2f}", va="center", fontsize=7, color=INK_SECONDARY)


def _legend(figure: Any, entries: list[tuple[str, str]]) -> None:
    """A legend under the plots for two or more series; one series is named by the title."""
    if len(entries) < 2:
        figure.tight_layout()
        return
    handles = [_handle(color, label) for color, label in entries]
    labels = [label for _, label in entries]
    figure.legend(handles, labels, loc="lower center", ncols=len(entries), frameon=False)
    figure.tight_layout(rect=(0, 0.08, 1, 1))


def _handle(color: str, label: str) -> Any:
    """A swatch for a series; a dashed line for the judge-change marker."""
    if label.startswith(JUDGE_CHANGE_LABEL):
        return Line2D([], [], color=color, linewidth=1, linestyle="--")
    return Line2D([], [], color=color, linewidth=6)


def _sample_deltas(report: ReleaseReport, path: Path) -> Path | None:
    """Rows are the compared samples (not carried), columns the targets: Δ mean, labelled."""
    targets, cells = _delta_cells(report)
    samples = sorted({sample for sample, _ in cells})
    if not samples:
        return None
    grid = [[cells.get((s, t), math.nan) for t in targets] for s in samples]
    limit = max(0.05, max(abs(v) for v in cells.values()))
    width = 2.2 + 1.4 * len(targets) + 0.06 * max(len(s) for s in samples)
    figure, axis = plt.subplots(figsize=(width, 0.32 * len(samples) + 1.6))
    colors = LinearSegmentedColormap.from_list("delta", DIVERGING).with_extremes(bad=SURFACE)
    image = axis.imshow(grid, cmap=colors, norm=Normalize(-limit, limit), aspect="auto")
    _label_cells(axis, grid, limit)
    axis.set_xticks(range(len(targets)), targets)
    axis.set_yticks(range(len(samples)), samples)
    axis.tick_params(length=0, labeltop=True, labelbottom=False)
    axis.set_title(f"Δ mean score per sample, {report.version} vs its baseline", loc="left")
    figure.colorbar(image, ax=axis, label="Δ mean (blue better, red worse)", shrink=0.6)
    return _save(figure, path)


def _delta_cells(report: ReleaseReport) -> tuple[list[str], dict[tuple[str, str], float]]:
    """The targets with a check and each compared sample's delta, keyed by (sample, target)."""
    targets = [s.target for s in report.targets if s.check is not None]
    cells = {}
    for section in report.targets:
        verdicts = section.check.samples if section.check is not None else ()
        for verdict in verdicts:
            if verdict.status != "carried" and verdict.delta is not None:
                cells[(verdict.sample_id, section.target)] = verdict.delta
    return targets, cells


def _label_cells(axis: Any, grid: list[list[float]], limit: float) -> None:
    for row, values in enumerate(grid):
        for column, value in enumerate(values):
            text, color = _cell_label(value, limit)
            axis.text(column, row, text, ha="center", va="center", fontsize=7, color=color)


def _cell_label(value: float, limit: float) -> tuple[str, str]:
    """The cell's text and ink: ``n/a`` for a sample the target lacks, white on strong fills."""
    if math.isnan(value):
        return "n/a", INK_SECONDARY
    return f"{value:+.2f}", SURFACE if abs(value) > 0.6 * limit else INK


def _task_trend(report: ReleaseReport, path: Path) -> Path:
    """Per task: pass rate over releases, one line per target, dashed at each judge change."""
    # Only the releases that measured one of this release's targets: no empty columns.
    measured = {point.release for point in report.trend}
    releases = [r for r in report.history.up_to(report.version) if r in measured]
    tasks = sorted({point.task for point in report.trend})
    rows = math.ceil(len(tasks) / TREND_COLUMNS) or 1
    columns = min(TREND_COLUMNS, len(tasks)) or 1
    size = (3.6 * columns, 2.4 * rows + 0.8)
    figure, axes = plt.subplots(rows, columns, figsize=size, squeeze=False, sharey=True)
    for index, axis in enumerate(axes.flat):
        if index >= len(tasks):
            axis.set_visible(False)
            continue
        _trend_panel(axis, report, tasks[index], releases)
    figure.suptitle(_trend_title(report), x=0.01, ha="left")
    _legend(figure, _trend_legend(report))
    return _save(figure, path)


def _trend_panel(axis: Any, report: ReleaseReport, task: str, releases: list[str]) -> None:
    for target, color in _target_colors(report).items():
        points = [p for p in report.trend if p.task == task and p.target == target]
        x = [releases.index(p.release) for p in points]
        axis.plot(x, [p.pass_rate for p in points], color=color, linewidth=2, marker="o")
    for release in sorted({p.release for p in report.trend if p.judge_changed}):
        axis.axvline(releases.index(release), color=INK_SECONDARY, linestyle="--", linewidth=1)
    axis.set_title(task, loc="left", fontsize=9)
    axis.set_xticks(range(len(releases)), releases, rotation=45, ha="right")
    axis.set_xlim(-0.5, len(releases) - 0.5)
    axis.set_ylim(0, 1.05)
    axis.yaxis.grid(visible=True, color=GRID, linewidth=0.6)
    axis.set_axisbelow(True)


def _trend_title(report: ReleaseReport) -> str:
    names = [section.target for section in report.targets]
    who = f" ({names[0]})" if len(names) == 1 else ""
    return f"Pass rate per task up to {report.version}{who}"


def _target_colors(report: ReleaseReport) -> dict[str, str]:
    """One categorical hue per target, by its order in the release (the slots wrap past seven)."""
    names = [section.target for section in report.targets]
    return {name: SERIES[index % len(SERIES)] for index, name in enumerate(names)}


def _trend_legend(report: ReleaseReport) -> list[tuple[str, str]]:
    entries = [(color, target) for target, color in _target_colors(report).items()]
    changed = sorted({point.target for point in report.trend if point.judge_changed})
    if changed:
        entries.append((INK_SECONDARY, f"{JUDGE_CHANGE_LABEL}: {', '.join(changed)}"))
    return entries
