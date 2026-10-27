"""Phase 3 of the review benchmark: tabulate and plot the scored runs.

Reads every ``score.json`` of one run and writes, next to them:

- ``summary.csv``: one row per experiment x sample.
- ``summary.md``: per-experiment totals, the per-sample grid and why gates failed.
- ``overview.png``: pass rate, mean judge score and median agent time per reviewer.
- ``judge_score_by_sample.png``: a sample x reviewer grid of weighted judge scores.
- ``detection.png``: CRBugBench-style detection next to the pass rate, on the
  samples with one known defect (when ``detect_runs.py`` has run).

Needs only matplotlib, not the engine, so it runs outside the project venv::

    uv run --no-project --with matplotlib python benchmarks/plot_results.py
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _bench

#: Categorical slots 1-7 of the reference palette, in experiment order (validated
#: for CVD on adjacent pairs; slots below 3:1 contrast get value labels on their
#: bars, and summary.md serves as the table view).
SERIES_COLORS = {
    "opencode-review": "#2a78d6",
    "opencode-playbook-v0.1.0": "#eb6834",
    "opencode-playbook-v0.2.0": "#1baf7a",
    "opencode-playbook-v0.3.0": "#eda100",
    "claude-code-review": "#e87ba4",
    "claude-playbook-v0.2.0": "#008300",
    "claude-playbook-v0.3.0": "#6250d6",
}
#: The sequential ramp for judge scores: one hue, light at 0 to dark at 1.
SCORE_RAMP = ("#cde2fb", "#86b6ef", "#3987e5", "#256abf", "#184f95", "#0d366b")
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
    judge_error: str = ""
    detected: str = ""  # yes / partial / no; "" when the run has no detection verdict
    detect_strict: float | None = None
    detect_lenient: float | None = None
    detect_top5: float | None = None
    first_match: int | None = None
    n_items: int | None = None
    second_pass_ran: bool | None = None  # None unless the prompt asks for a bug-only pass
    subagent_starts: dict[str, int] | None = None  # Claude Code: foreground/background counts


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
    rows = [
        _with_detection(_row(json.loads(p.read_text(encoding="utf-8")), exprs), p) for p in paths
    ]
    order = [e.key for e in _bench.EXPERIMENTS]
    return sorted(rows, key=lambda r: (order.index(r.experiment), r.sample_id))


def _gate_exprs() -> dict[str, str]:
    return {
        s.id: s.gate.expr or next(iter(s.gate.bind))  # a None expr names the sole handle
        for s in _bench.review_samples()
        if s.gate is not None
    }


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
        judge_error=payload.get("judge_error") or "",
        second_pass_ran=payload["agent"].get("second_pass_ran"),
        subagent_starts=payload["agent"].get("subagent_starts"),
    )


def _with_detection(row: RunRow, score_path: Path) -> RunRow:
    """``row`` plus the run's ``detect.json`` verdict, when there is one without an error."""
    path = score_path.with_name("detect.json")
    if not path.is_file():
        return row
    found = json.loads(path.read_text(encoding="utf-8"))
    if found.get("error"):
        row.detected = "error"
        return row
    row.detected = found["detected"]
    row.detect_strict, row.detect_lenient = found["strict"], found["lenient"]
    row.detect_top5, row.first_match, row.n_items = (
        found["top5"],
        found["first_match"],
        found["n_items"],
    )
    return row


def _short(sample_id: str) -> str:
    return sample_id.removeprefix("review/")


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
    lines += ["", *_set_totals(rows), *_detection_section(rows), *_second_pass_calls(rows)]
    lines += ["", *_sample_grid(rows), "", *_gate_failures(rows)]
    lines += ["", *_judge_refusals(rows)] if any(r.judge_error for r in rows) else []
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def sample_set(sample_id: str) -> str:
    """Which sample set ``sample_id`` belongs to: the CRBugBench-derived ones or the originals.

    Example::

        sample_set("review/crbug-log-textio")  # "CRBugBench"
    """
    return "CRBugBench" if sample_id.startswith("review/crbug-") else "original"


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


def detection_totals(rows: list[RunRow]) -> dict[str, dict[str, float]]:
    """Per reviewer, over its runs with a detection verdict: pass rate and detection rates."""
    totals: dict[str, dict[str, float]] = {}
    for key in dict.fromkeys(r.experiment for r in rows):
        mine = [r for r in rows if r.experiment == key and r.detect_strict is not None]
        if not mine:
            continue
        firsts = [r.first_match for r in mine if r.first_match is not None]
        totals[key] = {
            "runs": len(mine),
            "passed": sum(r.passed is True for r in mine) / len(mine),
            "strict": statistics.fmean(r.detect_strict or 0.0 for r in mine),
            "lenient": statistics.fmean(r.detect_lenient or 0.0 for r in mine),
            "top5": statistics.fmean(r.detect_top5 or 0.0 for r in mine),
            "median_first": statistics.median(firsts) if firsts else float("nan"),
            "mean_items": statistics.fmean(r.n_items or 0 for r in mine),
        }
    return totals


def _detection_section(rows: list[RunRow]) -> list[str]:
    """CRBugBench-style detection beside the pass rate, on the samples with a known defect."""
    totals = detection_totals(rows)
    if not totals:
        return []
    errors = [r for r in rows if r.detected == "error"]
    out = [
        "",
        "## CRBugBench-style detection (samples with one known defect)",
        "",
        "Did the review catch the known defect? Strict counts the judge's `yes`; "
        "lenient counts `yes` as 1 and `partial` as 0.5; top-5 is a `yes` whose first "
        "matching comment is among the review's first five. Passed is this "
        "benchmark's gate-and-rubric verdict on the same runs.",
        "",
        "| Reviewer | Runs | Passed | Strict detection | Lenient detection | Found in first 5 comments "
        "| Median first match | Comments per review |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for key, t in totals.items():
        first = "n/a" if t["median_first"] != t["median_first"] else f"{t['median_first']:.0f}"
        out.append(
            f"| {_label(key)} | {int(t['runs'])} | {t['passed']:.0%} | {t['strict']:.0%} | "
            f"{t['lenient']:.0%} | {t['top5']:.0%} | {first} | {t['mean_items']:.1f} |"
        )
    if errors:
        names = ", ".join(f"{_label(r.experiment)} / {_short(r.sample_id)}" for r in errors)
        out += ["", f"No detection verdict (the judge refused or failed): {names}."]
    return out


def _second_pass_calls(rows: list[RunRow]) -> list[str]:
    """For the setups whose prompt asks for a second, bug-only pass, how many runs started it."""
    keys = list(dict.fromkeys(r.experiment for r in rows if r.second_pass_ran is not None))
    if not keys:
        return []
    out = ["", "## Did the second pass run? (v0.3.0 and later)", ""]
    for key in keys:
        mine = [r for r in rows if r.experiment == key]
        known = [r for r in mine if r.second_pass_ran is not None]
        ran = sum(r.second_pass_ran is True for r in known)
        missing = len(mine) - len(known)
        unknown = f" ({_runs(missing)} not recorded)" if missing else ""
        out.append(f"- {_label(key)}: {ran} of {_runs(len(known))}{unknown}{_background(mine)}")
    return out


def _runs(count: int) -> str:
    return f"{count} run" if count == 1 else f"{count} runs"


def _background(rows: list[RunRow]) -> str:
    """How many of ``rows``' recorded subagent starts were background tasks, as a suffix."""
    starts = [r.subagent_starts for r in rows if r.subagent_starts is not None]
    if not starts:
        return ""
    total = sum(sum(s.values()) for s in starts)
    background = sum(s.get("background", 0) for s in starts)
    return f"; {background} of {total} subagent starts in the background"


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
        out.append(f"| {_short(sample_id)} | " + " | ".join(cells) + " |")
    return out


def _cell(row: RunRow | None) -> str:
    if row is None:
        return "-"
    score = "n/a" if row.judge_score is None else f"{row.judge_score:.2f}"
    verdict = {True: "pass", False: "FAIL", None: "n/a"}[row.passed]
    return f"{verdict} ({score})"


#: The refusal code the Anthropic API puts in brackets, e.g. ``[reasoning_extraction]``.
_REFUSAL_CODE_RE = re.compile(r"\[([a-z_]+)\]")


def judge_error_reason(error: str) -> str:
    """A short reason for a judge failure: the API's refusal code, else the error's lead.

    Example::

        judge_error_reason("... Details: `[reasoning_extraction]` ...")
        # "refused (`reasoning_extraction`)"
    """
    found = _REFUSAL_CODE_RE.search(error)
    if found:
        return f"refused (`{found.group(1)}`)"
    return f"{error.split(':', 1)[0]} (details in its score.json)"


def _judge_refusals(rows: list[RunRow]) -> list[str]:
    """The runs the judge could not score, with its reason (their mean leaves them out)."""
    refused = [r for r in rows if r.judge_error]
    if not refused:
        return []
    out = ["## Runs the judge could not score", ""]
    for r in refused:
        reason = judge_error_reason(r.judge_error)
        out.append(f"- {_label(r.experiment)} / {_short(r.sample_id)}: {reason}")
    return out


def _gate_failures(rows: list[RunRow]) -> list[str]:
    """Each setup's failed gate checks, counted over its runs (per run: ``summary.csv``)."""
    out = ["## Why gates failed", ""]
    failed = [r for r in rows if r.gate_passed is False]
    if not failed:
        return [*out, "Every gate passed."]
    out += ["Failed gate checks per setup, with the number of runs each failed in:", ""]
    for key in dict.fromkeys(r.experiment for r in failed):
        mine = [r for r in failed if r.experiment == key]
        checks = collections.Counter(
            check for r in mine for check in r.gate_failed_by.split("; ") if check
        )
        listed = ", ".join(f"`{check}` {count}" for check, count in checks.most_common())
        edited = sum(bool(r.edited_files) for r in mine)
        note = f"; {_runs(edited)} edited files" if edited else ""
        out.append(f"- {_label(key)} ({_runs(len(mine))}): {listed}{note}")
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


Panel = tuple[str, list[float], str, float | None]


def plot_overview(rows: list[RunRow], path: Path) -> None:
    """Three small multiples, one measure each (never two scales on one axis)."""
    totals = experiment_totals(rows)
    panels: list[Panel] = [
        ("Samples passed (%)", [100 * t["passed"] / t["runs"] for t in totals.values()], "{:.0f}%", 100),
        ("Mean judge score (0-1)", [t["mean_judge"] for t in totals.values()], "{:.2f}", 1),
        ("Median agent time (s)", [t["median_seconds"] for t in totals.values()], "{:.0f} s", None),
    ]  # fmt: skip
    _plot_panels(list(totals), panels, _figure_title(rows), path)


def plot_detection(rows: list[RunRow], path: Path) -> bool:
    """Pass rate beside strict detection and top-5 detection; False when nothing to plot."""
    totals = detection_totals(rows)
    if not totals:
        return False
    panels: list[Panel] = [
        ("Passed: gate and rubric (%)", [100 * t["passed"] for t in totals.values()], "{:.0f}%", 100),
        ("Strict detection: judge says yes (%)", [100 * t["strict"] for t in totals.values()], "{:.0f}%", 100),
        ("Found in the first 5 comments (%)", [100 * t["top5"] for t in totals.values()], "{:.0f}%", 100),
    ]  # fmt: skip
    runs = int(max(t["runs"] for t in totals.values()))
    title = f"CRBugBench-style detection vs pass rate, {runs} samples with a known defect"
    _plot_panels(list(totals), panels, f"{title}\njudge {rows[0].judge_model}", path)
    return True


def _plot_panels(keys: list[str], panels: list[Panel], title: str, path: Path) -> None:
    """One horizontal bar chart per panel, one bar per reviewer, value-labelled."""
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(
        1, len(panels), figsize=(12, 1.4 + 0.45 * len(keys)), facecolor=SURFACE
    )
    for ax, (panel_title, values, fmt, xmax) in zip(axes, panels, strict=True):
        _style_axes(ax)
        y = range(len(keys))
        ax.barh(y, values, height=0.56, color=[SERIES_COLORS[k] for k in keys], edgecolor=SURFACE)
        ax.set_yticks(list(y), [_label(k) for k in keys] if ax is axes[0] else [""] * len(keys))
        ax.invert_yaxis()
        top = xmax or max(values) * 1.25
        ax.set_xlim(0, top)
        for yi, v in zip(y, values, strict=True):
            ax.text(v + top * 0.02, yi, fmt.format(v), va="center", color=INK, fontsize=9)
        ax.set_title(panel_title, loc="left", color=INK, fontsize=10)
    fig.suptitle(title, x=0.01, ha="left", color=INK, fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def plot_judge_by_sample(rows: list[RunRow], path: Path) -> None:
    """A sample x reviewer grid of weighted judge scores, every cell labelled.

    A gap separates the harnesses; a run the judge could not score reads ``n/a``.
    """
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import LinearSegmentedColormap

    keys = list(dict.fromkeys(r.experiment for r in rows))
    samples = sorted({r.sample_id for r in rows})
    by_key = {(r.experiment, r.sample_id): r for r in rows}
    scores = np.ma.masked_invalid([[_score(by_key.get((k, s))) for k in keys] for s in samples])
    cmap = LinearSegmentedColormap.from_list("judge_score", SCORE_RAMP)
    cmap.set_bad(GRID)
    fig, ax = plt.subplots(
        figsize=(2.6 + 1.25 * len(keys), 1.8 + 0.4 * len(samples)), facecolor=SURFACE
    )
    mesh = ax.pcolormesh(scores, cmap=cmap, vmin=0, vmax=1, edgecolors=SURFACE, linewidth=2)
    for i, j in np.ndindex(scores.shape):
        value = scores[i, j]
        text = "n/a" if value is np.ma.masked else f"{value:.2f}"
        dark = value is not np.ma.masked and value > 0.55
        ax.text(j + 0.5, i + 0.5, text, ha="center", va="center", fontsize=8,
                color=SURFACE if dark else INK)  # fmt: skip
    for j in _harness_breaks(keys):
        ax.axvline(j, color=SURFACE, linewidth=8)
    ax.set_xticks([j + 0.5 for j in range(len(keys))], [_wrapped_label(k) for k in keys])
    ax.set_yticks([i + 0.5 for i in range(len(samples))], [_short(s) for s in samples])
    ax.xaxis.tick_top()
    ax.invert_yaxis()
    ax.tick_params(colors=INK_2, labelsize=8, length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    bar = fig.colorbar(mesh, ax=ax, fraction=0.025, pad=0.02)
    bar.outline.set_visible(False)
    bar.ax.tick_params(colors=INK_2, labelsize=8, length=0)
    bar.set_label(
        f"Weighted judge score (0-1); the rubric fails below {RUBRIC_FAIL_BOUND}",
        color=INK_2,
        fontsize=8,
    )
    ax.set_title(_figure_title(rows), loc="left", color=INK, fontsize=11, pad=36)
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def _score(row: RunRow | None) -> float:
    return float("nan") if row is None or row.judge_score is None else row.judge_score


def _wrapped_label(key: str) -> str:
    """A setup's label on two lines, harness first: ``"OpenCode\\n+ playbook v0.2.0"``."""
    return _label(key).replace(" + ", "\n+ ").replace(" /", "\n/")


def _harness_breaks(keys: list[str]) -> list[int]:
    """The column indexes where the harness changes, for a gap between the groups."""
    harnesses = [_bench.experiment_by_key(k).harness for k in keys]
    return [j for j in range(1, len(keys)) if harnesses[j] != harnesses[j - 1]]


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
    written = "summary.csv, summary.md, overview.png, judge_score_by_sample.png"
    if plot_detection(rows, run_root / "detection.png"):
        written += ", detection.png"
    print(f"wrote {written} in {run_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
