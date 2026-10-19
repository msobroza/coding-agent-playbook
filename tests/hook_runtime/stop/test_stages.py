"""The Stop stage contract (specs/prK-lifecycle-hooks.md §D.5.2, prK-hook-pack.md §E.0.4)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from coding_agent_playbook.grading.scope import CostTier
from coding_agent_playbook.hook_runtime.event import CanonicalEvent, EventName, Harness
from coding_agent_playbook.hook_runtime.stop.stages import (
    STAGE_COSTS,
    STOP_STAGE_ORDER,
    Stage,
    StageCost,
    StageResult,
    StopPlan,
    order_stages,
)

# N21 moved this file one level down, into tests/hook_runtime/stop/, so
# parents[3] (was parents[2]) is still the repository root.
_PACK_SPEC = Path(__file__).parents[3] / "specs" / "prK-hook-pack.md"
_ROW = re.compile(r"^\| (\d+) \| `([a-z-]+)` \| [^|]+\| ([^|]+)\|")


def _e04_rows() -> list[tuple[str, str]]:
    """``(stage, cost text)`` of every row of the §E.0.4 stage table, in table order."""
    text = _PACK_SPEC.read_text(encoding="utf-8")
    table = text[text.index("| # | Stage | Owner | Cost |") :]
    return [(m.group(2), m.group(3)) for line in table.splitlines() if (m := _ROW.match(line))][
        : len(STOP_STAGE_ORDER) + 1
    ]


@dataclass(frozen=True)
class FakeStage:
    """A ``Stage`` with a canned verdict."""

    name: str
    needs_diff: bool = True
    mode: str = "block"
    verdict: str = "green"

    @property
    def cost(self) -> StageCost:
        return STAGE_COSTS[self.name]

    def applies(self, plan: StopPlan) -> bool:
        return True

    def run(self, plan: StopPlan, deadline: float) -> StageResult:
        return StageResult(self.name, "green")


def _event() -> CanonicalEvent:
    return CanonicalEvent(
        name=EventName.STOP, harness=Harness.CLAUDE_CODE, session_id="s", cwd="/r", project_dir="/r"
    )


def test_stop_stage_order_matches_e04_table() -> None:
    rows = _e04_rows()

    assert [name for name, _ in rows] == list(STOP_STAGE_ORDER)
    for name, cost in rows:
        expected = StageCost.EXECUTION if cost.strip() == "execution" else StageCost.DETERMINISTIC
        assert STAGE_COSTS[name] is expected, name


def test_stage_cost_mirrors_grading_cost_tier() -> None:
    assert {m.name: m.value for m in StageCost} == {
        m.name: m.value for m in CostTier if m.name in StageCost.__members__
    }
    assert StageCost.DETERMINISTIC < StageCost.EXECUTION


def test_plan_keeps_stop_stage_order_whatever_it_is_given() -> None:
    stages: list[Stage] = [FakeStage("tests"), FakeStage("drift"), FakeStage("lint")]

    plan = StopPlan(event=_event(), stages=tuple(stages))

    assert [s.name for s in plan.stages] == ["drift", "lint", "tests"]
    assert [s.name for s in plan.deterministic] == ["drift", "lint"]
    assert [s.name for s in plan.execution] == ["tests"]


def test_only_keeps_the_stages_an_unchanged_tree_still_runs() -> None:
    plan = StopPlan(
        event=_event(),
        stages=(FakeStage("lint"), FakeStage("output-contract", needs_diff=False)),
    )

    assert [s.name for s in plan.only(needs_diff=False).stages] == ["output-contract"]


def test_plan_reads_the_ledger_touches() -> None:
    plan = StopPlan(
        event=_event(),
        stages=(),
        ledger=({"paths": ["src/a.py"], "cats": ["py"]}, {"writes": ["build/x"], "cats": [1]}),
    )

    assert plan.touched("paths") == {"src/a.py"}
    assert plan.touched("cats") == {"py"}


@pytest.mark.parametrize(
    ("stages", "message"),
    [
        ([FakeStage("lint"), FakeStage("lint")], "planned twice"),
        ([FakeStage("pytest")], "unknown stage 'pytest'"),
    ],
)
def test_order_stages_rejects_unknown_or_repeated_names(stages: list[Stage], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        order_stages(stages)


@pytest.mark.parametrize(
    ("status", "category", "ok"),
    [
        ("green", "", True),
        ("warn", "", True),
        ("red", "", True),
        ("skipped", "untrusted", True),
        ("skipped", "", False),
        ("green", "timeout", False),
        ("blue", "", False),
    ],
)
def test_stage_result_validates_status_and_skip_category(
    status: str, category: str, ok: bool
) -> None:
    if ok:
        result = StageResult("lint", status, skip_category=category)  # type: ignore[arg-type]
        assert result.verified is (status in ("green", "warn"))
    else:
        with pytest.raises(ValueError, match="stage"):
            StageResult("lint", status, skip_category=category)  # type: ignore[arg-type]


def test_stage_result_rejects_an_unknown_stage() -> None:
    with pytest.raises(ValueError, match="unknown stage"):
        StageResult("pytest", "green")
