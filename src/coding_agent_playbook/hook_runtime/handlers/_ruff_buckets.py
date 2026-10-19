"""§E.3 step 7: partition one event's D1 findings into the consumers' buckets, dedupe, cap (specs/prK-hook-pack.md §E.3).

Computed once per event (the event memo) by whichever ruff consumer asks
first, after post-edit-ruff-format's M1/M2 (it runs first: lower priority);
each consumer then emits its own bucket's lines as its ``context``:

- **partition** (:data:`BUCKETS`, first enabled row claiming a finding wins):
  bucket 1 is what CI fails on (a parse error, a code D1 did not add, or an
  added code the project itself selects); then one row per rule-linked hook,
  each with its own codes, paths and extra filters. A rule row's prefix is
  ``rule <id> (skill <skill>):``, naming the skill that holds the fix (D16).
  A bucket-1 finding that an enabled rule row would also claim gets
  `` (rule <id>, skill <skill>)`` appended, so the model learns both "CI
  fails" and "why". Sync puts the skill in ``lint_codes["skill"]``; without
  it (an always rule, or a config rendered before SPEC v0.21) the old
  ``rule <id>:`` and `` (rule <id>)`` spellings stay. With
  post-edit-ruff-format off, project-selected codes no rule claims are dropped;
- **dedupe**: a line already shown this session is not repeated; the key is
  ``sha256(rel, code, stripped source line)`` (line numbers shift between
  edits, the text does not), ``(rel, code)`` for once-per-file heuristics;
- **caps**: bucket 1 at most ``max_project_lines`` (5), any other bucket at
  most 5 (the per-hook context cap), 8 lines per event; bucket 1 first, then
  by file and line. The cap stops before a key is burned.

Rule rows' extra filters: ``S101`` is pytest's idiom under ``tests/``;
typing skips ``tests/`` and stubs, reports ``ANN001``/``ANN201`` on public
defs only, leaves every ``ANN*`` to a Stop ``typecheck`` stage when one is on,
and leaves ``UP007``/``UP045`` to M1 when the safe fixes cover them. An
``ANN401`` line carries the rule's "Any is a last resort" note.

§F's companions add two rows (§F.2.2, §F.3.2): ``quality:`` (C901 and the
PLR budget codes, opt-in) and ``rule python-docstrings (skill python-coding):``
(D100-D107, never under ``tests/``). Both report on def lines, so the
changed-lines filter already keeps them to defs that are new or whose
signature line changed.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime._ruff import selector_matches
from coding_agent_playbook.hook_runtime.dispatch.caps import OutputCaps, quote_data
from coding_agent_playbook.hook_runtime.dispatch.event import EventName
from coding_agent_playbook.hook_runtime.handlers._ruff_pipeline import (
    POST_EDIT_HOOK_ID,
    accepts_file,
    file_codes,
    lint_codes_of,
)

if TYPE_CHECKING:
    import ast  # the Python-edit branch imports it, inside _lint_ast (§D.1)
    from collections.abc import Callable, Sequence

    from coding_agent_playbook.hook_runtime._ruff import RuffDiagnostic
    from coding_agent_playbook.hook_runtime.config.guard_config import HookRecord
    from coding_agent_playbook.hook_runtime.handlers._ruff_pipeline import FileReport
    from coding_agent_playbook.hook_runtime.registry import HandlerContext

__all__ = [
    "BUCKETS",
    "DOCSTRINGS_HOOK_ID",
    "ERROR_HANDLING_HOOK_ID",
    "MAX_EVENT_LINES",
    "PYTEST_HOOK_ID",
    "QUALITY_HOOK_ID",
    "TYPING_HOOK_ID",
    "BucketRow",
    "Finding",
    "Judge",
    "event_lines",
    "partition",
    "rule_label",
    "rule_suffix",
]

ERROR_HANDLING_HOOK_ID: Final = "error-handling-lint-feedback"
TYPING_HOOK_ID: Final = "typing-lint-feedback"
PYTEST_HOOK_ID: Final = "pytest-conventions-feedback"
QUALITY_HOOK_ID: Final = "clean-code-metrics-nonregression"
DOCSTRINGS_HOOK_ID: Final = "docstring-nonregression"
#: §E.3: at most 8 lines per event, at most 5 from bucket 1 (post-edit's ``max_project_lines``).
MAX_EVENT_LINES: Final = OutputCaps.CONTEXT_ITEMS_PER_EVENT
DEFAULT_PROJECT_LINES: Final = 5
#: ``combine`` keeps at most this many items per hook: a longer bucket would burn keys unseen.
_MAX_ROW_LINES: Final = OutputCaps.CONTEXT_ITEMS_PER_HOOK
_CI_PREFIX: Final = "ruff (CI fails on this):"
_LINE_CHARS: Final = 240
_PUBLIC_ONLY: Final = frozenset({"ANN001", "ANN201"})
_FIXED_BY_M1: Final = frozenset({"UP007", "UP045"})
#: Heuristics reported once per file per session, whatever line they land on.
_ONCE_PER_FILE: Final = frozenset({"pytest-loop-assert"})
#: What the rule adds to ruff's own message (typing.md.j2's "when to use Any").
_MESSAGE_NOTES: Final = {
    "ANN401": "Any is a last resort: narrow it, or justify a `# type: ignore[code]`",
}


@dataclass(frozen=True, slots=True)
class Finding:
    """One diagnostic of one file, with ``U`` of that file (what D1 added to the project's)."""

    report: FileReport
    diagnostic: RuffDiagnostic
    extended: frozenset[str] = frozenset()

    @property
    def rel(self) -> str:
        """The file's repo-relative POSIX name."""
        return self.report.edited.rel


@dataclass(frozen=True)
class Judge:
    """The event-level facts the rows judge a finding by, read once per event.

    ``codes``/``files``/``rules``/``skills`` are per enabled consumer: its lint
    codes, the files its paths take, its linked rule id, that rule's owning
    skill (absent when sync named none). ``public_lines`` maps a report to its
    public signature lines (one ``ast.parse``, memoized by the caller).
    """

    codes: Mapping[str, frozenset[str]] = field(default_factory=dict)
    files: Mapping[str, frozenset[str]] = field(default_factory=dict)
    rules: Mapping[str, str] = field(default_factory=dict)
    skills: Mapping[str, str] = field(default_factory=dict)
    project_select: tuple[str, ...] = ()
    project_ignore: tuple[str, ...] = ()
    safe_fix_select: tuple[str, ...] = ()
    typecheck_at_stop: bool = False
    public_lines: Callable[[FileReport], frozenset[int]] = lambda _report: frozenset()

    def owns(self, hook_id: str, finding: Finding) -> bool:
        """Whether ``hook_id`` lists the finding's code and its paths take the finding's file."""
        code = finding.diagnostic.code or ""
        return code in self.codes.get(hook_id, ()) and finding.rel in self.files.get(hook_id, ())

    def project_selects(self, code: str) -> bool:
        """Whether the project's explicit ``select`` takes ``code`` and its ``ignore`` does not.

        Prefix-aware. With ruff's implicit default selection (no ``select``)
        nothing counts: the default changed across ruff versions.
        """
        chosen = any(selector_matches(s, code) for s in self.project_select)
        return chosen and not any(selector_matches(i, code) for i in self.project_ignore)

    def safe_fixes(self, code: str) -> bool:
        """Whether M1's safe-fix selection covers ``code``."""
        return any(selector_matches(s, code) for s in self.safe_fix_select)


@dataclass(frozen=True, slots=True)
class BucketRow:
    """One §E.3 bucket: the hook that reports it, its linked rule (``""``: CI's), its claim.

    ``label`` names a row with no linked rule (``quality``): its line prefix is
    ``<label>:`` instead of ``rule <id> (skill <skill>):``.
    """

    hook_id: str
    rule: str
    claims: Callable[[Finding, Judge], bool]
    label: str = ""


def _ci_fails(finding: Finding, judge: Judge) -> bool:
    diagnostic = finding.diagnostic
    if diagnostic.is_syntax_error or diagnostic.code not in finding.extended:
        return True  # D1 adds only U to the project's own selection: any other code is CI's
    return judge.project_selects(diagnostic.code or "")


def _in_tests(rel: str) -> bool:
    return rel.startswith("tests/")


def _error_handling(finding: Finding, judge: Judge) -> bool:
    if finding.diagnostic.code == "S101" and _in_tests(finding.rel):
        return False  # assert is the pytest idiom
    return judge.owns(ERROR_HANDLING_HOOK_ID, finding)


def _type_hints(finding: Finding, judge: Judge) -> bool:
    code, rel = finding.diagnostic.code or "", finding.rel
    if not judge.owns(TYPING_HOOK_ID, finding) or _in_tests(rel) or rel.endswith(".pyi"):
        return False
    if code.startswith("ANN") and judge.typecheck_at_stop:
        return False  # the type checker covers annotations at Stop
    if code in _FIXED_BY_M1 and judge.safe_fixes(code):
        return False  # M1 fixes it on a clean file; one still there is CI's (bucket 1)
    return code not in _PUBLIC_ONLY or finding.diagnostic.row in judge.public_lines(finding.report)


def _pytest(finding: Finding, judge: Judge) -> bool:
    return judge.owns(PYTEST_HOOK_ID, finding)


def _quality(finding: Finding, judge: Judge) -> bool:
    return judge.owns(QUALITY_HOOK_ID, finding)


def _docstrings(finding: Finding, judge: Judge) -> bool:
    return judge.owns(DOCSTRINGS_HOOK_ID, finding) and not _in_tests(finding.rel)


#: First match wins.
BUCKETS: Final[tuple[BucketRow, ...]] = (
    BucketRow(POST_EDIT_HOOK_ID, "", _ci_fails),
    BucketRow(ERROR_HANDLING_HOOK_ID, "python-error-handling", _error_handling),
    BucketRow(TYPING_HOOK_ID, "python-typing", _type_hints),
    BucketRow(PYTEST_HOOK_ID, "pytest", _pytest),
    BucketRow(QUALITY_HOOK_ID, "quality", _quality, label="quality"),
    BucketRow(DOCSTRINGS_HOOK_ID, "python-docstrings", _docstrings),
)


def partition(
    findings: Sequence[Finding],
    *,
    rows: Sequence[BucketRow],
    judge: Judge,
    once: Callable[[str], bool],
    project_cap: int = DEFAULT_PROJECT_LINES,
    assigned: Mapping[str, Sequence[Finding]] | None = None,
) -> dict[str, list[str]]:
    """Each enabled row's lines (``rows``, in :data:`BUCKETS` order), deduped and capped.

    ``assigned`` are findings already owned by one hook (the pytest heuristics,
    which no ruff code names). ``once(key)`` is ``SessionState.once``.

    Example::

        >>> partition([], rows=BUCKETS, judge=Judge(), once=lambda key: True)[POST_EDIT_HOOK_ID]
        []
    """
    placed = [p for f in findings if (p := _place(f, rows, judge)) is not None]
    for hook_id, owned in (assigned or {}).items():
        index = next((i for i, row in enumerate(rows) if row.hook_id == hook_id), None)
        placed.extend((index, f, "") for f in owned if index is not None)
    placed.sort(key=lambda p: (rows[p[0]].rule != "", p[1].rel, p[1].diagnostic.row, p[0]))
    lines: dict[str, list[str]] = {row.hook_id: [] for row in rows}
    shown = 0
    for index, finding, suffix in placed:
        if shown == MAX_EVENT_LINES:
            break
        row = rows[index]
        cap = project_cap if row.rule == "" else _MAX_ROW_LINES
        if len(lines[row.hook_id]) >= cap or not once(_dedupe_key(finding)):
            continue  # a capped line is skipped before its key is marked
        lines[row.hook_id].append(f"{_prefix(row, judge)} {_shown(finding)}{suffix}")
        shown += 1
    return lines


def _place(
    finding: Finding, rows: Sequence[BucketRow], judge: Judge
) -> tuple[int, Finding, str] | None:
    """``(row index, finding, rule suffix)`` of the first row claiming ``finding``."""
    claimed = [i for i, row in enumerate(rows) if row.claims(finding, judge)]
    if not claimed:
        return None
    first = claimed[0]
    if rows[first].rule != "":
        return first, finding, ""
    also = next((rows[i] for i in claimed[1:] if rows[i].rule != ""), None)
    return first, finding, "" if also is None else _suffix(also, judge)


def rule_label(rule_id: str, skill_id: str) -> str:
    """``rule <id> (skill <skill>)``, or ``rule <id>`` when no skill is known (D16).

    Example: ``rule_label("pytest", "python-testing")`` -> ``"rule pytest (skill python-testing)"``.
    """
    return f"rule {rule_id} (skill {skill_id})" if skill_id else f"rule {rule_id}"


def rule_suffix(rule_id: str, skill_id: str) -> str:
    """The bucket-1 tail naming the rule that also claims a CI finding (no nested parentheses).

    Example: ``rule_suffix("python-typing", "python-coding")`` ->
    ``" (rule python-typing, skill python-coding)"``.
    """
    return f" (rule {rule_id}, skill {skill_id})" if skill_id else f" (rule {rule_id})"


def _rule_id(row: BucketRow, judge: Judge) -> str:
    """The linked rule sync named in the hook's ``lint_codes``, else the row's default."""
    return judge.rules.get(row.hook_id, row.rule)


def _skill_id(row: BucketRow, judge: Judge) -> str:
    """The linked rule's skill sync named in the hook's ``lint_codes``, ``""`` when none."""
    return judge.skills.get(row.hook_id, "")


def _suffix(row: BucketRow, judge: Judge) -> str:
    """``rule_suffix`` of ``row``'s rule, or `` (<label>)`` when it has no linked rule."""
    return (
        f" ({row.label})" if row.label else rule_suffix(_rule_id(row, judge), _skill_id(row, judge))
    )


def _prefix(row: BucketRow, judge: Judge) -> str:
    if row.rule == "":
        return _CI_PREFIX
    return f"{row.label or rule_label(_rule_id(row, judge), _skill_id(row, judge))}:"


def _dedupe_key(finding: Finding) -> str:
    label = finding.diagnostic.label
    text = "" if label in _ONCE_PER_FILE else finding.report.line_text(finding.diagnostic.row)
    digest = hashlib.sha256("\0".join((finding.rel, label, text)).encode("utf-8", "surrogatepass"))
    return f"ruff:{digest.hexdigest()[:16]}"


def _shown(finding: Finding) -> str:
    d = finding.diagnostic
    note = _MESSAGE_NOTES.get(d.label)
    message = f"{d.message}; {note}" if note else d.message
    return quote_data(f"{finding.rel}:{d.row} {d.label} {message}", _LINE_CHARS)


# --- the event's partition, shared by every consumer ---------------------------------------------


def event_lines(
    ctx: HandlerContext, consumers: Mapping[str, HookRecord], reports: Sequence[FileReport]
) -> Mapping[str, list[str]]:
    """Every consumer's lines for this event, partitioned once (keyed by the files' contents).

    Example::

        >>> event_lines(ctx, consumers, reports).get(ctx.hook.id, [])  # doctest: +SKIP
        ['rule python-error-handling (skill python-coding): "src/app.py:4 E722 Do not use bare `except`"']
    """
    key = ("ruff-partition", tuple(sorted((r.edited.rel, r.sha) for r in reports)))
    lines: Mapping[str, list[str]] = ctx.memo.get_or_compute(
        key, lambda: _partition_event(ctx, consumers, reports)
    )
    return lines


def _partition_event(
    ctx: HandlerContext, consumers: Mapping[str, HookRecord], reports: Sequence[FileReport]
) -> dict[str, list[str]]:
    judge = _judge(ctx, consumers, reports)
    rows = [row for row in BUCKETS if row.hook_id in consumers]
    findings = [
        Finding(report, diagnostic, file_codes(consumers, report.edited))
        for report in reports
        for diagnostic in report.diagnostics
    ]
    return partition(
        findings,
        rows=rows,
        judge=judge,
        once=ctx.session.once,
        project_cap=_project_cap(consumers.get(POST_EDIT_HOOK_ID)),
        assigned={PYTEST_HOOK_ID: _heuristics(ctx, consumers.get(PYTEST_HOOK_ID), reports)},
    )


def _judge(
    ctx: HandlerContext, consumers: Mapping[str, HookRecord], reports: Sequence[FileReport]
) -> Judge:
    ruff = _table(ctx.cfg.tables.get("ruff"))
    return Judge(
        codes={hook_id: lint_codes_of(record) for hook_id, record in consumers.items()},
        files={
            hook_id: frozenset(r.edited.rel for r in reports if accepts_file(record, r.edited))
            for hook_id, record in consumers.items()
        },
        rules={hook_id: rule for hook_id, r in consumers.items() if (rule := _rule_of(r))},
        skills={hook_id: s for hook_id, r in consumers.items() if (s := _skill_of(r))},
        project_select=_strings(ruff.get("project_select")),
        project_ignore=_strings(ruff.get("project_ignore")),
        safe_fix_select=_strings(ruff.get("safe_fix_select")),
        typecheck_at_stop=_typecheck_at_stop(ctx),
        public_lines=lambda report: _public_lines(ctx, report),
    )


def _public_lines(ctx: HandlerContext, report: FileReport) -> frozenset[int]:
    from coding_agent_playbook.hook_runtime.handlers._lint_ast import public_def_lines

    tree = _tree(ctx, report)
    return frozenset() if tree is None else public_def_lines(tree)


def _tree(ctx: HandlerContext, report: FileReport) -> ast.Module | None:
    """The report's module (``None`` unparsable), parsed once per event and content."""
    from coding_agent_playbook.hook_runtime.handlers._lint_ast import parse_module

    key = ("ruff-ast", report.edited.path, report.sha)
    tree: ast.Module | None = ctx.memo.get_or_compute(key, lambda: parse_module(report.text))
    return tree


def _heuristics(
    ctx: HandlerContext, record: HookRecord | None, reports: Sequence[FileReport]
) -> list[Finding]:
    """pytest-conventions-feedback's opt-in AST findings on the changed lines of its files."""
    spec = None if record is None else record.handlers.get(EventName.POST_TOOL_USE)
    if record is None or spec is None or spec.config.get("ast_heuristics") is not True:
        return []
    from coding_agent_playbook.hook_runtime.handlers._lint_ast import pytest_ast_heuristics

    found: list[Finding] = []
    for report in reports:
        tree = _tree(ctx, report) if accepts_file(record, report.edited) else None
        if tree is None:
            continue
        marks = spec.config.get("asyncio_marks") is True
        hits = pytest_ast_heuristics(tree, created_this_session=report.is_new, asyncio_marks=marks)
        found.extend(Finding(report, hit) for hit in hits if hit.row in report.changed)
    return found


def _rule_of(record: HookRecord) -> str:
    return _lint_codes_string(record, "rule")


def _skill_of(record: HookRecord) -> str:
    """The skill sync named in ``lint_codes``; ``""`` for a stale config (fail-open)."""
    return _lint_codes_string(record, "skill")


def _lint_codes_string(record: HookRecord, key: str) -> str:
    """``config["lint_codes"][key]`` of the post-edit handler, ``""`` when absent or not a string."""
    spec = record.handlers.get(EventName.POST_TOOL_USE)
    codes = None if spec is None else spec.config.get("lint_codes")
    value = codes.get(key) if isinstance(codes, Mapping) else None
    return value if isinstance(value, str) else ""


def _project_cap(record: HookRecord | None) -> int:
    spec = None if record is None else record.handlers.get(EventName.POST_TOOL_USE)
    cap = None if spec is None else spec.config.get("max_project_lines")
    return cap if type(cap) is int and cap >= 0 else DEFAULT_PROJECT_LINES


def _typecheck_at_stop(ctx: HandlerContext) -> bool:
    """Whether the Stop coordinator runs a ``typecheck`` stage (it then covers ``ANN*``)."""
    stages = _table(ctx.cfg.tables.get("stop_gate")).get("stages")
    rows = stages if isinstance(stages, list) else []
    return any(isinstance(row, Mapping) and row.get("name") == "typecheck" for row in rows)


def _table(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(item for item in value if isinstance(item, str))
    return ()
