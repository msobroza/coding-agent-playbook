"""The shared §E.3 post-edit pipeline: one ruff diagnostics call per edited file (specs/prK-hook-pack.md §E.3).

Every ruff consumer hook (post-edit-ruff-format, the three rule-linked lint
hooks, §F's quality and docstrings companions) runs these steps per edited
file, in-process, sharing their work through the event memo:

1. **eligibility** (:func:`edited_python_files`): a ``.py``/``.pyi`` file
   tool write whose realpath is inside this worktree, not a secret path, not
   a frozen eval fixture. Anything else spawns nothing;
2. **pin check** (:func:`ruff_runner`): the ``machine.json`` ruff, unchanged
   since sync, or one note per session and no ruff work;
3. **HEAD blob** (:func:`head_blob`): one ``cat-file`` per file, ``None`` for
   a new or untracked file;
4. M1/M2 (post-edit-ruff-format only, in ``ruff_feedback``);
5. **D1** (:func:`file_report`): ``_ruff.ruff_diagnostics_for``, the
   project's selection plus ``U`` (:func:`file_codes`): the codes of the
   consumers that are on for this event **and** whose paths take this file.
   Every consumer computes the same ``U`` for a file, so D1 runs once. The
   quality companion's ``--config`` thresholds ride on D1, and its preview-only
   codes (PLR1702) get one separate ``--preview`` call (:func:`file_ruff_config`,
   :func:`file_preview_codes`);
6. **changed lines**: diagnostics outside the lines the edit inserted or
   replaced are dropped, so legacy code is never flooded; a parse error is
   always kept (the edit caused it, wherever ruff points);
7. partition, dedupe, cap, emit: ``_ruff_buckets``.

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
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.dispatch.event import EventName
from coding_agent_playbook.hook_runtime.handlers._shared.targets import file_write_paths, repo_file

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from coding_agent_playbook.hook_runtime._ruff import PinProblem, RuffDiagnostic
    from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig, HookRecord
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.dispatch.paths import NormalizedPath
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext

__all__ = [
    "POST_EDIT_HOOK_ID",
    "RUFF_CONSUMERS",
    "EditedFile",
    "FileReport",
    "HeadBlob",
    "accepts_file",
    "blob_oid",
    "edited_python_files",
    "enabled_consumers",
    "event_ruff_pin",
    "file_codes",
    "file_preview_codes",
    "file_report",
    "file_ruff_config",
    "head_blob",
    "lint_codes_of",
    "ruff_runner",
    "skip_note",
]

POST_EDIT_HOOK_ID: Final = "post-edit-ruff-format"
#: The builtins that read D1; every one of them computes the same codes, so D1 runs once.
RUFF_CONSUMERS: Final = frozenset(
    {
        "ruff_post_edit",
        "ruff_lint_feedback",
        "clean_code_metrics_nonregression:post_edit",
        "docstring_nonregression:post_edit",
    }
)
#: A file larger than this gets no ruff work: 2 s per call would not cover it.
MAX_FILE_BYTES: Final = 2 * 1024 * 1024
_PY_SUFFIXES: Final = (".py", ".pyi")
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
    """One eligible edited file: the realpath ruff runs on, its repo-relative POSIX name and
    its glob key (``NormalizedPath.key``: what a matcher's ``paths`` match)."""

    path: str
    rel: str
    key: str


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
    found = repo_file(path, root, cfg, suffixes=_PY_SUFFIXES)
    return None if found is None else EditedFile(found[0], found[1], path.key)


# --- 2. the pin ----------------------------------------------------------------------------------


def ruff_runner(ev: CanonicalEvent, ctx: HandlerContext) -> RuffRunner | PinProblem:
    """The pinned ruff of ``ev``'s worktree, read once per event, or why there is none.

    Example::

        >>> ruff_runner(ev, ctx)  # doctest: +SKIP
        'changed'
    """
    repo = ev.repo
    assert repo is not None  # eligibility found a file in this repo
    pin = event_ruff_pin(ctx, repo.git_dir)
    if isinstance(pin, RuffPin):
        return RuffRunner(ctx.proc, pin, cwd=repo.worktree_root)
    return pin


def event_ruff_pin(ctx: HandlerContext, git_dir: str | None) -> RuffPin | PinProblem:
    """The worktree's ruff pin, read once per event (post-edit and Stop share it).

    Example::

        >>> event_ruff_pin(ctx, ev.repo.git_dir)  # doctest: +SKIP
        'missing'
    """

    def load() -> RuffPin | PinProblem:
        from coding_agent_playbook.hook_runtime.config.pin import read_machine_pins

        return ruff_pin(read_machine_pins(git_dir=git_dir))

    pin: RuffPin | PinProblem = ctx.memo.get_or_compute(("ruff-pin", git_dir), load)
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
    """D1's diagnostics of one file on the lines the edit changed, and what they judge by.

    ``sha`` is the sha256 of the bytes D1 saw (after M1/M2), ``changed`` the
    lines the edit inserted or replaced, ``is_new`` whether the file has no
    HEAD blob (created this session or untracked).
    """

    edited: EditedFile
    diagnostics: tuple[RuffDiagnostic, ...]
    source: tuple[str, ...]
    sha: str = ""
    changed: frozenset[int] = frozenset()
    is_new: bool = False

    def line_text(self, row: int) -> str:
        """Line ``row`` (1-based) of the file as ruff saw it, stripped."""
        return self.source[row - 1].strip() if 0 < row <= len(self.source) else ""

    @property
    def text(self) -> str:
        """The file as ruff saw it (line endings normalized), for an ``ast.parse``."""
        return "\n".join(self.source) + "\n"


def file_report(
    runner: RuffRunner,
    ctx: HandlerContext,
    edited: EditedFile,
    head: HeadBlob | None,
    codes: Iterable[str],
    *,
    config: Sequence[str] = (),
    preview: Iterable[str] = (),
) -> FileReport | None:
    """D1 on ``edited`` as it is on disk now, kept to the changed lines; ``None`` if unreadable.

    Memoized per ``(path, content sha256)``: every consumer of the event gets
    the same report (one D1, one diff). Raises :class:`RuffFailure` when ruff
    cannot answer.
    """
    data = _read(edited.path)
    if data is None:
        return None
    sha = hashlib.sha256(data).hexdigest()
    wanted = frozenset(codes)

    def build() -> FileReport:
        found = ruff_diagnostics_for(
            runner, ctx.memo, edited.path, data, wanted, config=config, preview=preview
        )
        text = data.decode("utf-8", errors="replace")
        changed = frozenset(changed_lines(None if head is None else head.text, text))
        kept = tuple(d for d in found if d.is_syntax_error or d.row in changed)
        lines = tuple(text.splitlines())
        return FileReport(edited, kept, lines, sha, changed, is_new=head is None)

    report: FileReport = ctx.memo.get_or_compute(("ruff-report", edited.path, sha, wanted), build)
    return report


def _read(path: str) -> bytes | None:
    try:
        if os.stat(path).st_size > MAX_FILE_BYTES:
            return None
        with open(path, "rb") as handle:
            return handle.read(MAX_FILE_BYTES + 1)
    except OSError:
        return None


# --- the consumers and their codes ----------------------------------------------------------------


def enabled_consumers(ev: CanonicalEvent, ctx: HandlerContext) -> dict[str, HookRecord]:
    """The ruff consumers the dispatcher runs on ``ev``: D1 serves exactly these.

    The selection's own tests: a builtin of :data:`RUFF_CONSUMERS` on
    ``post_tool_use``, this harness in its ``supports``, not switched off by
    ``PLAYBOOK_HOOKS_DISABLE``, its matcher taking the event. A hook D1 served
    but the dispatcher skipped would burn its findings' dedupe keys unseen.

    Example::

        >>> sorted(enabled_consumers(ev, ctx))  # doctest: +SKIP
        ['error-handling-lint-feedback', 'post-edit-ruff-format']
    """
    from coding_agent_playbook.hook_runtime.dispatch.selection import matcher_accepts

    found: dict[str, HookRecord] = {}
    for hook_id, record in ctx.cfg.hooks.items():
        spec = record.handlers.get(EventName.POST_TOOL_USE)
        if spec is None or spec.kind != "builtin" or spec.name not in RUFF_CONSUMERS:
            continue
        if spec.config.get("lint_feedback") is False:
            continue  # a companion switched off by its consumer: no codes, no lines
        if ev.harness.value not in record.supports:
            continue
        if ctx.hatches.skips(hook_id, mandatory=record.mandatory):
            continue
        if matcher_accepts(record.matcher.get(EventName.POST_TOOL_USE), ev):
            found[hook_id] = record
    return found


def accepts_file(record: HookRecord, edited: EditedFile) -> bool:
    """Whether ``record``'s ``post_tool_use`` paths take ``edited`` (no paths: every file).

    The event matcher passes when *any* written path matches; a multi-file
    write needs the per-file answer.
    """
    spec = record.matcher.get(EventName.POST_TOOL_USE)
    return spec is None or not spec.paths.patterns or spec.paths.matches(edited.key)


def lint_codes_of(record: HookRecord) -> frozenset[str]:
    """The codes a consumer asks D1 to add: its ``config["lint_codes"]`` (list or ``{warn}``).

    Example::

        >>> lint_codes_of(post_edit_record)  # doctest: +SKIP
        frozenset()
    """
    spec = record.handlers.get(EventName.POST_TOOL_USE)
    listed = None if spec is None else spec.config.get("lint_codes")
    if isinstance(listed, Mapping):
        listed = listed.get("warn")
    if not isinstance(listed, list):
        return frozenset()
    return frozenset(code for code in listed if isinstance(code, str))


def file_ruff_config(consumers: Mapping[str, HookRecord], edited: EditedFile) -> list[str]:
    """The ``--config`` overrides D1 carries for ``edited``: its consumers' ``ruff_config``.

    Sync renders them from ``[metrics.ruff_violations] config`` into the
    quality companion's config, minus those of codes the project selects itself.

    Example::

        >>> file_ruff_config({}, edited)  # doctest: +SKIP
        []
    """
    flags: set[str] = set()
    for record in consumers.values():
        if accepts_file(record, edited):
            flags.update(_strings(_post_edit_config(record).get("ruff_config")))
    return sorted(flags)


def file_preview_codes(
    consumers: Mapping[str, HookRecord], edited: EditedFile, drop: Iterable[str]
) -> list[str]:
    """The codes of a ``ruff_preview`` consumer the pinned ruff runs only under ``--preview``.

    ``drop`` is the pin's: what plain D1 cannot run (preview-only or unknown).

    Example::

        >>> file_preview_codes({}, edited, ["PLR1702"])  # doctest: +SKIP
        []
    """
    dropped = set(drop)
    codes: set[str] = set()
    for record in consumers.values():
        if accepts_file(record, edited) and _post_edit_config(record).get("ruff_preview") is True:
            codes.update(lint_codes_of(record) & dropped)
    return sorted(codes)


def _post_edit_config(record: HookRecord) -> Mapping[str, object]:
    spec = record.handlers.get(EventName.POST_TOOL_USE)
    return {} if spec is None else spec.config


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def file_codes(consumers: Mapping[str, HookRecord], edited: EditedFile) -> frozenset[str]:
    """``U`` for ``edited``: the union of the codes of the consumers whose paths take it.

    Example::

        >>> file_codes({}, edited)  # doctest: +SKIP
        frozenset()
    """
    codes: set[str] = set()
    for record in consumers.values():
        if accepts_file(record, edited):
            codes.update(lint_codes_of(record))
    return frozenset(codes)
