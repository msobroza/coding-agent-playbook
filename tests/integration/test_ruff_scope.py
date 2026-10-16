"""ruff must never lint or reformat eval-fixture ``setup/`` trees (specs/prK-lifecycle-hooks.md §P9).

The fixtures under ``resources/eval_tasks/*/setup`` are deliberately unclean
needle material (the ``find-injected-vuln-*`` tasks hide a bug in them), so a
pre-commit ``ruff check --fix`` or a hook's post-edit ``ruff format`` must not
rewrite them. ``extend-exclude`` alone does not stop ruff from touching a path
passed explicitly on the command line, which is exactly what pre-commit and the
hooks do; ``force-exclude = true`` closes that hole.

The config half parses ``pyproject.toml``. The behaviour half drives the real
``ruff`` binary from the repo root with ``--no-cache`` (so no ``.ruff_cache`` is
written) and is skipped when ruff is not on ``PATH``.
"""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_GLOB = "src/coding_agent_playbook/resources/eval_tasks/*/setup"
#: The vendored pack stays byte-faithful; the distilled python_design pack only
#: keeps ruff off its markdown, because its stdlib scripts are our own code (SPEC §11.5.2).
_VENDORED_PACK_GLOB = "src/coding_agent_playbook/packs/superpowers/resources"
_DISTILLED_PACK_MD_GLOB = "src/coding_agent_playbook/packs/python_design/resources/**/*.md"
_DISTILLED_PACK_SCRIPT = (
    "src/coding_agent_playbook/packs/python_design/resources/skills/"
    "python-architecture/scripts/layer_map.py"
)
_ENGINE_MODULE = "src/coding_agent_playbook/__init__.py"
_NO_FILES = "No Python files found"
_RUFF_TIMEOUT_S = 60


def _ruff_table() -> dict[str, Any]:
    with (_REPO_ROOT / "pyproject.toml").open("rb") as handle:
        table: dict[str, Any] = tomllib.load(handle)["tool"]["ruff"]
    return table


def _fixture_file() -> str:
    """One real ``setup/**/*.py`` fixture, repo-relative (the glob must match something)."""
    fixtures = sorted(_REPO_ROOT.glob(f"{_FIXTURE_GLOB}/**/*.py"))
    assert fixtures, f"no eval fixture matches {_FIXTURE_GLOB}/**/*.py"
    return fixtures[0].relative_to(_REPO_ROOT).as_posix()


def _run_ruff(*args: str) -> subprocess.CompletedProcess[str]:
    ruff = shutil.which("ruff")
    if ruff is None:
        pytest.skip("ruff is not on PATH")
    return subprocess.run(
        [ruff, *args, "--no-cache"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=_RUFF_TIMEOUT_S,
    )


def test_ruff_config_excludes_fixtures_and_packs_with_force_exclude() -> None:
    table = _ruff_table()
    assert _FIXTURE_GLOB in table["extend-exclude"]
    assert _VENDORED_PACK_GLOB in table["extend-exclude"]
    assert _DISTILLED_PACK_MD_GLOB in table["extend-exclude"]
    assert table["force-exclude"] is True


# Pre-commit passes explicit paths with no flag (it relies on the config's
# force-exclude); hook and Stop-stage argvs carry --force-exclude (§E.3).
@pytest.mark.parametrize("flags", [(), ("--force-exclude",)], ids=["pre-commit", "hook-argv"])
def test_ruff_excludes_eval_fixture_setup(flags: tuple[str, ...]) -> None:
    completed = _run_ruff("check", *flags, _fixture_file())
    assert _NO_FILES in completed.stdout + completed.stderr
    assert completed.returncode == 0


@pytest.mark.parametrize("flags", [(), ("--force-exclude",)], ids=["pre-commit", "hook-argv"])
def test_ruff_format_skips_eval_fixture_setup(flags: tuple[str, ...]) -> None:
    completed = _run_ruff("format", "--check", *flags, _fixture_file())
    assert _NO_FILES in completed.stdout + completed.stderr
    assert completed.returncode == 0


def _repo_relative(listed_path: str) -> str:
    """``ruff --show-files`` prints absolute paths; compare them below the repo root."""
    root = f"{_REPO_ROOT.as_posix()}/"
    return listed_path.removeprefix(root)


def test_ruff_still_checks_engine_sources() -> None:
    """Control: an over-broad glob would silently stop linting the engine itself."""
    completed = _run_ruff("check", "--show-files", ".")
    assert completed.returncode == 0, completed.stderr
    listed = [_repo_relative(line) for line in completed.stdout.splitlines()]
    assert _ENGINE_MODULE in listed
    assert "src/coding_agent_playbook/packs/superpowers/__init__.py" in listed
    assert not [path for path in listed if "/eval_tasks/" in path and "/setup/" in path]
    assert not [path for path in listed if path.startswith(f"{_VENDORED_PACK_GLOB}/")]
    assert _DISTILLED_PACK_SCRIPT in listed
