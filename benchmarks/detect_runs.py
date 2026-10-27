"""Phase 2b of the review benchmark: CRBugBench-style detection verdicts for the saved runs.

For every saved run of a sample with one known defect (the ``review-crbug-*``
samples), asks the judge CRBugBench's question: did the review catch this
defect (yes / partial / no), and which of its comments reports it. Writes
``detect.json`` next to the run's ``score.json``; ``plot_results.py`` turns it
into strict and lenient detection rates and the first-match position, next to
the pass/fail. See ``_detection.py`` for the metric definitions.

The known defect is the sample's own detection criterion (its highest-weight
rubric criterion), and its location is the file the rubric asks the review to
cite: one source of truth, no second copy of the ground truth.

Usage::

    python benchmarks/detect_runs.py
    python benchmarks/detect_runs.py --votes 3 --force
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from functools import cache
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _bench
import _detection
from score_runs import judge_command, prepare_judge_env

#: Run directories of samples whose rubric names one known defect, the way
#: CRBugBench tasks do (``_bench.run_key`` of ``review/crbug-<name>``).
DETECTION_PREFIX: Final = "review-crbug-"
_ATTEMPTS: Final = 3
_LOCATION_RE: Final = re.compile(r"cites its file and line in (.+?), and its verdict")
_CRITERION_LEAD_RE: Final = re.compile(r"^The review reports (?:that )?")


class JudgeCallError(RuntimeError):
    """The judge command failed or timed out."""


@cache
def _sample_tomls() -> dict[str, Path]:
    # Run directories are named by run_key; the registry knows where each sample lives.
    return {_bench.run_key(s.id): s.source_path for s in _bench.review_samples()}


def defect_for(run_key: str) -> _detection.Defect | None:
    """The known defect of the sample run under ``run_key``, or None without a single defect.

    Example::

        defect_for("review-crbug-log-textio").location  # "src/service.py (stop)"
    """
    path = _sample_tomls().get(run_key)
    if path is None or not run_key.startswith(DETECTION_PREFIX):
        return None
    spec = tomllib.loads(path.read_text(encoding="utf-8"))
    criteria = [item for bind in spec["rubric"]["bind"].values() for item in bind["rubric"]]
    main = max(criteria, key=lambda item: float(item["weight"]))
    found = (_LOCATION_RE.search(str(item["judge"])) for item in criteria)
    location = next((m.group(1) for m in found if m), None)
    # The criterion reads "The review reports that X"; the judge gets X itself.
    description = _CRITERION_LEAD_RE.sub("", str(main["judge"]), count=1)
    return _detection.Defect(
        description=description[:1].upper() + description[1:], location=location
    )


def ask_judge(command: list[str], prompt: str) -> str:
    """Run the judge command once with ``prompt``; its stdout, or :class:`JudgeCallError`."""
    argv = [part.replace("{prompt}", prompt) for part in command]
    try:
        done = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_bench.JUDGE_TIMEOUT_S,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        raise JudgeCallError(f"timed out after {_bench.JUDGE_TIMEOUT_S:g}s") from exc
    if done.returncode != 0:
        tail = " ".join((done.stderr or done.stdout).split())[-300:]
        raise JudgeCallError(f"exited {done.returncode}: {tail}")
    return done.stdout


def one_vote(command: list[str], prompt: str) -> _detection.Verdict:
    """One verdict, retrying a failed call or an off-format answer up to 3 times."""
    last: Exception | None = None
    for _ in range(_ATTEMPTS):
        try:
            return _detection.parse_verdict(ask_judge(command, prompt))
        except (JudgeCallError, _detection.VerdictError) as exc:
            last = exc
    raise JudgeCallError(f"no usable verdict after {_ATTEMPTS} attempts: {last}")


def detect_one(run: Path, sample_id: str, command: list[str], args: argparse.Namespace) -> str:
    """Write ``detect.json`` for one run; a one-line status."""
    out = run / "detect.json"
    experiment = run.parent.name
    if out.is_file() and not args.force:
        return f"skip   {experiment:20} {sample_id}"
    defect = defect_for(sample_id)
    if defect is None:
        return f"n/a    {experiment:20} {sample_id}"
    review = (run / "transcript.txt").read_text(encoding="utf-8")
    prompt = _detection.detection_prompt(defect, review)
    payload: dict[str, object] = {
        "sample_id": sample_id,
        "experiment": experiment,
        "defect": asdict(defect),
        "judge": {
            "model": _bench.JUDGE_MODEL,
            "effort": _bench.JUDGE_EFFORT,
            "votes": args.votes,
        },
    }
    try:
        payload.update(
            _detection.summarize_votes([one_vote(command, prompt) for _ in range(args.votes)])
        )
        status = f"{payload['detected']:7} first match {payload['first_match']}"
    except JudgeCallError as exc:
        # A refusal or a broken answer leaves no verdict; record why, never a guess.
        payload["error"] = str(exc)[:500]
        status = "ERROR"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return f"detect {experiment:20} {sample_id:42} {status}"


def _runs(run_name: str, experiments: list[str] | None) -> list[tuple[Path, str]]:
    root = _bench.RESULTS_ROOT / run_name
    runs = sorted(p.parent for p in root.glob(f"*/{DETECTION_PREFIX}*/agent.json"))
    if experiments:
        runs = [r for r in runs if r.parent.name in experiments]
    if not runs:
        raise FileNotFoundError(f"no saved {DETECTION_PREFIX}* runs under {root}")
    return [(run, run.name) for run in runs]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-name", default=_bench.DEFAULT_RUN_NAME)
    parser.add_argument("--votes", type=int, default=1, help="judge verdicts per run, averaged")
    parser.add_argument("--experiments", nargs="*", default=None)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true", help="re-judge runs that have detect.json")
    args = parser.parse_args(argv)
    if args.votes < 1:
        parser.error(f"--votes must be at least 1, got {args.votes}")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _bench.load_env_file()
    prepare_judge_env()
    command = judge_command()
    errors = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(detect_one, run, sid, command, args)
            for run, sid in _runs(args.run_name, args.experiments)
        ]
        for future in as_completed(futures):
            line = future.result()
            errors += line.endswith("ERROR")
            print(line, flush=True)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
