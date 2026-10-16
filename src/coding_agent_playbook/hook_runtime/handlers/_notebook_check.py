"""The notebook-output check, shared by notebook-output-hygiene and its twin (specs/prK-hook-pack.md §E.3).

Pure apart from :func:`read_notebook`, which ``stat``\\s first: a file above
``max_bytes`` is reported without being parsed (``json.load`` of a 50 MB
notebook would blow the hook's budget). A code cell that keeps outputs is a
finding; an ``image/*`` (or other binary MIME) payload, a long base64 string,
or more than ``max_cell_output_kb`` of output are its details. Outputs may
embed data rows, which is why the advice is always to strip them before
committing (SPEC §13.2 keeps nbstripout out of the air-gapped starter).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.caps import quote_data
from coding_agent_playbook.hook_runtime.handlers._notebook_cells import cell_source, is_code_cell

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

__all__ = [
    "ADVICE",
    "DEFAULT_MAX_CELL_OUTPUT_KB",
    "NOTEBOOK_MAX_BYTES",
    "CellOutputs",
    "NotebookLimits",
    "Oversized",
    "cell_keys",
    "check_cells",
    "notebook_line",
    "read_notebook",
    "touched_cells",
]

#: ``guard_config.notebooks.max_bytes`` (shared with K9's sensitive-data-read-guard).
NOTEBOOK_MAX_BYTES: Final = 5 * 1024 * 1024
DEFAULT_MAX_CELL_OUTPUT_KB: Final = 64
ADVICE: Final = "Outputs may embed data rows; strip outputs before committing."
#: MIME types whose payload is binary data, never text a reviewer reads.
_BINARY_MIME: Final = ("image/", "video/", "audio/", "application/pdf")
#: A base64 run long enough to be an embedded file rather than prose.
_BASE64: Final = re.compile(r"[A-Za-z0-9+/]{1024,}={0,2}")
_LISTED: Final = 5
_MIB: Final = 1024 * 1024


@dataclass(frozen=True, slots=True)
class NotebookLimits:
    """The size cap before parsing and the per-cell output budget, in KB.

    Example: ``NotebookLimits(max_bytes=5 * 1024 * 1024, max_cell_output_kb=64)``.
    """

    max_bytes: int = NOTEBOOK_MAX_BYTES
    max_cell_output_kb: int = DEFAULT_MAX_CELL_OUTPUT_KB


@dataclass(frozen=True, slots=True)
class Oversized:
    """A notebook over ``max_bytes``: reported without parsing."""

    size: int


@dataclass(frozen=True, slots=True)
class CellOutputs:
    """One code cell that keeps outputs: its label, whether binary, how many bytes."""

    cell: str
    payload: bool
    output_bytes: int


def read_notebook(path: str, limits: NotebookLimits) -> list[object] | Oversized | None:
    """The cells of notebook ``path``; :class:`Oversized` (unparsed) or ``None`` if unreadable.

    Example::

        >>> read_notebook("/no/such.ipynb", NotebookLimits()) is None
        True
    """
    try:
        size = os.stat(path).st_size
        if size > limits.max_bytes:
            return Oversized(size)
        with open(path, "rb") as handle:
            doc = json.load(handle)
    except (OSError, ValueError, RecursionError):
        return None
    cells = doc.get("cells") if isinstance(doc, dict) else None
    return cells if isinstance(cells, list) else None


def cell_keys(cells: Sequence[object]) -> list[str]:
    """Each cell's label: its ``id`` (nbformat 4.5), else ``#<1-based index>``."""
    return [_key(cell, index) for index, cell in enumerate(cells)]


def _key(cell: object, index: int) -> str:
    cell_id = cell.get("id") if isinstance(cell, dict) else None
    return cell_id if isinstance(cell_id, str) and cell_id else f"#{index + 1}"


def touched_cells(cells: Sequence[object], head: Sequence[object] | None) -> frozenset[str] | None:
    """The cells whose source or outputs differ from ``head``'s; ``None`` (all) without one.

    Example::

        >>> touched_cells([{"id": "a", "source": "x"}], [{"id": "a", "source": "y"}])
        frozenset({'a'})
    """
    if head is None:
        return None
    before = dict(zip(cell_keys(head), map(_signature, head), strict=True))
    return frozenset(
        key
        for key, cell in zip(cell_keys(cells), cells, strict=True)
        if before.get(key) != _signature(cell)
    )


def _signature(cell: object) -> tuple[str, str]:
    outputs = cell.get("outputs") if isinstance(cell, dict) else None
    return (cell_source(cell), json.dumps(outputs, sort_keys=True, default=str))


def check_cells(cells: Sequence[object], touched: Collection[str] | None) -> list[CellOutputs]:
    """The code cells among ``touched`` (``None``: all) that keep outputs.

    Example::

        >>> check_cells([{"cell_type": "code", "outputs": [{"text": "1"}]}], None)[0].cell
        '#1'
    """
    found: list[CellOutputs] = []
    for key, cell in zip(cell_keys(cells), cells, strict=True):
        if touched is not None and key not in touched:
            continue
        outputs = cell.get("outputs") if is_code_cell(cell) and isinstance(cell, dict) else None
        if isinstance(outputs, list) and outputs:
            size = len(json.dumps(outputs, default=str))
            found.append(CellOutputs(key, any(map(_binary, outputs)), size))
    return found


def _binary(output: object) -> bool:
    data = output.get("data") if isinstance(output, dict) else None
    if not isinstance(data, dict):
        return False
    for mime, value in data.items():
        if str(mime).startswith(_BINARY_MIME):
            return True
        text = "".join(value) if isinstance(value, list) else value
        if isinstance(text, str) and _BASE64.search(text.replace("\n", "")):
            return True
    return False


def notebook_line(
    rel: str, found: Sequence[CellOutputs] | Oversized, limits: NotebookLimits
) -> str | None:
    """The one warning line for notebook ``rel``, or ``None`` when nothing was found.

    Example::

        >>> notebook_line("a.ipynb", [CellOutputs("c1", False, 10)], NotebookLimits())
        '"a.ipynb": cell c1 keeps outputs. Outputs may embed data rows; strip outputs before committing.'
    """
    if isinstance(found, Oversized):
        size = _size(limits.max_bytes)
        return f"{quote_data(rel)} is over {size} and was not parsed: it likely keeps outputs. {ADVICE}"
    if not found:
        return None
    labels = ", ".join(cell.cell for cell in found[:_LISTED]) + (
        ", …" if len(found) > _LISTED else ""
    )
    noun, verb = ("cell", "keeps") if len(found) == 1 else ("cells", "keep")
    details = _details(found, limits)
    return f"{quote_data(rel)}: {noun} {labels} {verb} outputs{details}. {ADVICE}"


def _details(found: Sequence[CellOutputs], limits: NotebookLimits) -> str:
    parts = []
    if any(cell.payload for cell in found):
        parts.append("an image/base64 payload")
    if any(cell.output_bytes > limits.max_cell_output_kb * 1024 for cell in found):
        parts.append(f"over {limits.max_cell_output_kb} KB of output")
    return f" ({'; '.join(parts)})" if parts else ""


def _size(count: int) -> str:
    return f"{count // _MIB} MiB" if count >= _MIB and count % _MIB == 0 else f"{count // 1024} KB"
