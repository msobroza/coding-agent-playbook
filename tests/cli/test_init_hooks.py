"""``playbook init``'s lifecycle-hooks opt-in (specs/prK-lifecycle-hooks.md §B.1, OQ-3).

An absent ``[hooks]`` table means hooks are off, so an engine upgrade never
injects executable hooks; new repos opt in through init instead. Interactive
init asks (default yes), non-interactive init enables them, ``--no-hooks``
records the opt-out, and a re-run keeps an explicit earlier choice.
"""

from __future__ import annotations

import argparse
import tomllib
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.cli import build_parser
from coding_agent_playbook.commands import init as _init

if TYPE_CHECKING:
    from pathlib import Path

# init ends with a real ``playbook sync``; keep its git calls off the machine config.
pytestmark = pytest.mark.usefixtures("hermetic_git_env")

_QUESTION = "Enable assistant lifecycle hooks? [Y/n]: "


def _ns(repo: Path, **kwargs: object) -> argparse.Namespace:
    base: dict[str, object] = {
        "repo_root": str(repo),
        "non_interactive": True,
        "name": "r",
        "kind": "python-library",
        "description": None,
        "adapters": None,
        "overlays": None,
        "no_hooks": False,
    }
    base.update(kwargs)
    return argparse.Namespace(**base)


def _pyproject(repo: Path) -> None:
    (repo / "pyproject.toml").write_text(
        '[project]\nname="x"\nrequires-python=">=3.12"\ndependencies=[]\n', encoding="utf-8"
    )


def _hooks_table(repo: Path) -> Any:
    with (repo / ".coding-agent-playbook.toml").open("rb") as handle:
        return tomllib.load(handle).get("hooks")


def _interactive(monkeypatch: pytest.MonkeyPatch, hooks_answers: list[str]) -> list[str]:
    """Feed the interactive prompts; return every question asked."""
    answers = iter(["interactive-repo", "", "python-library", "", "", *hooks_answers])
    asked: list[str] = []

    def _input(prompt: str = "") -> str:
        asked.append(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", _input)
    return asked


def test_interactive_hooks_prompt_default_yes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pyproject(tmp_path)
    asked = _interactive(monkeypatch, [""])

    assert _init.run(_ns(tmp_path, non_interactive=False)) == 0

    assert asked[-1] == _QUESTION
    assert _hooks_table(tmp_path) == {"enabled": True}


@pytest.mark.parametrize(("answers", "enabled"), [(["n"], False), (["maybe", "yes"], True)])
def test_interactive_hooks_prompt_takes_an_explicit_answer(
    answers: list[str], enabled: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pyproject(tmp_path)
    asked = _interactive(monkeypatch, answers)

    assert _init.run(_ns(tmp_path, non_interactive=False)) == 0

    assert asked.count(_QUESTION) == len(answers)  # an unclear reply is asked again
    assert _hooks_table(tmp_path) == {"enabled": enabled}


def test_non_interactive_enables_hooks(tmp_path: Path) -> None:
    _pyproject(tmp_path)

    assert _init.run(_ns(tmp_path)) == 0

    assert _hooks_table(tmp_path) == {"enabled": True}


@pytest.mark.parametrize("interactive", [False, True])
def test_no_hooks_flag_leaves_hooks_off(
    interactive: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pyproject(tmp_path)
    asked = _interactive(monkeypatch, [])

    assert _init.run(_ns(tmp_path, non_interactive=not interactive, no_hooks=True)) == 0

    assert _QUESTION not in asked
    assert _hooks_table(tmp_path) == {"enabled": False}


_EXISTING = """\
schema_version = 1
adapters_enabled = ["continue"]

[project]
name = "r"
kind = "python-library"

[engine]
version = "0.1.0a0"
"""


def test_rerun_keeps_an_explicit_choice_and_the_other_keys(tmp_path: Path) -> None:
    _pyproject(tmp_path)
    config = tmp_path / ".coding-agent-playbook.toml"
    config.write_text(_EXISTING + '\n[hooks]\nenabled = false\ntiers = ["default"]\n')

    assert _init.run(_ns(tmp_path)) == 0
    kept = _hooks_table(tmp_path)
    config.write_text(_EXISTING + '\n[hooks]\ntiers = ["default", "opt-in"]\n')
    assert _init.run(_ns(tmp_path)) == 0
    added = _hooks_table(tmp_path)

    assert kept == {"enabled": False, "tiers": ["default"]}
    assert added == {"enabled": True, "tiers": ["default", "opt-in"]}


def test_cli_parses_no_hooks() -> None:
    args = build_parser().parse_args(["init", "--non-interactive", "--no-hooks"])

    assert args.no_hooks is True
    assert build_parser().parse_args(["init"]).no_hooks is False
