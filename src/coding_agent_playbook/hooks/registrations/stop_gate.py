"""The Stop coordinator's stage records and budget (specs/prK-hook-pack.md §E.0.5, §E.2).

Read at sync from the resolved hooks, and nothing of the machine (§D.8.3):
absolute tool paths and stat signatures are pins in ``machine.json``, never here.

- ``stages``: one machine-independent record ``{name, owner, cost, tool,
  args, timeout_s, needs_diff, mode}`` per on Stop-stage hook (a hook whose
  stop handler names ``config.stage``) and per stage the coordinator owns
  (:data:`OWN_STAGE_COMMANDS`: ``lint`` and ``verify-claim`` always, the
  ``typecheck`` / ``tests`` execution stages when its ``stages`` opts in), in
  ``STOP_STAGE_ORDER``. A stage hook that runs a tool takes it from
  :data:`STAGE_HOOK_COMMANDS` (``coverage``: the project's pytest, its
  ``timeout_s`` from the hook's config, §F.1.2). An execution approval hashes
  exactly this list (§B.4), so any stage change needs a new one;
- ``budget_s`` from ``[hooks.stop-ci-parity-gate]`` (default 3.0).

``hooks.guard_config._tables_stop_gate`` renders them, with the verify commands
and claim patterns, into ``guard_config.json``'s ``stop_gate`` table.
:func:`execution_timeouts_s` feeds the §D.4 stop deadline, so the watchdog
and every registration timeout cover the enabled execution stages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.stop.stages import (
    DEFAULT_BUDGET_S,
    STAGE_COSTS,
    STOP_STAGE_ORDER,
    StageCost,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook

__all__ = [
    "COORDINATOR_STAGES",
    "OPT_IN_STAGES",
    "OWN_STAGE_COMMANDS",
    "STAGE_HOOK_COMMANDS",
    "STOP_COORDINATOR_ID",
    "StageRecord",
    "budget_of",
    "coordinator_budget_s",
    "coordinator_config",
    "execution_timeouts_s",
    "own_stage_names",
    "stop_stage_records",
]

#: The Stop coordinator hook, which owns the gate's policy (§E.0.4).
STOP_COORDINATOR_ID: Final = "stop-ci-parity-gate"
#: Stages whose verdict does not depend on the working-tree diff (generated
#: outputs are gitignored; a review turn has no diff): they still run on an
#: unchanged tree. Mirrors each stage class's ``needs_diff``; a test pins drift's.
_NO_DIFF_STAGES: Final = frozenset({"drift", "output-contract"})
#: The coordinator's own stages that always run (§E.2), and the opt-in execution ones
#: ``[hooks.stop-ci-parity-gate] stages`` may name (H21 checks the names).
COORDINATOR_STAGES: Final = ("lint", "verify-claim")
OPT_IN_STAGES: Final = ("typecheck", "tests")
#: Each own stage's logical tool, args and timeout. ``ruff check`` gives JSON so the
#: lint stage attributes findings; mypy and pytest run through the project's interpreter
#: with no path args (CI parity). A pin, never this table, says where a tool lives.
OWN_STAGE_COMMANDS: Final[Mapping[str, tuple[str, tuple[str, ...], float]]] = MappingProxyType(
    {
        "lint": ("ruff", ("check", "--output-format=json", "."), DEFAULT_BUDGET_S),
        "verify-claim": ("", (), 1.0),
        "typecheck": ("project_python", ("-m", "mypy"), 120.0),
        "tests": ("project_python", ("-m", "pytest", "-q"), 300.0),
    }
)
#: The tool and args of a stage hook that runs one (§F.1.2): coverage-diff-gate's shared
#: suite. ``-o addopts=`` drops a project ``--cov-fail-under``, as ``default_test_cmd`` does;
#: the run appends its report paths and ``--cov=<import root>``, which are per-worktree.
STAGE_HOOK_COMMANDS: Final[Mapping[str, tuple[str, tuple[str, ...]]]] = MappingProxyType(
    {
        "coverage": (
            "project_python",
            ("-m", "pytest", "-o", "addopts=", "-p", "no:cacheprovider", "-q"),
        )
    }
)


@dataclass(frozen=True)
class StageRecord:
    """One ``stop_gate.stages`` row: what runs, never where it lives on this machine.

    Example::

        >>> StageRecord("drift", "stop-drift-and-orphan-gate", timeout_s=5.0,
        ...             needs_diff=False).to_json()["cost"]
        'deterministic'
    """

    name: str
    owner: str
    tool: str = ""
    args: tuple[str, ...] = ()
    timeout_s: float = DEFAULT_BUDGET_S
    needs_diff: bool = True
    mode: str = "block"
    cost: str = field(init=False)

    def __post_init__(self) -> None:
        if self.name not in STAGE_COSTS:
            raise ValueError(
                f"unknown stage {self.name!r}; expected one of {list(STOP_STAGE_ORDER)}"
            )
        cost = "execution" if STAGE_COSTS[self.name] is StageCost.EXECUTION else "deterministic"
        object.__setattr__(self, "cost", cost)

    def to_json(self) -> dict[str, Any]:
        """The rendered row."""
        return {
            "name": self.name,
            "owner": self.owner,
            "cost": self.cost,
            "tool": self.tool,
            "args": list(self.args),
            "timeout_s": self.timeout_s,
            "needs_diff": self.needs_diff,
            "mode": self.mode,
        }


def coordinator_config(hooks: Iterable[ResolvedHook]) -> Mapping[str, Any]:
    """The Stop coordinator's merged ``handler.config`` (``{}`` when it is off).

    Example: ``coordinator_config(hooks).get("budget_s", 3.0)``.
    """
    for hook in hooks:
        handler = hook.handlers.get("stop")
        if hook.id == STOP_COORDINATOR_ID and handler is not None:
            return handler.config
    return {}


def stop_stage_records(hooks: Iterable[ResolvedHook]) -> list[StageRecord]:
    """One record per on Stop stage, in ``STOP_STAGE_ORDER`` (unknown stage names skipped).

    The coordinator's own stages come first, so a stage hook cannot replace them.
    Example: ``[r.name for r in stop_stage_records(hooks)] == ["drift", "lint", "verify-claim"]``.
    """
    listed = list(hooks)
    found = {record.name: record for record in _own_records(listed)}
    for hook in sorted(listed, key=lambda h: h.id):  # one stage per name: the first id wins
        record = _record(hook)
        if record is not None:
            found.setdefault(record.name, record)
    return [found[name] for name in STOP_STAGE_ORDER if name in found]


def own_stage_names(config: Mapping[str, Any]) -> tuple[str, ...]:
    """The coordinator's stages under its merged ``config``: the defaults plus the opted-in ones.

    Example: ``own_stage_names({"stages": ["tests"]}) == ("lint", "verify-claim", "tests")``.
    """
    opted = config.get("stages")
    chosen = [name for name in OPT_IN_STAGES if isinstance(opted, list) and name in opted]
    return (*COORDINATOR_STAGES, *chosen)


def _own_records(hooks: list[ResolvedHook]) -> list[StageRecord]:
    """The coordinator's own stage records, or none when the coordinator is off."""
    if not any(hook.id == STOP_COORDINATOR_ID and "stop" in hook.handlers for hook in hooks):
        return []
    records: list[StageRecord] = []
    for name in own_stage_names(coordinator_config(hooks)):
        tool, args, timeout_s = OWN_STAGE_COMMANDS[name]
        records.append(StageRecord(name, STOP_COORDINATOR_ID, tool, args, timeout_s))
    return records


def execution_timeouts_s(hooks: Iterable[ResolvedHook]) -> tuple[float, ...]:
    """The timeouts of the enabled execution stages, for the §D.4 stop deadline.

    Example: ``deadlines_ms(hooks, execution_timeouts_s=execution_timeouts_s(hooks))``.
    """
    return tuple(r.timeout_s for r in stop_stage_records(hooks) if r.cost == "execution")


def _record(hook: ResolvedHook) -> StageRecord | None:
    handler = hook.handlers.get("stop")
    stage = None if handler is None else handler.config.get("stage")
    if handler is None or stage not in STAGE_COSTS:
        return None
    tool, args = STAGE_HOOK_COMMANDS.get(str(stage), ("", ()))
    return StageRecord(
        name=str(stage),
        owner=hook.id,
        tool=tool,
        args=args,
        timeout_s=_stage_timeout(handler.config.get("timeout_s"), float(hook.timeout)),
        needs_diff=stage not in _NO_DIFF_STAGES,
        mode=_stage_mode(handler.config),
    )


def _stage_timeout(configured: object, default: float) -> float:
    """A stage hook's positive ``config.timeout_s`` (coverage-diff-gate), else its hook timeout."""
    if isinstance(configured, bool) or not isinstance(configured, int | float) or configured <= 0:
        return default
    return float(configured)


def _stage_mode(config: Mapping[str, Any]) -> str:
    """``config.mode``; ``decision = "context"`` (coverage-diff-gate) reads as ``warn``."""
    mode = config.get("mode")
    if isinstance(mode, str):
        return mode
    return "warn" if config.get("decision") == "context" else "block"


def budget_of(config: Mapping[str, Any]) -> float:
    """``config["budget_s"]`` when a positive number, else the default (validate reports a bad one).

    Example: ``budget_of({"budget_s": 7.5}) == 7.5``.
    """
    value = config.get("budget_s")
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        return DEFAULT_BUDGET_S
    return float(value)


def coordinator_budget_s(hooks: Iterable[ResolvedHook]) -> float:
    """The Stop coordinator's merged ``budget_s``, else :data:`DEFAULT_BUDGET_S`.

    Example: ``deadlines_ms(hooks, stop_budget_s=coordinator_budget_s(hooks))``.
    """
    return budget_of(coordinator_config(hooks))
