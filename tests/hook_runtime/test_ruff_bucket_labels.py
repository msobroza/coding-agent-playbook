"""Lint feedback names the skill that holds the fix (specs/prS-skills-context.md §8.3, D16).

``rule_label`` is a rule row's line prefix (without the colon) and
``rule_suffix`` the bucket-1 tail naming the rule that also claims a CI
finding. Both keep the pre-v0.21 spelling when no skill is known, which is
what a ``guard_config.json`` rendered before the skill key existed yields;
the ``partition`` tests check both spellings through the bucket seam.
"""

from __future__ import annotations

from typing import Final

from coding_agent_playbook.hook_runtime._ruff import RuffDiagnostic
from coding_agent_playbook.hook_runtime.handlers._ruff_buckets import (
    BUCKETS,
    ERROR_HANDLING_HOOK_ID,
    Finding,
    Judge,
    partition,
    rule_label,
    rule_suffix,
)
from coding_agent_playbook.hook_runtime.handlers._ruff_pipeline import (
    POST_EDIT_HOOK_ID,
    EditedFile,
    FileReport,
)

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
