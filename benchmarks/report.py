"""Write the review benchmark's charts and ``summary.md`` from its committed results.

Needs matplotlib, not the engine; ``--embed`` rebuilds the rubric map (numpy,
scikit-learn and ``OPENAI_API_KEY`` in ``.env``)::

    uv run --no-project --python 3.12 --with matplotlib python benchmarks/report.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _bench
import review_charts as rc
import review_data as rd
import rubric_map


def results_table(summaries: list[rd.Summary]) -> str:
    """The README's results table, one row per reviewer, as markdown."""
    head = (
        "| Reviewer (14 `review/*` samples x 3 runs) | Engine pass | Judge passes the review "
        "| Pass ignoring the verdict line | Judge score | Runs that edited code | Median time |\n"
        "|---|---|---|---|---|---|---|"
    )
    return "\n".join([head, *(_result_row(s) for s in summaries)])


def _result_row(s: rd.Summary) -> str:
    unjudged = s.runs - s.judged
    mark = f" ({unjudged} not judged)" if unjudged else ""
    bound = "≥ " if unjudged else ""
    cells = (
        f"**{s.reviewer.label}**",
        f"{s.passes}/{s.runs}",
        f"{bound}{s.judge_passes}/{s.runs}{mark}",
        f"{bound}{s.fair_passes}/{s.runs}{mark}",
        f"{s.judge_score:.2f}",
        f"{s.edited}" + (f" of {s.judged} judged" if unjudged else ""),
        f"{s.median_seconds:.0f} s",
    )
    return "| " + " | ".join(cells) + " |"


def never_met_table(criteria: list[rd.CriterionResult]) -> str:
    """The criteria a built-in reviewer never met, numbered as on the rubric map, as markdown."""
    lines = [
        "| # | Sample | Criterion (abridged) | /code-review met | /review met |",
        "|---|---|---|---|---|",
    ]
    for m in rd.never_met(criteria):
        text = m.criterion if len(m.criterion) <= 100 else m.criterion[:97].rstrip() + "..."
        cc, oc = m.met["claude-code-review"], m.met["opencode-review"]
        lines.append(f"| {m.number} | {m.sample} | {text} | {cc}/3 | {oc}/3 |")
    return "\n".join(lines)


def build_map(runs: list[rd.BuiltinRun]) -> None:
    """Embed every rubric criterion and cache the 2-D map (needs ``OPENAI_API_KEY``)."""
    _bench.load_env_file()
    order = rd.sample_order({r.sample for r in runs})
    pairs = sorted(
        {(r.sample, c) for r in runs for c, _, _ in r.criteria},
        key=lambda p: (order.index(p[0]), p[1]),
    )
    rubric_map.build(pairs, _bench.require_env("OPENAI_API_KEY"), rd.RUN_DIR / "rubric_map.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--embed", action="store_true", help="rebuild rubric_map.json first")
    args = parser.parse_args(argv)
    matplotlib.use("Agg")  # here, not at import: the notebook imports this module inline
    runs = rd.load_builtin_runs()
    if args.embed:
        build_map(runs)
    tasks = rd.all_tasks()
    summaries = rd.summarize(tasks, runs)
    criteria = rd.criterion_results(runs)
    rc.apply_style()
    figures = {
        "overview.png": rc.overview_figure(summaries),
        "tradeoff.png": rc.tradeoff_figure(summaries),
        "by_sample_pass.png": rc.task_heatmap_figure(tasks),
        "by_sample_judge.png": rc.task_judge_figure(tasks),
        "rubric_map.png": rc.rubric_map_figure(
            rubric_map.load(rd.RUN_DIR / "rubric_map.json"), criteria
        ),
    }
    for name, figure in figures.items():
        figure.savefig(rd.RUN_DIR / name, dpi=150)
    summary = (
        f"# Results\n\n{results_table(summaries)}\n\n"
        f"## Rubric criteria a built-in reviewer never met\n\n{never_met_table(criteria)}\n"
    )
    (rd.RUN_DIR / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
