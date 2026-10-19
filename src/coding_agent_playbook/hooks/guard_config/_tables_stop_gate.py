"""The Stop coordinator's sync-time table, ``guard_config.stop_gate`` (specs/prK-hook-pack.md §E.0.5, §E.2).

Rendered at sync from the resolved hooks and the detector facts, and nothing
of the machine (§D.8.3): absolute tool paths and stat signatures are pins in
``machine.json``, never here. The table holds:

- ``stages``: the records of ``hooks.registrations.stop_gate.stop_stage_records``,
  which the registrations also read for the §D.4 stop deadline;
- ``budget_s`` and ``max_blocks`` from ``[hooks.stop-ci-parity-gate]``
  (defaults 3.0 and 2; ``max_blocks`` clamped to 1-8);
- ``verify_commands``: ``{id, argv}`` rows from the consumer's
  ``verify_commands`` (``custom-<n>``), else derived from detector
  ``dev_tools``. The ledger stores only the id, never the command (§D.6.3);
- ``claim_patterns``: the engine's completion-claim regexes plus the consumer's.
"""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hooks.registrations.stop_gate import (
    budget_of,
    coordinator_config,
    stop_stage_records,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook

__all__ = ["DEFAULT_CLAIM_PATTERNS", "DEFAULT_MAX_BLOCKS", "stop_gate_table"]

DEFAULT_MAX_BLOCKS: Final = 2
_MAX_BLOCKS_RANGE: Final = (1, 8)
#: Phrases that claim completion (§E.2 verify-claim), case-insensitive.
DEFAULT_CLAIM_PATTERNS: Final[tuple[str, ...]] = (
    r"(?i)\b(?:all )?tests? (?:now )?pass(?:es|ed|ing)?\b",
    r"(?i)\b(?:mypy|ruff|lint|type ?check(?:s|ing)?) (?:is |are |now )?(?:clean|green|passing)\b",
    r"(?i)\b(?:all|everything) (?:is )?green\b",
    r"(?i)\bready to (?:merge|ship)\b",
)
#: ``dev_tools`` fact -> the verify commands it implies, in a fixed order.
_DERIVED_VERIFY: Final[tuple[tuple[str, str, tuple[str, ...]], ...]] = (
    ("ruff", "lint", ("ruff", "check")),
    ("ruff", "format", ("ruff", "format")),
    ("mypy", "typecheck", ("mypy",)),
    ("pyright", "typecheck", ("pyright",)),
    ("pytest", "tests", ("pytest",)),
)


def stop_gate_table(hooks: Iterable[ResolvedHook], facts: Mapping[str, Any]) -> dict[str, Any]:
    """The rendered ``stop_gate`` table (module docstring).

    Example::

        >>> stop_gate_table([], {})["max_blocks"]
        2
    """
    listed = list(hooks)
    config = coordinator_config(listed)
    return {
        "stages": [record.to_json() for record in stop_stage_records(listed)],
        "budget_s": budget_of(config),
        "max_blocks": _max_blocks(config.get("max_blocks")),
        "verify_commands": _verify_commands(config.get("verify_commands"), facts),
        "claim_patterns": _claim_patterns(config.get("claim_patterns")),
    }


def _max_blocks(value: object) -> int:
    if type(value) is not int:
        return DEFAULT_MAX_BLOCKS
    low, high = _MAX_BLOCKS_RANGE
    return min(high, max(low, value))


def _verify_commands(configured: object, facts: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The consumer's commands (``custom-<n>``), else the ones ``dev_tools`` implies."""
    if isinstance(configured, list) and configured:
        commands = [_argv(str(command)) for command in configured]
        return [{"id": f"custom-{n}", "argv": argv} for n, argv in enumerate(commands, 1) if argv]
    tools = set(facts.get("dev_tools") or ())
    rows: dict[str, dict[str, Any]] = {}
    for tool, verify_id, argv in _DERIVED_VERIFY:
        if tool in tools and verify_id not in rows:  # mypy before pyright for "typecheck"
            rows[verify_id] = {"id": verify_id, "argv": list(argv)}
    return list(rows.values())


def _argv(command: str) -> list[str]:
    """``command`` split as a shell would; unbalanced quotes fall back to whitespace."""
    try:
        return shlex.split(command)
    except ValueError:  # a consumer typo must not crash sync; the row still names the tool
        return command.split()


def _claim_patterns(configured: object) -> list[str]:
    extra = [str(p) for p in configured] if isinstance(configured, list) else []
    return list(dict.fromkeys([*DEFAULT_CLAIM_PATTERNS, *extra]))
