"""Tests for ``playbook init`` (PR 10 Task 4)."""

from __future__ import annotations

import argparse
import tomllib
from typing import TYPE_CHECKING

import pytest
import yaml

from coding_agent_playbook.commands import init as _init
from coding_agent_playbook.gitignore import BLOCK_START
from tests.unit.test_precommit_merge import LEGACY_APPENDED, LEGACY_STARTER

if TYPE_CHECKING:
    from pathlib import Path

# init ends by running a real ``playbook sync`` (default SubprocessGitClient);
# keep any git call it makes away from the developer's machine config.
pytestmark = pytest.mark.usefixtures("hermetic_git_env")


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

    # [output] commit is written explicitly (default false) so it is discoverable.
    assert data["output"] == {"commit": False}

    gitignore = tmp_path / ".gitignore"
    assert gitignore.is_file()
    gitignore_text = gitignore.read_text()
    assert ".coding-agent-playbook.local.toml" in gitignore_text
    # The final sync gitignores the generated output via the managed block.
    assert BLOCK_START in gitignore_text
    assert "\n/AGENTS.md\n" in gitignore_text

    pre_commit = tmp_path / ".pre-commit-config.yaml"
    assert pre_commit.is_file()
    text = pre_commit.read_text()
    # commit = false: auto-sync after checkout/merge + the staged-output guard,
    # not the legacy drift check.
    assert "coding-agent-playbook-autosync" in text
    assert "coding-agent-playbook-no-generated-output" in text
    assert "playbook sync --check-staged" in text
    assert "playbook sync --check\n" not in text
    # Fresh repo renders the full air-gapped starter: the playbook hooks plus the
    # ruff/mypy tooling hooks, all repo: local + language: system, nothing to
    # clone (works offline).
    assert "repo: local" in text
    assert "language: system" in text
    assert "ruff check --fix" in text
    assert "ruff format" in text
    assert "mypy --config-file=pyproject.toml" in text
    assert "https://" not in text
    parsed = yaml.safe_load(text)
    assert isinstance(parsed["repos"], list)
    assert all(entry.get("repo") == "local" for entry in parsed["repos"])
    assert parsed["default_install_hook_types"] == ["pre-commit", "post-checkout", "post-merge"]


def test_init_default_adapters_include_shared_skills(tmp_path):
    """The cross-agent skills hub (SPEC §10.8) is on by default, after the
    three harness adapters; ``agents_md`` stays implicit (force-enabled)."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nrequires-python=">=3.12"\ndependencies=[]\n'
    )
    assert _init._DEFAULT_ADAPTERS == ("continue", "claude_code", "opencode", "shared_skills")
    assert _init.run(_ns(tmp_path, name="r", kind="python-library")) == 0
    with (tmp_path / ".coding-agent-playbook.toml").open("rb") as f:
        data = tomllib.load(f)
    assert data["adapters_enabled"] == list(_init._DEFAULT_ADAPTERS)


def test_init_adapters_flag_can_opt_out_of_shared_skills(tmp_path):
    """``shared_skills`` is not force-enabled: an explicit list without it wins."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nrequires-python=">=3.12"\ndependencies=[]\n'
    )
    rc = _init.run(_ns(tmp_path, name="r", kind="python-library", adapters="claude_code"))
    assert rc == 0
    with (tmp_path / ".coding-agent-playbook.toml").open("rb") as f:
        data = tomllib.load(f)
    assert data["adapters_enabled"] == ["claude_code"]


def test_init_non_interactive_missing_name_returns_error_code(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nrequires-python=">=3.12"\ndependencies=[]\n'
    )
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
    result = _init._prompt_multi_select("pick", ["alpha", "beta", "gamma"], defaults=["gamma"])
    assert result == ["gamma"]


def test_prompt_multi_select_mixed_valid_and_invalid_keeps_valid(monkeypatch):
    """If at least one index is valid, only the valid ones are returned
    (defaults are NOT mixed in)."""
    answers = iter(["1,nope,99,2"])
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: next(answers))
    result = _init._prompt_multi_select("pick", ["alpha", "beta", "gamma"], defaults=["gamma"])
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
    assert first == second
    assert second.count("id: coding-agent-playbook-no-generated-output") == 1
    assert second.count("id: coding-agent-playbook-autosync") == 1
    # The second run hits the existing-file path and must not re-render the
    # tooling hooks either.
    assert first.count("- id: ruff\n") == 1
    assert second.count("- id: ruff\n") == 1


def test_init_existing_config_appends_sync_block_only(tmp_path):
    """An existing curated config gets ONLY our sync hook appended — init must
    not inject ruff/mypy into a config the consumer already maintains."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nrequires-python=">=3.12"\ndependencies=[]\n'
    )
    existing = (
        "repos:\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: my-own-hook\n"
        "        name: my own hook\n"
        "        entry: echo hi\n"
        "        language: system\n"
    )
    (tmp_path / ".pre-commit-config.yaml").write_text(existing)

    args = _ns(tmp_path, name="curated-repo", kind="python-library", description="")
    assert _init.run(args) == 0

    text = (tmp_path / ".pre-commit-config.yaml").read_text()
    assert "my-own-hook" in text  # the consumer's hook is preserved
    # commit = false (default): our auto-sync + staged-output guard are appended
    assert "coding-agent-playbook-autosync" in text
    assert "playbook sync --check-staged" in text
    assert "ruff check --fix" not in text  # tooling hooks are NOT injected
    assert "mypy --config-file" not in text
    hooks = [hook for repo in yaml.safe_load(text)["repos"] for hook in repo["hooks"]]
    stages = {hook["id"]: hook.get("stages") for hook in hooks}
    assert stages["coding-agent-playbook-autosync"] == ["post-checkout", "post-merge"]
    assert stages["coding-agent-playbook-no-generated-output"] == ["pre-commit"]


_COMMIT_TRUE_CONFIG = """\
schema_version = 1
adapters_enabled = ["continue"]

[project]
name = "legacy"
kind = "python-library"

[engine]
version = "0.1.0a0"

[output]
commit = true
"""


def _pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nrequires-python=">=3.12"\ndependencies=[]\n'
    )


def test_init_preserves_existing_output_commit_true(tmp_path, capsys):
    """A repo that opted into committed output keeps it, gets the legacy drift
    hook, no managed .gitignore block, and no post-checkout install hint."""
    _pyproject(tmp_path)
    (tmp_path / ".coding-agent-playbook.toml").write_text(_COMMIT_TRUE_CONFIG)
    assert _init.run(_ns(tmp_path, name="legacy", kind="python-library")) == 0
    with (tmp_path / ".coding-agent-playbook.toml").open("rb") as f:
        assert tomllib.load(f)["output"] == {"commit": True}
    text = (tmp_path / ".pre-commit-config.yaml").read_text()
    assert "entry: playbook sync --check\n" in text
    assert "--check-staged" not in text
    assert "default_install_hook_types" not in text
    assert BLOCK_START not in (tmp_path / ".gitignore").read_text()
    assert "--hook-type post-checkout" not in capsys.readouterr().out


def test_init_commit_true_appends_legacy_block_to_existing_pre_commit(tmp_path):
    _pyproject(tmp_path)
    (tmp_path / ".coding-agent-playbook.toml").write_text(_COMMIT_TRUE_CONFIG)
    (tmp_path / ".pre-commit-config.yaml").write_text(
        "repos:\n  - repo: local\n    hooks:\n      - id: mine\n"
        "        name: mine\n        entry: echo hi\n        language: system\n"
    )
    assert _init.run(_ns(tmp_path, name="legacy", kind="python-library")) == 0
    text = (tmp_path / ".pre-commit-config.yaml").read_text()
    hooks = {hook["id"]: hook for repo in yaml.safe_load(text)["repos"] for hook in repo["hooks"]}
    assert hooks["coding-agent-playbook-sync"]["entry"] == "playbook sync --check"
    assert "mine" in hooks
    assert "--check-staged" not in text


def test_init_prints_hook_install_command(tmp_path, capsys):
    _pyproject(tmp_path)
    assert _init.run(_ns(tmp_path, name="x", kind="python-library")) == 0
    out = capsys.readouterr().out
    assert (
        "pre-commit install --hook-type pre-commit --hook-type post-checkout "
        "--hook-type post-merge" in out
    )


def test_init_keeps_explicit_output_commit_false_on_rerun(tmp_path):
    _pyproject(tmp_path)
    args = _ns(tmp_path, name="x", kind="python-library")
    assert _init.run(args) == 0
    assert _init.run(args) == 0
    with (tmp_path / ".coding-agent-playbook.toml").open("rb") as f:
        assert tomllib.load(f)["output"] == {"commit": False}


def test_init_upgrades_a_pre_v015_starter_to_the_local_hooks(tmp_path, capsys):
    """Regression: re-running init on the old starter (drift check + always_run
    mypy, no ``stages``) must not leave ``playbook sync --check`` next to the
    new hooks — it would fail after every checkout/merge."""
    _pyproject(tmp_path)
    (tmp_path / ".pre-commit-config.yaml").write_text(LEGACY_STARTER)
    assert _init.run(_ns(tmp_path, name="x", kind="python-library")) == 0
    text = (tmp_path / ".pre-commit-config.yaml").read_text()
    hooks = {hook["id"] for repo in yaml.safe_load(text)["repos"] for hook in repo["hooks"]}
    assert "coding-agent-playbook-sync" not in hooks
    assert "entry: playbook sync --check\n" not in text
    assert {"coding-agent-playbook-autosync", "coding-agent-playbook-no-generated-output"} <= hooks
    err = capsys.readouterr().err
    assert "default_stages: [pre-commit]" in err


def test_init_warns_about_a_hand_edited_legacy_hook(tmp_path, capsys):
    _pyproject(tmp_path)
    edited = LEGACY_APPENDED.replace("always_run: true", "always_run: true\n        verbose: true")
    (tmp_path / ".pre-commit-config.yaml").write_text(edited)
    assert _init.run(_ns(tmp_path, name="x", kind="python-library")) == 0
    assert "legacy 'coding-agent-playbook-sync' hook" in capsys.readouterr().err
