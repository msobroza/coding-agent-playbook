"""``playbook eval --check-regressions NEW --against BASELINE``: the release regression check.

Spec #281 ticket 08. Both paths are release metrics files of one Eval target
(``eval --run --record``); the comparison is ``evals.release_regression``'s.
``--accept SAMPLE=REASON`` (repeatable) accepts one regression with a reason.
The new file is rewritten with ``previous``, each sample's ``vs_previous`` (the
accepted reasons included) and the summary counts, then a table (or
``--format json``) is printed. Exit ``0`` when no regression is unaccepted,
``1`` when one is, ``2`` on a usage error or a file that is not release metrics.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.release_metrics_schema import (
    ReleaseMetricsError,
    validate_release_metrics,
)
from coding_agent_playbook.evals.release_regression import (
    RegressionCheckError,
    annotate_release_metrics,
    check_regressions,
)
from coding_agent_playbook.evals.release_regression_format import (
    format_regression_table,
    regression_check_to_dict,
)

if TYPE_CHECKING:
    import argparse


def configure_regressions(parser: argparse.ArgumentParser) -> None:
    """Declare ``--check-regressions``, ``--against`` and ``--accept`` on ``playbook eval``.

    Example::

        >>> configure_regressions(argparse.ArgumentParser())  # doctest: +SKIP
    """
    parser.add_argument(
        "--check-regressions",
        metavar="NEW",
        dest="check_regressions",
        help="compare the release metrics file NEW with --against BASELINE (same target); "
        "exits 1 on an unaccepted regression and stores the comparison in NEW",
    )
    parser.add_argument(
        "--against",
        metavar="BASELINE",
        help="--check-regressions: the previous release's metrics file for the same target",
    )
    parser.add_argument(
        "--accept",
        metavar="SAMPLE=REASON",
        action="append",
        default=None,
        help="--check-regressions: accept the regression of SAMPLE, storing REASON "
        "in NEW (repeatable)",
    )


def wants_regressions(args: argparse.Namespace) -> bool:
    """Whether ``args`` name any regression-check flag."""
    flags = ("check_regressions", "against", "accept")
    return any(getattr(args, flag, None) is not None for flag in flags)


def run_regressions(args: argparse.Namespace) -> int:
    """Run the check ``args`` describe; see the module doc for the exit codes.

    Example::

        >>> run_regressions(parse(["eval", "--check-regressions", "n.json", "--against", "o.json"]))  # doctest: +SKIP
        0
    """
    if getattr(args, "run", False):
        raise RegressionCheckError("--check-regressions reads two files; drop --run")
    new_path, baseline_path = _paths(args)
    accepted = _acceptances(getattr(args, "accept", None) or [])
    new = _load(new_path)
    check = check_regressions(new, _load(baseline_path), accepted=accepted)
    annotated = annotate_release_metrics(new, check)
    validate_release_metrics(annotated)
    new_path.write_text(json.dumps(annotated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if (getattr(args, "format", None) or "text") == "json":
        print(json.dumps(regression_check_to_dict(check), indent=2, sort_keys=True))
    else:
        print(format_regression_table(check))
    print(f"stored the comparison in {new_path}", file=sys.stderr)
    return 1 if check.blocked else 0


def _paths(args: argparse.Namespace) -> tuple[Path, Path]:
    new, baseline = getattr(args, "check_regressions", None), getattr(args, "against", None)
    if new is None:
        raise RegressionCheckError("--against and --accept belong to --check-regressions NEW")
    if baseline is None:
        raise RegressionCheckError(
            "--check-regressions needs --against BASELINE, the previous release's file"
        )
    return Path(new), Path(baseline)


def _acceptances(values: list[str]) -> dict[str, str]:
    """``SAMPLE=REASON`` values by sample; refuse one without a sample or a reason."""
    accepted: dict[str, str] = {}
    for value in values:
        sample_id, _, reason = value.partition("=")
        if not sample_id.strip() or not reason.strip():
            raise RegressionCheckError(f"--accept expects SAMPLE=REASON, got {value!r}")
        accepted[sample_id.strip()] = reason.strip()
    return accepted


def _load(path: Path) -> dict[str, object]:
    """The validated release metrics file at ``path``."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RegressionCheckError(f"cannot read release metrics file {path}: {exc}") from exc
    try:
        validate_release_metrics(data)
    except ReleaseMetricsError as exc:
        raise RegressionCheckError(f"{path}: {exc}") from exc
    assert isinstance(data, dict)  # validate_release_metrics refuses anything else
    return data
