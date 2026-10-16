"""An unusable overlay is reported by every command, not only ``sync`` (SPEC §11.5).

"Unusable" is the one shared preflight check (``_sync_preflight``): importing the
package fails (it is missing, or its own code raises), or it imports but ships no
``resources/`` directory (the parent ``coding_agent_playbook.packs``, say).
``sync`` refuses (exit 1), ``validate`` fails (exit 1), ``check`` flags it and
stops claiming a clean state (exit 0, it is a diagnostic), and ``init`` refuses
before writing (exit 2, a usage error) — for ``--overlays`` and for a local
file's ``overlays_enabled``, which replaces it. Each unusable overlay gets its own
line. A name that reads like a mistyped bundled pack also lists the bundled packs.
A package that raises at import time used to crash every command with a traceback.
"""

from __future__ import annotations

import argparse
import tomllib
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import check as _check
from coding_agent_playbook.commands import init as _init
from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.commands._sync_preflight import bundled_packs
from coding_agent_playbook.packs.superpowers import PACK_NAME
from tests.conftest import _DEFAULT_CONFIG
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# init ends with a real sync (SubprocessGitClient); keep git off the developer's config.
pytestmark = pytest.mark.usefixtures("hermetic_git_env")

_TYPO = "coding_agent_playbook.packs.superpower"  # the trailing "s" is missing
_PARENT = "coding_agent_playbook.packs"  # importable, but no resources/ of its own
_NOT_A_PACK = "no_such_overlay_pkg"


def _packs_hint() -> str:
    return f"(bundled packs: {', '.join(bundled_packs())})"


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
        (_TYPO, f"FAIL overlays_enabled: {_TYPO}: not importable {_packs_hint()}"),
        (
            _PARENT,
            f"FAIL overlays_enabled: {_PARENT}: importable, but ships no resources/ "
            f"directory, so it is not an overlay package {_packs_hint()}",
        ),
        (_NOT_A_PACK, f"FAIL overlays_enabled: {_NOT_A_PACK}: not importable\n"),
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
    repo = _repo(tmp_path, make_synthetic_repo, _TYPO, _PARENT, *_raising_overlays(make_package))

    assert _validate.run(_ns(repo)) == 1

    out = capsys.readouterr().out
    fails = [line for line in out.splitlines() if line.startswith("FAIL overlays_enabled: ")]
    assert fails == [
        f"FAIL overlays_enabled: {_TYPO}: not importable {_packs_hint()}",
        f"FAIL overlays_enabled: {_PARENT}: importable, but ships no resources/ directory, "
        f"so it is not an overlay package {_packs_hint()}",
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


def test_check_flags_a_misspelled_pack_and_does_not_claim_a_clean_state(
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
    assert f"    ✗ {_TYPO}: not importable {_packs_hint()}\n" in environment
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
        tmp_path, make_synthetic_repo, _TYPO, _NOT_A_PACK, *_raising_overlays(make_package)
    )

    assert _check.run(_ns(repo, refresh=False)) == 0

    environment = capsys.readouterr().out.partition("=== Detected ===")[0]
    flagged = [line for line in environment.splitlines() if line.startswith("    ✗ ")]
    assert flagged == [
        f"    ✗ {_TYPO}: not importable {_packs_hint()}",
        f"    ✗ {_NOT_A_PACK}: not importable",
        *(f"    ✗ {reason}" for reason in _BOOM_REASONS),
    ]


def test_check_keeps_listing_lockfile_drift_next_to_the_overlay_problem(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path, rules=[("style", "Body\n")])
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    (repo / "AGENTS.md").write_text("edited\n", encoding="utf-8")
    (repo / ".coding-agent-playbook.toml").write_text(_config_with(_PARENT), encoding="utf-8")
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
        (_TYPO, f"{_TYPO}: not importable {_packs_hint()}"),
        (_PARENT, f"{_PARENT}: importable, but ships no resources/ directory"),
        (_NOT_A_PACK, f"{_NOT_A_PACK}: not importable\n"),
    ],
)
def test_init_refuses_an_unusable_overlay_before_writing(
    overlay: str, reason: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_pyproject(tmp_path)

    assert _init.run(_init_ns(tmp_path, overlays=f"{overlay}")) == 2

    err = capsys.readouterr().err
    assert err.startswith("error: --overlays names package(s) that cannot be used as overlays")
    assert f"\n  {reason}" in err
    assert sorted(path.name for path in tmp_path.iterdir()) == ["pyproject.toml"]


def test_init_lists_each_unusable_overlay_and_a_raising_one(
    tmp_path: Path, make_package: Callable[..., str], capsys: pytest.CaptureFixture[str]
) -> None:
    """A package raising at import used to pass, get written, then crash the sync."""
    _write_pyproject(tmp_path)
    overlays = ",".join([_TYPO, _NOT_A_PACK, *_raising_overlays(make_package)])

    assert _init.run(_init_ns(tmp_path, overlays=overlays)) == 2

    err = capsys.readouterr().err
    listed = [line for line in err.splitlines() if line.startswith("  ")]
    assert listed == [
        f"  {_TYPO}: not importable {_packs_hint()}",
        f"  {_NOT_A_PACK}: not importable",
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

    assert _init.run(_init_ns(tmp_path, overlays=PACK_NAME)) == 2

    err = capsys.readouterr().err
    assert err.startswith(
        "error: overlays_enabled in .coding-agent-playbook.local.toml names package(s) "
        "that cannot be used as overlays here; nothing was written:"
    )
    assert f"\n  {_TYPO}: not importable {_packs_hint()}" in err
    assert sorted(path.name for path in tmp_path.iterdir()) == [local.name, "pyproject.toml"]


@pytest.mark.parametrize("local_overlays", ["[]", f'["{PACK_NAME}"]'])
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
        "error: --overlays names package(s) that cannot be used as overlays here; "
        "nothing was written:"
    )
    assert f"\n  {_TYPO}: not importable {_packs_hint()}" in err
    assert "overlays_enabled in" not in err  # the local list is usable
    assert sorted(path.name for path in tmp_path.iterdir()) == [local.name, "pyproject.toml"]


def test_init_reports_both_unusable_lists_at_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_pyproject(tmp_path)
    local = tmp_path / ".coding-agent-playbook.local.toml"
    local.write_text(f'overlays_enabled = ["{_NOT_A_PACK}"]\n', encoding="utf-8")

    assert _init.run(_init_ns(tmp_path, overlays=_TYPO)) == 2

    err = capsys.readouterr().err
    assert err.startswith("error: --overlays names package(s)")
    assert "\nerror: overlays_enabled in .coding-agent-playbook.local.toml names package(s)" in err
    assert sorted(path.name for path in tmp_path.iterdir()) == [local.name, "pyproject.toml"]


def test_init_accepts_the_bundled_pack_and_writes_the_top_level_key(tmp_path: Path) -> None:
    _write_pyproject(tmp_path)

    assert _init.run(_init_ns(tmp_path, overlays=PACK_NAME)) == 0

    with (tmp_path / ".coding-agent-playbook.toml").open("rb") as handle:
        data = tomllib.load(handle)
    assert data["overlays_enabled"] == [PACK_NAME]
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
    repo = _repo(tmp_path, make_synthetic_repo, _PARENT)

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
    assert f"\n  {_PARENT}: importable, but ships no resources/ directory" in err
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
