"""``playbook init`` asks through an injected ``Ask`` (CP-3, specs/prT-package-layout.md AC.5.6).

``run(args, *, ask=console_ask)`` sends every interactive question through ``ask``
with today's exact strings, so a test scripts the replies without patching
``builtins.input``; the default ``console_ask`` still reads ``builtins.input`` at
call time, so the older monkeypatching tests keep working.
"""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import init as _init
from coding_agent_playbook.commands._init_answers import console_ask

if TYPE_CHECKING:
    from collections.abc import Iterable

# init ends with a real ``playbook sync``; keep its git calls off the machine config.
pytestmark = pytest.mark.usefixtures("hermetic_git_env")

#: Today's interactive questions, in order (the strings ``input()`` was called with).
_QUESTIONS = [
    "Project name: ",
    "Project description: ",
    "Project kind [python-application]: ",
    "> ",  # the adapters multi-select
    "Spec-driven framework (superpowers, mattpocock, an overlay module or none; "
    "blank keeps the current one, else none): ",
    "> ",  # the overlays multi-select
    "Enable assistant lifecycle hooks? [Y/n]: ",
]


class FakeAsk:
    """A scripted ``Ask``: returns ``replies`` in order and records each question."""

    def __init__(self, replies: Iterable[str]) -> None:
        self._replies = iter(replies)
        self.questions: list[str] = []

    def __call__(self, question: str) -> str:
        self.questions.append(question)
        return next(self._replies)


def _refuse_console_input(*_args: object) -> str:
    raise AssertionError("init read builtins.input instead of the injected ask")


def test_interactive_init_asks_through_the_injected_ask(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nrequires-python=">=3.12"\ndependencies=[]\n', encoding="utf-8"
    )
    monkeypatch.setattr("builtins.input", _refuse_console_input)
    ask = FakeAsk(["asked-repo", "", "python-library", "", "", "", "n"])

    assert _init.run(argparse.Namespace(repo_root=str(tmp_path)), ask=ask) == 0

    assert ask.questions == _QUESTIONS
    config = tomllib.loads((tmp_path / ".coding-agent-playbook.toml").read_text("utf-8"))
    assert config["project"]["name"] == "asked-repo"
    assert config["hooks"] == {"enabled": False}


def test_console_ask_reads_builtins_input_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []

    def patched_input(prompt: str = "") -> str:
        asked.append(prompt)
        return "typed"

    monkeypatch.setattr("builtins.input", patched_input)

    assert console_ask("Project name: ") == "typed"
    assert asked == ["Project name: "]


def test_init_args_from_a_partial_namespace_uses_the_flag_defaults() -> None:
    args = _init.InitArgs.from_namespace(argparse.Namespace(repo_root="r"))

    assert args == _init.InitArgs(
        repo_root=Path("r"),
        non_interactive=False,
        name=None,
        kind=None,
        description="",
        adapters=None,
        framework=None,
        overlays="",
        no_hooks=False,
    )


def test_init_args_from_a_namespace_without_repo_root_uses_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert _init.InitArgs.from_namespace(argparse.Namespace()).repo_root == tmp_path


def test_init_args_reads_none_description_and_overlays_as_empty() -> None:
    """Hand-built namespaces pass ``None`` where argparse leaves a flag unset."""
    namespace = argparse.Namespace(repo_root="r", description=None, overlays=None)

    args = _init.InitArgs.from_namespace(namespace)

    assert (args.description, args.overlays) == ("", "")
