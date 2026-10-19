"""The four ml-data members for array and data-frame code (specs/prS-skills-context.md 12).

They gate on ``any_ml_stack: [numpy, pandas, polars]`` (D9), one gate for the
three libraries, so each renders one section per library the repo declares: a
NumPy-only repo gets the NumPy parts and no data-frame guidance (R5-2). torch
alone activates none of them, so a torch-only repo keeps
``ml-serialization-security`` as ml-data's only member, and the resync golden
for adding torch stays byte-identical.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

import pytest

from coding_agent_playbook.orchestrator import filter_applies_if
from tests._budget_probe import render_core_rule
from tests._catalog import core_rules
from tests.unit.test_core_rule_shapes import ML_ARRAY_RULE_IDS, assert_fits_one_reference_read

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.detector import Facts

pytestmark = pytest.mark.catalog

#: Every library one of the four rules branches on: their longest rendered form.
_EVERY_BRANCH_LIBRARY: Final = ("numpy", "pandas", "polars", "scikit-learn", "torch")


def _ml_facts(*libraries: str) -> Facts:
    """Detector facts whose ``ml_stack`` declares exactly ``libraries``."""
    return cast("Facts", {"ml_stack": dict.fromkeys(libraries, ">=1")})


def _active_ml_data_members(facts: Facts, repo_root: Path) -> list[str]:
    """The ids of ml-data's member rules that pass ``applies_if``, as sync filters them."""
    members = [rule for rule in core_rules().values() if rule.frontmatter.skill == "ml-data"]
    return sorted(rule.frontmatter.id for rule in filter_applies_if(members, facts, repo_root))


@pytest.mark.parametrize(
    ("ml_stack", "active"),
    [
        (("numpy",), True),
        (("pandas",), True),
        (("polars",), True),
        (("torch",), False),
        ((), False),
    ],
)
def test_ml_data_rules_gate_on_numpy_pandas_polars(
    ml_stack: tuple[str, ...], active: bool, tmp_path: Path
) -> None:
    members = _active_ml_data_members(_ml_facts(*ml_stack), tmp_path)

    distilled = [rule_id for rule_id in members if rule_id in ML_ARRAY_RULE_IDS]
    assert distilled == (list(ML_ARRAY_RULE_IDS) if active else []), (
        f"ml_stack {list(ml_stack)} activates {distilled}; expected "
        f"{list(ML_ARRAY_RULE_IDS) if active else 'none'} of the four array rules"
    )


def test_torch_only_repo_keeps_serialization_as_the_only_ml_data_member(tmp_path: Path) -> None:
    """Spec 12.2: torch alone adds no member, so the add-torch resync golden is unchanged."""
    members = _active_ml_data_members(_ml_facts("torch"), tmp_path)

    assert members == ["ml-serialization-security"], f"torch alone activates {members}"


def _section_rows() -> list[tuple[str, tuple[str, ...], str, str]]:
    """(rule id, ml_stack, text that must render, text that must not) for each library."""
    rows: list[tuple[str, tuple[str, ...], str, str]] = []
    for rule_id in ML_ARRAY_RULE_IDS:
        rows += [
            (rule_id, ("pandas",), "## pandas", "## polars"),
            (rule_id, ("polars",), "## polars", "## pandas"),
            (rule_id, ("numpy",), "## NumPy", "## pandas"),
            (rule_id, ("numpy",), "## NumPy", "## polars"),
            (rule_id, ("pandas",), "## pandas", "## NumPy"),
        ]
    return [
        *rows,
        ("ml-data-transforms", ("pandas",), ".loc", "pl.col"),
        ("ml-data-transforms", ("polars",), "pl.col", ".loc"),
        # Library-specific seeding lines follow their own library, inside the shared section.
        (
            "ml-reproducibility-and-testing",
            ("numpy", "torch"),
            "torch.manual_seed",
            "random_state=",
        ),
        ("ml-reproducibility-and-testing", ("numpy", "scikit-learn"), "random_state=", "torch."),
    ]


@pytest.mark.parametrize(("rule_id", "ml_stack", "present", "absent"), _section_rows())
def test_library_sections_follow_the_ml_stack(
    rule_id: str, ml_stack: tuple[str, ...], present: str, absent: str
) -> None:
    body = render_core_rule(rule_id, _ml_facts(*ml_stack))

    assert body.count(present) >= 1, f"{rule_id} with {list(ml_stack)} lacks {present!r}"
    assert absent not in body, f"{rule_id} with {list(ml_stack)} renders {absent!r}"


@pytest.mark.parametrize("rule_id", ML_ARRAY_RULE_IDS)
def test_ml_array_rule_fits_one_reference_read_with_every_library(rule_id: str) -> None:
    """The longest form: the probe declares no polars, so its size test misses that section."""
    body = render_core_rule(rule_id, _ml_facts(*_EVERY_BRANCH_LIBRARY))

    assert_fits_one_reference_read(rule_id, body, f"ml_stack {list(_EVERY_BRANCH_LIBRARY)}")
