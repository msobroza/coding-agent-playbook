"""ruff must never lint or reformat eval-fixture ``setup/`` trees (specs/prK-lifecycle-hooks.md §P9).

The fixtures under ``catalog/core/eval_samples/*/setup`` are deliberately unclean
needle material (the ``find-injected-vuln-*`` samples hide a bug in them), so a
pre-commit ``ruff check --fix`` or a hook's post-edit ``ruff format`` must not
rewrite them. ``extend-exclude`` alone does not stop ruff from touching a path
passed explicitly on the command line, which is exactly what pre-commit and the
hooks do; ``force-exclude = true`` closes that hole.

Eval samples are per layer, so a bundled plugin's fixtures
(``catalog/plugins/*/eval_samples/*/setup``) need the same exclude. No shipped
plugin has eval samples yet, so that glob is proved in a scratch project that
carries the engine's ruff excludes. mypy needs no exclude for either home:
``catalog/`` is outside its ``files``.

The config half parses ``pyproject.toml``. The behaviour half drives the real
``ruff`` binary with ``--no-cache`` (so no ``.ruff_cache`` is written) and is
skipped when ruff is not on ``PATH``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.catalog

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_GLOB = "catalog/core/eval_samples/*/setup"
#: A bundled plugin's eval samples live in its own layer, fixtures included.
_PLUGIN_FIXTURE_GLOB = "catalog/plugins/*/eval_samples/*/setup"
#: The vendored superpowers plugin stays byte-faithful as a whole; mattpocock_skills
#: only keeps ruff off its markdown, because its Python script rewrites are our own
#: code (SPEC §11.5.3).
_VENDORED_PACK_GLOB = "catalog/plugins/superpowers"
_SPLIT_PACK_MD_GLOB = "catalog/plugins/mattpocock_skills/**/*.md"
_SPLIT_PACK_SCRIPT = "catalog/plugins/mattpocock_skills/skills/wizard/scripts/wizard_template.py"
_ENGINE_MODULE = "src/coding_agent_playbook/__init__.py"
#: Scratch-project paths: a plugin's eval fixture, and a plugin script beside it.
_SCRATCH_PLUGIN_FIXTURE = "catalog/plugins/demo/eval_samples/demo-sample/setup/needle.py"
_SCRATCH_PLUGIN_SCRIPT = "catalog/plugins/demo/skills/demo/scripts/tool.py"
#: An unused import (F401) that ``ruff format`` would also rewrite (``x=1``).
_UNCLEAN_SOURCE = "import os\nx=1\n"
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


def _run_ruff(*args: str, cwd: Path = _REPO_ROOT) -> subprocess.CompletedProcess[str]:
    ruff = shutil.which("ruff")
    if ruff is None:
        pytest.skip("ruff is not on PATH")
    return subprocess.run(
        [ruff, *args, "--no-cache"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=_RUFF_TIMEOUT_S,
    )


def test_ruff_config_excludes_fixtures_and_packs_with_force_exclude() -> None:
    table = _ruff_table()
    assert _FIXTURE_GLOB in table["extend-exclude"]
    assert _PLUGIN_FIXTURE_GLOB in table["extend-exclude"]
    assert _VENDORED_PACK_GLOB in table["extend-exclude"]
    assert _SPLIT_PACK_MD_GLOB in table["extend-exclude"]
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


def _write_scratch_project(root: Path) -> None:
    """A project carrying the engine's ruff excludes, a plugin eval fixture and a plugin script.

    Example::

        _write_scratch_project(tmp_path)  # then run ruff with cwd=tmp_path
    """
    table = _ruff_table()
    # A JSON array of strings is also a valid TOML array.
    excludes = json.dumps(table["extend-exclude"])
    (root / "pyproject.toml").write_text(
        f"[tool.ruff]\nextend-exclude = {excludes}\nforce-exclude = true\n", encoding="utf-8"
    )
    for rel in (_SCRATCH_PLUGIN_FIXTURE, _SCRATCH_PLUGIN_SCRIPT):
        path = root / rel
        path.parent.mkdir(parents=True)
        path.write_text(_UNCLEAN_SOURCE, encoding="utf-8")


@pytest.mark.parametrize("flags", [(), ("--force-exclude",)], ids=["pre-commit", "hook-argv"])
@pytest.mark.parametrize("command", [("check",), ("format", "--check")], ids=["check", "format"])
def test_ruff_skips_a_bundled_plugin_eval_fixture(
    tmp_path: Path, command: tuple[str, ...], flags: tuple[str, ...]
) -> None:
    _write_scratch_project(tmp_path)
    completed = _run_ruff(*command, *flags, _SCRATCH_PLUGIN_FIXTURE, cwd=tmp_path)
    assert _NO_FILES in completed.stdout + completed.stderr, completed
    assert completed.returncode == 0


def test_ruff_still_lints_a_plugin_script_beside_its_eval_fixtures(tmp_path: Path) -> None:
    """Control: the plugin fixture glob must not swallow the rest of the plugin."""
    _write_scratch_project(tmp_path)
    completed = _run_ruff("check", _SCRATCH_PLUGIN_SCRIPT, cwd=tmp_path)
    assert completed.returncode == 1, completed
    assert "F401" in completed.stdout


def test_mypy_never_reads_the_catalog() -> None:
    """Neither fixture home needs a mypy exclude: ``catalog/`` is outside mypy's ``files``."""
    with (_REPO_ROOT / "pyproject.toml").open("rb") as handle:
        files: list[str] = tomllib.load(handle)["tool"]["mypy"]["files"]
    assert files, "mypy must scan an explicit file list, never the whole repository"
    for entry in files:
        assert Path(entry).parts[0] not in {".", "catalog"}, files


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
    assert not [path for path in listed if "/eval_samples/" in path and "/setup/" in path]
    assert not [path for path in listed if path.startswith(f"{_VENDORED_PACK_GLOB}/")]
    assert _SPLIT_PACK_SCRIPT in listed
