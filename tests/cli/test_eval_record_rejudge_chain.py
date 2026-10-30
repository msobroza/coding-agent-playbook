"""Which answers a re-judge reads along a chain of releases (spec D9, ``judged_in``).

R1 measured a sample with judge A; R2 re-judged it with judge B, so R2's answers
lines hold B's scores and an ``artifact_ref`` to R1, which holds the artifact. A
record with judge C must read B's lines (the latest judge's) and R1's artifact,
directly from R2 or, after R2.1 carried R2's entry, through ``judged_in``.
Releases are hand-written; the resolver runs on the shipped ``spot-the-bug``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.commands._eval_record_rejudge import resolve_rejudges
from coding_agent_playbook.evals.answers_store import (
    ArtifactRef,
    StoredCriterion,
    StoredRun,
    answers_path,
    write_answers,
)
from coding_agent_playbook.evals.rejudge import rubric_criteria
from coding_agent_playbook.evals.release_carry import carried_entry
from coding_agent_playbook.evals.result_index import ReleaseIndex
from coding_agent_playbook.evals.setup_digest import SetupParts
from coding_agent_playbook.evals.task_registry import load_task_sample
from tests._catalog import CORE_ROOT
from tests.evals.release_metrics_files import metrics_file, sample_entry

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.evals.release_carry import CarryPlan

_ID = "review/spot-the-bug"
_TARGET = "opus"
_DIGEST = "in-a"
_SAMPLE = load_task_sample(CORE_ROOT / "eval_samples" / _ID, source_package="engine")
_BASE = SetupParts(
    "claude_code", "2.1.300", "m", None, None, 1, "judge-c", None, 1, None, True, True, "s1"
).as_dict()


def _setup(judge: str) -> dict[str, object]:
    return _BASE | {"judge_model": judge}


def _write(root: Path, release: str, entry: dict[str, Any], judge: str) -> None:
    data = metrics_file(release, {_ID: entry}, target=_TARGET, commit=f"c{release}")
    data |= {"setup_digest": "d", "setup": _setup(judge)}
    path = root / release / "metrics" / f"{_TARGET}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _line(score: float, artifact: str | None, ref: ArtifactRef | None = None) -> StoredRun:
    criteria = tuple(StoredCriterion(t, w, score, 1) for t, w in rubric_criteria(_SAMPLE))
    return StoredRun(_ID, _DIGEST, 0, artifact, {"gate": 1.0}, criteria, {}, ref)


def _r1_and_r2(root: Path) -> dict[str, Any]:
    """R1 (judge A, artifact) and R2 (judge B re-judged R1); returns R2's entry."""
    _write(root, "9.9.1", sample_entry(0.5, runs=1, passes=1, inputs=_DIGEST), "judge-a")
    write_answers(answers_path(root, "9.9.1", _TARGET), [_line(0.2, "diff of R1")])
    measured = {"release": "9.9.1", "commit": "c9.9.1", "target": _TARGET}
    rejudged = {"release": "9.9.1", "commit": "c9.9.1", "judge": {"judge_model": "judge-a"}}
    entry = sample_entry(0.6, runs=1, passes=1, inputs=_DIGEST) | {
        "measured_in": measured,
        "rejudged_from": rejudged,
    }
    _write(root, "9.9.2", entry, "judge-b")
    r1 = ArtifactRef("9.9.1", _TARGET)
    write_answers(answers_path(root, "9.9.2", _TARGET), [_line(0.7, None, r1)])
    return entry


def _resolved(root: Path) -> CarryPlan:
    plan = ReleaseIndex.load(root).plan(
        target_name=_TARGET, setup=_setup("judge-c"), inputs={_ID: _DIGEST}
    )
    return resolve_rejudges(plan, releases_root=root, samples={_ID: _SAMPLE})


def _assert_reads_r2(plan: CarryPlan, *, source: str) -> None:
    assert plan.rerun == {}
    found = plan.rejudge[_ID]
    assert found.label == f"{source} ({_TARGET})"
    assert found.judge["judge_model"] == "judge-b"
    assert found.rejudged_from["judge"] == found.judge
    (run,) = found.runs
    assert {criterion.score for criterion in run.criteria} == {0.7}  # judge B's lines
    assert (run.artifact, run.artifact_ref) == ("diff of R1", ArtifactRef("9.9.1", _TARGET))
    assert found.measured_in["release"] == "9.9.1"


def test_a_second_rejudge_reads_the_first_rejudges_lines(tmp_path: Path) -> None:
    _r1_and_r2(tmp_path)

    _assert_reads_r2(_resolved(tmp_path), source="9.9.2")


def test_a_carried_rejudged_entry_is_read_through_judged_in(tmp_path: Path) -> None:
    entry = _r1_and_r2(tmp_path)
    carried = carried_entry(entry, release="9.9.2", commit="c9.9.2", target=_TARGET)
    assert carried["judged_in"] == {"release": "9.9.2", "commit": "c9.9.2", "target": _TARGET}
    _write(tmp_path, "9.9.3", dict(carried), "judge-b")  # R2.1 carried R2's entry

    _assert_reads_r2(_resolved(tmp_path), source="9.9.3")
