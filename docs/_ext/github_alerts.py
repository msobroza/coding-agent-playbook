"""Turn GitHub alert blocks into MyST admonitions, so a note reads as a box on the site.

The docs are read on GitHub too, where a quote block opening with ``[!NOTE]``
renders as a callout. MyST has no such syntax, so the site rewrites each alert
into a ``:::{note}`` block (MyST's colon fence, which may hold a code block) as
it reads a page or an included file. Text inside code fences is left alone.
"""

from __future__ import annotations

import re
from typing import Final

#: GitHub's alert kinds and the admonition each becomes on the site.
ALERT_DIRECTIVES: Final = {
    "NOTE": "note",
    "TIP": "tip",
    "IMPORTANT": "important",
    "WARNING": "warning",
    "CAUTION": "caution",
}

_ALERT_START: Final = re.compile(r"^ {0,3}> ?\[!(?P<kind>[A-Z]+)\]\s*$")
_QUOTED: Final = re.compile(r"^ {0,3}> ?(?P<body>.*)$")
_FENCE: Final = re.compile(r"^ {0,3}(```|~~~)")


def alerts_to_admonitions(text: str) -> str:
    """Rewrite every ``> [!KIND]`` quote block outside code fences as a ``:::{kind}`` block.

    Example::

        >>> alerts_to_admonitions("> [!NOTE]\\n> Read me.\\n")
        ':::{note}\\nRead me.\\n:::\\n'
    """
    lines = text.split("\n")
    out: list[str] = []
    in_fence = False
    index = 0
    while index < len(lines):
        line = lines[index]
        start = None if in_fence else _ALERT_START.match(line)
        directive = ALERT_DIRECTIVES.get(start["kind"]) if start else None
        if directive is None:
            in_fence ^= bool(_FENCE.match(line))
            out.append(line)
            index += 1
            continue
        body, index = _quoted_body(lines, index + 1)
        out += [f":::{{{directive}}}", *body, ":::"]
    return "\n".join(out)


def _quoted_body(lines: list[str], index: int) -> tuple[list[str], int]:
    """The alert's lines with their ``>`` stripped, and the index of the first line after it."""
    body: list[str] = []
    while index < len(lines) and (quoted := _QUOTED.match(lines[index])):
        body.append(quoted["body"])
        index += 1
    return body, index
