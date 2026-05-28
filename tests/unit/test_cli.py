"""Tests for the cap / coding-agent-playbook CLI stub (PR 1)."""

from __future__ import annotations

import pytest

from coding_agent_playbook import __version__
from coding_agent_playbook.cli import main


def test_version_flag_prints_name_and_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "coding-agent-playbook" in out
    assert __version__ in out


def test_no_args_prints_help_and_exits_zero(capsys):
    assert main([]) == 0
    assert "usage" in capsys.readouterr().out.lower()


def test_unimplemented_subcommand_prints_deferred_message(capsys):
    assert main(["sync"]) == 0
    assert "not implemented yet" in capsys.readouterr().err
