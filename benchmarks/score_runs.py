"""Phase 2 of the review benchmark: grade the saved runs with the engine's scorer + LLM judge.

For each run ``run_agents.py`` saved, this rebuilds the engine's ``Baseline`` and
``Candidate`` from the kept working tree and transcript, then calls the engine's
own :func:`score` with full scoring (no fail-fast: the judge grades every run,
even one whose deterministic gate failed). The judge is the engine's
``LLMJudge`` running Opus 5.5 at medium effort through the ``claude`` CLI in
``--bare`` mode (no hooks, plugins, CLAUDE.md or tools), with ``ANT_API_KEY`` or
the ``ANTHROPIC_API_KEY`` from ``.env``.

Usage::

    python benchmarks/score_runs.py
    python benchmarks/score_runs.py --stub-judge   # free fixed 0.5 judge, a dry run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _bench

from coding_agent_playbook.evals.judge import Judge, JudgeError, LLMJudge, StubJudge
from coding_agent_playbook.evals.report_format import sample_result_to_dict
from coding_agent_playbook.evals.run.harness_runner import (
    Baseline,
    SampleResult,
    capture,
)
from coding_agent_playbook.evals.run.scoring import score
from coding_agent_playbook.grading.types import TrialResult

if TYPE_CHECKING:
    from coding_agent_playbook.evals.run.harness_runner import Candidate
    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.grading.types import EvaluationReport


def judge_command() -> list[str]:
    """The ``LLMJudge`` command template (``{prompt}`` filled per call).

    Example::

        judge_command()[:3]  # ["claude", "-p", "--bare"]
    """
    return [
        "claude", "-p", "--bare",
        "--model", _bench.JUDGE_MODEL,
        "--effort", _bench.JUDGE_EFFORT,
        "--tools", "",
        "--no-session-persistence",
        "{prompt}",
    ]  # fmt: skip


def prepare_judge_env() -> None:
    """Give the judge subprocesses the benchmark's key, never the parent session's."""
    _bench.drop_parent_session_env()
    os.environ["ANTHROPIC_API_KEY"] = anthropic_judge_key()


def anthropic_judge_key() -> str:
    """The Anthropic judge's key: ``ANT_API_KEY``, else the ``.env`` file's ``ANTHROPIC_API_KEY``.

    Never an inherited ``ANTHROPIC_API_KEY``: inside a Claude Code session that
    one belongs to the parent app (see :func:`_bench.drop_parent_session_env`).
    """
    key = os.environ.get("ANT_API_KEY") or _bench.env_file_value("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("no Anthropic judge key: set ANT_API_KEY or ANTHROPIC_API_KEY in .env")
    return key


class RecordingJudge:
    """Wraps a judge and keeps each criterion's score, which the engine's JSON omits.

    Example::

        judge = RecordingJudge(StubJudge(default=0.5))
        judge.score_criterion("finds the bug", "artifact")  # 0.5; judge.calls has one row
    """

    def __init__(self, inner: Judge) -> None:
        self._inner = inner
        self.calls: list[dict[str, object]] = []

    def score_criterion(self, criterion: str, artifact: Any, n: int = 1) -> float:
        value = self._inner.score_criterion(criterion, artifact, n)
        self.calls.append({"criterion": criterion, "score": value, "n": n})
        return value


def _sample_spec(sample: EvalSample) -> dict[str, Any]:
    return tomllib.loads(sample.source_path.read_text(encoding="utf-8"))


def gate_detail(sample: EvalSample, candidate: Candidate) -> dict[str, bool]:
    """Each ``[gate.bind]`` handle's own result; the engine's JSON keeps only the layer's.

    Re-derived for the two check kinds the review samples use, from the same
    artifact the engine grades (the diff when there is one, else the transcript).
    """
    artifact = candidate.diff if candidate.diff.strip() else candidate.transcript
    handles = _sample_spec(sample)["gate"]["bind"]
    return {
        name: _handle_passed(h, artifact, candidate.changed_files) for name, h in handles.items()
    }


def _handle_passed(handle: dict[str, str], artifact: str, changed: list[str]) -> bool:
    if handle["check"] == "file_unchanged":
        return handle["path"] not in changed
    if handle["check"] == "answer_matches":
        return re.search(handle["pattern"], artifact) is not None
    raise ValueError(
        f"unsupported gate check {handle['check']!r}; expected file_unchanged or answer_matches"
    )


def gate_expr_holds(sample: EvalSample, detail: dict[str, bool]) -> bool:
    """The sample's ``[gate].expr`` (``and``/``or``/``not`` over handle names) on ``detail``."""
    expr = _sample_spec(sample)["gate"]["expr"]
    return bool(eval(expr, {"__builtins__": {}}, dict(detail)))


def rubric_weighted(sample: EvalSample, calls: list[dict[str, object]]) -> float | None:
    """The weighted mean judge score over the sample's rubric criteria (``None`` if unjudged).

    The engine's rubric layer score is pass/fail against its ``fail`` bound; this
    is the 0-1 quality underneath it.
    """
    weights = {
        item["judge"]: float(item["weight"])
        for bind in _sample_spec(sample)["rubric"]["bind"].values()
        for item in bind["rubric"]
    }
    for call in calls:
        call["weight"] = weights.get(str(call["criterion"]))
    scored = [(float(c["weight"]), float(c["score"])) for c in calls if c["weight"] is not None]  # type: ignore[arg-type]
    total = sum(w for w, _ in scored)
    return sum(w * s for w, s in scored) / total if total else None


#: What score.json records as the stub judge's model.
_STUB_MODEL = "stub-0.5"


def build_judge(stub: bool) -> Judge:
    """The Opus 5.5 judge, or with ``stub`` a free fixed 0.5 for dry runs."""
    if stub:
        return StubJudge(default=0.5)
    return LLMJudge(command=judge_command(), timeout=_bench.JUDGE_TIMEOUT_S)


def _has_judge_score(out: Path) -> bool:
    """Whether ``out`` holds a ``score.json`` the judge scored.

    A run the judge refused or could not reach (a network outage) is tried
    again on the next pass instead of being skipped.
    """
    path = out / "score.json"
    return path.is_file() and not json.loads(path.read_text(encoding="utf-8")).get("judge_error")


def score_one(sample: EvalSample, out: Path, judge: Judge, args: argparse.Namespace) -> str:
    """Grade one saved run into ``score.json``; a one-line status."""
    meta = json.loads((out / "agent.json").read_text(encoding="utf-8"))
    if _has_judge_score(out) and not args.force:
        return f"skip  {meta['experiment']:16} {sample.id}"
    transcript = (out / "transcript.txt").read_text(encoding="utf-8")
    # Saved paths may start with ~ (results are committed without the home path).
    scratch = Path(meta["scratch"]).expanduser()
    snapshot = Path(meta["setup_snapshot"]).expanduser()
    baseline = Baseline(scratch, meta["baseline_commit"], snapshot)
    candidate = capture(scratch, baseline, transcript)
    recorder = RecordingJudge(judge)
    judge_error = None
    try:
        report = score(
            sample,
            baseline,
            candidate,
            judge=recorder,
            judge_samples=args.judge_samples,
            fail_fast=False,
        )
    except JudgeError as exc:
        # The judge refused or failed after its retries (the API's filters can
        # refuse a whole transcript). Keep the deterministic gate and record why
        # there is no judge score; a skipped rubric must never count as a pass.
        judge_error = str(exc)[:500]
        report = score(sample, baseline, candidate, judge=None, fail_fast=False)
    verdict = _verdict(report, judge_error)
    result = SampleResult(
        sample_id=sample.id,
        harness=f"{meta.get('harness', 'opencode')}:{meta['experiment']}",
        report=report,
        passed=bool(verdict),
        aggregate_score=report.composite if report.composite is not None else float(report.passed),
        duration_seconds=meta["duration_seconds"],
        transcript=transcript,
        trials=[TrialResult(report=report, verdict=report.passed)],
    )
    detail = gate_detail(sample, candidate)
    payload = sample_result_to_dict(result)
    payload.update(
        experiment=meta["experiment"],
        agent=meta,
        judge={"model": _STUB_MODEL if args.stub_judge else _bench.JUDGE_MODEL,
               "effort": _bench.JUDGE_EFFORT, "judge_samples": args.judge_samples},
        judge_calls=recorder.calls,
        rubric_weighted_score=rubric_weighted(sample, recorder.calls),
        gate_detail=detail,
        gate_detail_matches_engine=gate_expr_holds(sample, detail) == _layer_passed(report, "gate"),
        changed_files=candidate.changed_files,
        graded_artifact="diff" if candidate.diff.strip() else "transcript",
        passed=verdict,
        judge_error=judge_error,
    )  # fmt: skip
    (out / "score.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    shown = {True: "PASS", False: "fail", None: "n/a (no judge score)"}[verdict]
    return f"score {meta['experiment']:16} {sample.id:42} {shown}"


def _verdict(report: EvaluationReport, judge_error: str | None) -> bool | None:
    """The sample verdict; without a judge score only a lost gate decides it (a fail)."""
    if judge_error is None:
        return report.passed
    return False if _layer_passed(report, "gate") is False else None


def _layer_passed(report: EvaluationReport, layer: str) -> bool | None:
    for check in report.checks:
        if check.check_id == layer:
            return check.passed if check.status == "run" else None
    return None


def _saved_runs(run_name: str) -> list[tuple[EvalSample, Path]]:
    # Run dirs are named by run_key(sample.id), not by the <task>/<name> id itself.
    samples = {_bench.run_key(s.id): s for s in _bench.review_samples()}
    root = _bench.RESULTS_ROOT / run_name
    runs = sorted(root.glob("*/*/agent.json"))
    if not runs:
        raise FileNotFoundError(f"no saved runs under {root}; run run_agents.py first")
    return [(samples[path.parent.name], path.parent) for path in runs]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-name", default=_bench.DEFAULT_RUN_NAME)
    parser.add_argument(
        "--stub-judge", action="store_true", help="a free fixed 0.5 judge, to dry-run the pipeline"
    )
    parser.add_argument("--judge-samples", type=int, default=1)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true", help="re-score scored runs")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _bench.load_env_file()
    if not args.stub_judge:
        prepare_judge_env()
    judge = build_judge(args.stub_judge)
    runs = _saved_runs(args.run_name)
    failures = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(score_one, s, d, judge, args): d for s, d in runs}
        for future in as_completed(futures):
            try:
                print(future.result(), flush=True)
            except (JudgeError, RuntimeError, OSError) as exc:
                failures += 1
                print(f"FAIL  {futures[future]}: {exc}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
