"""An unusable overlay is reported by every command, not only ``sync`` (SPEC §11.5).

"Unusable" is the one shared preflight check (``_sync_preflight``): importing an
overlay package fails (it is missing, or its own code raises), or it imports but
ships no ``resources/`` directory (``json``, say). A bundled-plugin name is never
imported: it is unusable when no ``content/plugins/<leaf>/`` matches it ("no
such bundled plugin"), and the bare plugin namespace is never a plugin.
``sync`` refuses (exit 1), ``validate`` fails (exit 1), ``check`` flags it and
stops claiming a clean state (exit 0, it is a diagnostic), and ``init`` refuses
before writing (exit 2, a usage error) — for ``--overlays`` and for a local
file's ``overlays_enabled``, which replaces it. Each unusable overlay gets its own
line. A name that reads like a mistyped bundled plugin also lists the bundled
plugins. A package that raises at import time used to crash every command with a
traceback.
"""

from __future__ import annotations

import argparse
import tomllib
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.cli import main
from coding_agent_playbook.commands import check as _check
from coding_agent_playbook.commands import init as _init
from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.commands._sync_preflight import bundled_plugins
from tests.conftest import _DEFAULT_CONFIG
from tests.fakes import FakeGitClient
from tests.plugins.superpowers_expectations import PLUGIN_NAME

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# init ends with a real sync (SubprocessGitClient); keep git off the developer's config.
pytestmark = pytest.mark.usefixtures("hermetic_git_env")

_TYPO = "coding_agent_playbook.plugins.superpower"  # the trailing "s" is missing
_NO_RES = "json"  # importable, but no resources/ of its own
_NO_RES_REASON = "importable, but ships no resources/ directory, so it is not an overlay package"
_NAMESPACE = "coding_agent_playbook.plugins"  # the namespace itself, not a plugin
_NOT_A_PLUGIN = "no_such_overlay_pkg"


def _plugins_hint() -> str:
    return f"(bundled plugins: {', '.join(bundled_plugins())})"


def _config_with(*overlays: str) -> str:
    listed = ", ".join(f'"{overlay}"' for overlay in overlays)
    return _DEFAULT_CONFIG.replace("overlays_enabled = []", f"overlays_enabled = [{listed}]")


def _repo(tmp_path: Path, build: Callable[..., Path], *overlays: str) -> Path:
    return build(tmp_path, config_text=_config_with(*overlays), rules=[("style", "Body\n")])


def _raising_overlays(make_package: Callable[..., str]) -> tuple[str, str]:
    """A package that raises at import (with ``resources/``), and a child of one."""
    boom = make_package(
        "cap_boom_pkg", init="raise RuntimeError('boom at import')\n", resources=True
    )
    make_package("cap_boom_parent", init="raise RuntimeError('boom parent')\n")
    return boom, make_package("cap_boom_parent.sub", resources=True)


_BOOM_REASONS = (
    "cap_boom_pkg: not importable (RuntimeError: boom at import)",
    "cap_boom_parent.sub: not importable (RuntimeError: boom parent)",
)


def _ns(repo: Path, **kwargs: object) -> argparse.Namespace:
    return argparse.Namespace(repo_root=str(repo), **kwargs)


# --------------------------------------------------------------------------- #
# playbook validate
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("overlay", "expected"),
    [
        (_TYPO, f"FAIL overlays_enabled: {_TYPO}: no such bundled plugin {_plugins_hint()}"),
        (_NO_RES, f"FAIL overlays_enabled: {_NO_RES}: {_NO_RES_REASON}\n"),
        (
            _NAMESPACE,
            f"FAIL overlays_enabled: {_NAMESPACE}: the bundled plugin namespace, "
            f"not a plugin {_plugins_hint()}\n",
        ),
        (_NOT_A_PLUGIN, f"FAIL overlays_enabled: {_NOT_A_PLUGIN}: not importable\n"),
    ],
)
def test_validate_fails_on_an_unusable_overlay(
    overlay: str,
    expected: str,
    tmp_path: Path,
    make_synthetic_repo: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo, overlay)

    assert _validate.run(_ns(repo)) == 1

    out = capsys.readouterr().out
    assert expected in out
    assert "validation failed with 1 error(s)" in out


def test_validate_reports_each_unusable_overlay(
    tmp_path: Path,
    make_synthetic_repo: Callable[..., Path],
    make_package: Callable[..., str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo, _TYPO, _NO_RES, *_raising_overlays(make_package))

    assert _validate.run(_ns(repo)) == 1

    out = capsys.readouterr().out
    fails = [line for line in out.splitlines() if line.startswith("FAIL overlays_enabled: ")]
    assert fails == [
        f"FAIL overlays_enabled: {_TYPO}: no such bundled plugin {_plugins_hint()}",
        f"FAIL overlays_enabled: {_NO_RES}: {_NO_RES_REASON}",
        *(f"FAIL overlays_enabled: {reason}" for reason in _BOOM_REASONS),
    ]
    assert "validation failed with 4 error(s)" in out


def test_validate_passes_with_no_overlays(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path, rules=[("style", "Body\n")])
    assert _validate.run(_ns(repo)) == 0
    assert "overlays_enabled" not in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# playbook check
# --------------------------------------------------------------------------- #


def test_check_flags_a_misspelled_plugin_and_does_not_claim_a_clean_state(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path, rules=[("style", "Body\n")])
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    (repo / ".coding-agent-playbook.toml").write_text(_config_with(_TYPO), encoding="utf-8")
    capsys.readouterr()

    assert _check.run(_ns(repo, refresh=False)) == 0

    out = capsys.readouterr().out
    environment, _, rest = out.partition("=== Detected ===")
    assert f"  Overlays: {_TYPO}\n" in environment
    assert f"    ✗ {_TYPO}: no such bundled plugin {_plugins_hint()}\n" in environment
    assert "'playbook sync' refuses to run" in environment
    drift = rest.partition("=== Drift ===")[2]
    assert "All on-disk files match generated output." not in drift
    assert "On-disk files match the lockfile, but the state is not clean" in drift


def test_check_still_reports_a_clean_state_without_unusable_overlays(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path, rules=[("style", "Body\n")])
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    capsys.readouterr()

    assert _check.run(_ns(repo, refresh=False)) == 0

    out = capsys.readouterr().out
    assert "  Overlays: (none)\n" in out
    assert "✗" not in out.partition("=== Detected ===")[0]
    assert "All on-disk files match generated output." in out


def test_check_flags_each_unusable_overlay(
    tmp_path: Path,
    make_synthetic_repo: Callable[..., Path],
    make_package: Callable[..., str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Also a package raising at import: ``check`` used to crash with a traceback."""
    repo = _repo(
        tmp_path, make_synthetic_repo, _TYPO, _NOT_A_PLUGIN, *_raising_overlays(make_package)
    )

    assert _check.run(_ns(repo, refresh=False)) == 0

    environment = capsys.readouterr().out.partition("=== Detected ===")[0]
    flagged = [line for line in environment.splitlines() if line.startswith("    ✗ ")]
    assert flagged == [
        f"    ✗ {_TYPO}: no such bundled plugin {_plugins_hint()}",
        f"    ✗ {_NOT_A_PLUGIN}: not importable",
        *(f"    ✗ {reason}" for reason in _BOOM_REASONS),
    ]


def test_check_keeps_listing_lockfile_drift_next_to_the_overlay_problem(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path, rules=[("style", "Body\n")])
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    (repo / "AGENTS.md").write_text("edited\n", encoding="utf-8")
    (repo / ".coding-agent-playbook.toml").write_text(_config_with(_NO_RES), encoding="utf-8")
    capsys.readouterr()

    assert _check.run(_ns(repo, refresh=False)) == 0

    drift = capsys.readouterr().out.partition("=== Drift ===")[2]
    assert "  hash mismatch: AGENTS.md\n" in drift
    assert "'playbook sync' refuses to run" in drift


# --------------------------------------------------------------------------- #
# playbook init --overlays
# --------------------------------------------------------------------------- #


def _init_ns(repo: Path, overlays: str) -> argparse.Namespace:
    return argparse.Namespace(
        repo_root=str(repo),
        non_interactive=True,
        name="x",
        kind="python-library",
        description="",
        adapters=None,
        overlays=overlays,
    )


def _write_pyproject(repo: Path) -> None:
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "x"\nrequires-python = ">=3.12"\ndependencies = []\n', encoding="utf-8"
    )


@pytest.mark.parametrize(
    ("overlay", "reason"),
    [
        (_TYPO, f"{_TYPO}: no such bundled plugin {_plugins_hint()}"),
        (_NO_RES, f"{_NO_RES}: {_NO_RES_REASON}\n"),
        (_NAMESPACE, f"{_NAMESPACE}: the bundled plugin namespace, not a plugin {_plugins_hint()}"),
        (_NOT_A_PLUGIN, f"{_NOT_A_PLUGIN}: not importable\n"),
    ],
)
def test_init_refuses_an_unusable_overlay_before_writing(
    overlay: str, reason: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_pyproject(tmp_path)

    assert _init.run(_init_ns(tmp_path, overlays=f"{overlay}")) == 2

    err = capsys.readouterr().err
    assert err.startswith(
        "error: --overlays names overlay package(s) or bundled plugin(s) that cannot be used here"
    )
    assert f"\n  {reason}" in err
    assert sorted(path.name for path in tmp_path.iterdir()) == ["pyproject.toml"]


def test_init_lists_each_unusable_overlay_and_a_raising_one(
    tmp_path: Path, make_package: Callable[..., str], capsys: pytest.CaptureFixture[str]
) -> None:
    """A package raising at import used to pass, get written, then crash the sync."""
    _write_pyproject(tmp_path)
    overlays = ",".join([_TYPO, _NOT_A_PLUGIN, *_raising_overlays(make_package)])

    assert _init.run(_init_ns(tmp_path, overlays=overlays)) == 2

    err = capsys.readouterr().err
    listed = [line for line in err.splitlines() if line.startswith("  ")]
    assert listed == [
        f"  {_TYPO}: no such bundled plugin {_plugins_hint()}",
        f"  {_NOT_A_PLUGIN}: not importable",
        *(f"  {reason}" for reason in _BOOM_REASONS),
    ]
    assert sorted(path.name for path in tmp_path.iterdir()) == ["pyproject.toml"]


def test_init_checks_the_local_files_overlays_which_replace_the_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The final sync would use the local list (SPEC §7.2), so init checks that one."""
    _write_pyproject(tmp_path)
    local = tmp_path / ".coding-agent-playbook.local.toml"
    local.write_text(f'overlays_enabled = ["{_TYPO}"]\n', encoding="utf-8")

    assert _init.run(_init_ns(tmp_path, overlays=PLUGIN_NAME)) == 2

    err = capsys.readouterr().err
    assert err.startswith(
        "error: overlays_enabled in .coding-agent-playbook.local.toml names overlay package(s) "
        "or bundled plugin(s) that cannot be used here; nothing was written:"
    )
    assert f"\n  {_TYPO}: no such bundled plugin {_plugins_hint()}" in err
    assert sorted(path.name for path in tmp_path.iterdir()) == [local.name, "pyproject.toml"]


def test_init_refuses_unknown_bundled_plugin_in_local_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Review Focus 5: the final sync would refuse the local list, so init does first."""
    _write_pyproject(tmp_path)
    local = tmp_path / ".coding-agent-playbook.local.toml"
    unknown = "coding_agent_playbook.plugins.nope"
    local.write_text(f'overlays_enabled = ["{unknown}"]\n', encoding="utf-8")
    argv = ["init", "--non-interactive", "--name", "x", "--kind", "python-library"]

    assert main([*argv, "--repo-root", str(tmp_path)]) == 2

    err = capsys.readouterr().err
    assert (
        "error: overlays_enabled in .coding-agent-playbook.local.toml names overlay package(s) "
        "or bundled plugin(s)"
    ) in err
    assert f"\n  {unknown}: no such bundled plugin {_plugins_hint()}\n" in err
    assert not (tmp_path / ".coding-agent-playbook.toml").exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == [local.name, "pyproject.toml"]


@pytest.mark.parametrize("local_overlays", ["[]", f'["{PLUGIN_NAME}"]'])
def test_init_checks_the_flag_too_when_the_local_file_replaces_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], local_overlays: str
) -> None:
    """Regression: with a local ``overlays_enabled`` only that list was checked, so
    an unusable ``--overlays`` was written to the committed file (exit 0) and every
    teammate without the local file then failed ``playbook sync``."""
    _write_pyproject(tmp_path)
    local = tmp_path / ".coding-agent-playbook.local.toml"
    local.write_text(f"overlays_enabled = {local_overlays}\n", encoding="utf-8")

    assert _init.run(_init_ns(tmp_path, overlays=_TYPO)) == 2

    err = capsys.readouterr().err
    assert err.startswith(
        "error: --overlays names overlay package(s) or bundled plugin(s) that cannot be used "
        "here; nothing was written:"
    )
    assert f"\n  {_TYPO}: no such bundled plugin {_plugins_hint()}" in err
    assert "overlays_enabled in" not in err  # the local list is usable
    assert sorted(path.name for path in tmp_path.iterdir()) == [local.name, "pyproject.toml"]


def test_init_reports_both_unusable_lists_at_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_pyproject(tmp_path)
    local = tmp_path / ".coding-agent-playbook.local.toml"
    local.write_text(f'overlays_enabled = ["{_NOT_A_PLUGIN}"]\n', encoding="utf-8")

    assert _init.run(_init_ns(tmp_path, overlays=_TYPO)) == 2

    err = capsys.readouterr().err
    assert err.startswith("error: --overlays names overlay package(s) or bundled plugin(s)")
    assert (
        "\nerror: overlays_enabled in .coding-agent-playbook.local.toml names overlay package(s) "
        "or bundled plugin(s)"
    ) in err
    assert sorted(path.name for path in tmp_path.iterdir()) == [local.name, "pyproject.toml"]


def test_init_accepts_the_bundled_plugin_and_writes_the_top_level_key(tmp_path: Path) -> None:
    _write_pyproject(tmp_path)

    assert _init.run(_init_ns(tmp_path, overlays=PLUGIN_NAME)) == 0

    with (tmp_path / ".coding-agent-playbook.toml").open("rb") as handle:
        data = tomllib.load(handle)
    assert data["overlays_enabled"] == [PLUGIN_NAME]
    assert "overlays" not in data
    assert "adapters" not in data
    assert (tmp_path / ".claude" / "skills" / "brainstorming" / "SKILL.md").is_file()


# --------------------------------------------------------------------------- #
# playbook sync: the same shared check now covers a package without resources/
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mode", [{}, {"check": True}, {"check_staged": True}])
def test_sync_refuses_a_package_without_resources(
    mode: dict[str, bool],
    tmp_path: Path,
    make_synthetic_repo: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo, _NO_RES)

    assert (
        _sync.execute(
            repo,
            git=FakeGitClient(staged=["AGENTS.md"]),
            check=mode.get("check", False),
            check_staged=mode.get("check_staged", False),
        )
        == 1
    )

    err = capsys.readouterr().err
    assert f"\n  {_NO_RES}: {_NO_RES_REASON}\n" in err
    assert not (repo / "AGENTS.md").exists()
    assert not (repo / ".coding-agent-playbook.lock").exists()
    assert not (repo / ".gitignore").exists()


@pytest.mark.parametrize("mode", [{}, {"check": True}, {"check_staged": True}])
def test_sync_refuses_packages_that_raise_at_import(
    mode: dict[str, bool],
    tmp_path: Path,
    make_synthetic_repo: Callable[..., Path],
    make_package: Callable[..., str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Discovery skips them like missing packages, so the preflight must refuse:
    rendering without them would drop their artifacts (it used to be a traceback)."""
    repo = _repo(tmp_path, make_synthetic_repo, *_raising_overlays(make_package))

    assert (
        _sync.execute(
            repo,
            git=FakeGitClient(staged=["AGENTS.md"]),
            check=mode.get("check", False),
            check_staged=mode.get("check_staged", False),
        )
        == 1
    )

    err = capsys.readouterr().err
    assert "".join(f"\n  {reason}" for reason in _BOOM_REASONS) in err
    assert not (repo / "AGENTS.md").exists()
    assert not (repo / ".coding-agent-playbook.lock").exists()
    assert not (repo / ".gitignore").exists()
