"""``main`` installs the signal forwarding before any command runs a bounded child.

Worker threads (``eval --record --jobs N``, the grading scheduler) cannot install
a signal handler, so the entry point does it from the main thread first.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.cli import main
from coding_agent_playbook.grading import bounded_subprocess

if TYPE_CHECKING:
    import pytest


def test_main_installs_the_forwarding_before_running_a_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``main([])`` prints the help; the forwarding is installed all the same."""
    installs: list[None] = []
    monkeypatch.setattr(
        bounded_subprocess, "forward_signals_to_bounded_children", lambda: installs.append(None)
    )

    assert main([]) == 0
    assert installs == [None]
