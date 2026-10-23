"""One YAML line read without a YAML parser: the gate-weakening judges' shared helpers (prF §10.3, §14).

The hook runtime never imports YAML (Q54), so ``_gitlab_ci_gates`` and
``_scanner_config_gates`` read CI files line by line; both strip comments and
quotes the same way through this module.
"""

from __future__ import annotations

import re

__all__ = ["unquoted", "without_comment"]

#: A ``#`` that starts a YAML comment: at the line start or after a blank.
_COMMENT_START = re.compile(r"(?<![^ \t])#")


def without_comment(text: str) -> str:
    """``text`` up to its first `` #`` that sits outside quotes.

    Example::

        >>> without_comment('echo "a # b"  # why'), without_comment("x: 1 # note")
        ('echo "a # b"', 'x: 1')
    """
    for match in _COMMENT_START.finditer(text):
        head = text[: match.start()]
        if head.count('"') % 2 == 0 and head.count("'") % 2 == 0:
            return head.rstrip()
    return text


def unquoted(text: str) -> str:
    """``text`` without one pair of matching outer quotes.

    Example::

        >>> unquoted('"spec, test"'), unquoted("'x'"), unquoted('"half')
        ('spec, test', 'x', '"half')
    """
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text
