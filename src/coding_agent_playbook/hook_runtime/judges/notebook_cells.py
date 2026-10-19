"""Notebook cells as text, shared by the §E.3 notebook-aware hooks and their twins.

ml-unsafe-deserialization-guard scans a notebook's code cells as one module
(:func:`cells_code`: a later cell's ``np.load`` resolves through an earlier
cell's import), and notebook-output-hygiene compares cells by source. Stdlib
``json`` and ``re`` only.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "cell_index",
    "cell_source",
    "cells_code",
    "is_code_cell",
    "notebook_cells",
    "notebook_code",
]

#: An IPython magic or shell escape at a line start: commented out so the cell parses.
_MAGIC: Final = re.compile(r"^([ \t]*)([%!])", re.MULTILINE)
_NUMBERED: Final = re.compile(r"cell-(\d{1,6})")


def notebook_code(text: str) -> str | None:
    """The code cells of notebook JSON ``text``, joined (:func:`cells_code`); ``None`` if not one.

    Example::

        >>> notebook_code('{"cells": [{"cell_type": "code", "source": "%time f()"}]}')
        '#%time f()'
    """
    cells = notebook_cells(text)
    return None if cells is None else cells_code(cells)


def notebook_cells(text: str) -> list[object] | None:
    """The ``cells`` list of notebook JSON ``text``, or ``None`` when it is not a notebook."""
    try:
        doc = json.loads(text)
    except (ValueError, RecursionError):
        return None
    cells = doc.get("cells") if isinstance(doc, dict) else None
    return cells if isinstance(cells, list) else None


def cells_code(cells: Iterable[object]) -> str:
    """The code cells' sources joined by newlines, IPython magics (``%``, ``!``) commented out.

    Each cell starts on a new line, so line numbers point into the joined text.
    """
    sources = [cell_source(cell) for cell in cells if is_code_cell(cell)]
    return "\n".join(_MAGIC.sub(r"\1#\2", source) for source in sources)


def cell_source(cell: object) -> str:
    """A notebook cell's ``source`` as one string (nbformat allows a list of lines)."""
    source = cell.get("source") if isinstance(cell, dict) else None
    if isinstance(source, list):
        return "".join(part for part in source if isinstance(part, str))
    return source if isinstance(source, str) else ""


def cell_index(cells: list[object], cell_id: object) -> int | None:
    """The index of the cell a NotebookEdit ``cell_id`` names, else ``None``.

    The cell's own ``id`` (nbformat 4.5) first, then the ``cell-<n>`` form
    Claude Code uses for a notebook whose cells carry no id.

    Example::

        >>> cell_index([{"id": "a"}, {"id": "b"}], "b"), cell_index([{}, {}], "cell-1")
        (1, 1)
    """
    if not isinstance(cell_id, str) or not cell_id:
        return None
    for index, cell in enumerate(cells):
        if isinstance(cell, dict) and cell.get("id") == cell_id:
            return index
    numbered = _NUMBERED.fullmatch(cell_id)
    if numbered is not None and int(numbered[1]) < len(cells):
        return int(numbered[1])
    return None


def is_code_cell(cell: object) -> bool:
    """Whether ``cell`` is a well-formed code cell (a dict whose ``cell_type`` is ``code``)."""
    return isinstance(cell, dict) and cell.get("cell_type") == "code"
