"""``scripts/release_eval_mode.py``: the mode line of a release metrics file (spec D3)."""

from __future__ import annotations

from typing import Any

from release_eval_mode import (
    carried_count,
    carried_from_older,
    changed_only_mode,
    recorded_changed_only,
)

_PREVIOUS = "9.9.8"


def _metrics(*releases: str | None) -> dict[str, Any]:
    """A file with one rerun entry and one carried entry per release in ``releases``."""
    samples: dict[str, Any] = {"rerun": {}}
    for i, release in enumerate(releases):
        samples[f"carried-{i}"] = {"measured_in": {"release": release, "commit": "c"}}
    return {"samples": samples}


def test_carried_entries_from_other_releases_than_the_previous_are_older() -> None:
    metrics = _metrics(_PREVIOUS, "9.9.7", "9.9.6")

    assert carried_count(metrics) == 3
    assert carried_from_older(metrics, _PREVIOUS) == 2


def test_the_mode_line_names_the_older_count_only_when_there_is_one() -> None:
    older = changed_only_mode(
        _metrics(_PREVIOUS, "9.9.7"), full_rerun_reason=None, previous=_PREVIOUS
    )
    none = changed_only_mode(_metrics(_PREVIOUS), full_rerun_reason=None, previous=_PREVIOUS)

    assert older == "changed-only: 1 rerun, 2 carried (1 from older releases)"
    assert none == "changed-only: 1 rerun, 1 carried"


def test_without_a_previous_release_every_carried_entry_is_older() -> None:
    line = changed_only_mode(_metrics("9.9.7"), full_rerun_reason="setup differs", previous=None)

    assert line == "changed-only: 1 rerun (setup differs), 1 carried (1 from older releases)"


def test_a_file_is_changed_only_when_it_carries_or_counts_carried_entries() -> None:
    assert recorded_changed_only(_metrics("9.9.7"))
    assert recorded_changed_only({"samples": {}, "summary": {"carried": 0}})
    assert not recorded_changed_only({"samples": {"a": {}}, "summary": {}})
