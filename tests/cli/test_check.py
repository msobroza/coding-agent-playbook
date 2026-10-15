"""Tests for ``playbook check`` (PR 10 Task 5)."""

from __future__ import annotations

import argparse
import re
import tomllib
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.cli import main
from coding_agent_playbook.commands import check as _check
from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.packs.superpowers import PACK_NAME
from tests.toml_equality import assert_toml_identical

if TYPE_CHECKING:
    from pathlib import Path


def _ns(repo: Path, **kwargs: object) -> argparse.Namespace:
    base: dict[str, object] = {"repo_root": str(repo), "refresh": False}
    base.update(kwargs)
    return argparse.Namespace(**base)


def test_check_prints_all_sections(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(
        tmp_path,
        rules=[("rule-a", "Body a\n")],
        prompts=[("refactor", {"slash": "refactor"})],
    )
    rc = _check.run(_ns(repo))
    assert rc == 0
    out = capsys.readouterr().out
    assert "=== Environment ===" in out
    assert "=== Detected ===" in out
    assert "=== Artifacts ===" in out
    assert "=== Drift ===" in out
    # SPEC §12.4: applicable artifacts use the unicode tick marker.
    assert "[✓]" in out


def test_check_artifact_section_marks_applies_if(tmp_path, make_synthetic_repo, capsys):
    """A rule with applies_if not matching the facts should show as not-applicable."""
    repo = make_synthetic_repo(tmp_path)
    # Inject a rule with a predicate the facts can't satisfy.
    rules_dir = repo / "playbook" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "scoped.md").write_text(
        "---\n"
        "id: scoped\n"
        "name: Scoped Rule\n"
        "description: Only for repos with Hadoop\n"
        "scope: scoped\n"
        "priority: 50\n"
        "applies_if:\n"
        "  has_framework:\n"
        "    - some-framework-that-isnt-installed\n"
        "---\n"
        "Body\n",
        encoding="utf-8",
    )
    rc = _check.run(_ns(repo))
    assert rc == 0
    out = capsys.readouterr().out
    # The rule should appear with the not-applicable marker.
    assert "scoped" in out
    assert "[✗]" in out
    # Skip reason mirrors SPEC §12.4: the failing predicate key is surfaced.
    assert "skipped: applies_if has_framework=" in out
    assert "some-framework-that-isnt-installed" in out


def test_check_drift_section_reports_drift(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body\n")])
    sync_args = argparse.Namespace(repo_root=str(repo), check=False)
    _sync.run(sync_args)
    # Mutate AGENTS.md so its hash no longer matches the lockfile entry.
    (repo / "AGENTS.md").write_text("MUTATED\n", encoding="utf-8")
    capsys.readouterr()
    rc = _check.run(_ns(repo))
    assert rc == 0
    out = capsys.readouterr().out
    assert "hash mismatch" in out
    assert "AGENTS.md" in out


def test_check_refresh_updates_detector_cache(tmp_path, make_synthetic_repo):
    repo = make_synthetic_repo(tmp_path)
    # Update pyproject after the config was written — the cache should pick
    # up the new dependency once refresh runs.
    (repo / "pyproject.toml").write_text(
        '[project]\nname="x"\nrequires-python=">=3.12"\ndependencies=["fastapi"]\n'
    )
    rc = _check.run(_ns(repo, refresh=True))
    assert rc == 0
    with (repo / ".coding-agent-playbook.toml").open("rb") as f:
        data = tomllib.load(f)
    # fastapi should appear in either dependencies or frameworks after refresh.
    cache = data.get("detector_cache", {})
    assert "fastapi" in (cache.get("dependencies") or {}) or "fastapi" in (
        cache.get("frameworks") or {}
    )


# --- --refresh rewrites [detector_cache] in the committed config, nothing else (SPEC §7.2)

_PRIMARY = ".coding-agent-playbook.toml"
_LOCAL = ".coding-agent-playbook.local.toml"

#: Hand-added committed content ``Config`` does not manage — tables ``validate`` /
#: ``metrics`` read from the raw TOML, a future table — plus a stale
#: ``[detector_cache]`` entry, which the refresh must drop (regenerated whole).
_HAND_ADDED_COMMITTED = """
[links]
allowed_domains = ["example.com"]

[metrics]
mode = "absolute"

[metrics.weights]
coverage = 0.25

[future_feature]
since = 2026-10-14

[detector_cache.stale_table]
left = true
"""

#: A teammate's personal overrides in the gitignored local file: keys ``Config``
#: owns and tables it does not manage. None of them may reach the committed file.
_LOCAL_OVERRIDES = f"""\
adapters_enabled = ["claude_code"]
overlays_enabled = ["{PACK_NAME}"]

[user_choices]
style = "google"

[output]
commit = true

[metrics]
mode = "regression"

[personal_table]
note = "mine only"
"""


def _init_repo(repo: Path) -> Path:
    """``playbook init`` a repo with no dependencies yet; return its committed config."""
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "r"\nrequires-python = ">=3.12"\ndependencies = []\n', encoding="utf-8"
    )
    argv = ["init", "--repo-root", str(repo), "--non-interactive", "--name", "r"]
    assert main([*argv, "--kind", "python-library"]) == 0
    return repo / _PRIMARY


def _check_refresh(repo: Path) -> int:
    """``playbook check --refresh`` through the CLI, so a config error exits 2."""
    return main(["check", "--refresh", "--repo-root", str(repo)])


def _without_cache(table: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in table.items() if key != "detector_cache"}


def _snapshot(repo: Path) -> dict[str, bytes | None]:
    """Every path under ``repo`` outside ``.git/`` (directories map to ``None``)."""
    return {
        path.relative_to(repo).as_posix(): path.read_bytes() if path.is_file() else None
        for path in sorted(repo.rglob("*"))
        if ".git" not in path.relative_to(repo).parts
    }


@pytest.mark.usefixtures("hermetic_git_env")
def test_check_refresh_never_writes_local_overrides_into_the_committed_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: ``--refresh`` saved ``ctx.config`` — the config *merged* with the
    gitignored ``.local.toml`` — to the committed file, committing one teammate's
    adapters, overlays, ``[user_choices]`` and ``[output]`` for the whole team, and
    the round trip through ``Config`` deleted ``[links]``, ``[metrics]`` and every
    other table it does not manage. Only ``[detector_cache]`` changes now, and the
    report still describes the merged config."""
    primary = _init_repo(tmp_path)
    text = primary.read_text(encoding="utf-8")
    homepage = 'kind = "python-library"\nhomepage = "https://r.example"\n'
    with_homepage = text.replace('kind = "python-library"\n', homepage, 1)
    assert with_homepage != text  # the fixture took
    primary.write_text(with_homepage + _HAND_ADDED_COMMITTED, encoding="utf-8")
    local = tmp_path / _LOCAL
    local.write_text(_LOCAL_OVERRIDES, encoding="utf-8")
    local_bytes = local.read_bytes()
    # A new dependency, so the refresh has something to write.
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace("[]", '["fastapi"]'), encoding="utf-8")
    before = tomllib.loads(primary.read_text(encoding="utf-8"))
    assert "fastapi" not in before["detector_cache"].get("dependencies", {})
    capsys.readouterr()

    assert _check_refresh(tmp_path) == 0

    after = tomllib.loads(primary.read_text(encoding="utf-8"))
    # Type-strict, on every key but the cache: nothing local leaks in, nothing committed goes.
    assert_toml_identical(_without_cache(after), _without_cache(before))
    assert "fastapi" in after["detector_cache"]["dependencies"]
    assert "stale_table" not in after["detector_cache"]
    assert local.read_bytes() == local_bytes
    out = capsys.readouterr().out
    assert out.startswith(f"Refreshed detector_cache in {_PRIMARY}.\n")
    assert f"\n  Overlays: {PACK_NAME}\n" in out  # the local overlay list, as sync would run


@pytest.mark.usefixtures("hermetic_git_env")
def test_check_refresh_refuses_a_committed_config_missing_a_key_only_the_local_file_supplies(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: with ``[engine] version`` only in the gitignored local file,
    ``check`` (which merges both files) loads, and ``--refresh`` then copied that
    personal value into the committed file. Like ``init``, it now refuses — exit 2,
    naming the committed file and the line to add — before writing or printing."""
    primary = _init_repo(tmp_path)
    without_engine = re.sub(r'\[engine\]\nversion = "[^"]*"\n\n', "", primary.read_text())
    assert "[engine]" not in without_engine  # the fixture took
    primary.write_text(without_engine, encoding="utf-8")
    (tmp_path / _LOCAL).write_text('[engine]\nversion = "0.1.0a0"\n', encoding="utf-8")
    before = _snapshot(tmp_path)
    capsys.readouterr()

    assert _check_refresh(tmp_path) == 2

    captured = capsys.readouterr()
    assert captured.err == (
        f"error: {_PRIMARY}: the required key engine.version is missing; "
        'write version = "<engine version>" under the [engine] header\n'
    )
    assert captured.out == ""
    assert _snapshot(tmp_path) == before


@pytest.mark.usefixtures("hermetic_git_env")
@pytest.mark.parametrize(
    ("local", "error"),
    [
        pytest.param(
            '[output]\ncommit = "yes"\n',
            f"error: {_LOCAL}: [output] commit must be a boolean (true or false), got 'yes'\n",
            id="output-not-a-bool",
        ),
        pytest.param(
            'project = "x"\n',
            # Regression: the merged-table check named the committed file.
            f"error: {_LOCAL}: [project] must be a table, got 'x'; ",
            id="project-not-a-table",
        ),
        pytest.param(
            'user_choices = "x"\n',
            f"error: {_LOCAL}: [user_choices] must be a table, got 'x'; ",
            id="user-choices-not-a-table",
        ),
        pytest.param(
            "broken = [\n",
            f"error: {_LOCAL}: invalid TOML: ",
            id="invalid-toml",
        ),
        pytest.param(
            '[adapters]\nenabled = ["claude_code"]\n',
            f"error: {_LOCAL}: the [adapters] table is not read",
            id="adapters-table-form",
        ),
    ],
)
def test_check_refresh_refuses_a_broken_local_file_before_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], local: str, error: str
) -> None:
    """The refresh no longer saves the merged config, but a local file the engine
    would misread is still reported (exit 2) and nothing is written."""
    _init_repo(tmp_path)
    (tmp_path / _LOCAL).write_text(local, encoding="utf-8")
    before = _snapshot(tmp_path)
    capsys.readouterr()

    assert _check_refresh(tmp_path) == 2

    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert error in captured.err
    assert captured.out == ""
    assert _snapshot(tmp_path) == before


#: Every command that loads the config, as ``main`` arguments (``--repo-root`` appended).
_LOADING_COMMANDS = [
    pytest.param(["check"], id="check"),
    pytest.param(["check", "--refresh"], id="refresh"),
    pytest.param(["sync"], id="sync"),
    pytest.param(["validate"], id="validate"),
]


def _run_failing(repo: Path, command: list[str], capsys: pytest.CaptureFixture[str]) -> str:
    """Run ``command`` on ``repo``; assert exit 2 with nothing written; return stderr."""
    before = _snapshot(repo)
    capsys.readouterr()
    assert main([*command, "--repo-root", str(repo)]) == 2
    assert _snapshot(repo) == before
    return capsys.readouterr().err


@pytest.mark.usefixtures("hermetic_git_env")
@pytest.mark.parametrize("command", _LOADING_COMMANDS)
def test_every_command_names_the_local_file_for_a_table_it_breaks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], command: list[str]
) -> None:
    """Regression: ``load_config`` checked the shape on the merged table and blamed
    the committed file for a local ``project = "x"``, while ``init`` named the
    local one. Each file is now checked on its own first, in every command."""
    _init_repo(tmp_path)
    (tmp_path / _LOCAL).write_text('project = "x"\n', encoding="utf-8")
    err = _run_failing(tmp_path, command, capsys)
    assert err.startswith(f"error: {_LOCAL}: [project] must be a table, got 'x'; ")


@pytest.mark.usefixtures("hermetic_git_env")
@pytest.mark.parametrize("command", _LOADING_COMMANDS)
@pytest.mark.parametrize(
    ("committed", "local_table"),
    [
        pytest.param('user_choices = "x"', "user_choices", id="user-choices"),
        pytest.param('storage = "x"', "storage", id="storage"),
        pytest.param('detector_cache = ["x"]', "detector_cache", id="detector-cache"),
    ],
)
def test_a_committed_non_table_hidden_by_a_local_table_is_refused_everywhere(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    command: list[str],
    committed: str,
    local_table: str,
) -> None:
    """Regression: the local table replaced the committed scalar in the merge, so
    ``check``/``sync``/``validate`` ran while ``check --refresh`` (and ``init``),
    reading the committed file alone, crashed with a traceback (exit 1); teammates
    without that local file crashed in every command. Now every command refuses
    the committed file, naming it (exit 2)."""
    primary = _init_repo(tmp_path)
    body = primary.read_text(encoding="utf-8").replace("schema_version = 1\n", "", 1)
    # Drop the table init wrote (and its sub-tables): a second key would not parse.
    body = re.sub(rf"(?ms)^\[{local_table}(\.[^\]]*)?\]\n.*?(?=^\[|\Z)", "", body)
    primary.write_text(f"schema_version = 1\n{committed}\n{body}", encoding="utf-8")
    assert not isinstance(tomllib.loads(primary.read_text("utf-8"))[local_table], dict)
    (tmp_path / _LOCAL).write_text(f"[{local_table}]\n", encoding="utf-8")
    err = _run_failing(tmp_path, command, capsys)
    assert err.startswith(f"error: {_PRIMARY}: [{local_table}] must be a table, got ")


_HAND_WRITTEN_COMMITTED = """\
schema_version = 1
overlays_enabled = []
adapters_enabled = []

[project]
name = "r"
kind = "python-library"
description = ""

[engine]
version = "0.1.0a0"

[storage]
state_source = "filesystem"

[output]
note = "kept"

[user_choices]
"""


@pytest.mark.usefixtures("hermetic_git_env")
def test_check_refresh_changes_nothing_but_the_detector_cache(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: the refresh round-tripped through ``Config.to_dict``, dropping the
    explicit empty lists, ``description = ""`` and the empty ``[user_choices]``,
    and adding ``artifact_source`` and ``commit = false`` — all off SPEC §12.5's
    "only ``[detector_cache]``". Every other parsed value now stays as written."""
    primary = _init_repo(tmp_path)
    primary.write_text(_HAND_WRITTEN_COMMITTED, encoding="utf-8")
    capsys.readouterr()

    assert _check_refresh(tmp_path) == 0

    after = tomllib.loads(primary.read_text(encoding="utf-8"))
    assert_toml_identical(_without_cache(after), tomllib.loads(_HAND_WRITTEN_COMMITTED))
    assert "python_version" in after["detector_cache"]
