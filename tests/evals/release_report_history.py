"""A hand-written release metrics history for the release report's tests (spec D4).

:func:`write_history` writes three releases (9.9.2, 9.9.3, 9.9.4) of two
targets under ``<root>/<version>/metrics/<target>.json``; the judge of
``claude-opus`` changes at 9.9.4, which re-judges one sample and records
``judge_change``. Each entry is built with ``release_metrics_files`` so only the
numbers a report shows are spelled out here.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Final

from tests.evals.release_metrics_files import metrics_file, sample_entry

if TYPE_CHECKING:
    from pathlib import Path

OPUS: Final = "claude-opus"
QWEN: Final = "opencode-qwen"
RELEASES: Final = ("9.9.2", "9.9.3", "9.9.4")
OLD_JUDGE: Final = "judge-old"
NEW_JUDGE: Final = "judge-new"


def entry(task: str, mean: float, passes: int, **extra: Any) -> dict[str, Any]:
    """A 3-run entry of ``task`` with ``passes`` passing runs; ``extra`` adds provenance keys."""
    sample = sample_entry(mean, passes=passes, inputs=f"inputs-{task}-{mean}")
    return sample | {"prompt_id": task} | extra


def carried(task: str, mean: float, passes: int, inputs: str, release: str) -> dict[str, Any]:
    """An entry carried from ``release`` with the baseline's ``inputs`` digest."""
    place = {"release": release, "commit": None}
    return entry(task, mean, passes, measured_in=place) | {"inputs_digest": inputs}


def file_of(
    release: str,
    target: str,
    samples: dict[str, dict[str, Any]],
    *,
    judge: str = OLD_JUDGE,
    controls: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A metrics file of ``target`` in ``release``, judged by ``judge``, with a setup digest."""
    data = metrics_file(release, samples, target=target, controls=controls)
    data["target"]["judge_model"] = judge
    return data | {"setup_digest": f"setup-{release}-{target}"}


def write_file(root: Path, data: dict[str, Any]) -> Path:
    """Write ``data`` at ``<root>/<release>/metrics/<target>.json``; return the path."""
    path = root / str(data["release"]) / "metrics" / f"{data['target']['name']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _opus_992() -> dict[str, Any]:
    samples = {
        "review/a": entry("review", 0.9, 3),
        "review/b": entry("review", 0.7, 2),
        "tidy/a": entry("tidy", 0.8, 3),
    }
    controls = {"review/a": entry("review", 0.85, 3) | {"graded": "9.9.1"}}
    return file_of("9.9.2", OPUS, samples, controls=controls)


def _opus_993() -> dict[str, Any]:
    samples = {
        "review/a": entry("review", 0.92, 3),
        "review/b": entry("review", 0.5, 1),
        "review/c": entry("review", 0.95, 3),
        "tidy/a": carried("tidy", 0.8, 3, "inputs-tidy-0.8", "9.9.2"),
    }
    controls = {"review/a": entry("review", 0.86, 3) | {"graded": "9.9.1"}}
    return file_of("9.9.3", OPUS, samples, controls=controls)


def _opus_994() -> dict[str, Any]:
    rejudged_from = {"release": "9.9.3", "commit": None, "judge": {"judge_model": OLD_JUDGE}}
    rejudged = carried("review", 0.88, 3, "inputs-review-0.92", "9.9.3")
    samples = {
        "review/a": rejudged | {"rejudged_from": rejudged_from},
        "review/b": entry("review", 0.7, 2),
        "review/c": entry("review", 0.95, 3) | {"inputs_digest": "inputs-review-0.95"},
        "tidy/a": carried("tidy", 0.8, 3, "inputs-tidy-0.8", "9.9.2"),
    }
    controls = {"review/a": entry("review", 0.86, 3) | {"graded": "9.9.1"}}
    data = file_of("9.9.4", OPUS, samples, judge=NEW_JUDGE, controls=controls)
    return data | {"judge_change": _judge_change()}


def _judge_change() -> dict[str, Any]:
    review = {"runs": 3, "pass_agreement": 1.0, "mean_abs_score_diff": 0.04}
    return {
        "from": [{"judge_model": OLD_JUDGE}, {"judge_model": "judge-older"}],
        "to": {"judge_model": NEW_JUDGE},
        **review,
        "tasks": {"review": review},
    }


def _qwen(release: str, review: tuple[float, int], tidy: tuple[float, int]) -> dict[str, Any]:
    samples = {"review/a": entry("review", *review), "tidy/a": entry("tidy", *tidy)}
    return file_of(release, QWEN, samples)


def _qwen_994() -> dict[str, Any]:
    """9.9.4 of ``opencode-qwen``: ``review/a`` regressed, accepted by an earlier check."""
    data = _qwen("9.9.4", (0.6, 2), (0.6, 2))
    data["samples"]["review/a"]["vs_previous"] = {"accepted": "the rubric is stricter"}
    return data


def history_files() -> list[dict[str, Any]]:
    """Every file of the fixture history, oldest release first.

    Each file after a target's first records the release before it as
    ``previous``, as the release gate's regression check writes it.
    """
    files = [
        _opus_992(),
        _qwen("9.9.2", (0.6, 2), (0.5, 1)),
        _opus_993(),
        _qwen("9.9.3", (0.75, 3), (0.5, 1)),
        _opus_994(),
        _qwen_994(),
    ]
    last: dict[str, str] = {}
    for data in files:
        name = data["target"]["name"]
        data["previous"] = last.get(name)
        last[name] = data["release"]
    return files


def write_history(root: Path) -> Path:
    """Write :func:`history_files` under ``root``; return ``root``."""
    for data in history_files():
        write_file(root, data)
    return root
