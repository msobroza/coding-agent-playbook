"""What a file-tool call would leave in its file, simulated in memory (specs/prK-hook-pack.md §E.1).

control-plane-guard parses a control-plane file before and after an edit and
diffs the two; :func:`preview_after` computes the "after" from the current
text and the tool input, never touching the file. Edit, MultiEdit and Write
follow Claude Code's semantics: an ``old_string`` that is missing, or that
occurs more than once without ``replace_all``, makes the tool itself fail,
so there is no "after". ``apply_patch`` and NotebookEdit are not simulated.
``None`` always means "cannot simulate", which a guard treats as ``ask``.

OpenCode's native argument spellings (``oldString``, ...) are read as well as
the shim's snake_case aliases. Stdlib only (§D.1).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.dispatch.event import ToolClass

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime.dispatch.event import ToolCall

__all__ = ["preview_after"]

_EDIT: Final = frozenset({ToolClass.EDIT})
_WRITE: Final = frozenset({ToolClass.WRITE})
#: Each Edit argument with its Claude spelling first, then OpenCode's native one.
_OLD: Final = ("old_string", "oldString")
_NEW: Final = ("new_string", "newString")
_ALL: Final = ("replace_all", "replaceAll")


def preview_after(tool: ToolCall, before: str | None) -> str | None:
    """The file's text after ``tool`` runs on ``before`` (``None``: absent), or ``None``.

    Example::

        >>> call = ToolCall(name="Edit", native_name="Edit", tool_class=ToolClass.EDIT,
        ...                 raw_input={"file_path": "f", "old_string": "a", "new_string": "b"})
        >>> preview_after(call, "xa")
        'xb'
    """
    raw = tool.raw_input
    if tool.tool_classes == _WRITE:
        content = raw.get("content")
        return content if isinstance(content, str) else None
    if tool.tool_classes != _EDIT:
        return None  # apply_patch (edit + write), NotebookEdit, anything else
    edits = raw.get("edits")
    if edits is None:
        return _apply_one(before, raw)
    return _apply_all(before, edits)


def _apply_all(text: str | None, edits: object) -> str | None:
    """MultiEdit: each edit applies to the previous one's result; any failure fails all."""
    if not isinstance(edits, list):
        return None
    for edit in edits:
        if not isinstance(edit, Mapping):
            return None
        text = _apply_one(text, edit)
        if text is None:
            return None
    return text


def _apply_one(text: str | None, edit: Mapping[str, object]) -> str | None:
    """One Edit; an empty ``old_string`` creates a file that does not exist yet."""
    old, new = _string(edit, _OLD), _string(edit, _NEW)
    if old is None or new is None:
        return None
    if text is None or old == "":
        return new if text is None and old == "" else None
    count = text.count(old)
    if count == 0 or (count > 1 and not _flag(edit, _ALL)):
        return None
    return text.replace(old, new)


def _string(edit: Mapping[str, object], keys: tuple[str, ...]) -> str | None:
    value = next((edit[key] for key in keys if key in edit), None)
    return value if isinstance(value, str) else None


def _flag(edit: Mapping[str, object], keys: tuple[str, ...]) -> bool:
    return next((edit[key] for key in keys if key in edit), False) is True
