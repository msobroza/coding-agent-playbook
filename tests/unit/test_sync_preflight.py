"""Unit tests for the pre-render environment checks (``commands/_sync_preflight.py``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.commands._sync_preflight import (
    missing_adapters,
    missing_overlays,
    report_missing_overlays,
    warn_missing_adapters,
)

if TYPE_CHECKING:
    import pytest


def test_missing_overlays_lists_unimportable_names_in_order() -> None:
    names = ["json", "no_such_overlay_b", "coding_agent_playbook", "no_such_overlay_a"]
    assert missing_overlays(names) == ["no_such_overlay_b", "no_such_overlay_a"]


def test_missing_overlays_treats_invalid_names_as_missing() -> None:
    """A hyphenated distribution name or a dotted path under a missing parent
    is not importable — it must not crash ``find_spec``."""
    assert missing_overlays(["playbook-rules-bnp", "no_such_parent.child", ""]) == [
        "playbook-rules-bnp",
        "no_such_parent.child",
        "",
    ]


def test_missing_adapters_is_sorted_set_difference() -> None:
    assert missing_adapters(["z", "continue", "a", "a"], ["continue", "agents_md"]) == ["a", "z"]
    assert missing_adapters([], ["continue"]) == []


def test_report_missing_overlays_names_package_and_fix(capsys: pytest.CaptureFixture[str]) -> None:
    report_missing_overlays(["org_overlay"])
    err = capsys.readouterr().err
    assert err.startswith("error: ")
    assert "org_overlay" in err
    assert "additional_dependencies" in err
    assert "language: system" in err


def test_warn_missing_adapters_names_adapter(capsys: pytest.CaptureFixture[str]) -> None:
    warn_missing_adapters(["codex"])
    err = capsys.readouterr().err
    assert err.startswith("warning: ")
    assert "codex" in err
