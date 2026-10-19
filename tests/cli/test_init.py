"""Tests for ``playbook init`` (PR 10 Task 4)."""

from __future__ import annotations

import argparse
import re
import tomllib
from typing import TYPE_CHECKING

import pytest
import yaml

from coding_agent_playbook.cli import main
from coding_agent_playbook.commands import init as _init
from coding_agent_playbook.commands._init_adapters import DEFAULT_ADAPTERS
from coding_agent_playbook.config.model import Config, OutputConfig, ProjectMeta, StorageConfig
from coding_agent_playbook.gitignore import BLOCK_START
from coding_agent_playbook.toml_writer import dump_toml
from tests.cli.test_cli import break_catalog
from tests.hook_samples import write_hook
from tests.toml_equality import assert_toml_identical
from tests.unit.test_precommit import LEGACY_APPENDED, LEGACY_STARTER

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
    assert data["adapters_enabled"] == ["claude_code", "opencode", "shared_skills"]
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


def test_init_default_adapters_leave_continue_opt_in(tmp_path):
    """The shared skill root (SPEC §10.8) is on by default, after the two harness
    adapters; ``continue`` is opt-in since v0.21 and ``agents_md`` stays implicit
    (force-enabled)."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nrequires-python=">=3.12"\ndependencies=[]\n'
    )
    assert DEFAULT_ADAPTERS == ("claude_code", "opencode", "shared_skills")
    assert _init.run(_ns(tmp_path, name="r", kind="python-library")) == 0
    with (tmp_path / ".coding-agent-playbook.toml").open("rb") as f:
        data = tomllib.load(f)
    assert data["adapters_enabled"] == list(DEFAULT_ADAPTERS)


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
            "",  # lifecycle hooks: blank => yes (prK §B.1)
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


# --- P6: re-runs keep unmodelled tables and never persist .local.toml ---------

_PLAIN_CONFIG = """\
schema_version = 1
adapters_enabled = ["continue"]

[project]
name = "x"
kind = "python-library"

[engine]
version = "0.1.0a0"

[user_choices]
docstring_style = "numpy"
"""

# [hooks] is validated before init's final sync (H21): its ids name the
# repo-local hook the test writes. Quoted dotted keys ride an unvalidated table.
_EXTENSION_TABLES = """\

[hooks]
enabled = true
disable = ["some-hook"]

[hooks.some-hook]
budget_s = 2.5
limits = { paths = ["src/"], depth = { max = 3 } }

[acme."a.b"]
config = { paths = ["src/"], depth = { max = 3 } }

[guardrails.secrets]
extra_globs = ["*.vault"]

[links]
allowed_domains = ["agentharnesses.io"]

[metrics]
mode = "both"
test_cmd = ["python", "-m", "pytest"]

[metrics.thresholds.maintainability_index]
warn = 0.65
fail = 0.5

[metrics.regression.coverage]
max_worsening = 0.5

[metrics.weights]
x = 1.0
"""


def _committed_config(tmp_path: Path) -> dict[str, object]:
    with (tmp_path / ".coding-agent-playbook.toml").open("rb") as f:
        return tomllib.load(f)


@pytest.mark.usefixtures("sample_hook_handlers")
def test_init_rerun_preserves_hooks_guardrails_links_metrics(tmp_path):
    _pyproject(tmp_path)
    write_hook(tmp_path / "playbook" / "hooks", "some-hook")
    (tmp_path / ".coding-agent-playbook.toml").write_text(_PLAIN_CONFIG + _EXTENSION_TABLES)
    expected = tomllib.loads(_EXTENSION_TABLES)
    args = _ns(tmp_path, name="x", kind="python-library")
    for _ in range(2):  # the second run re-reads the first run's inline tables
        assert _init.run(args) == 0
        data = _committed_config(tmp_path)
        assert {key: data[key] for key in expected} == expected
    metrics = data["metrics"]
    assert isinstance(metrics, dict)
    assert repr(metrics["regression"]["coverage"]["max_worsening"]) == "0.5"
    assert repr(metrics["weights"]["x"]) == "1.0"
    assert data["user_choices"] == {"docstring_style": "numpy"}


def test_init_rerun_never_persists_local_overrides(tmp_path):
    _pyproject(tmp_path)
    (tmp_path / ".coding-agent-playbook.toml").write_text(_PLAIN_CONFIG)
    local = '[user_choices]\npersonal = "mine"\n\n[metrics]\nmode = "absolute"\n'
    (tmp_path / ".coding-agent-playbook.local.toml").write_text(local)
    assert _init.run(_ns(tmp_path, name="x", kind="python-library")) == 0
    data = _committed_config(tmp_path)
    assert data["user_choices"] == {"docstring_style": "numpy"}
    assert "metrics" not in data
    assert (tmp_path / ".coding-agent-playbook.local.toml").read_text() == local


def test_init_output_policy_comes_from_committed_config(tmp_path):
    """Behaviour change (P6): a local ``[output] commit = true`` no longer
    leaks into the committed file, so it no longer selects the committed
    ``.pre-commit-config.yaml`` hook set either."""
    _pyproject(tmp_path)
    (tmp_path / ".coding-agent-playbook.toml").write_text(_PLAIN_CONFIG)
    (tmp_path / ".coding-agent-playbook.local.toml").write_text("[output]\ncommit = true\n")
    assert _init.run(_ns(tmp_path, name="x", kind="python-library")) == 0
    assert _committed_config(tmp_path)["output"] == {"commit": False}
    text = (tmp_path / ".pre-commit-config.yaml").read_text()
    assert "--check-staged" in text
    assert "entry: playbook sync --check\n" not in text


def _starter_hooks(tmp_path: Path) -> tuple[set[str], list[str]]:
    """The hook ids and ``default_install_hook_types`` of init's ``.pre-commit-config.yaml``."""
    parsed = yaml.safe_load((tmp_path / ".pre-commit-config.yaml").read_text())
    hooks = {hook["id"] for repo in parsed["repos"] for hook in repo["hooks"]}
    return hooks, parsed["default_install_hook_types"]


@pytest.mark.parametrize("commitizen", [False, True])
def test_fresh_starter_adds_the_cz_twin_only_for_a_commitizen_repo(
    tmp_path: Path, commitizen: bool
) -> None:
    """prK §F.4.3: the commit-msg ``cz check`` twin follows the CI step's predicate.

    Runs ``init`` itself: it computes the predicate and hands it to
    ``write_pre_commit``, so this pins that wiring (N9 review).
    """
    pyproject = '[project]\nname="x"\nrequires-python=">=3.12"\ndependencies=[]\n'
    if commitizen:
        pyproject += "\n[tool.commitizen]\nname = 'cz_conventional_commits'\n"
    (tmp_path / "pyproject.toml").write_text(pyproject)

    assert _init.run(_ns(tmp_path, name="x", kind="python-library")) == 0

    hooks, install_types = _starter_hooks(tmp_path)
    assert ("coding-agent-playbook-commit-msg" in hooks) is commitizen
    assert ("commit-msg" in install_types) is commitizen
    assert "coding-agent-playbook-commit-trailers" not in hooks


_TRAILER_ROWS = '\n[hooks.git-commit-push-policy-guard]\nforbid_trailers = ["Co-Authored-By"]\n'


def test_fresh_starter_adds_the_trailer_twin_for_committed_trailer_rows(tmp_path: Path) -> None:
    """prK §E.4: a committed trailer row gives the starter its commit-msg trailer twin.

    Runs ``init`` itself, so the ``commit_trailers`` wiring into
    ``write_pre_commit`` is pinned too (N9 review).
    """
    _pyproject(tmp_path)
    (tmp_path / ".coding-agent-playbook.toml").write_text(_PLAIN_CONFIG + _TRAILER_ROWS)

    assert _init.run(_ns(tmp_path, name="x", kind="python-library")) == 0

    hooks, install_types = _starter_hooks(tmp_path)
    assert "coding-agent-playbook-commit-trailers" in hooks
    assert "coding-agent-playbook-commit-msg" not in hooks
    assert "commit-msg" in install_types


# --- re-runs: the committed config is rewritten from itself alone (SPEC §7.2/§12.1)

#: Every personal override a teammate might keep in the gitignored local file:
#: keys ``Config`` owns, an unknown key inside a table it owns (``[project]
#: homepage``), and tables it does not manage at all (``[metrics]``, a personal
#: one). ``init`` writes back what the *committed* file holds outside ``Config``;
#: computing that from the merged files would commit the last three.
# alias regression: init checks the local list as written (SPEC v0.19)
_LOCAL_OVERRIDES = """\
adapters_enabled = ["claude_code"]
overlays_enabled = ["coding_agent_playbook.packs.superpowers"]

[project]
homepage = "https://mine.example"

[user_choices]
style = "google"

[output]
commit = true

[metrics]
mode = "regression"

[personal_table]
note = "mine only"
"""


def _init_then_add_committed_user_choice(tmp_path: Path) -> argparse.Namespace:
    """First ``init`` run, plus a hand-added committed ``[user_choices]`` entry.

    Added where the writer puts it, after the tables ``Config`` owns and before the
    ``[hooks]`` table init writes (unmanaged entries come last), so a faithful
    rewrite is byte-identical.
    """
    _pyproject(tmp_path)
    args = _ns(tmp_path, name="r", kind="python-library")
    assert _init.run(args) == 0
    primary = tmp_path / ".coding-agent-playbook.toml"
    text = primary.read_text()
    assert text.count("\n[hooks]\n") == 1  # the first run wrote the hooks answer
    choice = '\n[user_choices]\ndocstring_style = "numpy"\n'
    primary.write_text(text.replace("\n[hooks]\n", f"{choice}\n[hooks]\n", 1))
    return args


def test_init_rerun_never_writes_local_overrides_into_the_committed_config(
    tmp_path: Path,
) -> None:
    """Regression: a re-run loaded the config *merged* with the gitignored
    ``.local.toml`` and saved it to the committed file, so a teammate's personal
    adapters list (reordered too), overlays, ``[user_choices]`` and ``[output]``
    got committed for the whole team. The committed file is now rewritten from
    itself only: here it comes back byte-identical, committed choices included."""
    args = _init_then_add_committed_user_choice(tmp_path)
    primary = tmp_path / ".coding-agent-playbook.toml"
    committed = primary.read_bytes()
    local = tmp_path / ".coding-agent-playbook.local.toml"
    local.write_text(_LOCAL_OVERRIDES)

    assert _init.run(args) == 0

    assert primary.read_bytes() == committed
    assert local.read_text() == _LOCAL_OVERRIDES  # the local file is never rewritten
    data = tomllib.loads(primary.read_text())
    assert data["user_choices"] == {"docstring_style": "numpy"}
    assert data["adapters_enabled"] == list(DEFAULT_ADAPTERS)
    assert "overlays_enabled" not in data
    assert data["output"] == {"commit": False}
    assert {"metrics", "personal_table"}.isdisjoint(data)
    assert "homepage" not in data["project"]
    assert data["hooks"] == {"enabled": True}  # the committed answer, kept by the re-run


def test_init_rerun_hooks_follow_the_committed_output_policy_not_the_local_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The committed ``.pre-commit-config.yaml`` follows the committed ``[output]``:
    a personal ``commit = true`` used to swap in the legacy drift hook for everyone."""
    args = _init_then_add_committed_user_choice(tmp_path)
    pre_commit = tmp_path / ".pre-commit-config.yaml"
    hooks_before = pre_commit.read_text()
    (tmp_path / ".coding-agent-playbook.local.toml").write_text(_LOCAL_OVERRIDES)
    capsys.readouterr()

    assert _init.run(args) == 0

    assert pre_commit.read_text() == hooks_before
    assert "--hook-type post-checkout" in capsys.readouterr().out


_UNMANAGED_COMMITTED_TABLES = """
[links]
allowed_domains = ["example.com", "docs.example.org"]

[metrics]
mode = "both"
fail_on_breach = false
test_cmd = ["python", "-m", "pytest", "-q"]

[metrics.thresholds.cyclomatic_complexity]
warn = 10
fail = 20.5

[metrics.thresholds.maintainability_index]
fail = 70.0

[metrics.regression.coverage]
max_worsening = 0.0

[metrics.weights]
cyclomatic_complexity = 1.0
coverage = 0.25

[future_feature]
since = 2026-10-14
stamp = 1979-05-27T00:32:00-07:00
ratio = 1e-05
labels = ["a", 1, { nested = true }]

[future_feature.deep.deeper]
leaf = "kept"

[[future_feature.rules]]
id = "r1"
"""


def test_init_rerun_preserves_committed_tables_config_does_not_manage(tmp_path: Path) -> None:
    """Regression: ``[links]`` and ``[metrics]`` are read from the raw TOML by
    ``validate`` / ``metrics``, not carried by ``Config``, so the round trip
    through ``Config`` deleted them (and any future table) although init promised
    to preserve what it does not know. Every such key now comes back as the same
    parsed value — floats, 3-level tables, arrays of tables and top-level keys too."""
    _pyproject(tmp_path)
    args = _ns(tmp_path, name="r", kind="python-library")
    assert _init.run(args) == 0
    primary = tmp_path / ".coding-agent-playbook.toml"
    text = primary.read_text().replace(
        "schema_version = 1\n", 'schema_version = 1\nfuture_top_level = "kept"\n', 1
    )
    primary.write_text(text + _UNMANAGED_COMMITTED_TABLES)
    before = tomllib.loads(primary.read_text())

    assert _init.run(args) == 0

    after = tomllib.loads(primary.read_text())
    # Type-strict: ``==`` would let ``1.0`` come back as ``1`` or the stamp at +00:00.
    assert_toml_identical(after, before)
    assert after["metrics"]["thresholds"]["cyclomatic_complexity"] == {"warn": 10, "fail": 20.5}
    assert after["future_top_level"] == "kept"


_STALE_COMMITTED = """\
schema_version = 1
overlays_enabled = ["coding_agent_playbook.plugins.superpowers"]
adapters_enabled = ["continue"]

[project]
name = "old-name"
kind = "python-library"
description = "an old description"

[engine]
version = "0.1.0a0"

[detector_cache]
python_version = "3.11"

[detector_cache.frameworks]
stale_framework = "1.0"
"""


def test_init_rerun_replaces_the_tables_config_manages_without_resurrecting(
    tmp_path: Path,
) -> None:
    """Keys ``Config`` manages are replaced wholesale, never deep-merged with the
    committed table: an emptied ``--overlays``, a dropped description and a stale
    detector entry must not come back from the file being rewritten."""
    _pyproject(tmp_path)
    (tmp_path / ".coding-agent-playbook.toml").write_text(_STALE_COMMITTED)

    assert _init.run(_ns(tmp_path, name="r", kind="python-library", overlays="")) == 0

    with (tmp_path / ".coding-agent-playbook.toml").open("rb") as f:
        data = tomllib.load(f)
    assert "overlays_enabled" not in data
    assert data["project"] == {"name": "r", "kind": "python-library"}
    assert "stale_framework" not in data["detector_cache"].get("frameworks", {})
    assert data["detector_cache"]["python_version"] != "3.11"
    assert data["adapters_enabled"] == [
        "continue",
        *(name for name in DEFAULT_ADAPTERS if name != "continue"),
    ]


_COMMITTED_WITH_UNKNOWN_SUB_KEYS = """\
schema_version = 1

[project]
name = "old-name"
kind = "python-library"
description = "an old description"
homepage = "https://r.example"

[project.urls]
docs = "https://docs.r.example"

[engine]
version = "0.1.0a0"
channel = "beta"

[storage]
artifact_source = "filesystem"
state_source = "filesystem"
cache_dir = ".cache"

[output]
commit = false
reviewed = 2026-10-14
"""


def test_init_rerun_keeps_unknown_keys_inside_the_tables_config_manages(tmp_path: Path) -> None:
    """Regression: a re-run replaced ``[project]``/``[engine]``/``[storage]``/``[output]``
    whole, silently deleting a hand-added ``[project] homepage`` and the like.
    ``Config``'s own keys are still replaced — the dropped description stays
    dropped — and the rest of each table is written back as parsed."""
    _pyproject(tmp_path)
    primary = tmp_path / ".coding-agent-playbook.toml"
    primary.write_text(_COMMITTED_WITH_UNKNOWN_SUB_KEYS)

    assert _init.run(_ns(tmp_path, name="r", kind="python-library")) == 0

    data = tomllib.loads(primary.read_text())
    before = tomllib.loads(_COMMITTED_WITH_UNKNOWN_SUB_KEYS)
    expected_project = {"name": "r", "kind": "python-library"}
    expected_project |= {key: before["project"][key] for key in ("homepage", "urls")}
    assert_toml_identical(data["project"], expected_project)
    for table in ("engine", "storage", "output"):
        assert_toml_identical(data[table], before[table])


@pytest.mark.parametrize(
    ("committed_output", "written_output"),
    [(OutputConfig(commit=True), OutputConfig(commit=True)), (None, OutputConfig(commit=False))],
)
def test_apply_answers_replaces_answered_fields_and_keeps_the_rest(
    committed_output: OutputConfig | None, written_output: OutputConfig
) -> None:
    committed = Config(
        schema_version=1,
        project=ProjectMeta("old", "python-library", "old description"),
        engine_version="0.1.0a0",
        overlays_enabled=["some_overlay"],
        adapters_enabled=["custom"],
        storage=StorageConfig(artifact_source="custom"),
        detector_cache={"stale": True},
        user_choices={"docstring_style": "numpy"},
        output=committed_output,
    )
    answers = _init._Answers(
        name="new",
        kind="python-application",
        description="",
        adapters=["continue"],
        overlays=[],
        hooks=None,
    )
    updated = _init._apply_answers(committed, answers, {"fresh": True})
    assert updated == Config(
        schema_version=1,
        project=ProjectMeta("new", "python-application"),
        engine_version="0.1.0a0",
        overlays_enabled=[],
        adapters_enabled=["custom", "continue"],
        storage=StorageConfig(artifact_source="custom"),
        detector_cache={"fresh": True},
        user_choices={"docstring_style": "numpy"},
        output=written_output,
    )
    assert committed.project.name == "old"  # a new Config; the committed one is untouched


# --- a config file init would misread stops it before its first write (SPEC §7.1)


def _snapshot(repo: Path) -> dict[str, bytes | None]:
    """Every path under ``repo`` (directories map to ``None``): catches any write."""
    return {
        path.relative_to(repo).as_posix(): path.read_bytes() if path.is_file() else None
        for path in sorted(repo.rglob("*"))
    }


def _main_init(repo: Path) -> int:
    """``playbook init`` through the CLI, so a ``ConfigError`` maps to ``error:`` + exit 2."""
    argv = ["init", "--repo-root", str(repo), "--non-interactive", "--name", "r2"]
    return main([*argv, "--kind", "ml-research", "--adapters", "claude_code,agent_harness"])


@pytest.mark.parametrize("rerun", [True, False], ids=["rerun", "first-run"])
@pytest.mark.parametrize(
    ("local", "error"),
    [
        pytest.param(
            '[output]\ncommit = "yes"\n',
            "error: .coding-agent-playbook.local.toml: "
            "[output] commit must be a boolean (true or false), got 'yes'\n",
            id="output-not-a-bool",
        ),
        pytest.param(
            'project = "x"\n',
            "error: .coding-agent-playbook.local.toml: [project] must be a table, got 'x'; ",
            id="project-not-a-table",
        ),
        pytest.param(
            "[user_choices\n",
            "error: .coding-agent-playbook.local.toml: invalid TOML: ",
            id="invalid-toml",
        ),
    ],
)
def test_init_refuses_a_local_file_config_rejects_before_writing_anything(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], rerun: bool, local: str, error: str
) -> None:
    """Regression: the up-front local check only ran the enabled-list check, and
    the re-run stopped loading the merged config, so these local files surfaced
    from init's final sync — after it had rewritten the committed config (new
    name, kind, adapters) and merged ``.pre-commit-config.yaml``; a TOML syntax
    error was a traceback. The local file is now checked whole, up front, naming
    it — on a first run too."""
    _pyproject(tmp_path)
    if rerun:
        assert _init.run(_ns(tmp_path, name="r", kind="python-library")) == 0
    (tmp_path / ".coding-agent-playbook.local.toml").write_text(local)
    before = _snapshot(tmp_path)
    capsys.readouterr()

    assert _main_init(tmp_path) == 2

    assert capsys.readouterr().err.startswith(error)
    assert _snapshot(tmp_path) == before


def test_init_refuses_a_committed_config_missing_a_key_only_the_local_file_supplies(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: with ``[engine] version`` only in the gitignored local file
    (``sync``, which merges both, still works), a re-run crashed with a bare
    ``KeyError: 'version'`` traceback, exit 1. Init must neither copy that
    personal value into the committed file (as before v0.18) nor guess a
    team-wide one, so it refuses — naming the committed file and the line to
    add, exit 2 like every other config error — before writing anything."""
    _pyproject(tmp_path)
    assert _init.run(_ns(tmp_path, name="r", kind="python-library")) == 0
    primary = tmp_path / ".coding-agent-playbook.toml"
    without_engine = re.sub(r'\[engine\]\nversion = "[^"]*"\n\n', "", primary.read_text())
    assert "[engine]" not in without_engine  # the fixture took
    primary.write_text(without_engine)
    local = '[engine]\nversion = "0.1.0a0"\n'
    (tmp_path / ".coding-agent-playbook.local.toml").write_text(local)
    before = _snapshot(tmp_path)
    capsys.readouterr()

    assert _main_init(tmp_path) == 2

    assert capsys.readouterr().err == (
        "error: .coding-agent-playbook.toml: the required key engine.version is missing; "
        'write version = "<engine version>" under the [engine] header\n'
    )
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    ("committed", "table"),
    [
        pytest.param('user_choices = "x"', "user_choices", id="user-choices"),
        pytest.param('storage = "x"', "storage", id="storage"),
        pytest.param('detector_cache = ["x"]', "detector_cache", id="detector-cache"),
    ],
)
def test_init_rerun_refuses_a_committed_non_table_the_local_file_hides(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], committed: str, table: str
) -> None:
    """Regression: the local table replaced the committed scalar in the merge (the
    ``[user_choices]`` local file init itself creates always hid one), so ``sync``
    ran, but a re-run — reading the committed file alone — crashed with a
    ``ValueError``/``AttributeError`` traceback (exit 1). It is now a
    ``ConfigError`` naming the committed file, exit 2, nothing written."""
    _pyproject(tmp_path)
    assert _init.run(_ns(tmp_path, name="r", kind="python-library")) == 0
    primary = tmp_path / ".coding-agent-playbook.toml"
    data = tomllib.loads(primary.read_text(encoding="utf-8"))
    data.pop(table, None)
    primary.write_text(f"{committed}\n{dump_toml(data)}", encoding="utf-8")
    (tmp_path / ".coding-agent-playbook.local.toml").write_text(f"[{table}]\n")
    before = _snapshot(tmp_path)
    capsys.readouterr()

    assert _main_init(tmp_path) == 2

    err = capsys.readouterr().err
    assert err.startswith(f"error: .coding-agent-playbook.toml: [{table}] must be a table, got ")
    assert _snapshot(tmp_path) == before


def test_init_writes_nothing_when_catalog_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A broken install exits 2 in init's preflight, never leaving a half-initialized repo."""
    expected = break_catalog(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    before = _snapshot(repo)

    argv = ["init", "--repo-root", str(repo), "--non-interactive", "--name", "x"]
    assert main([*argv, "--kind", "python-library"]) == 2

    assert capsys.readouterr().err == expected
    assert _snapshot(repo) == before
