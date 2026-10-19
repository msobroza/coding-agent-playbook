"""``docstring_example``: does a public function's docstring show how to use it (prK §F.3.1).

The opt-in strict docstring mode (OQ-42), in stdlib ``ast``. Per public
function or method (no ``_``-prefixed part in its qualname):

- ``1.0`` when ``ast.get_docstring`` holds a usage example: a doctest
  ``>>> `` line, an ``Example:`` / ``Examples:`` / ``Usage:`` header, a numpy
  ``Examples`` header over a ``---`` underline, or a reST ``::`` literal block
  (``Usage::``, as this repo writes them);
- ``0.5`` for a docstring without one (a summary only);
- ``0.0`` without a docstring.

Enable it with ``[metrics] extend_select = ["docstring_example"]`` and
``[metrics.thresholds.docstring_example] fail = 1.0``; in regression mode it
bites only new public functions.
"""

from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.grading.metric import Metric, register_metric
from coding_agent_playbook.grading.normalizer import Identity
from coding_agent_playbook.grading.scope import Scope
from coding_agent_playbook.grading.types import Measurement

if TYPE_CHECKING:
    from coding_agent_playbook.grading.parse import FunctionScope
    from coding_agent_playbook.grading.types import EvalContext

__all__ = ["DocstringExampleMetric", "docstring_example_score"]

_NAME: Final = "docstring_example"
_HEADER: Final = re.compile(r"(?:Examples?|Usage)\s*:")
_UNDERLINE: Final = re.compile(r"-{3,}")


def docstring_example_score(docstring: str | None) -> float:
    """``1.0`` with a usage example, ``0.5`` for a summary only, ``0.0`` without a docstring.

    Example::

        >>> docstring_example_score("Load it.\\n\\n>>> load('x')\\n")
        1.0
    """
    if docstring is None:
        return 0.0
    lines = [line.strip() for line in docstring.splitlines()]
    return 1.0 if _has_example(lines) else 0.5


def _has_example(lines: list[str]) -> bool:
    for index, line in enumerate(lines):
        if line.startswith(">>> ") or _HEADER.fullmatch(line) or line.endswith("::"):
            return True
        following = lines[index + 1] if index + 1 < len(lines) else ""
        if line == "Examples" and _UNDERLINE.fullmatch(following):
            return True
    return False


def _public(fn: FunctionScope) -> bool:
    return not any(part.startswith("_") for part in fn.qualname.split("."))


def _measure(ctx: EvalContext) -> list[Measurement]:
    """One measurement per public function or method of the parsed module."""
    if ctx.module is None:
        return []
    return [
        Measurement(_NAME, fn.scope_key, docstring_example_score(ast.get_docstring(fn.node)))
        for fn in ctx.module.functions
        if fn.node is not None and _public(fn)
    ]


@register_metric
class DocstringExampleMetric(Metric):
    """``docstring_example`` as a :class:`Metric` over public functions and methods."""

    name = _NAME
    scope = Scope.FUNCTION
    normalizer = Identity()

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return _measure(ctx)
