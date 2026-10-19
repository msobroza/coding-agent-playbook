"""The shared exit-2 error type of the ``playbook`` CLI (stdlib-only).

A command raises a subclass of :class:`ExitTwoError` for a failure the user must
fix before re-running (a broken install, for example); ``cli.main`` prints
``error: <message>`` on stderr and returns 2, with no traceback. The type lives
at the bottom of the dependency order, so any package can raise it and ``cli``
maps the one base instead of naming each command's error type
(specs/prT-package-layout.md AC.5.3 CP-D5).
"""

from __future__ import annotations

__all__ = ["ExitTwoError"]


class ExitTwoError(Exception):
    """An error ``playbook`` reports as ``error: <message>`` with exit code 2.

    Subclass it; ``str(error)`` is the message, so carry the offending value in it.

    Example::

        >>> class WidgetMissingError(ExitTwoError): ...
        >>> str(WidgetMissingError("the widget was not found at /w"))
        'the widget was not found at /w'
    """
