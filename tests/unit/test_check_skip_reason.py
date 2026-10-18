"""``playbook check`` skip reasons quote value-carrying ``applies_if`` gates as written.

Regression for PR #66 review: a ``package_manager`` gate fell through to the
boolean-fact branch, printing ``package_manager=False`` (no manager detected)
or the detected name (``package_manager=pip``) instead of the gate itself.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.commands.check import _format_skip_reason


@pytest.mark.parametrize(
    ("gate", "facts", "expected"),
    [
        ("uv", {}, "(skipped: applies_if package_manager='uv')"),
        (
            ["uv", "poetry"],
            {"package_manager": "pip"},
            "(skipped: applies_if package_manager=['uv', 'poetry'])",
        ),
    ],
    ids=["absent-fact", "mismatching-fact"],
)
def test_skip_reason_quotes_package_manager_gate(
    gate: object, facts: dict[str, object], expected: str
) -> None:
    assert _format_skip_reason({"package_manager": gate}, facts) == expected


def test_skip_reason_quotes_python_version_gate() -> None:
    reason = _format_skip_reason({"python_version": ">=3.11"}, {"python_version": "3.10"})
    assert reason == "(skipped: applies_if python_version='>=3.11')"


def test_skip_reason_reports_boolean_fact_value() -> None:
    assert _format_skip_reason({"has_notebooks": True}, {}) == "(skipped: has_notebooks=False)"
