"""Replacing an endpoint's secrets in agent output and graded diffs (spec #281 tickets 06, 06b, 07).

Both endpoint routes (``claude_code_route``, ``opencode_route``) redact the same
way: each secret as written and in its JSON-escaped forms (raw JSON output kept
as is, or a file the agent wrote, may carry a secret escaped), longest first so
a whole headers value is replaced before its parts are.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable

#: What a redacted secret reads as in a transcript, a diff or an error excerpt.
REDACTED: Final = "[redacted]"


def with_escaped_forms(plain: Iterable[str]) -> set[str]:
    """The non-empty ``plain`` secrets plus their JSON-escaped forms (ASCII and not).

    Example::

        >>> sorted(with_escaped_forms(['a"b', ""]))
        ['a"b', 'a\\\\"b']
    """
    secrets = {secret for secret in plain if secret}
    escaped = {json.dumps(secret)[1:-1] for secret in secrets}
    escaped |= {json.dumps(secret, ensure_ascii=False)[1:-1] for secret in secrets}
    return secrets | escaped


def redact_secrets(text: str, secrets: Iterable[str]) -> str:
    """``text`` with every non-empty secret replaced by :data:`REDACTED`, longest first.

    Example::

        >>> redact_secrets("k=t0 and t", ["t", "t0"])
        'k=[redacted] and [redacted]'
    """
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    return text
