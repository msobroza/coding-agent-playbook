"""post-edit-ruff-format: format clean files, safe fixes only, CI-relevant lint fed back (specs/prK-hook-pack.md §E.3).

Default, ``post_tool_use`` on a Python file tool write; the only §E.3-§E.5
hook with a working-tree side effect, so its builtin alone holds the
``mutates_edited_file`` capability (validate refuses it anywhere else). On
the shared pipeline (``_ruff_pipeline``), per edited file:

- **anti-churn**: the file is rewritten only when it is new/untracked or its
  HEAD blob is format-clean (``ruff format --check`` on the HEAD text, cached
  in the state root by blob id, so once per blob, not per edit). A legacy
  unformatted file is never reformatted, only reported;
- **M1** fixes only ``guard_config.ruff.safe_fix_select`` (``{I, UP}`` ∩ the
  project's selection, narrowed by this hook's ``safe_fix_allowlist``), never
  ``F401``/``F841``/``F811``: the agent adds an import in one Edit and its
  first use in the next. **M2** then formats, so the formatter has the last word;
- **D1** once, then the diagnostics on the changed lines that CI fails on
  (the project's own selection, and parse errors) as ``context``, at most
  ``max_project_lines`` per event, each once per session. Silent on success.

``on_error: open``: no pin, a changed ruff, a timeout or unreadable output
skips with one note per session; it never blocks.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime._ruff import (
    RUFF_TIMEOUT_S,
    RuffFailure,
    fix_args,
    format_args,
    format_check_args,
    intersect_selectors,
)
from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.handlers._ruff_pipeline import (
    BUCKETS,
    POST_EDIT_HOOK_ID,
    bucket_lines,
    edited_python_files,
    enabled_consumers,
    extended_codes,
    file_report,
    head_blob,
    ruff_runner,
    skip_note,
)
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.state import StateUnavailable

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime._ruff import RuffRunner
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.handlers._ruff_pipeline import (
        EditedFile,
        FileReport,
        HeadBlob,
    )
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.state import StateStore

__all__ = ["CONFIG_SCHEMA", "DEFAULT_MAX_PROJECT_LINES", "ruff_post_edit"]

CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "safe_fix_allowlist": ConfigKey("list"),
    "max_project_lines": ConfigKey("integer"),
}
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
    files = edited_python_files(ev, ctx)
    if not files:
        return None  # a .md, a secret, a fixture, outside the repo: no ruff work at all
    runner = ruff_runner(ev, ctx)
    if isinstance(runner, str):
        return skip_note(ctx, runner)
    consumers = enabled_consumers(ev, ctx.cfg)
    codes = extended_codes(consumers)
    try:
        reports = _reports(runner, ctx, files, codes)
    except RuffFailure as failure:
        return skip_note(ctx, failure)
    lines = _lines(ctx, reports, frozenset(consumers), codes)
    if not lines:
        return None
    return HandlerResult(
        decision=Decision.CONTEXT, hook_id=ctx.hook.id, rule_id="ruff", context=tuple(lines)
    )


def _reports(
    runner: RuffRunner, ctx: HandlerContext, files: list[EditedFile], codes: frozenset[str]
) -> list[FileReport]:
    """One report per file, while a ruff call can still finish before the event deadline."""
    reports: list[FileReport] = []
    for edited in files:
        if ctx.deadline - ctx.clock.monotonic() < RUFF_TIMEOUT_S:
            break  # the watchdog would cut the call; the file's next edit is checked instead
        report = _report(runner, ctx, edited, codes)
        if report is not None:
            reports.append(report)
    return reports


def _report(
    runner: RuffRunner, ctx: HandlerContext, edited: EditedFile, codes: frozenset[str]
) -> FileReport | None:
    head = head_blob(ctx, edited)
    if head is None or _clean_at_head(runner, ctx.session.store, edited, head):
        _rewrite(runner, ctx, edited)
    return file_report(runner, ctx, edited, head, codes)


def _rewrite(runner: RuffRunner, ctx: HandlerContext, edited: EditedFile) -> None:
    """M1 then M2; their exit codes are not verdicts (a parse error is D1's to report)."""
    table = ctx.cfg.tables.get("ruff")
    table = table if isinstance(table, Mapping) else {}
    allow = _strings(ctx.config.get("safe_fix_allowlist"), DEFAULT_SAFE_FIX_ALLOWLIST)
    select = intersect_selectors(allow, _strings(table.get("safe_fix_select"), ()))
    if select:
        runner.run(fix_args(edited.path, select, _strings(table.get("safe_fix_ignore"), ())))
    runner.run(format_args(edited.path))


def _clean_at_head(
    runner: RuffRunner, store: StateStore, edited: EditedFile, head: HeadBlob
) -> bool:
    """Whether the HEAD text is format-clean: once per blob id, then from the state root."""
    try:
        known = store.read_json(FORMAT_CACHE).get(head.oid)
    except StateUnavailable:
        known = None
    if isinstance(known, bool):
        return known
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


def _lines(
    ctx: HandlerContext,
    reports: list[FileReport],
    enabled: frozenset[str],
    codes: frozenset[str],
) -> list[str]:
    cap = ctx.config.get("max_project_lines", DEFAULT_MAX_PROJECT_LINES)
    cap = cap if type(cap) is int and cap >= 0 else DEFAULT_MAX_PROJECT_LINES
    row = BUCKETS[0]  # this hook's own bucket: the project's CI selection and parse errors
    on = enabled | {POST_EDIT_HOOK_ID}
    return bucket_lines(ctx, reports, row, enabled=on, extended=codes, cap=cap)


def _strings(value: object, default: tuple[str, ...]) -> list[str]:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    return list(default)
