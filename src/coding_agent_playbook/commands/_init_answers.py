"""The answers ``playbook init`` collects: from flags (non-interactive) or prompts.

Split out of ``commands/init.py`` (CP-2, specs/prT-package-layout.md AC.5.5), verbatim;
CP-3 gives the prompts an injected ``Ask`` seam.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, TypedDict

from coding_agent_playbook.commands._init_adapters import (
    ADAPTER_CHOICES,
    ADAPTERS_QUESTION,
    DEFAULT_ADAPTERS,
    adapters_from_flag,
)

if TYPE_CHECKING:
    import argparse


class Answers(TypedDict):
    """Shape of the user-collected answers handed to ``plan_config``.

    Keeping this in a TypedDict lets mypy verify each field is the right
    type without sprinkling ``cast`` / ``type: ignore`` at every key access.
    """

    name: str
    kind: str
    description: str
    adapters: list[str]
    overlays: list[str]
    # ``[hooks] enabled``; None = no explicit choice (non-interactive without
    # --no-hooks): keep a value the config already has, else enable.
    hooks: bool | None


_VALID_KINDS = (
    "python-application",
    "python-library",
    "ml-research",
    "notebook",
    "python-unknown",
)

_HOOKS_QUESTION = "Enable assistant lifecycle hooks?"
_YES = frozenset({"y", "yes"})
_NO = frozenset({"n", "no"})


def _prompt(question: str, default: str | None = None) -> str:
    """Wrap ``input()`` with an optional default. Returns the user's reply
    (stripped) or ``default`` when the reply is empty."""
    suffix = f" [{default}]" if default else ""
    answer = input(f"{question}{suffix}: ").strip()
    return answer or (default or "")


def _prompt_multi_select(question: str, choices: list[str], defaults: list[str]) -> list[str]:
    """Ask a multi-select question. The user enters comma-separated indices
    (1-based); an empty reply accepts ``defaults``."""
    print(f"{question} (comma-separated indices, blank=defaults={', '.join(defaults)})")
    for index, choice in enumerate(choices, start=1):
        marker = "*" if choice in defaults else " "
        print(f"  {marker} {index}. {choice}")
    answer = input("> ").strip()
    if not answer:
        return list(defaults)
    selected: list[str] = []
    for token in answer.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            idx = int(token)
        except ValueError:
            continue
        if 1 <= idx <= len(choices):
            selected.append(choices[idx - 1])
    return selected or list(defaults)


def _prompt_yes_no(question: str, *, default: bool = True) -> bool:
    """Ask a yes/no question until the reply is clear; an empty reply takes ``default``.

    Example: ``_prompt_yes_no("Enable assistant lifecycle hooks?")`` asks ``... [Y/n]: ``.
    """
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        answer = input(f"{question} {suffix}: ").strip().lower()
        if not answer:
            return default
        if answer in _YES or answer in _NO:
            return answer in _YES


def _hooks_answer(args: argparse.Namespace, *, interactive: bool) -> bool | None:
    """``False`` for ``--no-hooks``; the user's answer when interactive; else no choice (None)."""
    if getattr(args, "no_hooks", False):
        return False
    return _prompt_yes_no(_HOOKS_QUESTION) if interactive else None


def collect_answers(args: argparse.Namespace) -> Answers:
    """Resolve the project parameters from flags (non-interactive) or prompts
    (interactive). Returns a typed mapping the writer functions consume."""
    if getattr(args, "non_interactive", False):
        name = getattr(args, "name", None)
        kind = getattr(args, "kind", None)
        if not name or not kind:
            print(
                "error: --name and --kind are required in non-interactive mode",
                file=sys.stderr,
            )
            raise SystemExit(2)
        if kind not in _VALID_KINDS:
            print(
                f"error: --kind must be one of: {', '.join(_VALID_KINDS)}",
                file=sys.stderr,
            )
            raise SystemExit(2)
        adapters = adapters_from_flag(getattr(args, "adapters", None))
        overlays_raw = getattr(args, "overlays", "") or ""
        overlays = [o.strip() for o in str(overlays_raw).split(",") if o.strip()]
        return Answers(
            name=str(name),
            kind=str(kind),
            description=str(getattr(args, "description", "") or ""),
            adapters=adapters,
            overlays=overlays,
            hooks=_hooks_answer(args, interactive=False),
        )
    # Interactive path.
    name = _prompt("Project name")
    while not name:
        name = _prompt("Project name (required)")
    description = _prompt("Project description", default="")
    kind = _prompt("Project kind", default="python-application")
    while kind not in _VALID_KINDS:
        print(f"  valid kinds: {', '.join(_VALID_KINDS)}")
        kind = _prompt("Project kind", default="python-application")
    adapters = _prompt_multi_select(
        ADAPTERS_QUESTION, list(ADAPTER_CHOICES), list(DEFAULT_ADAPTERS)
    )
    overlays = _prompt_multi_select(
        "Enable overlay packages?",
        [],
        [],
    )
    return Answers(
        name=name,
        kind=kind,
        description=description,
        adapters=adapters,
        overlays=overlays,
        hooks=_hooks_answer(args, interactive=True),
    )
