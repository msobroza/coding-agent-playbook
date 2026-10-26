"""The eval flags that picked a prompt set are refused (ADR 0012, #300).

Prompt sets are gone: every sample grades the current text, or the edition it is
pinned to. ``--prompt-set`` and ``--base-prompt-set`` are hidden from ``--help``
and exit 2 with one line saying so, before anything runs. Hermetic: only the
``fake`` runner is named, and the refusal comes first.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.cli.parser import build_parser
from coding_agent_playbook.commands import eval as _eval

if TYPE_CHECKING:
    from pathlib import Path

_SHIPPED_SAMPLE = "refactor/extract-helper"


@pytest.mark.parametrize(
    ("flags", "flag"),
    [
        pytest.param(
            [_SHIPPED_SAMPLE, "--run", "--runner", "fake", "--prompt-set", "v2"],
            "--prompt-set",
            id="run",
        ),
        pytest.param(
            ["--compare", "HEAD", "--base-prompt-set", "v1"], "--base-prompt-set", id="compare"
        ),
        pytest.param(
            ["--compare", "HEAD", "--prompt-set", "v2"], "--prompt-set", id="compare-head"
        ),
    ],
)
def test_a_removed_prompt_set_flag_exits_2_naming_the_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], flags: list[str], flag: str
) -> None:
    args = build_parser().parse_args(["eval", *flags, "--repo-root", str(tmp_path)])

    assert _eval.run(args) == 2

    err = capsys.readouterr().err
    assert err.startswith(f"error: {flag} was removed with the prompt sets: ")
    assert "every sample grades the current text" in err


def test_the_removed_flags_are_hidden_from_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["eval", "--help"])

    assert "prompt-set" not in capsys.readouterr().out
