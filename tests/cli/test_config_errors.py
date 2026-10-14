"""A config the engine would misread stops every command before it writes (SPEC §7.1).

Before v0.17 the ``[overlays] enabled`` / ``[adapters] enabled`` table form was
read as two empty lists: ``playbook sync`` exited 0, rendered with only
``agents_md``, and settled every other adapter's earlier output as leftovers
(e.g. "1 files written, 278 removed" in a repo synced with the superpowers
pack). Every command that loads the config now exits 2 with an ``error:`` that
names the file, and the tree is left byte-identical. So does following the fix-it
hint *in place* (the key then nests under the table above it), appending the key
after the last table, or misspelling it.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.cli import main
from coding_agent_playbook.packs.superpowers import PACK_NAME
from tests.conftest import _DEFAULT_CONFIG
from tests.packs.superpowers_expectations import write_consumer_repo

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# Every command below loads the config; ``sync`` modes would also call git.
pytestmark = pytest.mark.usefixtures("hermetic_git_env")

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

_PRIMARY = ".coding-agent-playbook.toml"
_LOCAL = ".coding-agent-playbook.local.toml"

_HINT = "use the top-level key instead, at the top of the file, above the first [table] header: "

#: The table form README step 4 and SPEC §7.1 used to show, opting into the pack.
_TABLE_FORM_CONFIG = f"""\
schema_version = 1

[project]
name = "synthetic"
kind = "python-library"

[engine]
version = "0.1.0a0"

[overlays]
enabled = ["{PACK_NAME}"]

[adapters]
enabled = ["continue", "claude_code", "opencode", "shared_skills"]
"""

_ADAPTERS_LINE = 'adapters_enabled = ["continue", "claude_code", "opencode", "shared_skills"]'

#: The fix-it hint applied line for line where each table stood: TOML then reads
#: both keys as part of the [engine] table above them, so neither is top-level.
_IN_PLACE_FIX_CONFIG = _TABLE_FORM_CONFIG.replace(
    f'[overlays]\nenabled = ["{PACK_NAME}"]', f'overlays_enabled = ["{PACK_NAME}"]'
).replace(f"[adapters]\nenabled = {_ADAPTERS_LINE.partition(' = ')[2]}", _ADAPTERS_LINE)

#: The top-level keys appended after the last table ([output] here).
_APPENDED_CONFIG = (
    _TABLE_FORM_CONFIG.partition("[overlays]")[0]
    + f'[output]\ncommit = false\n\noverlays_enabled = ["{PACK_NAME}"]\n{_ADAPTERS_LINE}\n'
)

#: The keys at the top level, but misspelled.
_MISSPELLED_CONFIG = (
    f'overlay_enabled = ["{PACK_NAME}"]\n{_ADAPTERS_LINE}\n'
    + _TABLE_FORM_CONFIG.partition("[overlays]")[0]
)

_COMMANDS = [
    pytest.param(["sync"], id="sync"),
    pytest.param(["sync", "--check"], id="sync-check"),
    pytest.param(["sync", "--check-staged"], id="sync-check-staged"),
    pytest.param(["validate"], id="validate"),
    pytest.param(["check"], id="check"),
    pytest.param(["check", "--refresh"], id="check-refresh"),
    pytest.param(["render", "style"], id="render"),
    pytest.param(["eval", "--list"], id="eval-list"),
]

#: Each misread config, with the first line its error must start with.
_MISREAD_CONFIGS = [
    pytest.param(
        _IN_PLACE_FIX_CONFIG,
        f"error: {_PRIMARY}: 'overlays_enabled' in the [engine] table is not read",
        id="hint-applied-in-place",
    ),
    pytest.param(
        _APPENDED_CONFIG,
        f"error: {_PRIMARY}: 'overlays_enabled' in the [output] table is not read",
        id="appended-after-the-last-table",
    ),
    pytest.param(
        _MISSPELLED_CONFIG,
        f"error: {_PRIMARY}: the top-level key 'overlay_enabled' is not read",
        id="misspelled",
    ),
]


def _snapshot(repo: Path) -> dict[str, bytes | None]:
    """Every path under ``repo`` outside ``.git/`` (directories map to ``None``).

    Comparing two snapshots catches added, removed, and rewritten paths alike.
    """
    return {
        path.relative_to(repo).as_posix(): path.read_bytes() if path.is_file() else None
        for path in sorted(repo.rglob("*"))
        if ".git" not in path.relative_to(repo).parts
    }


def _run(argv: list[str], repo: Path) -> int:
    return main([*argv, "--repo-root", str(repo)])


@pytest.mark.parametrize("argv", _COMMANDS)
def test_every_command_refuses_the_table_form_before_writing(
    argv: list[str],
    tmp_path: Path,
    make_synthetic_repo: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_synthetic_repo(tmp_path, config_text=_TABLE_FORM_CONFIG, rules=[("style", "B\n")])
    before = _snapshot(repo)

    assert _run(argv, repo) == 2

    captured = capsys.readouterr()
    assert captured.err.startswith(f"error: {_PRIMARY}: the [overlays] table is not read")
    assert f'{_HINT}overlays_enabled = ["{PACK_NAME}"]' in captured.err
    assert f"\n{_PRIMARY}: the [adapters] table is not read" in captured.err
    assert captured.out == ""
    assert _snapshot(repo) == before


def test_check_staged_refuses_the_table_form_even_under_committed_output(
    tmp_path: Path,
    make_synthetic_repo: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--check-staged`` is a no-op under ``commit = true`` — but only once the
    config has loaded: a misread config still exits 2 (SPEC §12.3.1)."""
    config = _TABLE_FORM_CONFIG + "\n[output]\ncommit = true\n"
    repo = make_synthetic_repo(tmp_path, config_text=config, rules=[("style", "B\n")])
    before = _snapshot(repo)

    assert _run(["sync", "--check-staged"], repo) == 2

    assert capsys.readouterr().err.startswith(
        f"error: {_PRIMARY}: the [overlays] table is not read"
    )
    assert _snapshot(repo) == before


@pytest.mark.parametrize(("config", "first_line"), _MISREAD_CONFIGS)
@pytest.mark.parametrize("argv", _COMMANDS)
def test_every_command_refuses_a_nested_or_misspelled_enabled_key(
    argv: list[str],
    config: str,
    first_line: str,
    tmp_path: Path,
    make_synthetic_repo: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_synthetic_repo(tmp_path, config_text=config, rules=[("style", "B\n")])
    before = _snapshot(repo)

    assert _run(argv, repo) == 2

    captured = capsys.readouterr()
    assert captured.err.startswith(first_line)
    assert f'{_HINT}overlays_enabled = ["{PACK_NAME}"]' in captured.err
    assert captured.out == ""
    assert _snapshot(repo) == before


@pytest.mark.parametrize("argv", [["sync"], ["validate"], ["check"]])
def test_an_empty_overlay_name_is_a_config_error_not_a_traceback(
    argv: list[str],
    tmp_path: Path,
    make_synthetic_repo: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _DEFAULT_CONFIG.replace("overlays_enabled = []", 'overlays_enabled = [""]')
    repo = make_synthetic_repo(tmp_path, config_text=config)
    before = _snapshot(repo)

    assert _run(argv, repo) == 2

    assert capsys.readouterr().err == (
        f"error: {_PRIMARY}: overlays_enabled lists an empty name, got ['']; "
        "remove the empty entry\n"
    )
    assert _snapshot(repo) == before


def test_a_table_in_the_local_file_names_the_local_file(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    (repo / _LOCAL).write_text('[adapters]\nenabled = ["claude_code"]\n', encoding="utf-8")
    before = _snapshot(repo)

    assert _run(["sync"], repo) == 2

    err = capsys.readouterr().err
    assert err.startswith(f"error: {_LOCAL}: the [adapters] table is not read")
    assert err.rstrip().endswith('adapters_enabled = ["claude_code"]')
    assert _snapshot(repo) == before


def test_a_string_overlays_enabled_is_refused(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    config = _DEFAULT_CONFIG.replace("overlays_enabled = []", f'overlays_enabled = "{PACK_NAME}"')
    repo = make_synthetic_repo(tmp_path, config_text=config)
    before = _snapshot(repo)

    assert _run(["sync"], repo) == 2

    err = capsys.readouterr().err
    assert err.startswith(f"error: {_PRIMARY}: overlays_enabled must be a list of strings")
    assert f'write overlays_enabled = ["{PACK_NAME}"]' in err
    assert _snapshot(repo) == before


def test_a_non_boolean_output_commit_is_a_clean_error(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Was a traceback; every config error now shares the ``error:`` + exit 2 path."""
    repo = make_synthetic_repo(
        tmp_path, config_text=_DEFAULT_CONFIG + '\n[output]\ncommit = "no"\n'
    )

    assert _run(["sync"], repo) == 2

    err = capsys.readouterr().err
    assert err == "error: [output] commit must be a boolean (true or false), got 'no'\n"


def _init_argv(repo: Path) -> list[str]:
    return [
        "init",
        "--repo-root",
        str(repo),
        "--non-interactive",
        "--name",
        "x",
        "--kind",
        "python-library",
    ]


def _write_pyproject(repo: Path) -> None:
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "x"\nrequires-python = ">=3.12"\ndependencies = []\n', encoding="utf-8"
    )


def test_init_refuses_an_existing_table_form_config_before_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_pyproject(tmp_path)
    (tmp_path / _PRIMARY).write_text(_TABLE_FORM_CONFIG, encoding="utf-8")
    before = _snapshot(tmp_path)

    assert main(_init_argv(tmp_path)) == 2

    assert capsys.readouterr().err.startswith(f"error: {_PRIMARY}: the [overlays] table")
    assert _snapshot(tmp_path) == before


def test_init_refuses_a_table_form_local_file_before_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No primary config yet, so only an up-front check of the local file stops init."""
    _write_pyproject(tmp_path)
    (tmp_path / _LOCAL).write_text("[overlays]\nenabled = []\n", encoding="utf-8")
    before = _snapshot(tmp_path)

    assert main(_init_argv(tmp_path)) == 2

    assert capsys.readouterr().err.startswith(f"error: {_LOCAL}: the [overlays] table")
    assert _snapshot(tmp_path) == before


# --------------------------------------------------------------------------- #
# The safety test: a pack-synced repo, then the config switches to the table form
# --------------------------------------------------------------------------- #


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, timeout=10)


def _table_form_in_primary(repo: Path) -> None:
    (repo / _PRIMARY).write_text(_TABLE_FORM_CONFIG, encoding="utf-8")


def _table_form_in_local(repo: Path) -> None:
    (repo / _LOCAL).write_text('[adapters]\nenabled = ["claude_code"]\n', encoding="utf-8")


def _hint_applied_in_place_in_primary(repo: Path) -> None:
    (repo / _PRIMARY).write_text(_IN_PLACE_FIX_CONFIG, encoding="utf-8")


def _appended_after_the_last_table_in_primary(repo: Path) -> None:
    (repo / _PRIMARY).write_text(_APPENDED_CONFIG, encoding="utf-8")


def _misspelled_in_primary(repo: Path) -> None:
    (repo / _PRIMARY).write_text(_MISSPELLED_CONFIG, encoding="utf-8")


def _appended_to_the_init_written_local_file(repo: Path) -> None:
    """``playbook init`` writes the local file as ``[user_choices]`` only."""
    (repo / _LOCAL).write_text('[user_choices]\nadapters_enabled = ["claude_code"]\n', "utf-8")


@needs_git
@pytest.mark.parametrize(
    "switch_to_table_form",
    [
        pytest.param(_table_form_in_primary, id="primary"),
        pytest.param(_table_form_in_local, id="local"),
        pytest.param(_hint_applied_in_place_in_primary, id="primary-hint-applied-in-place"),
        pytest.param(_appended_after_the_last_table_in_primary, id="primary-appended"),
        pytest.param(_misspelled_in_primary, id="primary-misspelled"),
        pytest.param(_appended_to_the_init_written_local_file, id="local-appended"),
    ],
)
def test_a_pack_synced_repo_is_untouched_when_the_config_switches_to_the_table_form(
    switch_to_table_form: Callable[[Path], None],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = write_consumer_repo(tmp_path, overlays=[PACK_NAME])
    _git(repo, "init", "-q")
    assert _run(["sync"], repo) == 0
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-verify", "-m", "sources")
    # The pack output, its lockfile entries and the managed block all exist.
    assert (repo / ".claude" / "skills" / "brainstorming" / "SKILL.md").is_file()
    assert "brainstorming" in (repo / ".coding-agent-playbook.lock").read_text(encoding="utf-8")
    assert "/.claude/skills/brainstorming/" in (repo / ".gitignore").read_text(encoding="utf-8")
    switch_to_table_form(repo)
    before = _snapshot(repo)
    capsys.readouterr()

    for argv in (["sync"], ["sync", "--check"], ["sync", "--check-staged"]):
        assert _run(argv, repo) == 2, argv
        assert " is not read (found " in capsys.readouterr().err, argv

    # Byte-identical: no skill removed, lockfile not restamped, block not shrunk.
    assert _snapshot(repo) == before
