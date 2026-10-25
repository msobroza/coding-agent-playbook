"""The adapter list ``playbook init`` offers and writes (SPEC §12.1, SPEC v0.21).

``continue`` is opt-in since v0.21 (specs/prS-skills-context.md D11): the
default set is ``claude_code``, ``opencode``, ``shared_skills``. A committed
``continue`` survives every re-run, and the interactive menu offers installed
adapters only (the old ``codex`` choice named no adapter).
"""

from __future__ import annotations

import argparse
import tomllib
from importlib import metadata
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.cli import main
from coding_agent_playbook.commands import init as _init
from coding_agent_playbook.commands._init_adapters import (
    ADAPTER_CHOICES,
    DEFAULT_ADAPTERS,
    adapters_from_flag,
    adapters_union,
)
from coding_agent_playbook.commands._init_answers import _preselected_adapters

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

# init ends by running a real ``playbook sync`` (default SubprocessGitClient);
# keep any git call it makes away from the developer's machine config.
pytestmark = pytest.mark.usefixtures("hermetic_git_env")

_WITH_CONTINUE = "claude_code,opencode,shared_skills,continue"


def _ns(repo: Path, **kwargs: object) -> argparse.Namespace:
    base: dict[str, object] = {
        "repo_root": str(repo),
        "non_interactive": True,
        "name": "r",
        "kind": "python-library",
        "description": None,
        "adapters": None,
        "overlays": None,
    }
    base.update(kwargs)
    return argparse.Namespace(**base)


def _pyproject(repo: Path) -> None:
    (repo / "pyproject.toml").write_text(
        '[project]\nname="x"\nrequires-python=">=3.12"\ndependencies=[]\n'
    )


def _adapters_enabled(repo: Path) -> list[str]:
    data = tomllib.loads((repo / ".coding-agent-playbook.toml").read_text())
    enabled: list[str] = data["adapters_enabled"]
    return enabled


def _answer_interactively(monkeypatch: pytest.MonkeyPatch, adapters_answer: str) -> None:
    """Feed ``input()``: name, description, kind, adapters, framework, overlays, hooks."""
    replies: Iterator[str] = iter(["r", "", "python-library", adapters_answer, "", "", ""])
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: next(replies))


def test_fresh_init_enables_claude_code_opencode_and_shared_skills(tmp_path: Path) -> None:
    _pyproject(tmp_path)

    assert _init.run(_ns(tmp_path)) == 0

    assert _adapters_enabled(tmp_path) == ["claude_code", "opencode", "shared_skills"]
    assert _adapters_enabled(tmp_path) == list(DEFAULT_ADAPTERS)
    assert not (tmp_path / ".continue").exists()


def test_init_with_continue_listed_renders_continue_rules_and_prompts(tmp_path: Path) -> None:
    _pyproject(tmp_path)

    assert _init.run(_ns(tmp_path, adapters=_WITH_CONTINUE)) == 0

    assert _adapters_enabled(tmp_path) == _WITH_CONTINUE.split(",")
    assert (tmp_path / ".continue" / "rules" / "00-project-context.md").is_file()
    prompts = {path.name for path in (tmp_path / ".continue" / "prompts").iterdir()}
    assert {"review-core.md", "refactor.md"} <= prompts


def test_init_rerun_keeps_a_committed_continue(tmp_path: Path) -> None:
    """D11: an existing repo that lists continue keeps it; a re-run never drops it."""
    _pyproject(tmp_path)
    committed = "continue,claude_code,opencode,shared_skills"
    assert _init.run(_ns(tmp_path, adapters=committed)) == 0
    config = tmp_path / ".coding-agent-playbook.toml"
    before = config.read_bytes()

    assert _init.run(_ns(tmp_path)) == 0

    assert config.read_bytes() == before
    assert _adapters_enabled(tmp_path) == committed.split(",")


def test_interactive_choices_are_installed_adapters_defaults_first() -> None:
    """Regression: the menu offered ``codex``, which names no adapter (keep_all forever)."""
    installed = {ep.name for ep in metadata.entry_points(group="coding_agent_playbook.adapters")}
    assert ADAPTER_CHOICES[:3] == DEFAULT_ADAPTERS
    assert ADAPTER_CHOICES == ("claude_code", "opencode", "shared_skills", "continue")
    assert set(ADAPTER_CHOICES) <= installed
    assert "codex" not in ADAPTER_CHOICES


def test_interactive_blank_answer_leaves_continue_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _pyproject(tmp_path)
    _answer_interactively(monkeypatch, "")

    assert _init.run(_ns(tmp_path, non_interactive=False)) == 0

    assert _adapters_enabled(tmp_path) == list(DEFAULT_ADAPTERS)
    out = capsys.readouterr().out
    assert "continue is opt-in" in out
    assert "    4. continue\n" in out
    assert "codex." not in out


def test_interactive_index_four_enables_continue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pyproject(tmp_path)
    _answer_interactively(monkeypatch, "1,2,3,4")

    assert _init.run(_ns(tmp_path, non_interactive=False)) == 0

    assert _adapters_enabled(tmp_path) == [*DEFAULT_ADAPTERS, "continue"]
    assert (tmp_path / ".continue" / "rules").is_dir()


def test_interactive_blank_answer_takes_the_detected_adapters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """D79: harness files in the repo pre-select their adapters in the menu."""
    _pyproject(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("team notes\n")
    (tmp_path / ".continue").mkdir()
    (tmp_path / ".continue" / "config.yaml").write_text("name: x\n")
    _answer_interactively(monkeypatch, "")

    assert _init.run(_ns(tmp_path, non_interactive=False)) == 0

    assert _adapters_enabled(tmp_path) == ["claude_code", "continue"]
    out = capsys.readouterr().out
    assert "  * 1. claude_code\n" in out
    assert "    2. opencode\n" in out
    assert "  * 4. continue\n" in out


def test_preselection_survives_a_corrupt_lockfile(tmp_path: Path) -> None:
    """An unparsable lockfile excludes nothing; the markers still pre-select."""
    (tmp_path / ".coding-agent-playbook.lock").write_text("not = [toml\n")
    (tmp_path / "opencode.json").write_text("{}\n")

    assert _preselected_adapters(tmp_path) == ["opencode"]


def test_preselection_skips_files_the_lockfile_records(tmp_path: Path) -> None:
    """Re-running init in a synced repo: engine output never pre-selects its adapter."""
    (tmp_path / ".continue").mkdir()
    (tmp_path / ".continue" / "config.yaml").write_text("name: x\n")
    (tmp_path / ".coding-agent-playbook.lock").write_text(
        'schema_version = 2\nengine_version = "0"\nrendered_at = ""\n\n'
        '[[entries]]\npath = ".continue/config.yaml"\nsha256 = "' + "0" * 64 + '"\nbytes = 1\n'
    )

    assert _preselected_adapters(tmp_path) == list(DEFAULT_ADAPTERS)


def test_non_interactive_default_ignores_detected_harness_files(tmp_path: Path) -> None:
    _pyproject(tmp_path)
    (tmp_path / ".continue").mkdir()
    (tmp_path / ".continue" / "config.yaml").write_text("name: x\n")

    assert _init.run(_ns(tmp_path)) == 0

    assert _adapters_enabled(tmp_path) == ["claude_code", "opencode", "shared_skills"]


def test_adapters_flag_help_names_the_default_set(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["init", "--help"])

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "claude_code,opencode,shared_skills" in out
    assert "continue" in out


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ["claude_code", "opencode", "shared_skills"]),
        ("", ["claude_code", "opencode", "shared_skills"]),
        (" continue , claude_code ,", ["continue", "claude_code"]),
    ],
    ids=["absent", "blank", "spaced-with-trailing-comma"],
)
def test_adapters_from_flag_parses_and_defaults(raw: str | None, expected: list[str]) -> None:
    assert adapters_from_flag(raw) == expected


def test_adapters_union_keeps_committed_order_then_appends_new_answers() -> None:
    answered = ["claude_code", "continue", "claude_code"]
    assert adapters_union(["continue", "custom"], answered) == [
        "continue",
        "custom",
        "claude_code",
    ]
