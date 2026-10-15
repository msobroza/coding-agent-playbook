"""The sync-derived hook config of toolchain-missing-hint and pytest-conventions-feedback (specs/prK-hook-pack.md §E.3).

Pure functions of ``(package_manager, pyproject)`` and the detector facts, so
these tests need no repository except where the file read itself is the
point.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook._guard_config_toolchain import (
    ToolchainInputs,
    asyncio_marks_required,
    derived_hook_config,
    install_hint,
    read_toolchain_inputs,
    with_derived_config,
)

if TYPE_CHECKING:
    from pathlib import Path

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


def test_read_toolchain_inputs_from_the_repository(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n[project.optional-dependencies]\ndev = ["commitizen>=3"]\n',
        encoding="utf-8",
    )

    inputs = read_toolchain_inputs(tmp_path, {"package_manager": "uv"})
    malformed = tmp_path / "bad"
    malformed.mkdir()
    (malformed / "pyproject.toml").write_text("[project\n", encoding="utf-8")

    assert inputs == ToolchainInputs("uv sync --extra dev", "uv sync --extra dev", False)
    assert read_toolchain_inputs(malformed, {"package_manager": "uv"}).install_hint == "uv sync"


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
