"""``playbook`` / ``coding-agent-playbook`` entry point: :func:`main` and its error mapping.

``coding_agent_playbook.cli:main`` is the frozen console-script target (L2), so
this init holds ``main`` and the private helpers of its error-to-exit-2 mapping
only; the parser lives in :mod:`coding_agent_playbook.cli.parser` and
``python -m coding_agent_playbook.cli`` runs ``cli/__main__.py``.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from coding_agent_playbook.catalog import CatalogMissingError

# Aliased private so build_parser has one spelling (cli.parser), not a second one here.
from coding_agent_playbook.cli.parser import build_parser as _build_parser
from coding_agent_playbook.commands import init as init_cmd
from coding_agent_playbook.config import ConfigError
from coding_agent_playbook.types import HookSchemaError

if TYPE_CHECKING:
    from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv``, run the subcommand, and return its exit code.

    A missing config (:class:`FileNotFoundError`), a config the engine would
    misread (:class:`ConfigError`) and a malformed ``HOOK.md``
    (:class:`HookSchemaError`, prK §A.5) all print ``error: <message>`` and exit
    2. Commands load the config and the artifacts first, so each one stops them
    before they write.

    A broken install also exits 2, without a traceback. An engine catalog found in
    neither home (:class:`CatalogMissingError`) prints
    ``error: the engine's catalog was not found (looked in <a>, <b>);
    reinstall coding-agent-playbook`` on one line, where ``<a>`` and ``<b>`` are
    the wheel's ``<package>/_catalog`` and the checkout's ``<repo>/catalog``, in
    that order; it used to render zero engine artifacts silently. Only commands
    that load the catalog raise it (``init``, ``sync``, ``check``, ``validate``,
    ``render``, ``eval``). A missing pre-commit template
    (:class:`~coding_agent_playbook.commands.init.PrecommitTemplateMissingError`)
    prints ``error: <message>``.

    Example::

        >>> main(["--repo-root", "."])  # doctest: +SKIP
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "func", None) is None:
        parser.print_help()
        return 0
    try:
        return int(args.func(args))
    except SystemExit:
        raise
    except (
        FileNotFoundError,
        ConfigError,
        HookSchemaError,
        init_cmd.PrecommitTemplateMissingError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except CatalogMissingError as exc:
        print(_missing_catalog_line(exc), file=sys.stderr)
        return 2


def _missing_catalog_line(exc: CatalogMissingError) -> str:
    """The missing-catalog error line, naming every catalog home tried, in order."""
    looked_in = ", ".join(str(path) for path in exc.tried)
    return (
        f"error: the engine's catalog was not found (looked in {looked_in}); "
        "reinstall coding-agent-playbook"
    )
