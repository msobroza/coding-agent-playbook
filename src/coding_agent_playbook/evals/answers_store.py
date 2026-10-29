"""The answers store: what each run's judge graded, kept so a new judge can re-grade it.

A record run stores, per sample and run, one JSON line in a gzip file
(spec D8 of ``specs/release-metric-artifacts.md``): the graded ``artifact``,
the judge-free ``checks`` by check id, each rubric criterion's weight and mean
score, and the ``judge`` parts. ``evals.rejudge`` (D9) later re-grades the
stored artifacts without rerunning any agent. This module is the only reader
and writer of the format.

- ``artifact`` is ``None`` when fail-fast skipped the judge (its criterion
  scores are ``None`` too), and for a re-judged run, whose ``artifact_ref``
  names the release and target whose file holds the artifact.
- A release's files live at ``<releases>/<v>/answers/<target>.jsonl.gz``
  (:func:`answers_path`).
"""

from __future__ import annotations

import gzip
import json
import zlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.evals.judge import Judge
from coding_agent_playbook.exit_two import ExitTwoError

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

    from coding_agent_playbook.evals.setup_digest import SetupParts

#: The answers file name's suffix after the target name.
ANSWERS_SUFFIX: Final = ".jsonl.gz"
#: The release directory's subdirectory that holds its answers files.
ANSWERS_DIRNAME: Final = "answers"
#: The setup parts that name the judge, copied onto every answers line.
JUDGE_PART_KEYS: Final = (
    "judge_model",
    "judge_endpoint_fingerprint",
    "judge_samples",
    "judge_version",
    "judge_reasoning_effort",
)


class AnswersError(ExitTwoError):
    """An answers file that cannot be read; the message names the path and the line."""


@dataclass(frozen=True)
class StoredCriterion:
    """One rubric criterion of a run: its weight and the judge's mean score over ``n`` draws.

    ``score`` is ``None`` when fail-fast skipped the judge.
    """

    criterion: str
    weight: float
    score: float | None
    n: int


@dataclass(frozen=True)
class ArtifactRef:
    """The release and target whose answers file holds a re-judged run's artifact (D9)."""

    release: str
    target: str


@dataclass(frozen=True)
class StoredRun:
    """One run of one sample, as an answers file line stores it (D8)."""

    sample: str
    inputs_digest: str
    run: int
    artifact: str | None
    checks: Mapping[str, float]
    criteria: tuple[StoredCriterion, ...]
    judge: Mapping[str, object]
    artifact_ref: ArtifactRef | None = None


class CapturingJudge(Judge):
    """A :class:`Judge` that delegates to ``inner`` and records every score it returns.

    ``calls`` holds ``(criterion, artifact as str, score, n)`` per call, so a
    record can store what was graded. Use one instance per run: it keeps no
    state beyond its own ``calls``.

    Example::

        >>> judge = CapturingJudge(StubJudge(default=0.7))
        >>> judge.score_criterion("is correct", "diff")
        0.7
        >>> judge.calls
        [('is correct', 'diff', 0.7, 1)]
    """

    def __init__(self, inner: Judge) -> None:
        self.inner = inner
        self.name = inner.name
        self.calls: list[tuple[str, str, float, int]] = []

    def score_criterion(self, criterion: str, artifact: Any, n: int = 1) -> float:
        score = self.inner.score_criterion(criterion, artifact, n=n)
        self.calls.append((criterion, str(artifact), score, n))
        return score


def answers_path(releases_root: Path, release: str, target: str) -> Path:
    """The answers file of ``target`` in ``release`` under ``releases_root``.

    Example::

        >>> answers_path(Path("catalog/releases"), "9.9.2", "opencode-qwen").as_posix()
        'catalog/releases/9.9.2/answers/opencode-qwen.jsonl.gz'
    """
    return releases_root / release / ANSWERS_DIRNAME / f"{target}{ANSWERS_SUFFIX}"


def judge_parts(setup: SetupParts | None) -> dict[str, object]:
    """The judge's setup parts, by name; each ``None`` without setup parts.

    Example::

        >>> judge_parts(None)["judge_model"] is None
        True
    """
    parts = setup.as_dict() if setup is not None else {}
    return {key: parts.get(key) for key in JUDGE_PART_KEYS}


def write_answers(path: Path, runs: Iterable[StoredRun]) -> None:
    """Write ``runs`` to ``path`` as gzip JSON Lines, sorted by ``(sample, run)``.

    Example::

        >>> write_answers(tmp / "a.jsonl.gz", [run])  # doctest: +SKIP
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(runs, key=lambda stored: (stored.sample, stored.run))
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for stored in ordered:
            handle.write(json.dumps(run_to_json(stored), sort_keys=True) + "\n")


def read_answers(path: Path) -> list[StoredRun]:
    """The runs stored at ``path``; :class:`AnswersError` names a bad line by number.

    Example::

        >>> read_answers(tmp / "a.jsonl.gz")  # doctest: +SKIP
        [StoredRun(sample='s-a', ...)]
    """
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except (OSError, EOFError, UnicodeDecodeError, zlib.error) as error:
        raise AnswersError(f"cannot read the answers file {path}: {error}") from error
    return [_parsed_line(path, number, line) for number, line in enumerate(lines, start=1)]


def _parsed_line(path: Path, number: int, line: str) -> StoredRun:
    try:
        return run_from_json(json.loads(line))
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise AnswersError(
            f"{path}:{number}: not an answers line ({error!r}): {line[:80]!r}"
        ) from error


def run_to_json(stored: StoredRun) -> dict[str, object]:
    """``stored`` as one answers line's JSON object; :func:`run_from_json` reads it back.

    A record's checkpoint keeps its runs in this form too, so the format has one owner.

    Example::

        >>> run_to_json(run)["sample"]  # doctest: +SKIP
        's-a'
    """
    line: dict[str, object] = {
        "sample": stored.sample,
        "inputs_digest": stored.inputs_digest,
        "run": stored.run,
        "artifact": stored.artifact,
        "checks": dict(stored.checks),
        "criteria": [vars(criterion) for criterion in stored.criteria],
        "judge": dict(stored.judge),
    }
    if stored.artifact_ref is not None:
        line["artifact_ref"] = vars(stored.artifact_ref)
    return line


def run_from_json(line: Mapping[str, Any]) -> StoredRun:
    """The run one answers line's JSON object stores; raises ``KeyError``/``TypeError``/``ValueError``.

    Example::

        >>> run_from_json(run_to_json(run)) == run  # doctest: +SKIP
        True
    """
    ref = line.get("artifact_ref")
    return StoredRun(
        sample=str(line["sample"]),
        inputs_digest=str(line["inputs_digest"]),
        run=int(line["run"]),
        artifact=_artifact(line["artifact"]),
        checks={str(key): float(value) for key, value in line["checks"].items()},
        criteria=tuple(_criterion(item) for item in line["criteria"]),
        judge=dict(line["judge"]),
        artifact_ref=ArtifactRef(str(ref["release"]), str(ref["target"])) if ref else None,
    )


def _criterion(item: Mapping[str, Any]) -> StoredCriterion:
    score = item["score"]
    return StoredCriterion(
        criterion=str(item["criterion"]),
        weight=float(item["weight"]),
        score=None if score is None else float(score),
        n=int(item["n"]),
    )


def _artifact(value: object) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise TypeError(f"artifact must be a string or null, got {value!r}")
