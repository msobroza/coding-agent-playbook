"""Tests for the ``cap eval`` deferral stub (PR 10 Task 8).

PR 11 ships the real eval enumeration; this stub just confirms the CLI
shape and the deferral message until then.
"""

from __future__ import annotations

import argparse

from coding_agent_playbook.commands import eval as _eval


def _ns(**kwargs: object) -> argparse.Namespace:
    base: dict[str, object] = {"list": False, "show": None, "id": None}
    base.update(kwargs)
    return argparse.Namespace(**base)


def test_eval_list_returns_zero_with_message(capsys) -> None:
    rc = _eval.run(_ns(list=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert "PR 11" in out


def test_eval_show_returns_zero_with_message(capsys) -> None:
    rc = _eval.run(_ns(show="some-task"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "PR 11" in out
    assert "some-task" in out


def test_eval_bare_id_returns_zero_with_message(capsys) -> None:
    rc = _eval.run(_ns(id="some-task"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "PR 11" in out
    assert "some-task" in out


def test_eval_no_args_returns_zero_with_message(capsys) -> None:
    rc = _eval.run(_ns())
    assert rc == 0
    out = capsys.readouterr().out
    assert "PR 11" in out
