"""The §E.3 ruff consumers: post-edit-ruff-format and the rule-linked lint hooks (specs/prK-hook-pack.md §E.3).

Both builtins run on the shared pipeline (``_ruff_pipeline``) and read the
same per-event partition (``_ruff_buckets``), so D1 runs once per edited file
whatever the number of consumers.

**post-edit-ruff-format** (``ruff_post_edit``), default, ``post_tool_use`` on
a Python file tool write; the only §E.3-§E.5 hook with a working-tree side
effect, so its builtin alone holds the ``mutates_edited_file`` capability
(validate refuses it anywhere else). Per edited file:

- **M1** fixes only ``guard_config.ruff.safe_fix_select`` (``{I, UP}`` ∩ the
  project's selection, narrowed by this hook's ``safe_fix_allowlist``), never
  ``F401``/``F841``/``F811``: the agent adds an import in one Edit and its
  first use in the next. **M2** then formats, so the formatter has the last
  word. Both run over the file's bytes on stdin, and the result is written
  back only when it differs;
- **anti-churn**: it is written only when the file is new/untracked or its
  HEAD blob is format-clean (``ruff format --check`` on the HEAD text, cached
  in the state root by blob id, so once per blob, not per edit). The HEAD
  check runs only when M1/M2 changed the bytes: an edit they leave alone costs
  the one format call (review finding #5), and a cached "not clean" skips
  them. A legacy unformatted file is never reformatted, only reported;
- then bucket 1: what CI fails on, on the changed lines, at most
  ``max_project_lines``. It runs before the lint hooks (priority 50 < 60), so
  their D1 sees the mutated file.

**error-handling-lint-feedback**, **typing-lint-feedback**,
**pytest-conventions-feedback** (``ruff_lint_feedback``, one handler
parameterized by the linked rule's ``lint_codes`` that sync resolved into its
config): warn-only buckets 2-4 on the shared D1; pytest's opt-in
``ast_heuristics`` add the checks no ruff code covers. §F's post-edit
companions (the ``quality`` and ``docstrings`` buckets) run the same flow
through :func:`bucket_feedback`.

``on_error: open``: no pin, a changed ruff, a timeout or unreadable output
skips with one note per session (shared by every consumer); never blocks.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime._ruff import (
    RUFF_TIMEOUT_S,
    RuffFailure,
    fix_args,
    format_args,
    format_check_args,
    intersect_selectors,
    rewritten,
)
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.dispatch.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.handlers._ruff_buckets import event_lines
from coding_agent_playbook.hook_runtime.handlers._ruff_pipeline import (
    edited_python_files,
    enabled_consumers,
    file_codes,
    file_preview_codes,
    file_report,
    file_ruff_config,
    head_blob,
    ruff_runner,
    skip_note,
)
from coding_agent_playbook.hook_runtime.state.store import StateUnavailable

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime._ruff import RuffRunner
    from coding_agent_playbook.hook_runtime.config.guard_config import HookRecord
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.handlers._ruff_pipeline import (
        EditedFile,
        FileReport,
        HeadBlob,
    )
    from coding_agent_playbook.hook_runtime.state.store import StateStore

__all__ = [
    "CONFIG_SCHEMA",
    "DEFAULT_MAX_PROJECT_LINES",
    "LINT_CONFIG_SCHEMA",
    "bucket_feedback",
    "ruff_lint_feedback",
    "ruff_post_edit",
]

CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "safe_fix_allowlist": ConfigKey("list"),
    "max_project_lines": ConfigKey("integer"),
}
#: ``lint_codes`` is not a key: the linked rule is its one source (resolved at sync).
LINT_CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {"ast_heuristics": ConfigKey("boolean")}
DEFAULT_SAFE_FIX_ALLOWLIST: Final = ("I", "UP")
DEFAULT_MAX_PROJECT_LINES: Final = 5
#: The HEAD format-clean verdicts by blob id; the oldest go past this many.
FORMAT_CACHE: Final = "ruff/format-clean.json"
FORMAT_CACHE_KEEP: Final = 256


@register_hook_handler(
    "ruff_post_edit",
    events=["post_tool_use"],
    decisions=["context", "none"],
    config_schema=CONFIG_SCHEMA,
    mutates_edited_file=True,
)
def ruff_post_edit(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Format and safe-fix a clean edited Python file, then report what CI would fail on.

    Example::

        >>> ruff_post_edit(edit_of_app_py, ctx).context  # doctest: +SKIP
        ('ruff (CI fails on this): "src/app.py:3 F821 Undefined name `x`"',)
    """
    return _feedback(ev, ctx, rewrite=True, rule_id="ruff")


@register_hook_handler(
    "ruff_lint_feedback",
    events=["post_tool_use"],
    decisions=["context", "none"],
    config_schema=LINT_CONFIG_SCHEMA,
)
def ruff_lint_feedback(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Report the linked rule's codes on the lines this edit changed (warn only).

    Example::

        >>> ruff_lint_feedback(edit_adding_bare_except, ctx).context  # doctest: +SKIP
        ('rule python-error-handling (skill python-coding): "src/app.py:4 E722 Do not use bare `except`"',)
    """
    codes = ctx.config.get("lint_codes")
    rule = codes.get("rule") if isinstance(codes, Mapping) else None
    return _feedback(ev, ctx, rewrite=False, rule_id=rule if isinstance(rule, str) else "lint")


def bucket_feedback(
    ev: CanonicalEvent, ctx: HandlerContext, *, rule_id: str
) -> HandlerResult | None:
    """A report-only consumer's bucket of the shared D1 (the §F companions); never rewrites.

    Example::

        >>> bucket_feedback(edit_adding_load, ctx, rule_id="python-docstrings")  # doctest: +SKIP
        HandlerResult(decision=<Decision.CONTEXT: 'context'>, ...)
    """
    return _feedback(ev, ctx, rewrite=False, rule_id=rule_id)


def _feedback(
    ev: CanonicalEvent, ctx: HandlerContext, *, rewrite: bool, rule_id: str
) -> HandlerResult | None:
    """The shared flow: eligible files, the pin, the reports, then this hook's bucket."""
    files = edited_python_files(ev, ctx)
    if not files:
        return None  # a .md, a secret, a fixture, outside the repo: no ruff work at all
    runner = ruff_runner(ev, ctx)
    if isinstance(runner, str):
        return skip_note(ctx, runner)
    consumers = enabled_consumers(ev, ctx)
    try:
        reports = _reports(runner, ctx, files, consumers, rewrite=rewrite)
    except RuffFailure as failure:
        return skip_note(ctx, failure)
    lines = event_lines(ctx, consumers, reports).get(ctx.hook.id, [])
    if not lines:
        return None
    return HandlerResult(
        decision=Decision.CONTEXT, hook_id=ctx.hook.id, rule_id=rule_id, context=tuple(lines)
    )


def _reports(
    runner: RuffRunner,
    ctx: HandlerContext,
    files: list[EditedFile],
    consumers: Mapping[str, HookRecord],
    *,
    rewrite: bool,
) -> list[FileReport]:
    """One report per file, while a ruff call can still finish before the event deadline."""
    reports: list[FileReport] = []
    for edited in files:
        if ctx.deadline - ctx.clock.monotonic() < RUFF_TIMEOUT_S:
            break  # the watchdog would cut the call; the file's next edit is checked instead
        head = head_blob(ctx, edited)
        if rewrite:
            _rewrite(runner, ctx, edited, head)
        report = file_report(
            runner,
            ctx,
            edited,
            head,
            file_codes(consumers, edited),
            config=file_ruff_config(consumers, edited),
            preview=file_preview_codes(consumers, edited, runner.pin.drop),
        )
        if report is not None:
            reports.append(report)
    return reports


def _rewrite(
    runner: RuffRunner, ctx: HandlerContext, edited: EditedFile, head: HeadBlob | None
) -> None:
    """M1 then M2 over the file's bytes, written back when they changed and the file is eligible."""
    store = ctx.session.store
    verdict = True if head is None else _known_verdict(store, head.oid)
    before = None if verdict is False else _read_bytes(edited.path)
    if before is None:
        return  # a legacy file (cached), or an unreadable one: hands off
    after = _fixed_and_formatted(runner, ctx, edited, before)
    if after == before:
        return  # nothing to write, so HEAD's verdict cannot matter
    if verdict is None and head is not None and not _clean_at_head(runner, store, edited, head):
        return
    with suppress(OSError), open(edited.path, "wb") as handle:  # in place, as ruff writes
        handle.write(after)


def _fixed_and_formatted(
    runner: RuffRunner, ctx: HandlerContext, edited: EditedFile, text: bytes
) -> bytes:
    """M1 (when a safe-fix code is selected) then M2; a parse error is D1's to report."""
    table = ctx.cfg.tables.get("ruff")
    table = table if isinstance(table, Mapping) else {}
    allow = _strings(ctx.config.get("safe_fix_allowlist"), DEFAULT_SAFE_FIX_ALLOWLIST)
    select = intersect_selectors(allow, _strings(table.get("safe_fix_select"), ()))
    if select:
        ignore = _strings(table.get("safe_fix_ignore"), ())
        text = rewritten(runner.run(fix_args(edited.rel, select, ignore), stdin=text), text)
    return rewritten(runner.run(format_args(edited.rel), stdin=text), text)


def _read_bytes(path: str) -> bytes | None:
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return None


def _known_verdict(store: StateStore, oid: str) -> bool | None:
    """The cached HEAD format-clean verdict of blob ``oid``; ``None`` when not judged yet."""
    try:
        known = store.read_json(FORMAT_CACHE).get(oid)
    except StateUnavailable:
        return None
    return known if isinstance(known, bool) else None


def _clean_at_head(
    runner: RuffRunner, store: StateStore, edited: EditedFile, head: HeadBlob
) -> bool:
    """Judge the HEAD text with ``ruff format --check`` and remember it by blob id."""
    done = runner.run(format_check_args(edited.rel), stdin=head.data)
    clean = done.returncode == 0  # 1: would reformat; 2: HEAD does not parse. Either: hands off.
    _remember(store, head.oid, clean)
    return clean


def _remember(store: StateStore, oid: str, clean: bool) -> None:
    def put(document: dict[str, object]) -> None:
        document.pop(oid, None)
        document[oid] = clean
        for stale in list(document)[:-FORMAT_CACHE_KEEP]:
            del document[stale]

    try:
        store.update_json(FORMAT_CACHE, put)
    except StateUnavailable:
        return


def _strings(value: object, default: tuple[str, ...]) -> list[str]:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    return list(default)
