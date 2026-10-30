"""The mode a release metrics file was recorded in, as ``prepare --eval`` reports it.

A changed-only recording (``--carry-from``) marks each carried entry with
``measured_in``; ``scripts/release_eval.py`` counts them here for the pull
request's "changed-only: N rerun, M carried (K compared with <previous>)" line.
K counts the carried entries the regression check compared like a rerun: carried
from an older release, with inputs that differ from the previous release's entry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evals.release_metrics_schema import rejudged_here

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.evals.release_regression import RegressionCheck

#: Verdicts of a carried entry that the check did not compare with a previous entry
#: (a re-judged entry has ``measured_in`` too, spec D11).
_NOT_COMPARED: Final = frozenset({"carried", "new", "rejudged"})


def carried_count(metrics: Mapping[str, object]) -> int:
    """The number of carried entries (those with ``measured_in``) in ``metrics``.

    Example::

        >>> carried_count({"samples": {"a": {"measured_in": {"release": "9.9.8"}}, "b": {}}})
        1
    """
    return len(_carried_ids(metrics))


def carried_compared(metrics: Mapping[str, object], check: RegressionCheck) -> int:
    """The carried entries of ``metrics`` that ``check`` compared like a rerun.

    A ``carried`` verdict (same inputs as the previous entry), a ``new`` one
    (no previous entry) and a ``rejudged`` one (same answers, new judge) were not
    compared; any other verdict was, and can block. An entry re-judged in this
    file (``rejudged_here``) is not a carried one, even when the check compared
    it; one carried after a re-judge (``judged_in``) is.

    Example::

        >>> carried_compared(metrics, check)  # doctest: +SKIP
        1
    """
    compared = {v.sample_id for v in check.samples if v.status not in _NOT_COMPARED}
    samples = metrics.get("samples")
    entries = samples if isinstance(samples, dict) else {}
    carried = {sid for sid in _carried_ids(metrics) if not rejudged_here(entries[sid])}
    return len(compared & carried)


def changed_only_mode(
    metrics: Mapping[str, object], *, full_rerun_reason: str | None, check: RegressionCheck | None
) -> str:
    """``changed-only: N rerun, M carried``, with the full-rerun reason and the compared count.

    Without a ``check`` (no previous file) nothing was compared, so no count is added.

    Example::

        >>> changed_only_mode({"samples": {"a": {}}}, full_rerun_reason=None, check=None)
        'changed-only: 1 rerun, 0 carried'
    """
    carried = carried_count(metrics)
    samples = metrics.get("samples")
    total = len(samples) if isinstance(samples, dict) else 0
    why = "" if full_rerun_reason is None else f" ({full_rerun_reason})"
    compared = 0 if check is None else carried_compared(metrics, check)
    where = f" ({compared} compared with {check.previous})" if check and compared else ""
    return f"changed-only: {total - carried} rerun{why}, {carried} carried{where}"


def recorded_changed_only(metrics: Mapping[str, object]) -> bool:
    """Whether a kept file was recorded changed-only: it carries entries, or counts them.

    Only a ``--carry-from`` recording writes ``carried`` in the summary, so a
    changed-only file whose every sample changed (0 carried) still reads so.

    Example::

        >>> recorded_changed_only({"samples": {}, "summary": {"carried": 0}})
        True
    """
    summary = metrics.get("summary")
    return carried_count(metrics) > 0 or (isinstance(summary, dict) and "carried" in summary)


def _carried_ids(metrics: Mapping[str, object]) -> set[str]:
    """The sample ids of every carried entry (one with ``measured_in``) in ``metrics``."""
    samples = metrics.get("samples")
    entries = samples.items() if isinstance(samples, dict) else ()
    return {sid for sid, e in entries if isinstance(e, dict) and "measured_in" in e}
