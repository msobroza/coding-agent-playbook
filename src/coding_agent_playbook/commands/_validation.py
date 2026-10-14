"""The one finding type every ``playbook validate`` check returns (SPEC §12.6).

A module of its own so the check modules (``_validate_links`` today, K1's hook
checks next) and ``validate`` can all share it without importing each other.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationError:
    """One validate finding: where it is (a file path or a config key) and why.

    Example::

        >>> ValidationError(path="overlays_enabled", message="cannot import 'acme'")
        ValidationError(path='overlays_enabled', message="cannot import 'acme'")
    """

    path: str
    message: str
