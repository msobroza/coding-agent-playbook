"""The shared §E.3 post-edit pipeline: one ruff diagnostics call per edited file (specs/prK-hook-pack.md §E.3).

Every ruff consumer hook (post-edit-ruff-format now; the rule-linked lint
hooks, the quality and docstring companions later) runs these steps per
edited file, in-process, sharing their work through the event memo:

1. **eligibility** (:func:`edited_python_files`): a ``.py``/``.pyi`` file
   tool write whose realpath is inside this worktree, not a secret path, not
   a frozen eval fixture. Anything else spawns nothing;
2. **pin check** (:func:`ruff_runner`): the ``machine.json`` ruff, unchanged
   since sync, or one note per session and no ruff work;
3. **HEAD blob** (:func:`head_blob`): one ``cat-file`` per file, ``None`` for
   a new or untracked file;
4. M1/M2 (post-edit-ruff-format only, in ``ruff_feedback``);
5. **D1** (:func:`file_report`): ``_ruff.ruff_diagnostics_for``, the
   project's selection plus the consumers' codes (:func:`extended_codes`);
6. **changed lines**: diagnostics outside the lines the edit inserted or
   replaced are dropped, so legacy code is never flooded; a parse error is
   always kept (the edit caused it, wherever ruff points);
7. **partition, dedupe, cap, emit** (:data:`BUCKETS`, :func:`bucket_lines`):
   first matching row wins; a line seen this session (``sha256(rel, code,
   stripped source line)``: line numbers shift, text does not) is not
   repeated; the cap stops before a key is burned.

A private module: it registers no handler.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime._ruff import (
    RuffFailure,
    RuffPin,
    RuffRunner,
    changed_lines,
    ruff_diagnostics_for,
    ruff_pin,
)
from coding_agent_playbook.hook_runtime.caps import quote_data
from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.handlers._targets import file_write_paths

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from coding_agent_playbook.hook_runtime._ruff import PinProblem, RuffDiagnostic
    from coding_agent_playbook.hook_runtime.config import GuardConfig, HookRecord
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.paths import NormalizedPath
    from coding_agent_playbook.hook_runtime.registry import HandlerContext

__all__ = [
    "BUCKETS",
    "POST_EDIT_HOOK_ID",
    "RUFF_CONSUMERS",
    "BucketRow",
    "EditedFile",
    "FileReport",
    "HeadBlob",
    "blob_oid",
    "bucket_lines",
    "edited_python_files",
    "enabled_consumers",
    "extended_codes",
    "file_report",
    "head_blob",
    "ruff_runner",
    "skip_note",
]

POST_EDIT_HOOK_ID: Final = "post-edit-ruff-format"
#: The builtins that read D1; every one of them computes the same codes, so D1 runs once.
RUFF_CONSUMERS: Final = frozenset({"ruff_post_edit"})
#: A file larger than this gets no ruff work: 2 s per call would not cover it.
MAX_FILE_BYTES: Final = 2 * 1024 * 1024
_PY_SUFFIXES: Final = (".py", ".pyi")
_LINE_CHARS: Final = 240
_SKIP_NOTES: Final[Mapping[str, str]] = {
    "changed": (
        "ruff changed since the last `playbook sync`; post-edit checks skipped until it is "
        "re-pinned."
    ),
    "missing": "ruff is not pinned in this worktree; post-edit checks skipped (run playbook sync).",
    "timeout": "ruff timed out; post-edit checks skipped this time.",
    "error": "ruff failed; post-edit checks skipped this time.",
}


# --- 1. eligibility ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EditedFile:
    """One eligible edited file: the realpath ruff runs on and its repo-relative POSIX name."""

    path: str
    rel: str


def edited_python_files(ev: CanonicalEvent, ctx: HandlerContext) -> list[EditedFile]:
    """The eligible Python files of a file-tool write, each once, in payload order.

    Example::

        >>> edited_python_files(edit_of_readme, ctx)  # doctest: +SKIP
        []
    """
    if ev.tool is None or ev.repo is None:
        return []
    root = os.path.realpath(ev.repo.worktree_root)
    found: dict[str, EditedFile] = {}
    for path in file_write_paths(ev.tool):
        edited = _eligible(path, root, ctx.cfg)
        if edited is not None:
            found.setdefault(edited.rel, edited)
    return list(found.values())


def _eligible(path: NormalizedPath, root: str, cfg: GuardConfig) -> EditedFile | None:
    real = path.realpath
    if path.repo_rel is None or path.sibling_worktree or not real.endswith(_PY_SUFFIXES):
        return None
    if not real.startswith(root + os.sep):
        return None  # a symlink out of the worktree: not this repo's code
    rel = real[len(root) + 1 :].replace(os.sep, "/")
    fixtures = cfg.path_classes.get("eval_fixture")
    for key in (path.key, rel):
        if cfg.secret_paths.matches(key) or (fixtures is not None and fixtures.matches(key)):
            return None
    return EditedFile(real, rel)


# --- 2. the pin ----------------------------------------------------------------------------------


def ruff_runner(ev: CanonicalEvent, ctx: HandlerContext) -> RuffRunner | PinProblem:
    """The pinned ruff of ``ev``'s worktree, read once per event, or why there is none.

    Example::

        >>> ruff_runner(ev, ctx)  # doctest: +SKIP
        'changed'
    """
    repo = ev.repo
    assert repo is not None  # eligibility found a file in this repo

    def load() -> RuffPin | PinProblem:
        from coding_agent_playbook.hook_runtime.pin import read_machine_pins

        return ruff_pin(read_machine_pins(git_dir=repo.git_dir))

    pin = ctx.memo.get_or_compute(("ruff-pin",), load)
    if isinstance(pin, RuffPin):
        return RuffRunner(ctx.proc, pin, cwd=repo.worktree_root)
    return pin


def skip_note(ctx: HandlerContext, why: PinProblem | RuffFailure) -> HandlerResult | None:
    """Fail open: one note per session per cause, shared by every ruff consumer (§E.3).

    Example::

        >>> skip_note(ctx, "changed").user_note  # doctest: +SKIP
        'ruff changed since the last `playbook sync`; ...'
    """
    kind = why if isinstance(why, str) else why.kind
    if not ctx.session.once(f"ruff:{kind}"):
        return None
    return HandlerResult(
        decision=Decision.NONE,
        hook_id=ctx.hook.id,
        rule_id=f"ruff_{kind}",
        user_note=_SKIP_NOTES[kind],
    )


# --- 3. the HEAD blob -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HeadBlob:
    """A file's bytes at ``HEAD`` and their git blob id (the format-clean cache key)."""

    oid: str
    data: bytes

    @property
    def text(self) -> str:
        """The blob as text (undecodable bytes replaced)."""
        return self.data.decode("utf-8", errors="replace")


def blob_oid(data: bytes) -> str:
    """Git's blob id of ``data`` (``sha1("blob <n>\\0" + data)``): no second git call.

    Example::

        >>> blob_oid(b"")
        'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391'
    """
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def head_blob(ctx: HandlerContext, edited: EditedFile) -> HeadBlob | None:
    """``edited`` at ``HEAD`` through ``SafeGit``, once per event; ``None`` when new or untracked."""

    def read() -> HeadBlob | None:
        data = ctx.git.cat_head(edited.rel)
        return None if data is None else HeadBlob(blob_oid(data), data)

    head: HeadBlob | None = ctx.memo.get_or_compute(("ruff-head", edited.rel), read)
    return head


# --- 5./6. D1 on the changed lines --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FileReport:
    """D1's diagnostics of one file on the lines the edit changed, and the file's lines."""

    edited: EditedFile
    diagnostics: tuple[RuffDiagnostic, ...]
    source: tuple[str, ...]

    def line_text(self, row: int) -> str:
        """Line ``row`` (1-based) of the file as ruff saw it, stripped."""
        return self.source[row - 1].strip() if 0 < row <= len(self.source) else ""


def file_report(
    runner: RuffRunner,
    ctx: HandlerContext,
    edited: EditedFile,
    head: HeadBlob | None,
    codes: Iterable[str],
) -> FileReport | None:
    """D1 on ``edited`` as it is on disk now, kept to the changed lines; ``None`` if unreadable.

    Raises :class:`RuffFailure` when ruff cannot answer.
    """
    data = _read(edited.path)
    if data is None:
        return None
    found = ruff_diagnostics_for(runner, ctx.memo, edited.path, data, codes)
    text = data.decode("utf-8", errors="replace")
    changed = changed_lines(None if head is None else head.text, text)
    kept = tuple(d for d in found if d.is_syntax_error or d.row in changed)
    return FileReport(edited, kept, tuple(text.splitlines()))


def _read(path: str) -> bytes | None:
    try:
        if os.stat(path).st_size > MAX_FILE_BYTES:
            return None
        with open(path, "rb") as handle:
            return handle.read(MAX_FILE_BYTES + 1)
    except OSError:
        return None


# --- the consumers and their codes ----------------------------------------------------------------


def enabled_consumers(ev: CanonicalEvent, cfg: GuardConfig) -> dict[str, HookRecord]:
    """The enabled hooks whose ``post_tool_use`` handler reads D1 and whose matcher takes ``ev``.

    Example::

        >>> sorted(enabled_consumers(ev, cfg))  # doctest: +SKIP
        ['post-edit-ruff-format']
    """
    from coding_agent_playbook.hook_runtime._selection import matcher_accepts

    found: dict[str, HookRecord] = {}
    for hook_id, record in cfg.hooks.items():
        spec = record.handlers.get(EventName.POST_TOOL_USE)
        if spec is None or spec.kind != "builtin" or spec.name not in RUFF_CONSUMERS:
            continue
        if matcher_accepts(record.matcher.get(EventName.POST_TOOL_USE), ev):
            found[hook_id] = record
    return found


def extended_codes(consumers: Mapping[str, HookRecord]) -> frozenset[str]:
    """``U``: the sorted union of the consumers' ``lint_codes`` (D1's ``--extend-select``).

    Example::

        >>> extended_codes({})
        frozenset()
    """
    codes: set[str] = set()
    for record in consumers.values():
        spec = record.handlers[EventName.POST_TOOL_USE]
        listed = spec.config.get("lint_codes")
        if isinstance(listed, Mapping):
            listed = listed.get("warn")
        if isinstance(listed, list):
            codes.update(code for code in listed if isinstance(code, str))
    return frozenset(codes)


# --- 7. partition, dedupe, cap, emit --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BucketRow:
    """One §E.3 bucket: the hook that reports it, its line prefix, which diagnostics it claims."""

    hook_id: str
    prefix: str
    claims: Callable[[RuffDiagnostic, frozenset[str]], bool]


def _project_selected(diagnostic: RuffDiagnostic, extended: frozenset[str]) -> bool:
    """D1 adds only ``extended`` to the project's own selection: any other code is CI's."""
    return diagnostic.is_syntax_error or diagnostic.code not in extended


#: First match wins; the rule-linked lint hooks (K7 step 3) and §F's companions add rows.
BUCKETS: Final[tuple[BucketRow, ...]] = (
    BucketRow(POST_EDIT_HOOK_ID, "ruff (CI fails on this):", _project_selected),
)


def bucket_lines(
    ctx: HandlerContext,
    reports: Sequence[FileReport],
    row: BucketRow,
    *,
    enabled: frozenset[str],
    extended: frozenset[str],
    cap: int,
) -> list[str]:
    """``row``'s lines, by file then line number: each new this session, at most ``cap``.

    A diagnostic belongs to the first enabled row claiming it.

    Example::

        >>> bucket_lines(ctx, reports, BUCKETS[0], enabled=frozenset({POST_EDIT_HOOK_ID}),
        ...     extended=frozenset(), cap=5)  # doctest: +SKIP
        ['ruff (CI fails on this): "src/app.py:3 F821 Undefined name `x`"']
    """
    rows = [r for r in BUCKETS if r.hook_id in enabled]
    mine = [
        (report, d)
        for report in sorted(reports, key=lambda r: r.edited.rel)
        for d in sorted(report.diagnostics, key=lambda d: d.row)
        if next((r for r in rows if r.claims(d, extended)), None) is row
    ]
    lines: list[str] = []
    for report, diagnostic in mine:
        if len(lines) == cap:
            break  # before the dedupe: a line past the cap is not marked as shown
        if ctx.session.once(_dedupe_key(report, diagnostic)):
            lines.append(f"{row.prefix} {_shown(report, diagnostic)}")
    return lines


def _dedupe_key(report: FileReport, diagnostic: RuffDiagnostic) -> str:
    parts = (report.edited.rel, diagnostic.label, report.line_text(diagnostic.row))
    digest = hashlib.sha256("\0".join(parts).encode("utf-8", "surrogatepass")).hexdigest()
    return f"ruff:{digest[:16]}"


def _shown(report: FileReport, diagnostic: RuffDiagnostic) -> str:
    text = f"{report.edited.rel}:{diagnostic.row} {diagnostic.label} {diagnostic.message}"
    return quote_data(text, _LINE_CHARS)
