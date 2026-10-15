"""The managed merge into ``.claude/settings.json`` (specs/prK-lifecycle-hooks.md §C.2.4, L4).

``settings.json`` is co-owned: users and Claude Code write it too, and JSON has
no comment syntax for a sentinel. So the engine owns individual elements, each
proven by a scoped lockfile hash, and edits them by splicing the original text:

1. read (absent means ``{}``; whitespace-only means ``{}`` with a warning);
2. parse strictly (no duplicate keys, ``NaN``, comments or trailing commas);
3-4. plan per Claude event and per managed string array (:mod:`._settings_plan`);
5. leave the text alone when the plan is empty (byte stability);
6. splice only the managed spans, in the file's own indent/newline/BOM;
7. re-parse the result and compare it with the plan;
8. write bytes atomically, re-reading once to survive a concurrent writer.

:func:`merge_managed_entries` is pure (steps 1-7); :func:`write_settings` adds
step 8 over an injectable :class:`SettingsIO`. Stdlib-only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from coding_agent_playbook._atomic_io import atomic_write_bytes
from coding_agent_playbook.adapters._json_edits import apply_edits, edit_splices, render_fragment
from coding_agent_playbook.adapters._json_spans import (
    DEFAULT_STYLE,
    JsonSpanError,
    JsonSpanIndex,
    apply_splices,
    detect_style,
    line_col,
)
from coding_agent_playbook.adapters._settings_plan import (
    CLAUDE_SETTINGS_PATH,
    LAUNCHER_TOKEN,
    MANAGED_STRING_POINTERS,
    DesiredGroup,
    SettingsPlan,
    SettingsShapeError,
    canonical_json,
    json_pointer,
    plan_settings,
    scoped_lock_entry,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.adapters._json_spans import Splice
    from coding_agent_playbook.lockfile import LockEntry

__all__ = [
    "CLAUDE_SETTINGS_PATH",
    "LAUNCHER_TOKEN",
    "MANAGED_STRING_POINTERS",
    "DesiredGroup",
    "FileSettingsIO",
    "MergeFn",
    "MergeResult",
    "SettingsIO",
    "SettingsMergeError",
    "Splicer",
    "canonical_json",
    "decode_settings",
    "json_pointer",
    "merge_managed_entries",
    "parse_settings",
    "scoped_lock_entry",
    "write_settings",
]

type Splicer = Callable[[str, Sequence[Splice]], str]
type MergeFn = Callable[[str | None], MergeResult]


class SettingsMergeError(ValueError):
    """``settings.json`` cannot be merged safely; sync must exit 1 and write nothing.

    ``str()`` is ``<path>:<line>:<col>: <message>`` (1-based).

    Example::

        SettingsMergeError(".claude/settings.json", 3, 3, "invalid JSON: duplicate key 'a'")
    """

    def __init__(self, path: str, line: int, col: int, message: str) -> None:
        super().__init__(f"{path}:{line}:{col}: {message}")
        self.path = path
        self.line = line
        self.col = col
        self.message = message


@dataclass(frozen=True)
class MergeResult:
    """The merged text and what the merge did.

    ``text`` is ``None`` only when the file was absent and stays absent.
    ``entries`` holds a scoped lock entry for every desired group (no-op ones
    included) and every claimed managed string (§C.2.4 step 9). ``warnings``
    are hand-edit and duplicate reports; ``notes`` are info lines ("re-added");
    ``updated`` / ``removed`` count managed elements for the sync summary.
    """

    text: str | None
    changed: bool
    warnings: tuple[str, ...] = ()
    entries: tuple[LockEntry, ...] = ()
    notes: tuple[str, ...] = ()
    updated: int = 0
    removed: int = 0


@dataclass(frozen=True)
class _Source:
    """The document as read: parsed value, text without BOM, and how to re-emit it."""

    doc: Any
    body: str
    bom: str
    fresh: bool
    warnings: tuple[str, ...] = ()


def merge_managed_entries(
    text: str | None,
    desired: Mapping[str, Sequence[DesiredGroup]],
    prior: Iterable[LockEntry],
    *,
    strings: Mapping[str, Sequence[str]] | None = None,
    path: str = CLAUDE_SETTINGS_PATH,
    splicer: Splicer = apply_splices,
) -> MergeResult:
    """Merge the managed hook groups and strings into ``text`` (§C.2.4 steps 1-7).

    ``desired`` maps Claude event names to wanted groups (new event keys are
    appended in this order); ``strings`` maps :data:`MANAGED_STRING_POINTERS`
    to wanted strings; ``prior`` is the previous lockfile's entries. Raises
    :class:`SettingsMergeError` (with ``path:line:col``) for invalid JSON, a
    wrong shape, a mixed matcher group or a failed self-check. ``splicer`` is a
    seam for tests.

    Example::

        result = merge_managed_entries(path.read_text(), {"Stop": [DesiredGroup(...)]},
                                       lock.entries)
    """
    source = _load(text, path)
    plan = _plan(source, desired, prior, strings or {}, path)
    warnings = (*source.warnings, *plan.warnings)
    if all(edit.is_noop for edit in plan.edits):
        return MergeResult(text, False, warnings, tuple(plan.entries), tuple(plan.notes))
    planned = apply_edits(source.doc, plan.edits)
    body = _render(source, planned, plan, splicer)
    _self_check(body, planned, path)
    return MergeResult(
        source.bom + body,
        True,
        warnings,
        tuple(plan.entries),
        tuple(plan.notes),
        plan.updated,
        plan.removed,
    )


def parse_settings(text: str | None, *, path: str = CLAUDE_SETTINGS_PATH) -> Any:
    """The strictly parsed document (§C.2.4 step 2); absent or whitespace-only text is ``{}``.

    Raises :class:`SettingsMergeError` (``path:line:col``) for anything Claude
    Code's own parser rejects. ``playbook check`` reads the file through it.

    Example::

        >>> parse_settings('{"model": "x"}')
        {'model': 'x'}
    """
    return _load(text, path).doc


def _load(text: str | None, path: str) -> _Source:
    if text is None:
        return _Source({}, "", "", fresh=True)
    bom = "\ufeff" if text.startswith("\ufeff") else ""
    body = text[len(bom) :]
    if not body.strip(" \t\r\n"):
        note = f"{path}: the file holds only whitespace; treated as {{}}."
        return _Source({}, body, bom, fresh=True, warnings=(note,))
    return _Source(_strict_parse(body, path), body, bom, fresh=False)


class _NotStrictJson(ValueError):
    """Python's json accepted something Claude Code's parser rejects."""


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    for key, _ in pairs:
        if key in seen:
            raise _NotStrictJson(f"duplicate key {key!r}")
        seen.add(key)
    return dict(pairs)


def _reject_constant(name: str) -> Any:
    raise _NotStrictJson(f"{name} is not valid JSON")


def _strict_parse(body: str, path: str) -> Any:
    """``json.loads`` without duplicate keys or non-finite numbers (§C.2.4 step 2)."""
    try:
        return json.loads(body, object_pairs_hook=_unique_keys, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise SettingsMergeError(path, exc.lineno, exc.colno, f"invalid JSON: {exc.msg}") from None
    except _NotStrictJson as exc:
        raise _locate_violation(body, path, str(exc)) from None
    except RecursionError:
        raise SettingsMergeError(path, 1, 1, "invalid JSON: nested too deeply") from None


def _locate_violation(body: str, path: str, message: str) -> SettingsMergeError:
    """Position a duplicate key or ``NaN`` with the span scanner (json's hooks have none)."""
    try:
        JsonSpanIndex.build(body)
    except JsonSpanError as exc:
        line, col = line_col(body, exc.offset)
        return SettingsMergeError(path, line, col, f"invalid JSON: {exc.message}")
    return SettingsMergeError(path, 1, 1, f"invalid JSON: {message}")


def _plan(
    source: _Source,
    desired: Mapping[str, Sequence[DesiredGroup]],
    prior: Iterable[LockEntry],
    strings: Mapping[str, Sequence[str]],
    path: str,
) -> SettingsPlan:
    """:func:`plan_settings`, with shape errors positioned at the offending value."""
    try:
        return plan_settings(source.doc, desired, prior, strings, path=path)
    except SettingsShapeError as exc:
        # A fresh source is ``{}``; its (whitespace-only) body has no spans to index.
        node = None if source.fresh else JsonSpanIndex.build(source.body).locate(exc.path)
        line, col = line_col(source.body, node.start if node is not None else 0)
        raise SettingsMergeError(path, line, col, exc.message) from None


def _render(source: _Source, planned: dict[str, Any], plan: SettingsPlan, splicer: Splicer) -> str:
    """Splice the plan into the original text, or render a new two-space LF document."""
    if source.fresh:
        return render_fragment(planned, DEFAULT_STYLE, "") + DEFAULT_STYLE.newline
    index = JsonSpanIndex.build(source.body)
    style = detect_style(source.body)
    return splicer(source.body, edit_splices(index, planned, plan.edits, style))


def _self_check(body: str, planned: dict[str, Any], path: str) -> None:
    """A merged text whose meaning differs from the plan never reaches disk (§C.2.4 step 7)."""
    prefix = "self-check failed, nothing was written"
    try:
        reparsed = _strict_parse(body, path)
    except SettingsMergeError as exc:
        message = f"{prefix}: the merged text is not strict JSON ({exc.message})"
        raise SettingsMergeError(path, exc.line, exc.col, message) from exc
    if canonical_json(reparsed) != canonical_json(planned):
        message = f"{prefix}: the merged text does not mean the planned document"
        raise SettingsMergeError(path, 1, 1, message)


class SettingsIO(Protocol):
    """Byte-level file access for :func:`write_settings` (a seam for race tests)."""

    def read_bytes(self, path: Path) -> bytes | None:
        """The file's bytes, or ``None`` when it does not exist."""
        ...

    def write_bytes(self, path: Path, data: bytes) -> None:
        """Replace the file atomically, creating parent directories."""
        ...


class FileSettingsIO:
    """The real filesystem: atomic byte writes, never text mode."""

    def read_bytes(self, path: Path) -> bytes | None:
        """The file's bytes, or ``None`` when it does not exist."""
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None

    def write_bytes(self, path: Path, data: bytes) -> None:
        """Replace the file atomically, creating parent directories."""
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(path, data)


def decode_settings(data: bytes | None, *, path: str = CLAUDE_SETTINGS_PATH) -> str | None:
    """Decode settings bytes as UTF-8 (a BOM stays in the text); ``None`` passes through.

    Example::

        >>> decode_settings(b'{}')
        '{}'
    """
    if data is None:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        prefix = data[: exc.start].decode("utf-8", errors="replace")
        line, col = line_col(prefix, len(prefix))
        message = f"not valid UTF-8 (byte {data[exc.start]:#04x}); Claude Code reads UTF-8"
        raise SettingsMergeError(path, line, col, message) from None


def write_settings(
    source: Path,
    target: Path,
    merge: MergeFn,
    *,
    io: SettingsIO | None = None,
    path: str = CLAUDE_SETTINGS_PATH,
) -> MergeResult:
    """Read ``source``, merge, and write ``target`` only when the merge changed something.

    When ``source == target`` (write mode) the file is re-read just before the
    write; if a concurrent writer (Claude Code saving a permission approval)
    changed it, the merge is redone once on the new bytes, and a second change
    fails with :class:`SettingsMergeError` (§C.2.4 step 8). ``sync --check``
    passes a scratch ``target``, so the real file is read once and never written.

    Example::

        write_settings(repo / CLAUDE_SETTINGS_PATH, out / CLAUDE_SETTINGS_PATH,
                       lambda text: merge_managed_entries(text, desired, prior))
    """
    files = io if io is not None else FileSettingsIO()
    base = files.read_bytes(source)
    result = merge(decode_settings(base, path=path))
    if result.changed and source == target:
        result = _settle_race(source, base, result, merge, files, path)
    if result.changed and result.text is not None:
        files.write_bytes(target, result.text.encode("utf-8", errors="surrogatepass"))
    return result


def _settle_race(
    source: Path,
    base: bytes | None,
    result: MergeResult,
    merge: MergeFn,
    files: SettingsIO,
    path: str,
) -> MergeResult:
    current = files.read_bytes(source)
    if current == base:
        return result
    redone = merge(decode_settings(current, path=path))
    if redone.changed and files.read_bytes(source) != current:
        message = (
            "the file changed while playbook sync was merging it (twice); nothing was written. "
            "Run 'playbook sync' again."
        )
        raise SettingsMergeError(path, 1, 1, message)
    return redone
