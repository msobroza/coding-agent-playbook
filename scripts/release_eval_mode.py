"""The mode a release metrics file was recorded in, as ``prepare --eval`` reports it.

A changed-only recording (``--carry-from``) marks each carried entry with
``measured_in``; ``scripts/release_eval.py`` counts them here for the pull
request's "changed-only: N rerun, M carried (K from older releases)" line.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


def carried_count(metrics: Mapping[str, object]) -> int:
    """The number of carried entries (those with ``measured_in``) in ``metrics``.

    Example::

        >>> carried_count({"samples": {"a": {"measured_in": {"release": "9.9.8"}}, "b": {}}})
        1
    """
    return len(_measured_in(metrics))


def carried_from_older(metrics: Mapping[str, object], previous: str | None) -> int:
    """The carried entries of ``metrics`` measured in a release other than ``previous``.

    Example::

        >>> carried_from_older({"samples": {"a": {"measured_in": {"release": "9.9.7"}}}}, "9.9.8")
        1
    """
    releases = [
        where.get("release") if isinstance(where, dict) else None for where in _measured_in(metrics)
    ]
    return sum(1 for release in releases if release != previous)


def changed_only_mode(
    metrics: Mapping[str, object], *, full_rerun_reason: str | None, previous: str | None
) -> str:
    """``changed-only: N rerun, M carried``, with the full-rerun reason and the older count.

    Example::

        >>> changed_only_mode({"samples": {"a": {}}}, full_rerun_reason=None, previous=None)
        'changed-only: 1 rerun, 0 carried'
    """
    carried = carried_count(metrics)
    samples = metrics.get("samples")
    total = len(samples) if isinstance(samples, dict) else 0
    why = "" if full_rerun_reason is None else f" ({full_rerun_reason})"
    older = carried_from_older(metrics, previous)
    where = f" ({older} from older releases)" if older else ""
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


def _measured_in(metrics: Mapping[str, object]) -> list[object]:
    """The ``measured_in`` of every carried entry in ``metrics``."""
    samples = metrics.get("samples")
    entries = samples.values() if isinstance(samples, dict) else ()
    return [e["measured_in"] for e in entries if isinstance(e, dict) and "measured_in" in e]
