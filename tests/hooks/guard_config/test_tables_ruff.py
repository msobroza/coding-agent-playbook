"""The ``ruff`` table of ``guard_config.json`` (specs/prK-hook-pack.md §E.3).

``guard_config.json`` gets only the repo's own ruff selection (machine-
independent); the pinned ruff's rule set is probed apart (``test_ruff_probe``),
whose sample rule listings the machine-independence test reuses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.config.tables.hooks import GuardrailsConfig, HooksConfig
from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig, parse_guard_config
from coding_agent_playbook.hooks.guard_config._tables_ruff import (
    RuffSelection,
    read_project_ruff_selection,
    ruff_table,
)
from coding_agent_playbook.hooks.guard_config.compile import (
    GuardConfigInputs,
    render_guard_config,
    serialize_guard_config,
)
from coding_agent_playbook.sync._machine_local import SyncHookDeps, write_pins
from tests.fakes import FakePinWriter
from tests.hook_runtime.fakes import FakeRuff
from tests.hooks.guard_config.test_ruff_probe import RULES_017, RULES_OLD

if TYPE_CHECKING:
    from pathlib import Path


# --- the project's selection -------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "text", "expected"),
    [
        (
            "pyproject.toml",
            '[tool.ruff.lint]\nselect = ["E", "I", "UP"]\nextend-select = ["B"]\n'
            'ignore = ["E501"]\nextend-ignore = ["UP007"]\n',
            RuffSelection(("B", "E", "I", "UP"), ("E501", "UP007"), default_select=False),
        ),
        (
            "pyproject.toml",
            '[tool.ruff]\nselect = ["F", "I"]\n',  # the deprecated top-level keys
            RuffSelection(("F", "I"), (), default_select=False),
        ),
        (
            "ruff.toml",
            '[lint]\nselect = ["ALL"]\nignore = ["D"]\n',
            RuffSelection(("ALL",), ("D",), False),
        ),
        ("pyproject.toml", '[project]\nname = "x"\n', RuffSelection()),  # not a ruff config
        ("ruff.toml", 'line-length = 100\n[lint]\nextend-select = ["I"]\n', RuffSelection(("I",))),
        ("pyproject.toml", "[tool.ruff\n", RuffSelection()),  # malformed: ruff's defaults
    ],
    ids=[
        "pyproject-lint",
        "pyproject-legacy",
        "ruff-toml",
        "no-tool-ruff",
        "defaults+extend",
        "bad",
    ],
)
def test_project_select_from_pyproject_ruff_toml_and_defaults(
    tmp_path: Path, name: str, text: str, expected: RuffSelection
) -> None:
    (tmp_path / name).write_text(text, encoding="utf-8")

    assert read_project_ruff_selection(tmp_path) == expected


def test_dot_ruff_toml_wins_over_ruff_toml_over_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.ruff.lint]\nselect = ["E"]\n', "utf-8")
    (tmp_path / "ruff.toml").write_text('[lint]\nselect = ["F"]\n', "utf-8")
    assert read_project_ruff_selection(tmp_path).select == ("F",)

    (tmp_path / ".ruff.toml").write_text('[lint]\nselect = ["I"]\n', "utf-8")
    assert read_project_ruff_selection(tmp_path).select == ("I",)


@pytest.mark.parametrize(
    ("select", "ignore", "safe", "safe_ignore"),
    [
        (("B", "E", "F", "I", "UP", "W"), ("E501",), ["I", "UP"], []),
        (("E", "F"), (), [], []),
        (("ALL",), ("I",), ["UP"], []),
        (("I", "UP006", "UP007"), (), ["I", "UP006", "UP007"], []),
        (("I", "UP"), ("UP007",), ["I", "UP"], ["UP007"]),
        (("INP", "F"), (), [], []),  # INP is flake8-no-pep420, not isort
    ],
)
def test_safe_fix_select_is_I_UP_intersect_project(
    select: tuple[str, ...], ignore: tuple[str, ...], safe: list[str], safe_ignore: list[str]
) -> None:
    table = ruff_table(RuffSelection(select, ignore, default_select=False))

    assert table["safe_fix_select"] == safe
    assert table["safe_fix_ignore"] == safe_ignore
    assert table["project_select"] == list(select)


def test_default_selection_fixes_nothing() -> None:
    """Ruff's default selection changed in 0.17; the committed table cannot name it."""
    table = ruff_table(RuffSelection())

    assert table == {
        "default_select": True,
        "project_select": [],
        "project_ignore": [],
        "safe_fix_select": [],
        "safe_fix_ignore": [],
    }


# --- machine independence ----------------------------------------------------------------


def test_guard_config_ruff_tables_machine_independent(tmp_path: Path) -> None:
    """Two ruff versions: identical guard_config.json bytes, different machine.json drops."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff.lint]\nselect = ["E", "F", "I", "UP"]\n', encoding="utf-8"
    )
    configs: list[bytes] = []
    drops: list[dict[str, list[str]]] = []
    for rules in (RULES_017, RULES_OLD):
        venv_ruff = tmp_path / ".venv" / "bin" / "ruff"
        venv_ruff.parent.mkdir(parents=True, exist_ok=True)
        venv_ruff.write_bytes(repr(rules).encode())
        venv_ruff.chmod(0o755)
        pins = FakePinWriter()
        deps = SyncHookDeps(
            pins=pins, which=lambda _: None, proc=FakeRuff(rules=rules), rule_cache=lambda _: None
        )
        write_pins(tmp_path, deps, engine_version="0.2.0", ruff_codes=["B006", "UP045"])
        inputs = GuardConfigInputs(
            hooks=[],
            hooks_config=HooksConfig(enabled=True),
            guardrails=GuardrailsConfig(),
            engine_version="0.2.0",
            ruff=read_project_ruff_selection(tmp_path),
        )
        configs.append(serialize_guard_config(render_guard_config(inputs)))
        drops.append(pins.drops)

    assert configs[0] == configs[1]
    assert b'"safe_fix_select":["I","UP"]' in configs[0]
    assert drops == [{}, {"ruff": ["UP045"]}]


def test_runtime_reads_the_ruff_table_back() -> None:
    inputs = GuardConfigInputs(
        hooks=[],
        hooks_config=HooksConfig(enabled=True),
        guardrails=GuardrailsConfig(),
        engine_version="0.2.0",
        ruff=RuffSelection(("E", "I", "UP"), ("UP007",), default_select=False),
    )

    parsed = parse_guard_config(serialize_guard_config(render_guard_config(inputs)))

    assert isinstance(parsed, GuardConfig)
    assert parsed.tables["ruff"]["safe_fix_select"] == ["I", "UP"]
    assert parsed.tables["ruff"]["safe_fix_ignore"] == ["UP007"]
