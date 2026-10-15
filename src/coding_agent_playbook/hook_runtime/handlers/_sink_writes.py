"""The text a file-tool call leaves in each file, for the sink guard (specs/prK-hook-pack.md §E.3).

ml-unsafe-deserialization-guard compares a file before and after the edit,
built in memory before anything reaches the disk:

- Write / Edit / MultiEdit: ``edit_preview.preview_after`` on the current
  text (``replace_all`` honored); a notebook's images are its code cells
  (``_notebook_cells.cells_code``), so an earlier cell's import resolves a
  later cell's alias;
- NotebookEdit: the notebook with that cell's ``new_source`` replaced or
  inserted (a ``delete`` or a markdown cell adds nothing);
- anything that cannot be simulated (``apply_patch``, an ``old_string`` that
  no longer matches, a file over 2 MiB) falls back to the call's own text
  fragments: ``old_string`` against ``new_string``, nothing against
  ``content``, a patch's ``-`` lines against its ``+`` lines.

Only ``.py`` and ``.ipynb`` files inside the worktree count; secret paths and
frozen eval fixtures never do (``_targets.repo_file``). A private module.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.edit_preview import preview_after
from coding_agent_playbook.hook_runtime.event import ToolClass
from coding_agent_playbook.hook_runtime.handlers._notebook_cells import (
    cell_index,
    cells_code,
    is_code_cell,
    notebook_cells,
    notebook_code,
)
from coding_agent_playbook.hook_runtime.handlers._targets import file_write_paths, repo_file

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime.config import GuardConfig
    from coding_agent_playbook.hook_runtime.event import ToolCall

__all__ = ["MAX_FILE_BYTES", "SinkWrite", "notebook_edit_images", "sink_writes"]

#: A larger file is not read: the call's own fragments are judged instead.
MAX_FILE_BYTES: Final = 2 * 1024 * 1024
_SUFFIXES: Final = (".py", ".ipynb")
#: Each argument with its Claude spelling first, then OpenCode's native one.
_OLD: Final = ("old_string", "oldString")
_NEW: Final = ("new_string", "newString", "content", "new_source")
_PATCH: Final = ("patch_text", "patchText")

type Images = tuple[str | None, str]


@dataclass(frozen=True, slots=True)
class SinkWrite:
    """One file an edit writes: its text before (``None``: new) and after, as Python code.

    ``notebook`` marks the code cells of a ``.ipynb`` file, joined.
    """

    rel: str
    notebook: bool
    pre: str | None
    post: str


def sink_writes(tool: ToolCall, root: str, cfg: GuardConfig) -> list[SinkWrite]:
    """The judged files of ``tool`` (``root``: the worktree's realpath), each once.

    A fallback shared by several files of one patch is judged once.

    Example::

        >>> sink_writes(write_of_readme, "/repo", cfg)  # doctest: +SKIP
        []
    """
    found: dict[Images, SinkWrite] = {}
    for path in file_write_paths(tool):
        located = repo_file(path, root, cfg, suffixes=_SUFFIXES)
        if located is None:
            continue
        real, rel = located
        notebook = rel.endswith(".ipynb")
        images = _images(tool, _read(real), notebook=notebook)
        if images is not None:
            found.setdefault(images, SinkWrite(rel, notebook, *images))
    return list(found.values())


def _images(tool: ToolCall, current: tuple[bool, str | None], *, notebook: bool) -> Images | None:
    known, text = current
    if tool.tool_class is ToolClass.NOTEBOOK_EDIT:
        return notebook_edit_images(tool.raw_input, text if known else None)
    after = preview_after(tool, text) if known else None
    if after is None:
        return _fragments(tool.raw_input)
    if not notebook:
        return (text, after)
    post = notebook_code(after)
    if post is None:
        return _fragments(tool.raw_input)  # not a notebook any more: judge what was written
    return (None if text is None else notebook_code(text), post)


def notebook_edit_images(raw: Mapping[str, object], current: str | None) -> Images | None:
    """The code of notebook ``current`` before and after a NotebookEdit, or ``None`` if none added.

    Without a notebook to place it in (absent, unparseable, unknown cell) the
    new source is judged alone.

    Example::

        >>> notebook_edit_images({"new_source": "x = 1", "edit_mode": "insert"}, None)
        ('', 'x = 1')
    """
    source, mode = raw.get("new_source"), raw.get("edit_mode") or "replace"
    if mode == "delete" or not isinstance(source, str) or raw.get("cell_type") == "markdown":
        return None
    cells = None if current is None else notebook_cells(current)
    index = None if cells is None else cell_index(cells, raw.get("cell_id"))
    if cells is None or (index is None and mode != "insert"):
        return ("", source)
    if mode == "insert":
        at = 0 if index is None else index + 1
        after = [*cells[:at], {"cell_type": "code", "source": source}, *cells[at:]]
        return (cells_code(cells), cells_code(after))
    assert index is not None  # the replace of an unknown cell returned above
    old = cells[index]
    if not is_code_cell(old) and raw.get("cell_type") != "code":
        return None  # a markdown cell stays markdown: no code added
    base = old if isinstance(old, dict) else {}
    replaced = {**base, "cell_type": "code", "source": source}
    return (cells_code(cells), cells_code([*cells[:index], replaced, *cells[index + 1 :]]))


def _fragments(raw: Mapping[str, object]) -> Images | None:
    """The call's own text: removed fragments as "before", written ones as "after"."""
    old: list[str] = []
    new: list[str] = []
    edits = raw.get("edits")
    for edit in [raw, *(edits if isinstance(edits, list) else [])]:
        if isinstance(edit, Mapping):
            old.extend(_strings(edit, _OLD))
            new.extend(_strings(edit, _NEW))
    for patch in _strings(raw, _PATCH):
        for line in patch.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                new.append(line[1:])
            elif line.startswith("-") and not line.startswith("---"):
                old.append(line[1:])
    return ("\n".join(old), "\n".join(new)) if new else None


def _strings(edit: Mapping[str, object], keys: tuple[str, ...]) -> list[str]:
    return [value for key in keys if isinstance(value := edit.get(key), str)]


def _read(path: str) -> tuple[bool, str | None]:
    """``(True, text)``, ``(True, None)`` when absent, ``(False, None)`` when not readable here."""
    try:
        if os.stat(path).st_size > MAX_FILE_BYTES:
            return (False, None)
        with open(path, "rb") as handle:
            return (True, handle.read().decode("utf-8", errors="replace"))
    except FileNotFoundError:
        return (True, None)
    except OSError:
        return (False, None)
