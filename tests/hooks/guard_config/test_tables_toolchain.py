"""The sync-derived hook config of toolchain-missing-hint and pytest-conventions-feedback (specs/prK-hook-pack.md §E.3).

Pure functions of ``(package_manager, pyproject)`` and the detector facts, so
these tests need no repository; ``compile_guard_config`` reads the pyproject
(``test_compile`` pins the read and its default for a malformed file).
"""

from __future__ import annotations

from typing import Any

import pytest

from coding_agent_playbook.hooks.guard_config._tables_toolchain import (
    ToolchainInputs,
    asyncio_marks_required,
    derived_hook_config,
    install_hint,
    with_derived_config,
)

_EXTRA: dict[str, Any] = {"project": {"optional-dependencies": {"dev": ["ruff"]}}}
_GROUP: dict[str, Any] = {"dependency-groups": {"dev": ["ruff"]}}
_TEST_ONLY: dict[str, Any] = {"project": {"optional-dependencies": {"test": ["pytest"]}}}


@pytest.mark.parametrize(
    ("manager", "pyproject", "hint"),
    [
        ("uv", _EXTRA, "uv sync --extra dev"),
        ("uv", _GROUP, "uv sync --group dev"),
        ("uv", _TEST_ONLY, "uv sync --extra test"),
        ("uv", {}, "uv sync"),
        ("poetry", {}, "poetry install --with dev"),
        ("pip", _EXTRA, 'pip install -e ".[dev]"'),
        ("pip-tools", _GROUP, "pip install --group dev"),
        ("pip", {}, "pip install -e ."),
        (None, _EXTRA, ""),
    ],
)
def test_install_hint_per_package_manager(
    manager: str | None, pyproject: dict[str, Any], hint: str
) -> None:
    assert install_hint(manager, pyproject) == hint


@pytest.mark.parametrize(
    ("frameworks", "pyproject", "required"),
    [
        ({"pytest": ""}, {}, False),
        ({"pytest-asyncio": ""}, {}, True),
        (
            {"pytest-asyncio": ""},
            {"tool": {"pytest": {"ini_options": {"asyncio_mode": "auto"}}}},
            False,
        ),
        (
            {"pytest-asyncio": ""},
            {"tool": {"pytest": {"ini_options": {"asyncio_mode": "strict"}}}},
            True,
        ),
    ],
)
def test_asyncio_marks_follow_the_rule_body_fact_and_the_mode(
    frameworks: dict[str, str], pyproject: dict[str, Any], required: bool
) -> None:
    """``has_framework("pytest-asyncio")``, as pytest.md.j2 reads it, and no auto mode."""
    assert asyncio_marks_required({"frameworks": frameworks}, pyproject) is required


def test_derived_config_reaches_every_handler_of_its_hook_only() -> None:
    derived = derived_hook_config(ToolchainInputs("uv sync", "", True))
    record: dict[str, Any] = {
        "id": "toolchain-missing-hint",
        "handlers": {"post_tool_use": {"config": {}}, "post_tool_use_failure": {}},
    }
    other: dict[str, Any] = {"id": "guard-x", "handlers": {"pre_tool_use": {"config": {"k": 1}}}}

    updated = with_derived_config(record, derived)

    assert {e: h["config"] for e, h in updated["handlers"].items()} == {
        "post_tool_use": {"install_hint": "uv sync", "cz_install_hint": ""},
        "post_tool_use_failure": {"install_hint": "uv sync", "cz_install_hint": ""},
    }
    assert with_derived_config(other, derived) == other
    assert record["handlers"]["post_tool_use"] == {"config": {}}  # the input is not mutated
    assert derived["pytest-conventions-feedback"] == {"asyncio_marks": True}
