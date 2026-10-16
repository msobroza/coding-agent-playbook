"""``playbook check-deps``: dependency-allowlist-guard's CI twin (specs/prK-hook-pack.md §E.4).

The command runs in-process against a real git fixture repository (through
``real_git``, under ``hermetic_git_env``): a committed base, then working-tree
edits. Its rules are the hook's merged config whatever ``[hooks]`` says. Exit
codes: 0 no deny-class finding, 1 a deny-class finding, 2 a git or config error.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.cli import main

if TYPE_CHECKING:
    from collections.abc import Callable

CONFIG: Final = """\
schema_version = 1
adapters_enabled = ["claude_code"]
overlays_enabled = []

[project]
name = "consumer"
kind = "python-library"

[engine]
version = "0.1.0a0"
{tables}"""
ALLOWLIST: Final = """
[hooks]
enabled = false

[hooks.dependency-allowlist-guard]
allowlist = ["httpx", "Requests", "torch"]
"""
PYPROJECT: Final = '[project]\nname = "consumer"\ndependencies = [{deps}]\n'


def _pyproject(*deps: str) -> str:
    return PYPROJECT.format(deps=", ".join(f'"{dep}"' for dep in deps))


@pytest.fixture
def make_repo(tmp_path: Path, real_git: Callable[..., str]) -> Callable[..., Path]:
    """``make(tables, files) -> root``: commit ``files`` on ``main`` with the config."""

    def make(tables: str, files: dict[str, str]) -> Path:
        root = Path(os.path.realpath(tmp_path)) / "consumer"
        root.mkdir()
        (root / ".coding-agent-playbook.toml").write_text(CONFIG.format(tables=tables), "utf-8")
        for name, text in files.items():
            (root / name).write_text(text, "utf-8")
        real_git("init", "-q", "-b", "main", cwd=root)
        real_git("add", "-A", cwd=root)
        real_git("commit", "-q", "-m", "chore: base", cwd=root)
        return root

    return make


def _check(root: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, list[str]]:
    code = main(["check-deps", "--base", "main", "--repo-root", str(root)])
    return code, capsys.readouterr().out.splitlines()


def test_new_dep_outside_allowlist_exits_1(
    make_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo(ALLOWLIST, {"pyproject.toml": _pyproject("httpx")})
    (root / "pyproject.toml").write_text(_pyproject("httpx", "reqeusts>=2", "requests"), "utf-8")

    code, lines = _check(root, capsys)

    assert code == 1
    assert lines == [
        "pyproject.toml: deny not_allowlisted: Not on this repository's dependency "
        "allowlist: reqeusts (did you mean requests?)."
    ]


def test_existing_deps_grandfathered(
    make_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """``numpy`` is outside the allowlist but was there at the base: not reported."""
    root = make_repo(ALLOWLIST, {"pyproject.toml": _pyproject("httpx", "numpy")})
    (root / "pyproject.toml").write_text(_pyproject("numpy>=2", "HTTPX"), "utf-8")

    assert _check(root, capsys) == (0, [])


def test_extra_index_reported(
    make_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo("", {"requirements.txt": "torch\n"})
    pinned = "--extra-index-url https://download.pytorch.org/whl/cu121\ntorch\n"
    (root / "requirements.txt").write_text(pinned, "utf-8")

    code, lines = _check(root, capsys)

    assert code == 0  # index_mode = ask: reported, not failed
    assert lines == [
        "requirements.txt: ask index_mixing: `requirements.txt` adds the package index "
        '"download.pytorch.org", and mixing indexes is the dependency-confusion vector.'
    ]


def test_index_mode_deny_fails_on_a_new_uv_index(
    make_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    tables = '\n[hooks.dependency-allowlist-guard]\nindex_mode = "deny"\n'
    root = make_repo(tables, {"pyproject.toml": _pyproject("torch")})
    index = '\n[[tool.uv.index]]\nname = "pt"\nurl = "https://download.pytorch.org/whl/cu121"\n'
    (root / "pyproject.toml").write_text(_pyproject("torch") + index, "utf-8")

    code, lines = _check(root, capsys)

    assert code == 1
    assert [line.split(": ", 2)[1] for line in lines] == ["deny index_mixing"]


def test_no_policy_lists_new_names_and_exits_0(
    make_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo("", {"pyproject.toml": _pyproject("httpx")})
    (root / "pyproject.toml").write_text(_pyproject("httpx", "rich", "typer"), "utf-8")
    (root / "requirements-dev.txt").write_text("pytest\n", "utf-8")  # untracked

    code, lines = _check(root, capsys)

    assert code == 0
    assert lines == [
        "pyproject.toml: ask new_dependency: rich, typer",
        "requirements-dev.txt: ask new_dependency: pytest",
    ]


def test_names_pep503_normalized(
    make_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo("", {"pyproject.toml": _pyproject("Foo_Bar")})
    (root / "pyproject.toml").write_text(_pyproject("foo.bar", "Baz_Qux.Extra"), "utf-8")

    assert _check(root, capsys) == (0, ["pyproject.toml: ask new_dependency: baz-qux-extra"])


def test_without_a_repository_exits_2(
    tmp_path: Path, hermetic_git_env: None, capsys: pytest.CaptureFixture[str]
) -> None:
    root = Path(os.path.realpath(tmp_path)) / "plain"
    root.mkdir()

    assert main(["check-deps", "--repo-root", str(root)]) == 2
    assert capsys.readouterr().err.startswith("error: ")
