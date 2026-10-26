"""Phase 3 of the review benchmark: tabulate and plot the scored runs.

Reads every ``score.json`` of one run and writes, next to them:

- ``summary.csv``: one row per experiment x sample.
- ``summary.md``: per-experiment totals, the per-sample grid and why gates failed.
- ``overview.png``: pass rate, mean judge score and median agent time per reviewer.
- ``judge_score_by_sample.png``: the weighted judge score of every run.

Needs only matplotlib, not the engine, so it runs outside the project venv::

    uv run --no-project --with matplotlib python benchmarks/plot_results.py
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _bench

#: Categorical slots 1-5 of the reference palette, in order (validated for CVD on
#: adjacent pairs; three slots sit below 3:1 contrast, so bars carry value labels
#: or summary.md serves as the table view).
SERIES_COLORS = {
    "opencode-review": "#2a78d6",
    "playbook-v1": "#eb6834",
    "playbook-v2": "#1baf7a",
    "claude-code-review": "#eda100",
    "claude-playbook-v2": "#e87ba4",
}
INK, INK_2, MUTED, GRID, AXIS, SURFACE = (
    "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb",
)  # fmt: skip
RUBRIC_FAIL_BOUND = 0.5


@dataclass
class RunRow:
    """One scored experiment x sample run, flattened for tables and charts."""

    experiment: str
    sample_id: str
    passed: bool | None  # None: no judge score, so no verdict
    gate_passed: bool | None
    rubric_passed: bool | None
    judge_score: float | None
    edited_files: str
    gate_failed_by: str
    duration_seconds: float
    timed_out: bool
    judge_model: str
    sample_version: int | None = None
    judge_error: str = ""


def _layer(payload: dict, layer: str) -> bool | None:
    for check in payload["report"]["checks"]:
        if check["check_id"] == layer and check["status"] == "run":
            return bool(check["passed"])
    return None


def gate_failed_by(expr: str, detail: dict[str, bool]) -> list[str]:
    """The ``and``-chained gate terms that do not hold (``not x`` fails when x holds).

    Example::

        gate_failed_by("a and not b", {"a": True, "b": True})  # ["not b"]
    """
    failed = []
    for term in (t.strip() for t in expr.split(" and ")):
        name = term.removeprefix("not ").strip()
        holds = detail.get(name, False)
        if holds == term.startswith("not "):
            failed.append(term)
    return failed


def load_rows(run_root: Path) -> list[RunRow]:
    """Every ``score.json`` under ``run_root``, as rows in experiment then sample order."""
    paths = sorted(run_root.glob("*/*/score.json"))
    if not paths:
        raise FileNotFoundError(f"no score.json under {run_root}; run score_runs.py first")
    exprs = _gate_exprs()
    rows = [_row(json.loads(p.read_text(encoding="utf-8")), exprs) for p in paths]
    order = [e.key for e in _bench.EXPERIMENTS]
    return sorted(rows, key=lambda r: (order.index(r.experiment), r.sample_id))


def _gate_exprs() -> dict[str, str]:
    import tomllib

    samples = _bench.REPO_ROOT / "catalog" / "core" / "eval_samples"
    specs = (tomllib.loads(p.read_text(encoding="utf-8")) for p in samples.glob("*/sample.toml"))
    return {s["id"]: s["gate"]["expr"] for s in specs}


def _row(payload: dict, exprs: dict[str, str]) -> RunRow:
    sample_id = payload["sample_id"]
    return RunRow(
        experiment=payload["experiment"],
        sample_id=sample_id,
        passed=payload["passed"],
        gate_passed=_layer(payload, "gate"),
        rubric_passed=_layer(payload, "rubric"),
        judge_score=payload.get("rubric_weighted_score"),
        edited_files=" ".join(payload.get("changed_files") or []),
        gate_failed_by="; ".join(gate_failed_by(exprs[sample_id], payload["gate_detail"])),
        duration_seconds=float(payload["agent"]["duration_seconds"]),
        timed_out=bool(payload["agent"]["timed_out"]),
        judge_model=payload["judge"]["model"],
        sample_version=payload.get("sample_version"),
        judge_error=payload.get("judge_error") or "",
    )


def _short(sample_id: str) -> str:
    return sample_id.removeprefix("review-")


def _label(key: str) -> str:
    return _bench.experiment_by_key(key).label


# --------------------------------------------------------------------------- #
# Tables
# --------------------------------------------------------------------------- #


def write_csv(rows: list[RunRow], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0])))
        writer.writeheader()
        writer.writerows(asdict(r) for r in rows)


def experiment_totals(rows: list[RunRow]) -> dict[str, dict[str, float]]:
    """Per experiment: pass/gate/rubric counts, mean judge score, median time, edits."""
    totals: dict[str, dict[str, float]] = {}
    for key in dict.fromkeys(r.experiment for r in rows):
        mine = [r for r in rows if r.experiment == key]
        scores = [r.judge_score for r in mine if r.judge_score is not None]
        totals[key] = {
            "runs": len(mine),
            "passed": sum(r.passed is True for r in mine),
            "gate_passed": sum(bool(r.gate_passed) for r in mine),
            "rubric_passed": sum(bool(r.rubric_passed) for r in mine),
            "mean_judge": statistics.fmean(scores) if scores else float("nan"),
            "median_seconds": statistics.median(r.duration_seconds for r in mine),
            "edited": sum(bool(r.edited_files) for r in mine),
        }
    return totals


def write_markdown(rows: list[RunRow], path: Path, run_name: str) -> None:
    totals = experiment_totals(rows)
    lines = [
        f"# Review benchmark: `{run_name}`",
        "",
        f"Agent: `{_bench.CLAUDE_AGENT_MODEL}` through OpenRouter, in {_harnesses(rows)}. "
        f"Judge: `{rows[0].judge_model}` "
        f"({_bench.JUDGE_EFFORT} effort). One trial per sample; a sample passes when "
        "its gate and its rubric both pass.",
        "",
        "| Reviewer | Passed | Gate passed | Rubric passed | Mean judge score | "
        "Median agent time | Runs that edited files |",
        "|---|---|---|---|---|---|---|",
    ]
    for key, t in totals.items():
        n = int(t["runs"])
        lines.append(
            f"| {_label(key)} | {int(t['passed'])}/{n} | {int(t['gate_passed'])}/{n} | "
            f"{int(t['rubric_passed'])}/{n} | {t['mean_judge']:.2f} | "
            f"{t['median_seconds']:.0f} s | {int(t['edited'])}/{n} |"
        )
    lines += ["", *_set_totals(rows), "", *_sample_grid(rows), "", *_gate_failures(rows)]
    lines += ["", *_judge_refusals(rows)] if any(r.judge_error for r in rows) else []
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def sample_set(sample_id: str) -> str:
    """Which sample set ``sample_id`` belongs to: the CRBugBench-derived ones or the originals.

    Example::

        sample_set("review-crbug-log-textio")  # "CRBugBench"
    """
    return "CRBugBench" if sample_id.startswith("review-crbug-") else "original"


def _set_totals(rows: list[RunRow]) -> list[str]:
    """Passed and mean judge score per reviewer within each sample set."""
    sets = sorted({sample_set(r.sample_id) for r in rows}, reverse=True)
    if len(sets) < 2:
        return []
    keys = list(dict.fromkeys(r.experiment for r in rows))
    out = [
        "## By sample set (passed, mean judge score)",
        "",
        "| Sample set | " + " | ".join(_label(k) for k in keys) + " |",
        "|---|" + "---|" * len(keys),
    ]
    for name in sets:
        cells = []
        for key in keys:
            mine = [r for r in rows if r.experiment == key and sample_set(r.sample_id) == name]
            scores = [r.judge_score for r in mine if r.judge_score is not None]
            mean = f"{statistics.fmean(scores):.2f}" if scores else "n/a"
            cells.append(f"{sum(r.passed is True for r in mine)}/{len(mine)} ({mean})")
        count = len({r.sample_id for r in rows if sample_set(r.sample_id) == name})
        out.append(f"| {name} ({count} samples) | " + " | ".join(cells) + " |")
    return out


def _sample_grid(rows: list[RunRow]) -> list[str]:
    keys = list(dict.fromkeys(r.experiment for r in rows))
    out = [
        "## Per sample (verdict, judge score)",
        "",
        "| Sample | " + " | ".join(_label(k) for k in keys) + " |",
        "|---|" + "---|" * len(keys),
    ]
    by_key = {(r.experiment, r.sample_id): r for r in rows}
    for sample_id in sorted({r.sample_id for r in rows}):
        cells = [_cell(by_key.get((k, sample_id))) for k in keys]
        out.append(f"| {_sample_label(rows, sample_id)} | " + " | ".join(cells) + " |")
    return out


def _sample_label(rows: list[RunRow], sample_id: str) -> str:
    """The sample's short id, plus ``(vN)`` when its runs recorded the sample version."""
    versions = {r.sample_version for r in rows if r.sample_id == sample_id} - {None}
    suffix = f" (v{', v'.join(str(v) for v in sorted(versions))})" if versions else ""
    return f"{_short(sample_id)}{suffix}"


def _cell(row: RunRow | None) -> str:
    if row is None:
        return "-"
    score = "n/a" if row.judge_score is None else f"{row.judge_score:.2f}"
    verdict = {True: "pass", False: "FAIL", None: "n/a"}[row.passed]
    return f"{verdict} ({score})"


def _judge_refusals(rows: list[RunRow]) -> list[str]:
    """The runs the judge could not score, with its reason (their mean leaves them out)."""
    refused = [r for r in rows if r.judge_error]
    if not refused:
        return []
    out = ["## Runs the judge could not score", ""]
    for r in refused:
        out.append(f"- {_label(r.experiment)} / {_short(r.sample_id)}: {r.judge_error[-160:]}")
    return out


def _gate_failures(rows: list[RunRow]) -> list[str]:
    out = ["## Why gates failed", ""]
    failed = [r for r in rows if r.gate_passed is False]
    if not failed:
        return [*out, "Every gate passed."]
    for r in failed:
        edits = f" (edited: {r.edited_files})" if r.edited_files else ""
        out.append(f"- {_label(r.experiment)} / {_short(r.sample_id)}: `{r.gate_failed_by}`{edits}")
    return out


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #


def _style_axes(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=INK_2, labelsize=9, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def plot_overview(rows: list[RunRow], path: Path) -> None:
    """Three small multiples, one measure each (never two scales on one axis)."""
    import matplotlib.pyplot as plt

    totals = experiment_totals(rows)
    keys = list(totals)
    panels = [
        ("Samples passed (%)", [100 * t["passed"] / t["runs"] for t in totals.values()], "{:.0f}%", 100),
        ("Mean judge score (0-1)", [t["mean_judge"] for t in totals.values()], "{:.2f}", 1),
        ("Median agent time (s)", [t["median_seconds"] for t in totals.values()], "{:.0f} s", None),
    ]  # fmt: skip
    fig, axes = plt.subplots(1, 3, figsize=(12, 1.4 + 0.45 * len(keys)), facecolor=SURFACE)
    for ax, (title, values, fmt, xmax) in zip(axes, panels, strict=True):
        _style_axes(ax)
        y = range(len(keys))
        ax.barh(y, values, height=0.56, color=[SERIES_COLORS[k] for k in keys], edgecolor=SURFACE)
        ax.set_yticks(list(y), [_label(k) for k in keys] if ax is axes[0] else [""] * len(keys))
        ax.invert_yaxis()
        top = xmax or max(values) * 1.25
        ax.set_xlim(0, top)
        for yi, v in zip(y, values, strict=True):
            ax.text(v + top * 0.02, yi, fmt.format(v), va="center", color=INK, fontsize=9)
        ax.set_title(title, loc="left", color=INK, fontsize=10)
    fig.suptitle(_figure_title(rows), x=0.01, ha="left", color=INK, fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def plot_judge_by_sample(rows: list[RunRow], path: Path) -> None:
    """Grouped horizontal bars: each sample's weighted judge score per reviewer."""
    import matplotlib.pyplot as plt

    keys = list(dict.fromkeys(r.experiment for r in rows))
    samples = sorted({r.sample_id for r in rows})
    by_key = {(r.experiment, r.sample_id): r for r in rows}
    fig, ax = plt.subplots(figsize=(9, 0.25 * len(samples) * len(keys) + 1.6), facecolor=SURFACE)
    _style_axes(ax)
    height = 0.8 / len(keys)
    for i, key in enumerate(keys):
        scores = [(by_key.get((key, s)) or _missing(key, s)).judge_score or 0.0 for s in samples]
        offsets = [j + (i - (len(keys) - 1) / 2) * height for j in range(len(samples))]
        ax.barh(offsets, scores, height=height * 0.92, color=SERIES_COLORS[key], label=_label(key))
    ax.axvline(RUBRIC_FAIL_BOUND, color=MUTED, linestyle="--", linewidth=1)
    ax.set_yticks(range(len(samples)), [_short(s) for s in samples])
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel(
        f"Weighted judge score (0-1); dashed line = rubric fail bound ({RUBRIC_FAIL_BOUND})",
        color=INK_2,
        fontsize=9,
    )
    legend_rows = -(-len(keys) // 3)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=min(len(keys), 3), frameon=False,
              fontsize=9, labelcolor=INK)  # fmt: skip
    ax.set_title(
        _figure_title(rows), loc="left", color=INK, fontsize=11, pad=12 + 16 * legend_rows + 14
    )
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def _missing(experiment: str, sample_id: str) -> RunRow:
    return RunRow(experiment, sample_id, False, None, None, None, "", "", 0.0, False, "")


_HARNESS_NAMES = {"opencode": "OpenCode", "claude": "Claude Code"}


def _harnesses(rows: list[RunRow]) -> str:
    """The harnesses in ``rows``, in experiment order: ``"OpenCode and Claude Code"``."""
    present = {r.experiment for r in rows}
    harnesses = [e.harness for e in _bench.EXPERIMENTS if e.key in present]
    return " and ".join(_HARNESS_NAMES[h] for h in dict.fromkeys(harnesses))


def _figure_title(rows: list[RunRow]) -> str:
    model = _bench.AGENT_MODEL.split("/")[-1]
    return f"{model} in {_harnesses(rows)} on the review samples\njudge {rows[0].judge_model}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-name", default=_bench.DEFAULT_RUN_NAME)
    args = parser.parse_args(argv)
    run_root = _bench.RESULTS_ROOT / args.run_name
    rows = load_rows(run_root)
    write_csv(rows, run_root / "summary.csv")
    write_markdown(rows, run_root / "summary.md", args.run_name)
    plot_overview(rows, run_root / "overview.png")
    plot_judge_by_sample(rows, run_root / "judge_score_by_sample.png")
    print(f"wrote summary.csv, summary.md, overview.png, judge_score_by_sample.png in {run_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
