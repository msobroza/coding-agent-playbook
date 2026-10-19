"""The Command protocol: what a ``playbook`` subcommand module declares.

A subcommand is its module under ``coding_agent_playbook.commands``: the module
defines ``NAME``, ``HELP``, ``configure(parser)`` and ``run(args)``, so its flags
sit next to the ``run`` that reads them. There is no command object and no import
of ``cli``: mypy checks a module against a protocol structurally, and the layers
run ``cli -> commands`` (ADR 0002). ``cli.parser.build_parser`` walks its ordered
``_COMMANDS`` tuple of such modules (specs/prT-package-layout.md B.12.2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import argparse

__all__ = ["Command"]


class Command(Protocol):
    """A ``playbook`` subcommand: a module with these four names.

    ``NAME`` is the subcommand, ``HELP`` its line in ``playbook --help``,
    ``configure`` declares its flags on the subparser and ``run`` returns the exit
    code. A ``run`` with extra keyword-only parameters (``git=None``) conforms.

    Example::

        >>> from coding_agent_playbook.commands import check
        >>> command: Command = check
        >>> command.NAME
        'check'
    """

    @property
    def NAME(self) -> str: ...

    @property
    def HELP(self) -> str: ...

    def configure(self, parser: argparse.ArgumentParser) -> None: ...

    def run(self, args: argparse.Namespace) -> int: ...
