"""``playbook validate`` reports every layout rewrite per file, and refuses a bad ``[layout]`` (D71).

prU L0-23: with a ``[layout]`` key off its D60 default, validate prints one line
per generated file and prefix: ``layout: <file>: <from> -> <to> (<count>)``. The
lines come from the sync step's own rewrite list on a scratch render, so they name
exactly what ``playbook sync`` rewrites.
An absolute path, a ``..`` segment or an unknown key stops every command with an
``error:`` naming the key (exit 2), before anything is written.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.cli import main
from coding_agent_playbook.commands import init as _init
from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.sync import pipeline as _sync
from coding_agent_playbook.sync._layout_outputs import rewrite_layout_outputs
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.sync._layout_outputs import FileRewrite

pytestmark = [pytest.mark.usefixtures("hermetic_git_env"), pytest.mark.catalog]

_CONFIG = ".coding-agent-playbook.toml"


def _init_repo(repo: Path, framework: str = "mattpocock") -> None:
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "probe"\nrequires-python = ">=3.12"\ndependencies = []\n',
        encoding="utf-8",
    )
    args = argparse.Namespace(
        repo_root=str(repo),
        non_interactive=True,
        name="probe",
        kind="python-library",
        adapters="claude_code",
        framework=framework,
    )
    assert _init.run(args) == 0


def _append_layout(repo: Path, body: str) -> None:
    path = repo / _CONFIG
    path.write_text(path.read_text(encoding="utf-8") + f"\n[layout]\n{body}\n", encoding="utf-8")


def _layout_lines(repo: Path, capsys: pytest.CaptureFixture[str]) -> list[str]:
    capsys.readouterr()
    assert _validate.run(argparse.Namespace(repo_root=str(repo))) == 0
    out = capsys.readouterr().out
    return [line for line in out.splitlines() if line.startswith("layout: ")]


def test_validate_lists_each_rewrite_with_file_from_to_and_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_repo(tmp_path)
    _append_layout(tmp_path, 'agents = "notes/agents"')

    lines = _layout_lines(tmp_path, capsys)

    assert "layout: AGENTS.md: docs/agents -> notes/agents (3)" in lines
    assert all(" -> notes/agents (" in line for line in lines)
    assert "notes/agents" not in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")


def test_validate_reports_exactly_what_sync_rewrites(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    _append_layout(tmp_path, 'agents = "notes/agents"\nspecs = "specs"')
    reported = _layout_lines(tmp_path, capsys)
    synced: list[FileRewrite] = []

    def _spy(*args: Any, **kwargs: Any) -> list[FileRewrite]:
        done = rewrite_layout_outputs(*args, **kwargs)
        synced.extend(done)
        return done

    monkeypatch.setattr(_sync, "rewrite_layout_outputs", _spy)

    assert _sync.execute(tmp_path, git=FakeGitClient()) == 0
    assert sorted(reported) == sorted(line for done in synced for line in done.lines())
    # The engine-assembled AGENTS.md has no source file of its own; it is reported too.
    assert any(line.startswith("layout: AGENTS.md: ") for line in reported)


def test_validate_reports_no_rewrite_for_a_bundled_framework_under_the_default_layout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """superpowers names the default paths itself, so nothing is rewritten (D61)."""
    _init_repo(tmp_path, framework="superpowers")

    assert _layout_lines(tmp_path, capsys) == []


def test_validate_reports_a_bundled_framework_plan_path_under_a_custom_layout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_repo(tmp_path, framework="superpowers")
    _append_layout(tmp_path, 'plans = "plans"')

    lines = _layout_lines(tmp_path, capsys)

    assert any(
        line.startswith("layout: .claude/skills/writing-plans/SKILL.md: docs/plans -> plans (")
        for line in lines
    )


def test_validate_prints_no_rewrite_for_the_default_layout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_repo(tmp_path)
    _append_layout(tmp_path, 'agents = "docs/agents"')

    assert _layout_lines(tmp_path, capsys) == []


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ('specs = "/srv/specs"', "[layout] specs must be a relative path inside the repo"),
        ('plans = "../plans"', "[layout] plans must not contain a '..' segment"),
        ('spec = "specs"', "[layout] unknown key 'spec'"),
    ],
)
def test_a_bad_layout_is_an_error_naming_the_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], body: str, fragment: str
) -> None:
    _init_repo(tmp_path)
    _append_layout(tmp_path, body)
    capsys.readouterr()

    assert main(["validate", "--repo-root", str(tmp_path)]) == 2

    err = capsys.readouterr().err
    assert f"error: {tmp_path / _CONFIG}" in err or f"error: {_CONFIG}" in err
    assert fragment in err
