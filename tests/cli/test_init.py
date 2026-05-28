"""Tests for ``cap init`` (PR 10 Task 4)."""

from __future__ import annotations

import argparse
import tomllib
from typing import TYPE_CHECKING

from coding_agent_playbook.commands import init as _init

if TYPE_CHECKING:
    from pathlib import Path


def _ns(repo: Path, **kwargs: object) -> argparse.Namespace:
    base: dict[str, object] = {
        "repo_root": str(repo),
        "non_interactive": True,
        "name": None,
        "kind": None,
        "description": None,
        "adapters": None,
        "overlays": None,
    }
    base.update(kwargs)
    return argparse.Namespace(**base)


def test_init_non_interactive_writes_expected_files(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nrequires-python=">=3.12"\ndependencies=["fastapi"]\n'
    )
    rc = _init.run(
        _ns(
            tmp_path,
            name="my-repo",
            kind="python-application",
            description="A test repo",
        )
    )
    assert rc == 0

    primary = tmp_path / ".coding-agent-playbook.toml"
    assert primary.is_file()
    with primary.open("rb") as f:
        data = tomllib.load(f)
    assert data["project"]["name"] == "my-repo"
    assert data["project"]["kind"] == "python-application"
    assert "continue" in data["adapters_enabled"]
    assert "agents_md" not in data["adapters_enabled"]  # always-on, not stored

    local = tmp_path / ".coding-agent-playbook.local.toml"
    assert local.is_file()

    gitignore = tmp_path / ".gitignore"
    assert gitignore.is_file()
    assert ".coding-agent-playbook.local.toml" in gitignore.read_text()

    pre_commit = tmp_path / ".pre-commit-config.yaml"
    assert pre_commit.is_file()
    assert "coding-agent-playbook-sync" in pre_commit.read_text()


def test_init_non_interactive_missing_name_returns_error_code(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nrequires-python=">=3.12"\ndependencies=[]\n'
    )
    import pytest

    with pytest.raises(SystemExit) as exc:
        _init.run(_ns(tmp_path, non_interactive=True))
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "name" in err.lower()


def test_init_interactive_uses_input(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nrequires-python=">=3.12"\ndependencies=[]\n'
    )

    answers = iter(
        [
            "interactive-repo",  # project name
            "Some description",  # project description
            "python-library",  # kind
            "",  # adapters: blank => defaults
            "",  # overlays: blank => defaults
        ]
    )
    monkeypatch.setattr("builtins.input", lambda *_args, **_kw: next(answers))

    rc = _init.run(_ns(tmp_path, non_interactive=False))
    assert rc == 0
    with (tmp_path / ".coding-agent-playbook.toml").open("rb") as f:
        data = tomllib.load(f)
    assert data["project"]["name"] == "interactive-repo"
    assert data["project"]["kind"] == "python-library"


def test_init_is_idempotent_does_not_clobber_existing_config(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nrequires-python=">=3.12"\ndependencies=[]\n'
    )
    # Pre-existing config: a user added a custom field by hand.
    existing = """\
schema_version = 1
adapters_enabled = ["continue", "custom_adapter"]

[project]
name = "first-name"
kind = "python-library"

[engine]
version = "0.1.0a0"

[storage]
artifact_source = "filesystem"
state_source = "filesystem"

[user_choices]
docstring_style = "numpy"
"""
    (tmp_path / ".coding-agent-playbook.toml").write_text(existing)

    rc = _init.run(
        _ns(
            tmp_path,
            name="second-name",
            kind="python-application",
            description="Updated",
        )
    )
    assert rc == 0
    with (tmp_path / ".coding-agent-playbook.toml").open("rb") as f:
        data = tomllib.load(f)
    assert data["project"]["name"] == "second-name"
    # The user's custom adapter should remain in adapters_enabled.
    assert "custom_adapter" in data["adapters_enabled"]
    # User_choices preserved.
    assert data.get("user_choices", {}).get("docstring_style") == "numpy"


def test_prompt_multi_select_parses_comma_separated_indices(monkeypatch, capsys):
    """``1,3`` selects choices at 1-based indices 1 and 3."""
    answers = iter(["1,3"])
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: next(answers))
    result = _init._prompt_multi_select(
        "pick", ["alpha", "beta", "gamma", "delta"], defaults=["alpha"]
    )
    assert result == ["alpha", "gamma"]
    # The choice menu should have been printed (sanity check).
    out = capsys.readouterr().out
    assert "alpha" in out and "gamma" in out


def test_prompt_multi_select_falls_back_to_defaults_on_non_integer(monkeypatch):
    """Non-integer tokens are silently skipped; with no valid tokens the
    function falls back to ``defaults`` rather than raising."""
    answers = iter(["nonsense,more-nonsense"])
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: next(answers))
    result = _init._prompt_multi_select(
        "pick", ["alpha", "beta", "gamma"], defaults=["alpha", "beta"]
    )
    assert result == ["alpha", "beta"]


def test_prompt_multi_select_falls_back_to_defaults_on_out_of_range(monkeypatch):
    """Indices outside ``1..len(choices)`` are silently skipped; an
    all-out-of-range reply falls back to ``defaults``."""
    answers = iter(["99,0,-1"])
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: next(answers))
    result = _init._prompt_multi_select(
        "pick", ["alpha", "beta", "gamma"], defaults=["gamma"]
    )
    assert result == ["gamma"]


def test_prompt_multi_select_mixed_valid_and_invalid_keeps_valid(monkeypatch):
    """If at least one index is valid, only the valid ones are returned
    (defaults are NOT mixed in)."""
    answers = iter(["1,nope,99,2"])
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: next(answers))
    result = _init._prompt_multi_select(
        "pick", ["alpha", "beta", "gamma"], defaults=["gamma"]
    )
    assert result == ["alpha", "beta"]


def test_init_does_not_duplicate_pre_commit_hook(tmp_path):
    """Running init twice must not append the hook block twice."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nrequires-python=">=3.12"\ndependencies=[]\n'
    )
    args = _ns(
        tmp_path,
        name="dedup-repo",
        kind="python-library",
        description="",
    )
    assert _init.run(args) == 0
    first = (tmp_path / ".pre-commit-config.yaml").read_text()
    assert _init.run(args) == 0
    second = (tmp_path / ".pre-commit-config.yaml").read_text()
    assert first.count("coding-agent-playbook-sync") == 1
    assert second.count("coding-agent-playbook-sync") == 1
