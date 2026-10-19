"""The answers ``playbook init`` collects: from flags (non-interactive) or questions.

Split out of ``commands/init.py`` (CP-2, specs/prT-package-layout.md AC.5.5). Every
question goes through an injected :data:`Ask` (CP-3): ``playbook`` passes
:func:`console_ask`, and a test passes a scripted fake instead of patching
``builtins.input``.
"""

from __future__ import annotations

import builtins
import sys
from typing import TYPE_CHECKING, TypedDict

from coding_agent_playbook.commands._init_adapters import (
    ADAPTER_CHOICES,
    ADAPTERS_QUESTION,
    DEFAULT_ADAPTERS,
    adapters_from_flag,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.commands.init import InitArgs

#: Asks one question (the full prompt text, suffix included) and returns the raw reply.
type Ask = Callable[[str], str]


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


def console_ask(question: str) -> str:
    """``input(question)``, with ``builtins.input`` looked up at call time.

    The lookup happens on each call, not at import, so a test that patches
    ``builtins.input`` after this module was imported still feeds the replies.

    Example::

        >>> console_ask("Project name: ")  # doctest: +SKIP
        'my-repo'
    """
    return builtins.input(question)


def _prompt(question: str, default: str | None = None, *, ask: Ask = console_ask) -> str:
    """Ask ``question`` with an optional default. Returns the user's reply
    (stripped) or ``default`` when the reply is empty."""
    suffix = f" [{default}]" if default else ""
    answer = ask(f"{question}{suffix}: ").strip()
    return answer or (default or "")


def _prompt_multi_select(
    question: str, choices: list[str], defaults: list[str], *, ask: Ask = console_ask
) -> list[str]:
    """Ask a multi-select question. The user enters comma-separated indices
    (1-based); an empty reply accepts ``defaults``."""
    print(f"{question} (comma-separated indices, blank=defaults={', '.join(defaults)})")
    for index, choice in enumerate(choices, start=1):
        marker = "*" if choice in defaults else " "
        print(f"  {marker} {index}. {choice}")
    answer = ask("> ").strip()
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


def _prompt_yes_no(question: str, *, default: bool = True, ask: Ask = console_ask) -> bool:
    """Ask a yes/no question until the reply is clear; an empty reply takes ``default``.

    Example: ``_prompt_yes_no("Enable assistant lifecycle hooks?")`` asks ``... [Y/n]: ``.
    """
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        answer = ask(f"{question} {suffix}: ").strip().lower()
        if not answer:
            return default
        if answer in _YES or answer in _NO:
            return answer in _YES


def _hooks_answer(args: InitArgs, ask: Ask | None) -> bool | None:
    """``False`` for ``--no-hooks``; the reply when interactive (``ask``); else no choice (None)."""
    if args.no_hooks:
        return False
    return None if ask is None else _prompt_yes_no(_HOOKS_QUESTION, ask=ask)


def collect_answers(args: InitArgs, ask: Ask) -> Answers:
    """Resolve the project parameters from the flags (non-interactive) or through ``ask``.

    Returns a typed mapping the writer functions consume. A non-interactive run
    without ``--name`` or ``--kind``, or with an unknown kind, prints ``error:``
    and exits 2.

    Example::

        >>> collect_answers(InitArgs.from_namespace(namespace), console_ask)  # doctest: +SKIP
    """
    if args.non_interactive:
        return _answers_from_flags(args)
    return _answers_from_questions(args, ask)


def _answers_from_flags(args: InitArgs) -> Answers:
    """The non-interactive answers; ``--name`` and a known ``--kind`` are required."""
    name, kind = args.name, args.kind
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
    return Answers(
        name=name,
        kind=kind,
        description=args.description,
        adapters=adapters_from_flag(args.adapters),
        overlays=[o.strip() for o in args.overlays.split(",") if o.strip()],
        hooks=_hooks_answer(args, None),
    )


def _answers_from_questions(args: InitArgs, ask: Ask) -> Answers:
    """The interactive answers, asked in today's order; the hooks question comes last."""
    name = _prompt("Project name", ask=ask)
    while not name:
        name = _prompt("Project name (required)", ask=ask)
    description = _prompt("Project description", default="", ask=ask)
    kind = _prompt("Project kind", default="python-application", ask=ask)
    while kind not in _VALID_KINDS:
        print(f"  valid kinds: {', '.join(_VALID_KINDS)}")
        kind = _prompt("Project kind", default="python-application", ask=ask)
    adapters = _prompt_multi_select(
        ADAPTERS_QUESTION, list(ADAPTER_CHOICES), list(DEFAULT_ADAPTERS), ask=ask
    )
    overlays = _prompt_multi_select("Enable overlay packages?", [], [], ask=ask)
    return Answers(
        name=name,
        kind=kind,
        description=description,
        adapters=adapters,
        overlays=overlays,
        hooks=_hooks_answer(args, ask),
    )
