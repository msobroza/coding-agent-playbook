"""``HARNESS.md`` is named after the real repo, never after the output root (#268).

``sync --check`` renders into a scratch directory, so naming the harness after
``output_root`` made the two modes disagree whenever the typed ``--repo-root``
spelling differed from the directory's name. The adapter now takes the name
from ``begin_sync``'s ``repo_root`` (the real repo in every mode, per the
``Adapter.begin_sync`` contract) through ``generated_output.repo_name``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.agent_harness.adapter import AgentHarnessAdapter
from tests.agent_harness.test_adapter import _make_rule

if TYPE_CHECKING:
    import pytest


def _harness_md(adapter: AgentHarnessAdapter, output_root: Path) -> str:
    """Buffer one always-rule, finalize into ``output_root`` and return ``HARNESS.md``."""
    output_root.mkdir(parents=True, exist_ok=True)
    adapter.write_rule(_make_rule(), output_root)
    adapter.finalize(output_root)
    return (output_root / "HARNESS.md").read_text(encoding="utf-8")


def _assert_named(text: str, name: str) -> None:
    assert f"name: {name}\n" in text
    assert f"description: Coding-agent harness for {name}.\n" in text
    assert f"\n# {name}\n" in text


def test_name_comes_from_begin_sync_root_not_output_root(tmp_path: Path) -> None:
    real = tmp_path / "probe"
    real.mkdir()
    adapter = AgentHarnessAdapter()
    adapter.begin_sync(real, None)
    text = _harness_md(adapter, tmp_path / "scratch" / "something-else")
    _assert_named(text, "probe")


def test_dot_root_names_the_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``begin_sync(Path("."))`` used to fall back to ``harness`` (``Path(".").name == ""``)."""
    real = tmp_path / "probe"
    real.mkdir()
    monkeypatch.chdir(real)
    adapter = AgentHarnessAdapter()
    adapter.begin_sync(Path("."), None)
    _assert_named(_harness_md(adapter, Path(".")), "probe")


def test_dot_dot_root_names_the_directory(tmp_path: Path) -> None:
    """``x/sub/..`` used to write ``name: ..`` and the heading ``# ..``."""
    real = tmp_path / "probe"
    (real / "sub").mkdir(parents=True)
    adapter = AgentHarnessAdapter()
    typed = real / "sub" / ".."
    adapter.begin_sync(typed, None)
    _assert_named(_harness_md(adapter, typed), "probe")


def test_without_begin_sync_names_the_output_root(tmp_path: Path) -> None:
    """A caller that skips ``begin_sync`` (a direct render) still gets the root's real name."""
    real = tmp_path / "probe"
    (real / "sub").mkdir(parents=True)
    _assert_named(_harness_md(AgentHarnessAdapter(), real / "sub" / ".."), "probe")
