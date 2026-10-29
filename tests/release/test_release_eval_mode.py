"""``scripts/release_eval_mode.py``: the mode line of a release metrics file (spec D3)."""

from __future__ import annotations

from typing import Any

from coding_agent_playbook.evals.release_regression import check_regressions
from release_eval_mode import (
    carried_compared,
    carried_count,
    changed_only_mode,
    recorded_changed_only,
)
from tests.evals.release_metrics_files import metrics_file, sample_entry

_PREVIOUS = "9.9.8"


def _carried(release: str, inputs: str) -> dict[str, Any]:
    return sample_entry(0.9, inputs=inputs) | {"measured_in": {"release": release, "commit": "c"}}


def _new_file() -> dict[str, Any]:
    """One rerun entry and three carried ones; only ``c`` differs from the previous entry."""
    samples = {
        "a": sample_entry(0.9, inputs="i2"),
        # Measured in 9.9.7 and carried along through 9.9.8: the same inputs, not compared.
        "b": _carried("9.9.7", "i1"),
        "c": _carried("9.9.7", "i0"),
        "d": _carried("9.9.6", "i1"),
    }
    return metrics_file("9.9.9", samples)


def _previous_file() -> dict[str, Any]:
    samples = {sid: sample_entry(0.9, inputs="i1") for sid in ("a", "b", "c")}
    return metrics_file(_PREVIOUS, samples)


def test_only_carried_entries_the_check_compared_are_counted() -> None:
    new = _new_file()
    check = check_regressions(new, _previous_file())

    assert carried_count(new) == 3
    assert carried_compared(new, check) == 1


def test_the_mode_line_names_the_compared_count_and_the_previous_release() -> None:
    new = _new_file()
    check = check_regressions(new, _previous_file())

    line = changed_only_mode(new, full_rerun_reason=None, check=check)

    assert line == f"changed-only: 1 rerun, 3 carried (1 compared with {_PREVIOUS})"


def test_without_a_compared_entry_or_a_check_no_count_is_added() -> None:
    new = _new_file()
    del new["samples"]["c"]
    check = check_regressions(new, _previous_file())

    assert changed_only_mode(new, full_rerun_reason=None, check=check) == (
        "changed-only: 1 rerun, 2 carried"
    )
    assert changed_only_mode(new, full_rerun_reason="setup differs", check=None) == (
        "changed-only: 1 rerun (setup differs), 2 carried"
    )


def test_a_file_is_changed_only_when_it_carries_or_counts_carried_entries() -> None:
    assert recorded_changed_only(_new_file())
    assert recorded_changed_only({"samples": {}, "summary": {"carried": 0}})
    assert not recorded_changed_only({"samples": {"a": {}}, "summary": {}})
