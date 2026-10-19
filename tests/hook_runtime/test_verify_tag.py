"""Which ``stop_gate.verify_commands`` a shell call ran (specs/prK-lifecycle-hooks.md §D.6.3).

``verify_ids`` over a parsed Bash call and a rendered ``stop_gate`` table; the
ledger write itself is driven end to end by the verify-claim hook tests. Both
the command and each row are unwrapped with ``guard_config.shell``, exactly as
the guards unwrap a command, so a run behind a configured launcher counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import pytest

from coding_agent_playbook.hook_runtime._verify_tag import verify_ids
from coding_agent_playbook.hook_runtime.config.guard_tables import GuardTables
from coding_agent_playbook.hook_runtime.event import ShellSource, ToolCall, ToolClass
from coding_agent_playbook.hook_runtime.shell import ShellConfig

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig

ROWS: list[dict[str, Any]] = [
    {"id": "lint", "argv": ["ruff", "check"]},
    {"id": "format", "argv": ["ruff", "format"]},
    {"id": "tests", "argv": ["pytest"]},
    {"id": "custom-1", "argv": ["uv", "run", "--frozen", "--no-sync", "mypy", "--strict"]},
]


@dataclass
class _Cfg:
    """The one part of ``GuardConfig`` ``verify_ids`` reads."""

    tables: GuardTables = field(
        default_factory=lambda: GuardTables({"stop_gate": {"verify_commands": ROWS}})
    )
    shell: ShellConfig = field(default_factory=ShellConfig)


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
    empty = cast("GuardConfig", _Cfg(tables=GuardTables({})))
    edit = ToolCall(name="Edit", native_name="Edit", tool_class=ToolClass.EDIT)

    assert verify_ids(_bash("pytest"), empty) == []
    assert verify_ids(edit, cast("GuardConfig", _Cfg())) == []


_LAUNCHER = ShellConfig(wrapper_prefixes=("proxy run", "proxy"))


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("proxy uv run pytest -q tests", ["tests"]),
        ("proxy run ruff check src", ["lint"]),
        ("timeout 600 proxy python3 -m pytest", ["tests"]),
        ("env CI=1 proxy poetry run mypy --strict src", ["custom-1"]),
        ("proxy echo pytest", []),
    ],
)
def test_a_run_behind_a_configured_launcher_is_tagged(command: str, expected: list[str]) -> None:
    """Regression: the tagger parsed with the engine default, not ``guard_config.shell``."""
    cfg = cast("GuardConfig", _Cfg(shell=_LAUNCHER))

    assert verify_ids(_bash(command), cfg) == expected


def test_a_row_written_with_launchers_matches_the_bare_run() -> None:
    """Regression: a row's own launchers (``timeout``, a configured wrapper) were never stripped."""
    rows = [{"id": "slow", "argv": ["timeout", "900", "proxy", "uvx", "pytest", "-x"]}]
    cfg = cast(
        "GuardConfig",
        _Cfg(tables=GuardTables({"stop_gate": {"verify_commands": rows}}), shell=_LAUNCHER),
    )

    assert verify_ids(_bash("pytest -x tests"), cfg) == ["slow"]
    assert verify_ids(_bash("pytest tests"), cfg) == []  # the row demands -x


def test_an_unreadable_launcher_tags_nothing_and_never_raises() -> None:
    rows = [*ROWS, {"id": "odd", "argv": ["env", "-S", "'unbalanced", "pytest"]}]
    cfg = cast("GuardConfig", _Cfg(tables=GuardTables({"stop_gate": {"verify_commands": rows}})))

    assert verify_ids(_bash("pytest -q"), cfg) == ["tests"]
