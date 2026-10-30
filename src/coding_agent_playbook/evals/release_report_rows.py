"""The release report's CSV and judge-agreement rows (spec D4, D10).

Pure renderers over the sections ``evals.release_report`` builds: every value
is a string, ready for ``csv.DictWriter``; a missing value is the empty string.
A release with no baseline has an empty ``delta_mean`` and ``verdict``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.evals.release_metrics_schema import (
    JUDGE_CHANGE_KEY,
    MEASURED_IN_KEY,
    REJUDGED_FROM_KEY,
    SETUP_DIGEST_KEY,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.evals.release_regression import SampleVerdict
    from coding_agent_playbook.evals.release_report import TargetReport

#: The CSV columns, in order (spec D4).
CSV_COLUMNS: Final = (
    "release",
    "target",
    "task",
    "sample",
    "passes",
    "runs",
    "pass_rate",
    "mean_score",
    "delta_mean",
    "verdict",
    "measured_in_release",
    "rejudged_from_release",
    "judge_model",
    "inputs_digest",
    "setup_digest",
)
#: The judge-agreement columns, in order (spec D4).
AGREEMENT_COLUMNS: Final = (
    "release",
    "target",
    "task",
    "runs",
    "pass_agreement",
    "mean_abs_score_diff",
    "old_judge",
    "new_judge",
)


def csv_rows(sections: Sequence[TargetReport]) -> list[dict[str, str]]:
    """One row per sample of each section, in section order then sample id.

    Example::

        >>> csv_rows(report_sections)[0]["verdict"]  # doctest: +SKIP
        ''
    """
    rows = []
    for section in sections:
        verdicts = {v.sample_id: v for v in section.check.samples} if section.check else {}
        for sample_id, entry in sorted(section.data["samples"].items()):
            rows.append(_csv_row(section, sample_id, entry, verdicts.get(sample_id)))
    return rows


def agreement_rows(files: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """One row per task of each file that records ``judge_change``, tasks sorted.

    ``old_judge`` joins the old judges' models, sorted; ``new_judge`` is the new one's.

    Example::

        >>> agreement_rows(files)[0]["old_judge"]  # doctest: +SKIP
        'judge-old, judge-older'
    """
    rows = []
    for data in files:
        change = data.get(JUDGE_CHANGE_KEY)
        if not isinstance(change, dict):
            continue
        place = {"release": str(data["release"]), "target": str(data["target"]["name"])}
        judges = {
            "old_judge": old_judges(change),
            "new_judge": text(change["to"].get("judge_model")),
        }
        for task, agreement in sorted(change["tasks"].items()):
            rows.append(place | {"task": task} | _agreement(agreement) | judges)
    return rows


def old_judges(change: Mapping[str, Any]) -> str:
    """The old judges' models of a ``judge_change``, sorted and comma-separated."""
    models = {text(parts.get("judge_model")) for parts in change["from"]}
    return ", ".join(sorted(models))


def text(value: object) -> str:
    """``value`` as a CSV cell: numbers in short form, ``None`` as the empty string."""
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _csv_row(
    section: TargetReport,
    sample_id: str,
    entry: Mapping[str, Any],
    verdict: SampleVerdict | None,
) -> dict[str, str]:
    runs = int(entry["runs"])
    values: dict[str, object] = {
        "release": section.data["release"],
        "target": section.target,
        "task": entry["prompt_id"],
        "sample": sample_id,
        "passes": entry["passes"],
        "runs": runs,
        "pass_rate": float(entry["passes"]) / runs if runs else None,
        "mean_score": float(entry["mean_score"]),
        "delta_mean": verdict.delta if verdict is not None else None,
        "verdict": verdict.status if verdict is not None else None,
        "measured_in_release": _release(entry.get(MEASURED_IN_KEY)),
        "rejudged_from_release": _release(entry.get(REJUDGED_FROM_KEY)),
        "judge_model": section.data["target"].get("judge_model"),
        "inputs_digest": entry.get("inputs_digest"),
        "setup_digest": section.data.get(SETUP_DIGEST_KEY),
    }
    return {column: text(values[column]) for column in CSV_COLUMNS}


def _agreement(agreement: Mapping[str, Any]) -> dict[str, str]:
    keys = ("runs", "pass_agreement", "mean_abs_score_diff")
    return {key: text(agreement[key]) for key in keys}


def _release(place: object) -> str | None:
    """The ``release`` of a ``measured_in`` or ``rejudged_from`` object, else ``None``."""
    return str(place["release"]) if isinstance(place, dict) else None
