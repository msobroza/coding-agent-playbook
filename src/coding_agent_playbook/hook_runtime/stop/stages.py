"""The Stop stage contract (specs/prK-lifecycle-hooks.md §D.5.2; the stage table is prK-hook-pack.md §E.0.4).

The Stop coordinator is the dispatcher's only ``stop`` handler; every other
Stop hook contributes one named **stage**. A stage declares only its name (in
``handler.config.stage``): the run order is the engine constant
:data:`STOP_STAGE_ORDER`, never ``priority`` (K-10). Deterministic stages run
first and all feed one combined reason; execution stages (repo-controlled
code: pytest, mypy plugins) run only when every deterministic stage is green
and the user trusts this repo's stage list (§B.4).

This module is the contract only, so stage owners (K5's ``drift``, K6's
``lint``, ...) can be built and tested before the coordinator (K6) exists.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from enum import IntEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.git import Fingerprint

__all__ = [
    "DEFAULT_BUDGET_S",
    "STAGE_COSTS",
    "STOP_STAGE_ORDER",
    "SkipCategory",
    "Stage",
    "StageCost",
    "StageResult",
    "StageStatus",
    "StopPlan",
    "order_stages",
]

#: The Stop stages in run order (§E.0.4). A new stage is added here and in that table.
STOP_STAGE_ORDER: Final[tuple[str, ...]] = (
    "drift",
    "lint",
    "quality-metrics",
    "docstrings",
    "gate-integrity",
    "secrets",
    "notebooks",
    "verify-claim",
    "output-contract",
    "tests-nudge",
    "typecheck",
    "tests",
    "coverage",
)
#: The default stages' wall-clock budget (§D.5.2 rule 1).
DEFAULT_BUDGET_S: Final = 3.0


class StageCost(IntEnum):
    """How expensive a stage is, cheapest first.

    Mirrors ``evaluators.scope.CostTier`` (``DETERMINISTIC < EXECUTION``) without
    importing it: ``evaluators/__init__`` is heavy, and a test keeps the values equal.
    """

    DETERMINISTIC = 0
    EXECUTION = 1


_EXECUTION_STAGES: Final = frozenset({"typecheck", "tests", "coverage"})
#: Each stage's cost class (§E.0.4): only the three that run repo code are execution stages.
STAGE_COSTS: Final[Mapping[str, StageCost]] = MappingProxyType(
    {
        name: StageCost.EXECUTION if name in _EXECUTION_STAGES else StageCost.DETERMINISTIC
        for name in STOP_STAGE_ORDER
    }
)

type StageStatus = Literal["green", "red", "warn", "skipped"]
#: Why a stage did not run to a verdict; a skipped stage is never reported green.
#: ``suite_red``: the suite the ``coverage`` stage grades failed, so it is not graded (§F.1.2).
type SkipCategory = Literal[
    "", "timeout", "crash", "tool_changed", "toolchain_missing", "untrusted", "suite_red"
]

_STATUSES: Final = frozenset({"green", "red", "warn", "skipped"})
_SKIP_CATEGORIES: Final = frozenset(
    {"timeout", "crash", "tool_changed", "toolchain_missing", "untrusted", "suite_red"}
)


@dataclass(frozen=True, slots=True)
class StageResult:
    """One stage's verdict.

    ``lines`` are model-facing diagnostics (repo strings through
    ``caps.quote_data``); ``user_lines`` always go to the user (e.g. a gate
    loosening). A ``skipped`` result names its ``skip_category``, and only it does.

    Example::

        >>> StageResult("lint", "skipped", skip_category="toolchain_missing").verified
        False
    """

    stage: str
    status: StageStatus
    lines: tuple[str, ...] = ()
    user_lines: tuple[str, ...] = ()
    skip_category: SkipCategory = ""

    def __post_init__(self) -> None:
        if self.stage not in STAGE_COSTS:
            raise ValueError(
                f"unknown stage {self.stage!r}; expected one of {list(STOP_STAGE_ORDER)}"
            )
        if self.status not in _STATUSES:
            raise ValueError(f"stage status {self.status!r} is not one of {sorted(_STATUSES)}")
        skipped = self.status == "skipped"
        if skipped != (self.skip_category in _SKIP_CATEGORIES):
            raise ValueError(
                f"stage {self.stage!r}: skip_category {self.skip_category!r} is required for "
                f"a skipped stage and forbidden otherwise (status {self.status!r})"
            )

    @property
    def verified(self) -> bool:
        """Whether the stage reached a verdict that does not block: green or warn."""
        return self.status in ("green", "warn")


class Stage(Protocol):
    """One Stop stage, as the coordinator plans and runs it (§D.5.2)."""

    @property
    def name(self) -> str: ...

    @property
    def cost(self) -> StageCost: ...

    @property
    def needs_diff(self) -> bool: ...

    @property
    def mode(self) -> str: ...  # block | warn, from the stage's config

    def applies(self, plan: StopPlan) -> bool: ...

    def run(self, plan: StopPlan, deadline: float) -> StageResult: ...


def order_stages(stages: Iterable[Stage]) -> tuple[Stage, ...]:
    """``stages`` in :data:`STOP_STAGE_ORDER`; raises ``ValueError`` for an unknown or repeated name.

    Example::

        >>> [s.name for s in order_stages([tests_stage, drift_stage])]  # doctest: +SKIP
        ['drift', 'tests']
    """
    by_name: dict[str, Stage] = {}
    for stage in stages:
        if stage.name not in STAGE_COSTS:
            raise ValueError(
                f"unknown stage {stage.name!r}; expected one of {list(STOP_STAGE_ORDER)}"
            )
        if stage.name in by_name:
            raise ValueError(f"stage {stage.name!r} is planned twice")
        by_name[stage.name] = stage
    return tuple(by_name[name] for name in STOP_STAGE_ORDER if name in by_name)


@dataclass(frozen=True, slots=True, kw_only=True)
class StopPlan:
    """The stages one Stop will consider, with what they may read.

    ``fingerprint`` is ``None`` outside git or on a git error; ``ledger`` is
    the session ledger's lines (§D.6.3). ``stages`` is kept in
    :data:`STOP_STAGE_ORDER` whatever order it was given in.

    Example::

        >>> StopPlan(event=ev, stages=(lint, tests)).only(needs_diff=False)  # doctest: +SKIP
    """

    event: CanonicalEvent
    stages: tuple[Stage, ...]
    fingerprint: Fingerprint | None = None
    head_tree: str | None = None
    ledger: tuple[Mapping[str, Any], ...] = ()
    budget_s: float = DEFAULT_BUDGET_S

    def __post_init__(self) -> None:
        object.__setattr__(self, "stages", order_stages(self.stages))

    def only(self, *, needs_diff: bool) -> StopPlan:
        """This plan narrowed to the stages whose ``needs_diff`` equals ``needs_diff``.

        An unchanged tree keeps the stages that do not need a diff (§D.5.1).
        """
        kept = tuple(stage for stage in self.stages if stage.needs_diff == needs_diff)
        return dataclasses.replace(self, stages=kept)

    @property
    def deterministic(self) -> tuple[Stage, ...]:
        """The deterministic stages, in order."""
        return tuple(s for s in self.stages if s.cost is StageCost.DETERMINISTIC)

    @property
    def execution(self) -> tuple[Stage, ...]:
        """The execution stages (trust-gated, opt-in), in order."""
        return tuple(s for s in self.stages if s.cost is StageCost.EXECUTION)

    def touched(self, key: str) -> frozenset[str]:
        """Every string the ledger lines hold under ``key`` (``paths``, ``writes`` or ``cats``)."""
        return frozenset(
            item for line in self.ledger for item in line.get(key, ()) if isinstance(item, str)
        )
