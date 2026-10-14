"""The one finding type every ``playbook validate`` check returns (SPEC §12.6).

A module of its own so the check modules (``_validate_links`` today, K1's hook
checks next), ``validate`` and the validate-gated ``sync`` can all share it,
and its report format, without importing each other.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TextIO


@dataclass(frozen=True)
class ValidationError:
    """One validate finding: where it is (a file path or a config key) and why.

    Example::

        >>> ValidationError(path="overlays_enabled", message="cannot import 'acme'")
        ValidationError(path='overlays_enabled', message="cannot import 'acme'")
    """

    path: str
    message: str


def report_validation_errors(errors: Sequence[ValidationError], stream: TextIO) -> None:
    """Print one ``FAIL <path>: <message>`` line per error, then the count line.

    ``playbook validate`` reports on stdout; the validate gate in ``playbook
    sync`` reports on stderr (prK §P P8b).

    Example::

        >>> import sys
        >>> report_validation_errors([ValidationError("a.md", "bad")], sys.stdout)
        FAIL a.md: bad
        validation failed with 1 error(s)
    """
    for error in errors:
        print(f"FAIL {error.path}: {error.message}", file=stream)
    print(f"validation failed with {len(errors)} error(s)", file=stream)
