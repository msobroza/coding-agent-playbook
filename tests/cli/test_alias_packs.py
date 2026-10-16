"""``coding_agent_playbook.packs.<leaf>`` is a deprecated alias of ``plugins.<leaf>`` (SPEC v0.19).

Before v0.19 the bundled plugins were the ``coding_agent_playbook.packs.*``
packages. Configs naming them keep working: ``Config`` canonicalizes the name,
``SyncContext.from_repo`` prints one ``warning:`` line per deprecated name
(naming the file whose list is in effect), and ``init --overlays`` writes the
canonical name. ``check --refresh`` keeps the committed file as written
(SPEC §12.5), so only the warning nudges the user to migrate.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.bundled_content import bundled_plugins
from coding_agent_playbook.cli import main
from tests.plugins.superpowers_expectations import PLUGIN_NAME, write_consumer_repo

if TYPE_CHECKING:
    from pathlib import Path

# sync and init's final sync use the real SubprocessGitClient.
pytestmark = pytest.mark.usefixtures("hermetic_git_env")

_PRIMARY = ".coding-agent-playbook.toml"
_LOCAL = ".coding-agent-playbook.local.toml"
_OLD = "coding_agent_playbook.packs.superpowers"
_SKILL = ".claude/skills/brainstorming/SKILL.md"


def _config_warning(source: str, old: str = _OLD, new: str = PLUGIN_NAME) -> str:
    return f"warning: {source}: overlays_enabled: '{old}' is deprecated; use '{new}'"


_FLAG_WARNING = f"warning: --overlays: '{_OLD}' is deprecated; use '{PLUGIN_NAME}'"


def _run(argv: list[str], repo: Path) -> int:
    return main([*argv, "--repo-root", str(repo)])


def _committed_overlays(repo: Path) -> list[str]:
    data = tomllib.loads((repo / _PRIMARY).read_text(encoding="utf-8"))
    overlays: list[str] = data["overlays_enabled"]
    return overlays


@pytest.mark.parametrize(
    "local_text",
    [
        pytest.param(None, id="no-local-file"),
        # init always writes this local file (_write_local_config in
        # commands/init.py), so it is the most common real state: the local
        # file is the one to fix only when it sets overlays_enabled, never
        # because it merely exists.
        pytest.param("[user_choices]\n", id="local-file-without-list"),
    ],
)
def test_sync_with_pack_name_warns_once_and_renders(
    local_text: str | None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = write_consumer_repo(tmp_path, overlays=[_OLD])
    if local_text is not None:
        (repo / _LOCAL).write_text(local_text, encoding="utf-8")

    assert _run(["sync"], repo) == 0

    assert capsys.readouterr().err.splitlines() == [_config_warning(_PRIMARY)]
    assert (repo / _SKILL).is_file()


@pytest.mark.parametrize(
    "overlays",
    [
        pytest.param([_OLD, PLUGIN_NAME], id="both"),
        pytest.param([_OLD, PLUGIN_NAME, _OLD], id="old-twice"),
    ],
)
def test_both_spellings_listed(
    overlays: list[str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Review Focus 1: listing both spellings walks the plugin twice, as listing
    one name twice always did, and warns once per distinct deprecated name."""
    repo = write_consumer_repo(tmp_path, overlays=overlays)

    assert _run(["sync"], repo) == 0

    assert capsys.readouterr().err.splitlines() == [_config_warning(_PRIMARY)]
    assert (repo / _SKILL).is_file()


def test_warning_names_local_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The local list replaces the committed one (SPEC §7.2), so it is the file to fix."""
    repo = write_consumer_repo(tmp_path, overlays=[])
    (repo / _LOCAL).write_text(f'overlays_enabled = ["{_OLD}"]\n', encoding="utf-8")

    assert _run(["sync"], repo) == 0

    assert capsys.readouterr().err.splitlines() == [_config_warning(_LOCAL)]
    assert (repo / _SKILL).is_file()


def test_typo_under_old_namespace(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Review Focus 4: the warning recommends the canonical spelling, and the
    preflight error that follows names that canonical spelling."""
    typo = "coding_agent_playbook.packs.superpower"
    canonical = "coding_agent_playbook.plugins.superpower"
    repo = write_consumer_repo(tmp_path, overlays=[typo])

    assert _run(["sync"], repo) == 1

    lines = capsys.readouterr().err.splitlines()
    assert lines[0] == _config_warning(_PRIMARY, old=typo, new=canonical)
    assert lines[1].startswith("error: ")
    hint = f"(bundled plugins: {', '.join(bundled_plugins())})"
    assert lines[2] == f"  {canonical}: no such bundled plugin {hint}"
    assert not (repo / _SKILL).exists()


def test_check_reports_canonical_overlay(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = write_consumer_repo(tmp_path, overlays=[_OLD])

    assert _run(["check"], repo) == 0

    captured = capsys.readouterr()
    assert f"  Overlays: {PLUGIN_NAME}" in captured.out.splitlines()
    assert captured.err.splitlines() == [_config_warning(_PRIMARY)]


def test_check_refresh_keeps_deprecated_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SPEC §12.5: ``--refresh`` rewrites only ``[detector_cache]``; the deprecated
    name stays in the committed file while the report shows the canonical one."""
    repo = write_consumer_repo(tmp_path, overlays=[_OLD])

    assert _run(["check", "--refresh"], repo) == 0

    assert _committed_overlays(repo) == [_OLD]
    captured = capsys.readouterr()
    assert f"  Overlays: {PLUGIN_NAME}" in captured.out.splitlines()
    assert captured.err.splitlines() == [_config_warning(_PRIMARY)]


def _init_argv(*extra: str) -> list[str]:
    return ["init", "--non-interactive", "--name", "x", "--kind", "python-library", *extra]


def _write_pyproject(repo: Path) -> None:
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "x"\nrequires-python = ">=3.12"\ndependencies = []\n', encoding="utf-8"
    )


def _warnings(err: str) -> list[str]:
    return [line for line in err.splitlines() if line.startswith("warning:")]


def test_init_overlays_flag_canonicalizes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A first run and a re-run write the canonical name: a re-run is the
    migration path for a committed file that still names the old package."""
    _write_pyproject(tmp_path)

    assert _run(_init_argv("--overlays", _OLD), tmp_path) == 0
    assert _committed_overlays(tmp_path) == [PLUGIN_NAME]
    assert _warnings(capsys.readouterr().err) == [_FLAG_WARNING]

    primary = tmp_path / _PRIMARY
    primary.write_text(primary.read_text(encoding="utf-8").replace(PLUGIN_NAME, _OLD))
    assert _committed_overlays(tmp_path) == [_OLD]

    assert _run(_init_argv("--overlays", _OLD), tmp_path) == 0
    assert _committed_overlays(tmp_path) == [PLUGIN_NAME]
    assert _warnings(capsys.readouterr().err) == [_FLAG_WARNING]
    assert (tmp_path / _SKILL).is_file()


def test_init_leaves_the_local_list_to_the_final_sync(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """init accepts a deprecated name in the local file and does not warn about
    it itself: its final sync's ``from_repo`` does, once, naming the local file."""
    _write_pyproject(tmp_path)
    (tmp_path / _LOCAL).write_text(f'overlays_enabled = ["{_OLD}"]\n', encoding="utf-8")

    assert _run(_init_argv(), tmp_path) == 0

    assert _warnings(capsys.readouterr().err) == [_config_warning(_LOCAL)]
    assert (tmp_path / _SKILL).is_file()
