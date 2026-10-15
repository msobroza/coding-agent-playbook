"""The regex fallback of the unsafe-sink visitor (specs/prK-hook-pack.md §E.3).

Used by ``_sink_scan.new_sink_calls`` when a pre- or post-image does not
parse: a call head (``callee(``) is found anywhere, its top-level keyword
arguments read up to the matching parenthesis, and ``import`` lines give the
aliases. It also matches inside strings and comments, which is the price of
not parsing; only ``def``/``class`` heads are skipped.
"""

from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.handlers._sink_scan import (
    CONVENTIONAL_ALIASES,
    EXPR,
    SPLAT,
    SinkCall,
    resolve_alias,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from coding_agent_playbook.hook_runtime.handlers._sink_scan import Keyword, SinkTable

__all__ = ["regex_sink_calls"]

#: A call's head only: its arguments are read by :func:`_top_level_args`, so a call
#: nested in another's arguments is still found.
_CALL = re.compile(r"(?<![\w.])(?P<callee>[A-Za-z_]\w*(?:\s*\.\s*[A-Za-z_]\w*)*)\s*\(")
#: How far the fallback reads one call's arguments.
_ARGS_CHARS: Final = 4_096
_KWARG = re.compile(
    r"(?<![\w.])(?P<name>[A-Za-z_]\w*)\s*=(?!=)\s*"
    r"(?P<value>True\b|False\b|None\b|-?\d+(?:\.\d+)?|'[^']*'|\"[^\"]*\"|[A-Za-z_][\w.]*)?"
)
_SPLAT_ARG = re.compile(r"(?<![*\w])\*\*\s*[A-Za-z_(]")
_IMPORT = re.compile(r"^[ \t]*import[ \t]+(?P<names>[\w., \t]+)$", re.MULTILINE)
_FROM = re.compile(
    r"^[ \t]*from[ \t]+(?P<module>\w[\w.]*)[ \t]+import[ \t]+(?P<names>[\w, \t]+)$", re.MULTILINE
)
_DEF = re.compile(r"\b(?:def|class)\s+$")


def regex_sink_calls(text: str, table: SinkTable) -> list[SinkCall]:
    """Every call in ``text`` a row matches, found by regex (``text`` need not parse).

    Example: ``regex_sink_calls("def f(:\\n    pickle.loads(b)\\n", table)`` finds
    ``pickle.loads`` on line 2, where ``ast.parse`` raises.
    """
    aliases = {**CONVENTIONAL_ALIASES, **_regex_aliases(text)}
    found: list[SinkCall] = []
    for match in _CALL.finditer(text):
        if _DEF.search(text, max(0, match.start() - 8), match.start()):
            continue  # ``def eval(`` defines, it does not call
        callee = resolve_alias(re.sub(r"\s+", "", match["callee"]), aliases)
        keywords = frozenset(_regex_keywords(_top_level_args(text, match.end())))
        if table.classify(callee, keywords) is not None:
            found.append(SinkCall(callee, keywords, text.count("\n", 0, match.start()) + 1))
    return found


def _top_level_args(text: str, start: int) -> str:
    """The text of one call's arguments from ``start`` (after ``(``), nested parentheses dropped."""
    depth, kept = 1, []
    for char in text[start : start + _ARGS_CHARS]:
        depth += (char == "(") - (char == ")")
        if depth == 0:
            break
        if depth == 1 and char not in "()":
            kept.append(char)
    return "".join(kept)


def _regex_keywords(args: str) -> Iterable[Keyword]:
    for match in _KWARG.finditer(args):
        yield (match["name"], _regex_value(match["value"]))
    if _SPLAT_ARG.search(args):
        yield (SPLAT, EXPR)


def _regex_value(token: str | None) -> str:
    if token is None:
        return EXPR
    try:
        return repr(ast.literal_eval(token))
    except (ValueError, SyntaxError):
        return token  # a dotted name


def _regex_aliases(text: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for match in _IMPORT.finditer(text):
        for module, local in _as_pairs(match["names"]):
            aliases[local or module.split(".")[0]] = module if local else module.split(".")[0]
    for match in _FROM.finditer(text):
        for name, local in _as_pairs(match["names"]):
            aliases[local or name] = f"{match['module']}.{name}"
    return aliases


def _as_pairs(names: str) -> Iterator[tuple[str, str]]:
    for part in names.split(","):
        name, _, local = part.strip().partition(" as ")
        if name.strip():
            yield name.strip(), local.strip()
