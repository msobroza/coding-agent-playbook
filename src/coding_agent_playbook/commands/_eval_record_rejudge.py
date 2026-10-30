"""Re-grade the stored answers of samples found only in agent-compatible files (spec D9).

``evals.result_index`` plans a re-judge for a sample whose entry only a file of
another judge holds (``CarryPlan.rejudge``). Before the first paid run,
:func:`resolve_rejudges` finds each entry's stored runs in the answers file of the
release that measured them (``RejudgeSource.answers_at``), following a re-judged
line's ``artifact_ref`` to the file holding its artifact. A sample reruns instead,
with the reason, when the file is missing (``answers not stored``), unreadable
(``answers unreadable: <path>``), lacks one of the entry's runs, holds a run no
judge graded although its gate held, or the sample cannot be re-scored.

Each remaining sample is a ``rejudge`` unit (``commands._eval_record_runs``):
:class:`Rejudger` grades every stored artifact on each rubric criterion with the
record's judge, through a new ``CapturingJudge`` per run, and re-scores the run
(``evals.rejudge``). A run whose gate fail-fast lost has no artifact and is not
re-graded: its verdict stays a fail. The entry folds like a fresh one
(``evals.release_metrics.rejudged_record``), and each run's new answers line
keeps no artifact but an ``artifact_ref`` to the file that holds it.
"""

from __future__ import annotations

import dataclasses
import sys
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands._eval_record_answers import captured_criteria
from coding_agent_playbook.commands._eval_record_runs import RecordUnit
from coding_agent_playbook.evals.answers_store import (
    AnswersError,
    CapturingJudge,
    StoredRun,
    answers_path,
    read_answers,
)
from coding_agent_playbook.evals.judge import JudgeError
from coding_agent_playbook.evals.model_pins import RecordRefusedError
from coding_agent_playbook.evals.rejudge import (
    RejudgeError,
    rejudge_refusal,
    rescore_run,
    rescore_unjudged_run,
    rubric_criteria,
)
from coding_agent_playbook.evals.release_metrics import (
    GRADED_HEAD,
    RunOutcome,
    SampleRuns,
    rejudged_record,
)
from coding_agent_playbook.evals.release_metrics_schema import (
    INPUTS_DIGEST_KEY,
    MEASURED_IN_KEY,
    REJUDGED_FROM_KEY,
)
from coding_agent_playbook.evals.sample_digest import prompt_digest, sample_digest

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.evals.answers_store import ArtifactRef
    from coding_agent_playbook.evals.judge import Judge
    from coding_agent_playbook.evals.release_carry import CarryPlan, RejudgeSource
    from coding_agent_playbook.evals.release_metrics import SampleRecord
    from coding_agent_playbook.evals.sample import EvalSample

#: The rerun reason of a sample whose stored answers cannot be found (spec D9).
NOT_STORED: Final = "answers not stored"


def resolve_rejudges(
    plan: CarryPlan, *, releases_root: Path | None, samples: Mapping[str, EvalSample]
) -> CarryPlan:
    """``plan`` with each re-judge's stored runs found, or the sample moved to ``rerun``.

    Example::

        >>> resolve_rejudges(plan, releases_root=Path("catalog/releases"), samples=by_id).rerun
        ... # doctest: +SKIP
        {'t/a': 'answers not stored'}
    """
    if not plan.rejudge:
        return plan
    files = _AnswersFiles(releases_root)
    rerun = dict(plan.rerun)
    rejudge: dict[str, RejudgeSource] = {}
    for sample_id, source in plan.rejudge.items():
        found = _stored_runs(files, samples[sample_id], source)
        if isinstance(found, str):
            rerun[sample_id] = found
            continue
        rejudge[sample_id] = dataclasses.replace(source, runs=found)
    return dataclasses.replace(plan, rerun=dict(sorted(rerun.items())), rejudge=rejudge)


def rejudge_units(
    samples: Sequence[EvalSample], inputs: Mapping[str, str], carry: CarryPlan | None
) -> list[RecordUnit]:
    """One ``rejudge`` unit per sample of ``carry.rejudge``; none without a carry plan.

    Example::

        >>> rejudge_units(samples, inputs, None)
        []
    """
    if carry is None:
        return []
    return [
        RecordUnit("rejudge", sample, index, inputs[sample.id])
        for index, sample in enumerate(samples)
        if sample.id in carry.rejudge
    ]


def rejudger(
    judge: Judge | None, *, judge_samples: int, parts: Mapping[str, object], carry: CarryPlan | None
) -> Rejudger | None:
    """The re-grader of ``carry``'s re-judge units; ``None`` when there is none to run.

    Example::

        >>> rejudger(None, judge_samples=1, parts={}, carry=None) is None
        True
    """
    if judge is None or carry is None or not carry.rejudge:
        return None
    return Rejudger(judge, judge_samples, parts, carry.rejudge)


@dataclasses.dataclass(frozen=True)
class Rejudger:
    """Re-grades one ``rejudge`` unit's stored runs with the record's ``judge`` (spec D9).

    ``parts`` are this record's judge parts, written on each new answers line.

    Example::

        >>> Rejudger(judge, 2, parts, plan.rejudge)(unit).entry["rejudged_from"]  # doctest: +SKIP
        {'release': '9.9.2', 'commit': None, 'judge': {...}}
    """

    judge: Judge
    judge_samples: int
    parts: Mapping[str, object]
    sources: Mapping[str, RejudgeSource]

    def __call__(self, unit: RecordUnit) -> SampleRecord:
        sample = unit.sample
        source = self.sources[sample.id]
        try:
            graded = [self._regrade(sample, stored) for stored in source.runs]
        except JudgeError as exc:
            raise RecordRefusedError(
                f"sample {sample.id!r} could not be re-judged, so nothing was recorded: {exc}"
            ) from exc
        outcomes = [outcome for outcome, _line in graded]
        passes = sum(1 for outcome in outcomes if outcome.passed)
        print(f"{sample.id}: re-judged, {passes}/{len(outcomes)} passed", file=sys.stderr)
        runs = SampleRuns(
            sample_id=sample.id,
            prompt_id=sample.prompt_id,
            graded=GRADED_HEAD,
            prompt_digest=prompt_digest(sample),
            sample_digest=sample_digest(sample),
            results=(),
            inputs_digest=unit.inputs_digest,
            answers=tuple(line for _outcome, line in graded),
        )
        provenance = {REJUDGED_FROM_KEY: source.rejudged_from, MEASURED_IN_KEY: source.measured_in}
        return rejudged_record(runs, outcomes, source.entry, provenance)

    def _regrade(self, sample: EvalSample, stored: StoredRun) -> tuple[RunOutcome, StoredRun]:
        """One stored run re-scored, and its new answers line; a lost gate is not re-graded."""
        judge = None if stored.artifact is None else self._grade(sample, stored.artifact)
        criteria = captured_criteria(sample, judge)
        if judge is None:
            score = rescore_unjudged_run(sample, stored.checks)
        else:
            scores = {c.criterion: c.score for c in criteria if c.score is not None}
            score = rescore_run(sample, stored.checks, scores)
        line = dataclasses.replace(stored, artifact=None, criteria=criteria, judge=dict(self.parts))
        return RunOutcome(score.passed, score.aggregate_score, score.checks), line

    def _grade(self, sample: EvalSample, artifact: str) -> CapturingJudge:
        """Every rubric criterion of ``sample`` graded on ``artifact`` by a fresh capture."""
        judge = CapturingJudge(self.judge)
        for text, _weight in rubric_criteria(sample):
            judge.score_criterion(text, artifact, n=max(1, self.judge_samples))
        return judge


class _AnswersFiles:
    """The releases directory's answers files, each read once: its runs, or why not."""

    def __init__(self, root: Path | None) -> None:
        self._root = root
        self._read: dict[Path, list[StoredRun] | str] = {}

    def lines(self, at: ArtifactRef) -> list[StoredRun] | str:
        if self._root is None:
            return NOT_STORED
        path = answers_path(self._root, at.release, at.target)
        if path not in self._read:
            self._read[path] = _read(path)
        return self._read[path]

    def located(self, run: StoredRun, at: ArtifactRef) -> StoredRun | str:
        """``run`` naming in ``artifact_ref`` the file whose line holds its artifact.

        A re-judged line keeps no artifact: its own ``artifact_ref`` is followed.
        """
        if run.artifact is not None or run.artifact_ref is None:
            return dataclasses.replace(run, artifact_ref=at)
        ref = run.artifact_ref
        lines = self.lines(ref)
        if isinstance(lines, str):
            return lines
        key = (run.sample, run.run, run.inputs_digest)
        match = next(
            (line for line in lines if (line.sample, line.run, line.inputs_digest) == key), None
        )
        if match is None:
            return NOT_STORED
        return dataclasses.replace(run, artifact=match.artifact, artifact_ref=ref)


def _read(path: Path) -> list[StoredRun] | str:
    """The runs stored at ``path``, or the rerun reason when it is missing or unreadable."""
    if not path.is_file():
        return NOT_STORED
    try:
        return read_answers(path)
    except AnswersError:
        return f"answers unreadable: {path}"


def _stored_runs(
    files: _AnswersFiles, sample: EvalSample, source: RejudgeSource
) -> tuple[StoredRun, ...] | str:
    """The entry's stored runs, located and re-scorable, or why the sample reruns."""
    refusal = rejudge_refusal(sample)
    if refusal is not None:
        return refusal
    lines = files.lines(source.answers_at)
    if isinstance(lines, str):
        return lines
    runs = _entry_runs(lines, sample.id, source)
    if runs is None:
        return NOT_STORED
    located = [files.located(run, source.answers_at) for run in runs]
    reasons = [run for run in located if isinstance(run, str)]
    if reasons:
        return reasons[0]
    found = tuple(run for run in located if not isinstance(run, str))
    return found if all(_regradable(sample, run) for run in found) else NOT_STORED


def _entry_runs(
    lines: Sequence[StoredRun], sample_id: str, source: RejudgeSource
) -> list[StoredRun] | None:
    """The line of each of the entry's runs at its inputs digest; ``None`` when one is missing."""
    digest = source.entry.get(INPUTS_DIGEST_KEY)
    mine = {
        line.run: line for line in lines if (line.sample, line.inputs_digest) == (sample_id, digest)
    }
    wanted = range(int(source.entry["runs"]))
    if any(run not in mine for run in wanted):
        return None
    return [mine[run] for run in wanted]


def _regradable(sample: EvalSample, run: StoredRun) -> bool:
    """Whether ``run`` can be re-scored: it has an artifact, or no judge was due (a lost gate)."""
    if run.artifact is not None:
        return True
    try:
        rescore_unjudged_run(sample, run.checks)
    except RejudgeError:
        return False
    return True
