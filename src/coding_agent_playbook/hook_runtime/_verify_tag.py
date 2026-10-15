"""Which ``stop_gate.verify_commands`` a shell command ran (specs/prK-lifecycle-hooks.md §D.6.3).

The ledger tags a ``post_tool_use`` (green) or ``post_tool_use_failure``
(red) shell call with the id of each verify command one of its segments ran,
never the command itself; verify-claim reads the tags back at Stop.

A segment matches a row when, after dropping the launchers both may carry
(``uv run --frozen``, ``poetry run``, ``uvx``, ``python -m``), the program is
the same and every remaining word of the row appears in the segment:
``uv run pytest -q tests/x.py`` ran ``pytest``; ``ruff check src`` ran
``ruff check``. The parser already strips env prefixes and wrapper prefixes.
"""

from __future__ import annotations

import posixpath
import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.hook_runtime.config import GuardConfig
    from coding_agent_playbook.hook_runtime.event import ToolCall

__all__ = ["verify_ids"]

_RUNNERS: Final = frozenset({"uv", "poetry", "pdm", "hatch", "pipx"})
_PYTHON: Final = re.compile(r"python(?:\d+(?:\.\d+)?)?(?:\.exe)?")


def verify_ids(tool: ToolCall, cfg: GuardConfig) -> list[str]:
    """The ids of the verify commands ``tool``'s shell segments ran, in row order, once each.

    Example::

        >>> verify_ids(bash("uv run pytest -q"), cfg)  # doctest: +SKIP
        ['tests']
    """
    command = tool.command
    rows = _rows(cfg)
    if command is None or not rows:
        return []
    cores = [_core(segment.argv) for segment in command.segments]
    return [verify_id for verify_id, row in rows if any(_runs(core, row) for core in cores)]


def _rows(cfg: GuardConfig) -> list[tuple[str, list[str]]]:
    table = cfg.tables.get("stop_gate")
    rows = table.get("verify_commands") if isinstance(table, dict) else None
    found: list[tuple[str, list[str]]] = []
    for row in rows if isinstance(rows, list) else ():
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            core = _core([str(word) for word in row.get("argv") or ()])
            if core:
                found.append((row["id"], core))
    return found


def _core(argv: Sequence[str]) -> list[str]:
    """``argv`` without its launchers, its program reduced to the basename."""
    words = list(argv)
    if words and posixpath.basename(words[0]) == "uvx":
        words = words[1:]
    elif words[:1] and posixpath.basename(words[0]) in _RUNNERS and words[1:2] == ["run"]:
        words = _after_options(words[2:])
    if len(words) >= 2 and _PYTHON.fullmatch(posixpath.basename(words[0])) and words[1] == "-m":
        words = words[2:]
    return [posixpath.basename(words[0]), *words[1:]] if words else []


def _after_options(words: list[str]) -> list[str]:
    """``uv run --frozen --no-sync pytest`` -> ``pytest`` (flags before the program)."""
    index = 0
    while index < len(words) and words[index].startswith("-"):
        index += 1
    return words[index:]


def _runs(core: Sequence[str], row: Sequence[str]) -> bool:
    return bool(core) and core[0] == row[0] and set(row[1:]) <= set(core[1:])
