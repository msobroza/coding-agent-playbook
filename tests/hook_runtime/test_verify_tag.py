"""Which ``stop_gate.verify_commands`` a shell call ran (specs/prK-lifecycle-hooks.md §D.6.3).

``verify_ids`` over a parsed Bash call and a rendered ``stop_gate`` table; the
ledger write itself is driven end to end by the verify-claim hook tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import pytest

from coding_agent_playbook.hook_runtime._verify_tag import verify_ids
from coding_agent_playbook.hook_runtime.event import ShellSource, ToolCall, ToolClass

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime.config import GuardConfig

ROWS: list[dict[str, Any]] = [
    {"id": "lint", "argv": ["ruff", "check"]},
    {"id": "format", "argv": ["ruff", "format"]},
    {"id": "tests", "argv": ["pytest"]},
    {"id": "custom-1", "argv": ["uv", "run", "--frozen", "--no-sync", "mypy", "--strict"]},
]


@dataclass
class _Cfg:
    """The one part of ``GuardConfig`` ``verify_ids`` reads."""

    tables: dict[str, Any] = field(default_factory=lambda: {"stop_gate": {"verify_commands": ROWS}})


def _bash(command: str) -> ToolCall:
    return ToolCall(
        name="Bash",
        native_name="Bash",
        tool_class=ToolClass.SHELL,
        shell=ShellSource(text=command, cwd="/r"),
    )


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("ruff check .", ["lint"]),
        ("uv run ruff check src && python3 -m pytest -q tests/x.py", ["lint", "tests"]),
        ("ruff format --check . ; ruff check --fix", ["lint", "format"]),
        ("poetry run mypy --strict src", ["custom-1"]),
        ("mypy src", []),  # the row demands --strict
        ("cat pytest.ini", []),
        ("echo ruff check", []),
    ],
)
def test_segments_matched_after_their_launchers(command: str, expected: list[str]) -> None:
    assert verify_ids(_bash(command), cast("GuardConfig", _Cfg())) == expected


def test_no_rows_no_shell_no_ids() -> None:
    empty = cast("GuardConfig", _Cfg(tables={}))
    edit = ToolCall(name="Edit", native_name="Edit", tool_class=ToolClass.EDIT)

    assert verify_ids(_bash("pytest"), empty) == []
    assert verify_ids(edit, cast("GuardConfig", _Cfg())) == []
