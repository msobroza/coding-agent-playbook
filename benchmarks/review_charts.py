"""Charts of the review benchmark, drawn with matplotlib from ``review_data``.

Color does one job per chart: blue is the playbook's ``review`` prompt and
orange a harness's built-in reviewer (slots 1-2 of the dataviz reference
palette, CVD-checked as a pair); harness identity is a facet or a marker shape,
never a third hue. Pass/miss on the rubric map uses the status colors, each
paired with its own marker shape and a legend label.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import review_data as rd

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure
    from rubric_map import MapPoint

PLAYBOOK: Final = "#2a78d6"
BUILTIN: Final = "#eb6834"
UNJUDGED: Final = "#cde2fb"
INK, INK_2, MUTED, GRID, AXIS, SURFACE = (
    "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb",
)  # fmt: skip
#: Runs passed of 3, one blue ramp; 0 sits on a neutral step so it reads as "none".
PASS_RAMP: Final = ("#f0efec", "#b7d3f6", "#5598e7", "#1c5cab")
#: Rubric criterion met in 3/3, 1-2/3 and 0/3 runs: status color + marker + label.
MET_STYLES: Final = (
    ("met in every run", "#0ca30c", "o"),
    ("met in some runs", "#fab219", "^"),
    ("never met", "#d03b3b", "X"),
)
HARNESSES: Final = ("Claude Code", "OpenCode")


def apply_style() -> None:
    """Recessive axes and grid, system sans, the chart surface as background."""
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
            "font.size": 10,
            "text.color": INK,
            "axes.labelcolor": INK_2,
            "axes.edgecolor": AXIS,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "xtick.color": MUTED,
            "ytick.color": INK_2,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "legend.frameon": False,
        }
    )


def _reviewers(harness: str) -> tuple[rd.Reviewer, rd.Reviewer]:
    playbook, builtin = (r for r in rd.REVIEWERS if r.harness == harness)
    return playbook, builtin


def overview_figure(summaries: list[rd.Summary]) -> Figure:
    """Runs that pass (of 42) on each metric, playbook vs built-in, one facet per harness."""
    metrics = (
        ("Engine pass\n(gate + judge)", "passes"),
        ("Judge passes\nthe review", "judge_passes"),
        ("Pass ignoring the\nverdict line", "fair_passes"),
    )
    by_key = {s.reviewer.key: s for s in summaries}
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6), sharey=True, layout="constrained")
    for ax, harness in zip(axes, HARNESSES, strict=True):
        playbook, builtin = (by_key[r.key] for r in _reviewers(harness))
        for row, (_, field) in enumerate(metrics):
            _overview_bar(ax, row - 0.18, playbook, field, PLAYBOOK)
            _overview_bar(ax, row + 0.18, builtin, field, BUILTIN)
        ax.set_title(harness)
        ax.set_yticks(range(len(metrics)), [m for m, _ in metrics])
        ax.set_ylim(len(metrics) - 0.5, -0.5)  # first metric on top (sharey: set once is enough)
        ax.set_xlim(0, 48)
        ax.set_xticks([0, 10, 20, 30, 42])
        ax.set_xlabel("runs that pass, of 42 (14 samples x 3)")
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)
    fig.legend(
        handles=[
            Patch(color=PLAYBOOK, label="playbook review prompt"),
            Patch(color=BUILTIN, label="built-in reviewer"),
            Patch(
                facecolor=UNJUDGED, edgecolor=PLAYBOOK, hatch="///", label="not judged (fail-fast)"
            ),
        ],
        loc="outside upper right",
        ncols=3,
    )
    return fig


def _overview_bar(ax: Axes, y: float, summary: rd.Summary, field: str, color: str) -> None:
    value = int(getattr(summary, field))
    unknown = summary.runs - summary.judged if field != "passes" else 0
    ax.barh(y, value, height=0.32, color=color)
    label = f"{value}/{summary.runs}"
    if unknown:
        ax.barh(
            y,
            unknown,
            left=value,
            height=0.32,
            color=UNJUDGED,
            edgecolor=color,
            hatch="///",
            linewidth=0,
        )
        label = f"{value} + {unknown} not judged"
    ax.text(value + unknown + 0.6, y, label, va="center", fontsize=9, color=INK)


#: Where each point's label sits (offset in points, ha, va): the pairs are close.
_TRADEOFF_LABELS: Final = {
    "claude-playbook": ((-12, 0), "right", "center"),
    "opencode-playbook": ((12, 0), "left", "center"),
    "claude-code-review": ((10, 10), "left", "bottom"),
    "opencode-review": ((10, -10), "left", "top"),
}


def tradeoff_figure(summaries: list[rd.Summary]) -> Figure:
    """Mean judge score against median time per run: what the extra time buys."""
    fig, ax = plt.subplots(figsize=(6.4, 4.2), layout="constrained")
    for s in summaries:
        color = BUILTIN if s.reviewer.builtin else PLAYBOOK
        marker = "o" if s.reviewer.harness == "Claude Code" else "s"
        ax.scatter(
            s.median_seconds,
            s.judge_score,
            s=90,
            color=color,
            marker=marker,
            edgecolor=SURFACE,
            linewidth=2,
            zorder=3,
        )
        offset, ha, va = _TRADEOFF_LABELS[s.reviewer.key]
        ax.annotate(
            f"{s.reviewer.label}\n{s.passes}/{s.runs} pass, {s.median_seconds:.0f} s",
            (s.median_seconds, s.judge_score),
            xytext=offset,
            textcoords="offset points",
            fontsize=9,
            ha=ha,
            va=va,
        )
    ax.set_xlim(0, 480)
    ax.set_ylim(0.5, 1.0)
    ax.set_xlabel("median time per run (seconds)")
    ax.set_ylabel("mean judge score (0-1)")
    ax.set_title("Review quality vs time per run")
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(
        handles=[
            Line2D([], [], marker="o", linestyle="", color=MUTED, label="Claude Code"),
            Line2D([], [], marker="s", linestyle="", color=MUTED, label="OpenCode"),
        ],
        loc="lower right",
    )
    return fig


def task_heatmap_figure(tasks: list[rd.TaskResult]) -> Figure:
    """Runs passed (of 3) per sample: playbook, built-in, built-in without the verdict check."""
    samples = rd.sample_order({t.sample for t in tasks})
    by = {(t.reviewer, t.sample): t for t in tasks}
    columns: list[tuple[str, str, str]] = []
    for harness in HARNESSES:
        playbook, builtin = _reviewers(harness)
        name = builtin.label.split()[-1]
        columns += [
            (playbook.key, "passes", "playbook"),
            (builtin.key, "passes", name),
            (builtin.key, "fair_passes", f"{name}\nno verdict check"),
        ]
    fig, ax = plt.subplots(figsize=(10, 7.6), layout="constrained")
    xs = [col + (0.4 if col >= 3 else 0) for col in range(len(columns))]
    for x, (key, field, header) in zip(xs, columns, strict=True):
        ax.text(x, -0.75, header, ha="center", va="bottom", fontsize=9, color=INK_2)
        for row, sample in enumerate(samples):
            _heat_cell(ax, x, row, by[key, sample], field)
    for x, harness in ((1, HARNESSES[0]), (4.4, HARNESSES[1])):
        ax.text(x, -1.55, harness, ha="center", va="bottom", fontweight="bold", fontsize=11)
    ax.text(
        -0.5, len(samples) + 0.1,
        "Row label: the verdict the sample's gate expects. Above the line: the original samples; "
        "below: CRBugBench paraphrases.\n"
        "* some runs stopped at the gate and were never judged (the playbook release eval is fail-fast).",
        va="top", fontsize=8.5, color=INK_2,
    )  # fmt: skip
    ax.set_xlim(-0.6, 6.0)
    ax.set_ylim(len(samples) + 0.9, -2.0)
    ax.set_xticks([])
    ax.set_yticks(
        range(len(samples)), [f"{s}  ({rd.expected_verdict(s)})" for s in samples], fontsize=9
    )
    ax.plot([-0.5, 5.9], [len(rd.ORIGINAL_SAMPLES) - 0.5] * 2, color=AXIS, linewidth=1)
    for side in ("left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    ax.set_title("Runs that pass, by sample (of 3)")
    return fig


def _heat_cell(ax: Axes, x: float, row: int, task: rd.TaskResult, field: str) -> None:
    value = getattr(task, field)
    if value is None:  # playbook: some runs never judged, so only engine passes are known
        value = task.passes
    color = PASS_RAMP[min(value, 3)]
    ax.add_patch(plt.Rectangle((x - 0.46, row - 0.44), 0.92, 0.88, color=color, linewidth=0))
    star = "*" if field == "passes" and task.judged < task.runs else ""
    ax.text(
        x,
        row,
        f"{value}/{task.runs}{star}",
        ha="center",
        va="center",
        fontsize=9,
        color="white" if value >= 2 else INK,
    )


def task_judge_figure(tasks: list[rd.TaskResult]) -> Figure:
    """Mean judge score per sample, playbook vs built-in, one facet per harness."""
    samples = rd.sample_order({t.sample for t in tasks})
    by = {(t.reviewer, t.sample): t for t in tasks}
    fig, axes = plt.subplots(1, 2, figsize=(11, 6.4), sharey=True, layout="constrained")
    for ax, harness in zip(axes, HARNESSES, strict=True):
        playbook, builtin = _reviewers(harness)
        for row, sample in enumerate(samples):
            _dumbbell(
                ax, row, by[playbook.key, sample].judge_score, by[builtin.key, sample].judge_score
            )
        ax.axvline(0.5, color=MUTED, linestyle="--", linewidth=1)
        ax.text(0.505, -0.9, "rubric pass line", fontsize=8.5, color=MUTED)
        ax.axhline(len(rd.ORIGINAL_SAMPLES) - 0.5, color=AXIS, linewidth=1)
        ax.set_title(harness)
        ax.set_xlim(0, 1.02)
        ax.set_xlabel("mean judge score (weighted rubric, 0-1)")
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)
    axes[0].set_yticks(range(len(samples)), samples, fontsize=9)
    axes[0].set_ylim(len(samples) - 0.5, -1.3)
    fig.legend(
        handles=[
            Line2D(
                [],
                [],
                marker="o",
                linestyle="",
                color=PLAYBOOK,
                label="playbook review prompt (judged runs)",
            ),
            Line2D(
                [],
                [],
                marker="o",
                linestyle="",
                color=BUILTIN,
                label="built-in reviewer (all 3 runs)",
            ),
        ],
        loc="outside upper right",
        ncols=2,
    )
    return fig


def _dumbbell(ax: Axes, row: int, playbook: float | None, builtin: float | None) -> None:
    if playbook is not None and builtin is not None:
        ax.plot([playbook, builtin], [row, row], color=AXIS, linewidth=2, zorder=1)
    if builtin is not None:
        ax.scatter(builtin, row, s=60, color=BUILTIN, edgecolor=SURFACE, linewidth=1.5, zorder=3)
    if playbook is None:  # beside the built-in dot, on whichever side has room
        x, ha = (
            ((builtin or 0) - 0.03, "right")
            if (builtin or 0) > 0.5
            else ((builtin or 0) + 0.03, "left")
        )
        ax.text(x, row, "playbook: not judged", ha=ha, va="center", fontsize=8.5, color=PLAYBOOK)
        return
    ax.scatter(playbook, row, s=60, color=PLAYBOOK, edgecolor=SURFACE, linewidth=1.5, zorder=3)


#: Region labels on the rubric map: a keyword rule per kind of criterion, placed
#: at the centroid of the criteria it matches. First match wins.
CRITERION_KINDS: Final = (
    ("verdict on a correct change", ("verdict is 'approve'",)),
    (
        "does not invent bugs",
        ("does not invent", "no correctness", "does not propose", "does not raise"),
    ),
    ("cites file:line", ("cites file and line", "quotes the offending", "reads every file")),
    ("names the bug, then blocks it", ("reports", "identifies", "blocking")),
)


def criterion_kind(criterion: str) -> str | None:
    """The :data:`CRITERION_KINDS` label of ``criterion``; ``None`` for the odd ones out."""
    text = criterion.lower()
    for label, keys in CRITERION_KINDS:
        if any(key in text for key in keys):
            return label
    return None


def rubric_map_figure(points: list[MapPoint], criteria: list[rd.CriterionResult]) -> Figure:
    """Every rubric criterion on its embedding map, colored by how often each built-in met it."""
    met = {(c.reviewer, c.sample, c.criterion): c.met for c in criteria}
    numbers = {(m.sample, m.criterion): m.number for m in rd.never_met(criteria)}
    builtins = [r for r in rd.REVIEWERS if r.builtin]
    fig, axes = plt.subplots(
        1, len(builtins), figsize=(12, 5.8), sharex=True, sharey=True, layout="constrained"
    )
    for ax, reviewer in zip(axes, builtins, strict=True):
        for point in points:
            count = met[reviewer.key, point.sample, point.criterion]
            _, color, marker = _met_style(count)
            ax.scatter(
                point.x,
                point.y,
                s=70,
                color=color,
                marker=marker,
                edgecolor=SURFACE,
                linewidth=1.5,
                zorder=3,
            )
            if count == 0:
                number = str(numbers[point.sample, point.criterion])
                ax.annotate(
                    number,
                    (point.x, point.y),
                    xytext=(6, 4),
                    textcoords="offset points",
                    fontsize=8.5,
                    fontweight="bold",
                    color=INK,
                )
        _kind_labels(ax, points)
        ax.set_title(f"{reviewer.label}: rubric criteria met")
        ax.set_xticks([])
        ax.set_yticks([])
        for side in ("left", "bottom"):
            ax.spines[side].set_visible(False)
    fig.legend(
        handles=[
            Line2D([], [], marker=m, linestyle="", color=c, markersize=8, label=f"{lbl} (of 3)")
            for lbl, c, m in MET_STYLES
        ],
        loc="outside lower center",
        ncols=3,
    )
    return fig


def _met_style(met: int) -> tuple[str, str, str]:
    if met == 3:
        return MET_STYLES[0]
    return MET_STYLES[1] if met else MET_STYLES[2]


#: Label offsets tried around a kind's medoid, nearest first (display pixels).
_LABEL_OFFSETS: Final = tuple(
    (r * dx, r * dy)
    for r in (24, 42, 64)
    for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, 1), (1, -1), (-1, -1))
)


def _kind_labels(ax: Axes, points: list[MapPoint]) -> None:
    # Near the medoid, the point nearest all others of its kind (a mean lands
    # between a kind's clusters when its criteria split in two), at the first
    # offset whose box covers no marker, measured in pixels once the layout settles.
    ax.figure.canvas.draw()
    dots = [ax.transData.transform((p.x, p.y)) for p in points]
    for label, _ in CRITERION_KINDS:
        mine = [p for p in points if criterion_kind(p.criterion) == label]
        if not mine:
            continue
        medoid = min(mine, key=lambda p: sum((p.x - q.x) ** 2 + (p.y - q.y) ** 2 for q in mine))
        mx, my = ax.transData.transform((medoid.x, medoid.y))
        half_w, half_h = 3.2 * len(label) + 8, 14
        free = (
            (dx, dy)
            for dx, dy in _LABEL_OFFSETS
            if all(abs(px - mx - dx) > half_w or abs(py - my - dy) > half_h for px, py in dots)
        )
        dx, dy = next(free, (0, 24))
        scale = 72 / ax.figure.dpi  # pixels -> points, so the offset survives savefig's dpi
        ax.annotate(
            label, (medoid.x, medoid.y), xytext=(dx * scale, dy * scale), textcoords="offset points",
            ha="center", va="center", fontsize=9.5, color=INK_2, style="italic", zorder=2,
        )  # fmt: skip
