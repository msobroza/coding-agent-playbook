"""Edits to JSON arrays at object paths, as a plan and as splices (specs/prK-lifecycle-hooks.md §C.2.4).

An :class:`ArrayEdit` names an array by its path of object keys and says which
original elements to delete, which to replace in place, and what to append.
:func:`apply_edits` computes the document the edits mean (the plan that the
merge's self-check compares against); :func:`edit_splices` turns the same edits
into :class:`~._json_spans.Splice` values over the original text, so every byte
outside the edited spans stays as the user wrote it. Stdlib-only.

Both functions follow one shape rule:

- a missing array, with any missing parent objects, is created only when
  something is appended to it;
- an array an edit empties is removed, and so is every parent object that
  becomes empty because of it, up to but never including the root. An empty
  container the user wrote is left alone.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.adapters.claude_code.settings._json_spans import Splice, line_indent

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from coding_agent_playbook.adapters.claude_code.settings._json_spans import (
        JsonNode,
        JsonSpanIndex,
        JsonStyle,
    )

__all__ = ["ArrayEdit", "apply_edits", "edit_splices", "render_fragment"]

type KeyPath = tuple[str, ...]
#: Renders one item given the base indent of its line and whether the container is one-line.
type _Renderer = Callable[[str, bool], str]


@dataclass(frozen=True)
class ArrayEdit:
    """Delete, replace and append elements of the array at ``path`` (object keys from the root).

    Indexes refer to the array as it is before the edit.

    Example::

        ArrayEdit(("hooks", "Stop"), delete=frozenset({2}), replace={0: group}, append=(new,))
    """

    path: KeyPath
    delete: frozenset[int] = frozenset()
    replace: Mapping[int, Any] = field(default_factory=dict)
    append: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("ArrayEdit.path must name an array below the root object, got ()")
        both = self.delete & set(self.replace)
        if both:
            raise ValueError(
                f"ArrayEdit {self.path}: indexes {sorted(both)} are deleted and replaced"
            )

    @property
    def is_noop(self) -> bool:
        """True when the edit changes nothing."""
        return not (self.delete or self.replace or self.append)


def render_fragment(
    value: object, style: JsonStyle, base_indent: str, *, compact: bool = False
) -> str:
    """``value`` as JSON text ready to splice at a line indented by ``base_indent``.

    Expanded fragments use the file's indent unit and newline, and continuation
    lines are shifted by ``base_indent``; ``compact`` gives one-line JSON for
    one-line containers. Raw newlines only occur between tokens, since
    ``json.dumps`` escapes them inside strings.

    Example::

        >>> render_fragment({"k": 1}, DEFAULT_STYLE, "  ")
        '{\\n    "k": 1\\n  }'
    """
    if compact:
        return json.dumps(value, ensure_ascii=False)
    text = json.dumps(value, indent=style.indent, ensure_ascii=False)
    return text.replace("\n", style.newline + base_indent)


def apply_edits(doc: Mapping[str, Any], edits: Sequence[ArrayEdit]) -> dict[str, Any]:
    """The document ``edits`` produce from ``doc`` (a deep copy; ``doc`` is never mutated).

    New keys are added in edit order. Raises ``ValueError`` naming the path when
    a path step is not an object or an index is outside the array.

    Example::

        >>> apply_edits({"a": [1, 2]}, [ArrayEdit(("a",), delete=frozenset({0}))])
        {'a': [2]}
    """
    planned: dict[str, Any] = copy.deepcopy(dict(doc))
    for edit in edits:
        if not edit.is_noop:
            _apply_one(planned, edit)
    return planned


def _apply_one(root: dict[str, Any], edit: ArrayEdit) -> None:
    chain = _parent_chain(root, edit)
    leaf = edit.path[-1]
    current = chain[-1].get(leaf, [])
    if not isinstance(current, list):
        raise ValueError(f"ArrayEdit {edit.path}: expected an array, got {type(current).__name__}")
    bad = sorted(i for i in (*edit.delete, *edit.replace) if not 0 <= i < len(current))
    if bad:
        raise ValueError(f"ArrayEdit {edit.path}: indexes {bad} outside an array of {len(current)}")
    result = [edit.replace.get(i, item) for i, item in enumerate(current) if i not in edit.delete]
    result.extend(edit.append)
    if result:
        chain[-1][leaf] = result
        return
    del chain[-1][leaf]
    for depth in range(len(chain) - 1, 0, -1):  # prune parents the edit emptied
        if chain[depth]:
            break
        del chain[depth - 1][edit.path[depth - 1]]


def _parent_chain(root: dict[str, Any], edit: ArrayEdit) -> list[dict[str, Any]]:
    """The objects along ``edit.path[:-1]``, created when missing and the edit appends."""
    chain = [root]
    for key in edit.path[:-1]:
        parent = chain[-1]
        if key not in parent and edit.append:
            parent[key] = {}
        node = parent.get(key)
        if not isinstance(node, dict):
            raise ValueError(f"ArrayEdit {edit.path}: {key!r} is not an object (got {node!r})")
        chain.append(node)
    return chain


def edit_splices(
    index: JsonSpanIndex, planned: Mapping[str, Any], edits: Sequence[ArrayEdit], style: JsonStyle
) -> list[Splice]:
    """Splices that turn ``index.text`` into a text meaning ``planned``.

    ``planned`` must be ``apply_edits(<document of index.text>, edits)``: it
    says which arrays and parents were pruned or created. Arrays that survive
    get element splices; pruned subtrees are deleted at their topmost member and
    created ones are inserted whole, rendered in ``style``.

    Example::

        apply_splices(text, edit_splices(JsonSpanIndex.build(text), planned, edits, style))
    """
    plans: dict[KeyPath, _ContainerPlan] = {}
    for edit in edits:
        if not edit.is_noop:
            _plan_edit(plans, index, planned, edit, style)
    splices: list[Splice] = []
    for path, plan in plans.items():
        node = index.locate(path)
        if node is None:  # unreachable: plans only name containers present in the original
            raise ValueError(f"no container at {path} in the original text")
        splices.extend(plan.splices(index.text, node, style))
    return splices


@dataclass
class _ContainerPlan:
    """Item-level changes to one existing container (object members or array elements)."""

    deleted: set[int] = field(default_factory=set)
    replaced: dict[int, _Renderer] = field(default_factory=dict)
    appended: list[_Renderer] = field(default_factory=list)
    added_keys: set[str] = field(default_factory=set)

    def splices(self, text: str, node: JsonNode, style: JsonStyle) -> list[Splice]:
        if node.kind == "object":
            spans = [(m.key_start, m.value.end) for m in node.members]
        else:
            spans = [(e.start, e.end) for e in node.elements]
        return _sequence_splices(text, node, spans, self, style)


def _plan_edit(
    plans: dict[KeyPath, _ContainerPlan],
    index: JsonSpanIndex,
    planned: Mapping[str, Any],
    edit: ArrayEdit,
    style: JsonStyle,
) -> None:
    pruned = _first_prefix(
        edit.path, lambda p: index.locate(p) is not None and not _has(planned, p)
    )
    if pruned is not None:
        _plan_member_delete(plans.setdefault(pruned[:-1], _ContainerPlan()), index, pruned)
        return
    created = _first_prefix(edit.path, lambda p: index.locate(p) is None)
    if created is not None:
        _plan_member_add(plans.setdefault(created[:-1], _ContainerPlan()), planned, created, style)
        return
    plan = plans.setdefault(edit.path, _ContainerPlan())
    plan.deleted.update(edit.delete)
    plan.replaced.update({i: _value_renderer(v, style) for i, v in edit.replace.items()})
    plan.appended.extend(_value_renderer(v, style) for v in edit.append)


def _plan_member_delete(plan: _ContainerPlan, index: JsonSpanIndex, path: KeyPath) -> None:
    parent = index.locate(path[:-1])
    keys = [m.key for m in parent.members] if parent is not None else []
    plan.deleted.add(keys.index(path[-1]))


def _plan_member_add(
    plan: _ContainerPlan, planned: Mapping[str, Any], path: KeyPath, style: JsonStyle
) -> None:
    if path[-1] in plan.added_keys:  # two edits created the same missing parent
        return
    plan.added_keys.add(path[-1])
    plan.appended.append(_member_renderer(path[-1], _lookup(planned, path), style))


def _first_prefix(path: KeyPath, test: Callable[[KeyPath], bool]) -> KeyPath | None:
    return next((path[:n] for n in range(1, len(path) + 1) if test(path[:n])), None)


def _has(doc: Mapping[str, Any], path: KeyPath) -> bool:
    node: Any = doc
    for key in path:
        if not isinstance(node, Mapping) or key not in node:
            return False
        node = node[key]
    return True


def _lookup(doc: Mapping[str, Any], path: KeyPath) -> Any:
    node: Any = doc
    for key in path:
        node = node[key]
    return node


def _value_renderer(value: object, style: JsonStyle) -> _Renderer:
    return lambda base, compact: render_fragment(value, style, base, compact=compact)


def _member_renderer(key: str, value: object, style: JsonStyle) -> _Renderer:
    prefix = json.dumps(key, ensure_ascii=False) + ": "
    return lambda base, compact: prefix + render_fragment(value, style, base, compact=compact)


def _sequence_splices(
    text: str, node: JsonNode, spans: list[tuple[int, int]], plan: _ContainerPlan, style: JsonStyle
) -> list[Splice]:
    """Splices for one container whose items sit at ``spans`` in ``text``."""
    survivors = [i for i in range(len(spans)) if i not in plan.deleted]
    if not survivors:
        return [_rewrite_interior(text, node, plan.appended, style)]
    multiline = "\n" in text[node.start + 1 : spans[0][0]]
    splices = [
        Splice(*spans[i], render(line_indent(text, spans[i][0]), not multiline))
        for i, render in plan.replaced.items()
    ]
    splices.extend(_deletion_splices(spans, plan.deleted, survivors[0]))
    if plan.appended:
        last = survivors[-1]
        added = _appended_text(text, spans, last, multiline, plan.appended, style)
        splices = _with_tail_text(splices, spans[last][1], added)
    return splices


def _appended_text(
    text: str,
    spans: list[tuple[int, int]],
    last: int,
    multiline: bool,
    appended: list[_Renderer],
    style: JsonStyle,
) -> str:
    """The new items, each led by its separator, to place right after item ``last``.

    Multi-line containers put each item on its own line at the last survivor's
    indent; one-line containers reuse their own separator.
    """
    if multiline:
        base = line_indent(text, spans[last][0])
        separator = "," + style.newline + base
    else:
        base, separator = "", _compact_separator(text, spans)
    return "".join(separator + render(base, not multiline) for render in appended)


def _deletion_splices(spans: list[tuple[int, int]], deleted: set[int], first: int) -> list[Splice]:
    """One splice per run of deleted items, taking exactly one separating comma with it.

    Items before the first survivor go with the separator that follows them;
    every later run goes with the separator that precedes it.
    """
    splices = [Splice(spans[0][0], spans[first][0], "")] if first > 0 else []
    run_start: int | None = None
    for i in range(first + 1, len(spans) + 1):
        if i < len(spans) and i in deleted:
            run_start = i if run_start is None else run_start
        elif run_start is not None:
            splices.append(Splice(spans[run_start - 1][1], spans[i - 1][1], ""))
            run_start = None
    return splices


def _with_tail_text(splices: list[Splice], offset: int, text: str) -> list[Splice]:
    """Insert ``text`` at ``offset``, folding it into a tail deletion that starts there."""
    tail = next((s for s in splices if s.start == offset and s.end > offset), None)
    if tail is None:
        return [*splices, Splice(offset, offset, text)]
    return [s for s in splices if s is not tail] + [Splice(tail.start, tail.end, text)]


def _compact_separator(text: str, spans: list[tuple[int, int]]) -> str:
    """The separator a one-line container already uses between its first two items."""
    if len(spans) > 1:
        between = text[spans[0][1] : spans[1][0]]
        if "\n" not in between:
            return between
    return ", "


def _rewrite_interior(
    text: str, node: JsonNode, appended: list[_Renderer], style: JsonStyle
) -> Splice:
    """Replace everything between the brackets: empty, or the appended items one per line."""
    if not appended:
        return Splice(node.start + 1, node.end - 1, "")
    base = line_indent(text, node.start)
    inner = base + style.indent
    body = ("," + style.newline + inner).join(render(inner, False) for render in appended)
    return Splice(node.start + 1, node.end - 1, style.newline + inner + body + style.newline + base)
