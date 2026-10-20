"""Lint feedback names the skill that holds the fix (specs/prS-skills-context.md §8.3, D16).

``rule_label`` is a rule row's line prefix (without the colon) and
``rule_suffix`` the bucket-1 tail naming the rule that also claims a CI
finding. Both keep the pre-v0.21 spelling when no skill is known, which is
what a ``guard_config.json`` rendered before the skill key existed yields;
the ``partition`` tests check both spellings through the bucket seam.
"""

from __future__ import annotations

from typing import Any, Final

import pytest

from coding_agent_playbook.hook_runtime.config.hook_records import HandlerSpec, HookRecord
from coding_agent_playbook.hook_runtime.dispatch.event import EventName
from coding_agent_playbook.hook_runtime.handlers._shared.ruff_pipeline import (
    POST_EDIT_HOOK_ID,
    EditedFile,
    FileReport,
)
from coding_agent_playbook.hook_runtime.handlers.feedback._ruff_buckets import (
    BUCKETS,
    ERROR_HANDLING_HOOK_ID,
    Finding,
    Judge,
    _rule_of,
    _skill_of,
    partition,
    rule_label,
    rule_suffix,
)
from coding_agent_playbook.hook_runtime.ruff import RuffDiagnostic

APP: Final = "src/app.py"
_BARE: Final = RuffDiagnostic("E722", 1, "Do not use bare `except`")
_REPORT: Final = FileReport(EditedFile(f"/repo/{APP}", APP, APP), (_BARE,), ("except:",))
_ROWS: Final = [
    row for row in BUCKETS if row.hook_id in {POST_EDIT_HOOK_ID, ERROR_HANDLING_HOOK_ID}
]


def _judge(*, skills: dict[str, str], project_select: tuple[str, ...] = ()) -> Judge:
    """error-handling-lint-feedback owns E722 on ``APP``; ``skills`` is what sync named."""
    return Judge(
        codes={ERROR_HANDLING_HOOK_ID: frozenset({"E722"})},
        files={ERROR_HANDLING_HOOK_ID: frozenset({APP})},
        rules={ERROR_HANDLING_HOOK_ID: "python-error-handling"},
        skills=skills,
        project_select=project_select,
    )


def _lines(judge: Judge) -> dict[str, list[str]]:
    finding = Finding(_REPORT, _BARE, frozenset({"E722"}))
    return partition([finding], rows=_ROWS, judge=judge, once=lambda _key: True)


def test_rule_label_names_the_skill() -> None:
    assert rule_label("pytest", "python-testing") == "rule pytest (skill python-testing)"


def test_rule_label_without_skill_keeps_the_old_prefix() -> None:
    """Regression: a stale config (no ``skill`` key) must not break or change the line."""
    assert rule_label("python-error-handling", "") == "rule python-error-handling"


def test_rule_suffix_names_rule_and_skill_without_nesting() -> None:
    assert (
        rule_suffix("python-typing", "python-coding")
        == " (rule python-typing, skill python-coding)"
    )
    assert rule_suffix("python-typing", "") == " (rule python-typing)"


def test_partition_prefix_names_the_skill_sync_named() -> None:
    lines = _lines(_judge(skills={ERROR_HANDLING_HOOK_ID: "python-coding"}))

    assert lines[ERROR_HANDLING_HOOK_ID] == [
        'rule python-error-handling (skill python-coding): "src/app.py:1 E722 Do not use bare '
        '`except`"'
    ]


def test_partition_with_a_stale_config_keeps_the_old_prefix_and_suffix() -> None:
    """Regression: a guard_config.json rendered before the ``skill`` key still yields lines."""
    rule_row = _lines(_judge(skills={}))
    ci_row = _lines(_judge(skills={}, project_select=("E",)))

    assert rule_row[ERROR_HANDLING_HOOK_ID] == [
        'rule python-error-handling: "src/app.py:1 E722 Do not use bare `except`"'
    ]
    assert ci_row[POST_EDIT_HOOK_ID] == [
        'ruff (CI fails on this): "src/app.py:1 E722 Do not use bare `except`" '
        "(rule python-error-handling)"
    ]


def _record(lint_codes: object) -> HookRecord:
    """error-handling-lint-feedback as guard_config.json carries it, with ``lint_codes`` as given."""
    spec = HandlerSpec(kind="builtin", name="ruff_lint_feedback", config={"lint_codes": lint_codes})
    return HookRecord(
        id=ERROR_HANDLING_HOOK_ID,
        source_package="core",
        events=(EventName.POST_TOOL_USE,),
        priority=50,
        matcher={},
        handlers={EventName.POST_TOOL_USE: spec},
        decisions=frozenset(),
        timeout_ms=1000,
        on_error={},
        supports=frozenset(),
        mandatory=False,
        script_sha256=None,
        raw={},
    )


_STALE: Final[dict[str, Any]] = {"rule": "python-error-handling", "warn": ["E722"]}


@pytest.mark.parametrize(
    "lint_codes",
    [
        pytest.param(_STALE, id="pre-v0.21 record without skill"),
        pytest.param({**_STALE, "skill": 5}, id="non-string skill"),
        pytest.param({**_STALE, "skill": None}, id="null skill"),
    ],
)
def test_stale_record_reads_no_skill_and_keeps_the_old_prefix(lint_codes: object) -> None:
    """Regression (§8.3 fail-open): a record without a usable ``skill`` reads ``""``, never raises."""
    record = _record(lint_codes)
    skills = {ERROR_HANDLING_HOOK_ID: s} if (s := _skill_of(record)) else {}

    assert _rule_of(record) == "python-error-handling"
    assert _skill_of(record) == ""
    assert _lines(_judge(skills=skills))[ERROR_HANDLING_HOOK_ID] == [
        'rule python-error-handling: "src/app.py:1 E722 Do not use bare `except`"'
    ]


@pytest.mark.parametrize("lint_codes", [None, ["E722"], "python-error-handling"])
def test_record_with_malformed_lint_codes_reads_empty_rule_and_skill(lint_codes: object) -> None:
    record = _record(lint_codes)

    assert (_rule_of(record), _skill_of(record)) == ("", "")


def test_current_record_reads_the_skill_sync_named() -> None:
    record = _record({**_STALE, "skill": "python-coding"})

    assert (_rule_of(record), _skill_of(record)) == ("python-error-handling", "python-coding")
