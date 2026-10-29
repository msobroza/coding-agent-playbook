"""The flags of ``playbook eval --record`` and their checks (``commands._eval_record``).

Kept apart from the record run itself so each module stays one read: this one
declares ``--all``, ``--runs``, ``--record``, ``--carry-from``, ``--jobs``,
``--checkpoint`` and ``--resume``, and refuses their misuse before any paid run.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.model_pins import RecordRefusedError

if TYPE_CHECKING:
    import argparse


def configure_record(parser: argparse.ArgumentParser) -> None:
    """Declare ``--all``, ``--runs`` and ``--record`` on ``playbook eval``.

    Example::

        >>> configure_record(argparse.ArgumentParser())  # doctest: +SKIP
    """
    parser.add_argument(
        "--all",
        action="store_true",
        dest="all_samples",
        help="--record: run every eval sample (instead of the sample <id>)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        help="--record: runs per eval sample (default: the target's runs, else 1)",
    )
    parser.add_argument(
        "--record",
        metavar="PATH",
        help="with --run: write the release metrics file (schema version 1) of the "
        "samples on one target to PATH; refuses unpinned models",
    )
    parser.add_argument(
        "--carry-from",
        metavar="PREVIOUS",
        dest="carry_from",
        help="--record --all: rerun only new samples, samples whose inputs changed and "
        "edition controls, copying the other entries from the metrics file PREVIOUS of "
        "the same target, or from any metrics file of this setup under the releases "
        "directory PREVIOUS (<release>/metrics/*.json); a different setup reruns everything",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        help="--record: samples run at the same time (default 1); bounded by the "
        "harness and judge rate limits",
    )
    parser.add_argument(
        "--checkpoint",
        metavar="PATH",
        help="--record: save each finished sample to PATH as it ends (default: the "
        "record path + .partial.jsonl); removed once the metrics file is written",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="--record: reuse the checkpoint's samples measured on the same setup and "
        "inputs instead of running them again",
    )


def wants_record(args: argparse.Namespace) -> bool:
    """Whether ``args`` ask for a recording (``--record`` or a flag that belongs to it)."""
    flags = (
        getattr(args, "record", None),
        getattr(args, "runs", None),
        getattr(args, "carry_from", None),
        getattr(args, "jobs", None),
        getattr(args, "checkpoint", None),
    )
    switches = (getattr(args, "all_samples", False), getattr(args, "resume", False))
    return any(switches) or any(flag is not None for flag in flags)


def record_path(args: argparse.Namespace) -> Path:
    record = getattr(args, "record", None)
    if record is None:
        raise RecordRefusedError(
            "--all, --runs, --carry-from, --jobs, --checkpoint and --resume belong to "
            "--record <path>; pass --record too"
        )
    return Path(record)


def carry_from_path(args: argparse.Namespace) -> Path | None:
    """The ``--carry-from`` metrics file or releases directory; refused without ``--all``."""
    carry_from = getattr(args, "carry_from", None)
    if carry_from is None:
        return None
    if not getattr(args, "all_samples", False):
        raise RecordRefusedError(
            f"--carry-from needs --all: a record carried from {carry_from} must cover every "
            "sample, so pass --all instead of a sample or task"
        )
    return Path(carry_from)


def refuse_format(args: argparse.Namespace) -> None:
    """``--format`` shapes the one-sample ``--run`` report; ``--record`` writes JSON only."""
    fmt = getattr(args, "format", None)
    if fmt is not None:
        raise RecordRefusedError(
            f"--format {fmt} does not apply to --record, which always writes the release "
            "metrics JSON file; drop --format"
        )


def job_count(flag: int | None) -> int:
    jobs = 1 if flag is None else flag
    if jobs < 1:
        raise RecordRefusedError(f"--jobs must be >= 1, got {jobs}")
    return jobs


def run_count(flag: int | None, target_runs: int | None) -> int:
    runs = flag if flag is not None else (target_runs or 1)
    if runs < 1:
        raise RecordRefusedError(f"--runs must be >= 1, got {runs}")
    return runs
