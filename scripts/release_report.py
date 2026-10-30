#!/usr/bin/env python3
"""Build a release's metric bundle: the files a GitHub or GitLab Release publishes (spec D5).

::

    python scripts/release_report.py --version 0.4.0 --out release-report
    python scripts/release_report.py --version 0.4.0 --out DIR --checkout tag-tree
    python scripts/release_report.py --version 0.4.0 --out DIR --no-charts

``--checkout`` (default ``.``) is the tree whose ``catalog/releases/`` holds the
release data, such as a worktree of the release tag; this script's own code
runs from wherever it is installed. The bundle is flat (release assets are flat
file names):

- ``report.md``: the release report (``evals.release_report``), also the
  release description, cut under GitHub's 125,000-character body cap;
- ``metrics-history.csv``: one row per release, target and sample;
- ``metrics-<target>.json``: byte copies of the release's metrics files;
- ``judge-agreement.csv``: only for a release whose own files record a judge
  change, with that release's rows only;
- ``task-deltas.png``, ``sample-deltas.png``, ``task-trend.png``
  (``scripts/release_report_charts.py``): the charts need matplotlib, which
  only this script imports, lazily; ``--no-charts`` builds without it.

It exits 2 on an unknown version or an unreadable metrics file, else 0.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evals.release_report import (
    METRICS_DIRNAME,
    ReleaseReportError,
    load_history,
    release_report,
)
from coding_agent_playbook.evals.release_report_rows import AGREEMENT_COLUMNS, CSV_COLUMNS

if TYPE_CHECKING:
    from collections.abc import Sequence

#: The exit code of a refusal (an unknown version, an unreadable file, no matplotlib).
REFUSED_EXIT: Final = 2
RELEASES_PATH: Final = Path("catalog") / "releases"
REPORT_NAME: Final = "report.md"
HISTORY_NAME: Final = "metrics-history.csv"
AGREEMENT_NAME: Final = "judge-agreement.csv"


def build_bundle(checkout: Path, version: str, out: Path, *, charts: bool) -> list[Path]:
    """Write ``version``'s bundle from ``checkout``'s releases into ``out``; return its files.

    Raises ``ReleaseReportError`` for a version without metrics files, and
    ``ImportError`` when ``charts`` is on without matplotlib.

    Example::

        >>> [p.name for p in build_bundle(Path("."), "0.4.0", Path("b"), charts=False)]  # doctest: +SKIP
        ['report.md', 'metrics-history.csv', 'metrics-opencode-qwen.json']
    """
    releases = checkout / RELEASES_PATH
    report = release_report(load_history(releases), version)
    out.mkdir(parents=True, exist_ok=True)
    (out / REPORT_NAME).write_text(report.markdown(), encoding="utf-8")
    paths = [out / REPORT_NAME, _write_csv(out / HISTORY_NAME, CSV_COLUMNS, report.csv_rows())]
    paths += _copy_metrics(releases / version / METRICS_DIRNAME, out)
    # agreement_rows() spans the history; the bundle keeps only this release's judge change.
    agreement = [row for row in report.agreement_rows() if row["release"] == version]
    if agreement:
        paths.append(_write_csv(out / AGREEMENT_NAME, AGREEMENT_COLUMNS, agreement))
    if charts:
        from release_report_charts import write_charts  # lazily: matplotlib is optional

        paths += write_charts(report, out)
    return paths


def _write_csv(path: Path, columns: Sequence[str], rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _copy_metrics(metrics_dir: Path, out: Path) -> list[Path]:
    """Byte copies of ``metrics_dir/<target>.json`` as ``out/metrics-<target>.json``."""
    copies = []
    for source in sorted(metrics_dir.glob("*.json")):
        copies.append(Path(shutil.copyfile(source, out / f"metrics-{source.name}")))
    return copies


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="release_report.py", description=__doc__.splitlines()[0])
    parser.add_argument("--version", required=True, help="the release, such as 0.4.0")
    parser.add_argument("--out", required=True, type=Path, help="the bundle directory")
    parser.add_argument(
        "--checkout", type=Path, default=Path("."), help="the tree holding catalog/releases/"
    )
    parser.add_argument("--no-charts", action="store_true", help="skip the PNGs (no matplotlib)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Build the bundle; return 0, or 2 on a refusal (argparse exits 2 on a usage error)."""
    args = _parser().parse_args(argv)
    try:
        paths = build_bundle(args.checkout, args.version, args.out, charts=not args.no_charts)
    except ReleaseReportError as exc:
        print(f"release_report: {exc}", file=sys.stderr)
        return REFUSED_EXIT
    except ImportError as exc:
        print(f"release_report: {exc}; install matplotlib or pass --no-charts", file=sys.stderr)
        return REFUSED_EXIT
    for path in paths:
        print(f"release_report: wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
