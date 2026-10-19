"""``config/committed``: rewrite the committed config from itself alone (SPEC §7.2).

``playbook init`` and ``playbook check --refresh`` share it; their CLI tests pin
the end-to-end behaviour, these pin each helper.
"""

from __future__ import annotations

import ast
import dataclasses
import re
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import coding_agent_playbook
from coding_agent_playbook.config.committed import (
    detector_cache_table,
    plan_committed_update,
    plan_detector_cache_refresh,
    plan_first_config,
)
from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.config.model import Config
from coding_agent_playbook.config.schema import ConfigError
from tests.engine_modules import engine_module
from tests.toml_equality import assert_toml_identical

if TYPE_CHECKING:
    from collections.abc import Iterator

_PRIMARY = ".coding-agent-playbook.toml"
_LOCAL = ".coding-agent-playbook.local.toml"

#: What ``Config.to_dict`` writes for itself, plus what it does not own.
_COMMITTED = """\
schema_version = 1
adapters_enabled = ["continue"]

[project]
name = "x"
kind = "python-library"
homepage = "https://x.example"

[engine]
version = "0.1.0a0"

[storage]
artifact_source = "filesystem"
state_source = "filesystem"

[links]
allowed_domains = ["example.com"]
"""

_PERSONAL = 'adapters_enabled = ["claude_code"]\n\n[user_choices]\nstyle = "google"\n'


def _state(repo: Path, local: str = _PERSONAL) -> FileSystemStateSource:
    (repo / _PRIMARY).write_text(_COMMITTED, encoding="utf-8")
    (repo / _LOCAL).write_text(local, encoding="utf-8")
    return FileSystemStateSource(repo_root=repo)


def _fresh_cache(config: Config) -> Config:
    return dataclasses.replace(config, detector_cache={"fresh": True})


def test_plan_committed_update_updates_the_committed_config_alone_and_writes_nothing(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    seen: list[Config] = []

    def update(config: Config) -> Config:
        seen.append(config)
        return _fresh_cache(config)

    rewrite = plan_committed_update(state, update)

    assert [config.adapters_enabled for config in seen] == [["continue"]]  # not the local list
    assert seen[0].user_choices == {}
    assert rewrite.config.detector_cache == {"fresh": True}
    expected = rewrite.config.to_dict()
    expected["project"]["homepage"] = "https://x.example"
    expected["links"] = {"allowed_domains": ["example.com"]}
    assert rewrite.table == expected
    assert (tmp_path / _PRIMARY).read_text(encoding="utf-8") == _COMMITTED


def test_config_rewrite_save_writes_the_update_and_keeps_everything_else(tmp_path: Path) -> None:
    state = _state(tmp_path)
    rewrite = plan_committed_update(state, _fresh_cache)

    assert rewrite.save(state) is rewrite.config

    after = tomllib.loads((tmp_path / _PRIMARY).read_text(encoding="utf-8"))
    assert after.pop("detector_cache") == {"fresh": True}
    assert_toml_identical(after, tomllib.loads(_COMMITTED))
    assert (tmp_path / _LOCAL).read_text(encoding="utf-8") == _PERSONAL


@pytest.mark.parametrize("plan", ["update", "refresh"])
def test_a_plan_refuses_a_local_file_that_breaks_the_result_before_writing(
    tmp_path: Path, plan: str
) -> None:
    state = _state(tmp_path, local='[output]\ncommit = "yes"\n')

    expected = f"^{re.escape(_LOCAL)}: " + r"\[output\] commit must be a boolean"
    with pytest.raises(ConfigError, match=expected):
        if plan == "update":
            plan_committed_update(state, lambda config: config)
        else:
            plan_detector_cache_refresh(state, {})

    assert (tmp_path / _PRIMARY).read_text(encoding="utf-8") == _COMMITTED


#: A hand-written committed file holding every value ``Config.to_dict`` normalizes.
_HAND_WRITTEN = """\
schema_version = 1
overlays_enabled = []
adapters_enabled = []

[project]
name = "x"
kind = "python-library"
description = ""

[engine]
version = "0.1.0a0"

[storage]
state_source = "filesystem"

[output]
note = "x"

[user_choices]

[detector_cache]
stale = true
"""


def test_plan_detector_cache_refresh_changes_only_the_detector_cache(tmp_path: Path) -> None:
    """Regression: the refresh went through ``Config.to_dict``, which dropped the
    explicit empty lists, ``description = ""`` and the empty ``[user_choices]``,
    and added ``artifact_source`` and ``commit = false``, although SPEC §12.5 says
    only ``[detector_cache]`` changes."""
    state = _state(tmp_path, local=_PERSONAL)
    (tmp_path / _PRIMARY).write_text(_HAND_WRITTEN, encoding="utf-8")

    rewrite = plan_detector_cache_refresh(state, {"fresh": True})
    assert rewrite.save(state) is rewrite.config

    expected = {**tomllib.loads(_HAND_WRITTEN), "detector_cache": {"fresh": True}}
    assert_toml_identical(tomllib.loads((tmp_path / _PRIMARY).read_text("utf-8")), expected)
    assert rewrite.config.adapters_enabled == []  # the committed list, not the local one
    assert (tmp_path / _LOCAL).read_text(encoding="utf-8") == _PERSONAL


def test_plan_detector_cache_refresh_keeps_deprecated_overlay(tmp_path: Path) -> None:
    """SPEC §12.5: a refresh writes every other key as parsed, so a deprecated
    ``packs`` name stays in the committed file; ``config`` is its canonical view."""
    old = "coding_agent_playbook.packs.superpowers"
    state = _state(tmp_path)
    (tmp_path / _PRIMARY).write_text(f'overlays_enabled = ["{old}"]\n' + _COMMITTED)

    rewrite = plan_detector_cache_refresh(state, {"fresh": True})

    assert rewrite.table["overlays_enabled"] == [old]
    assert rewrite.config.overlays_enabled == ["coding_agent_playbook.plugins.superpowers"]
    assert rewrite.config.deprecated_overlay_names == (old,)


def test_plan_detector_cache_refresh_appends_a_missing_detector_cache(tmp_path: Path) -> None:
    state = _state(tmp_path)
    table = plan_detector_cache_refresh(state, {"fresh": True}).table
    assert list(table)[-1] == "detector_cache"
    assert {key: value for key, value in table.items() if key != "detector_cache"} == (
        tomllib.loads(_COMMITTED)
    )


@pytest.mark.parametrize("plan", ["update", "refresh"])
def test_a_plan_refuses_a_committed_file_missing_a_key_only_the_local_file_has(
    tmp_path: Path, plan: str
) -> None:
    state = _state(tmp_path, local='[engine]\nversion = "0.1.0a0"\n')
    (tmp_path / _PRIMARY).write_text(_COMMITTED.replace('version = "0.1.0a0"\n', ""))

    expected = f"^{re.escape(_PRIMARY)}: " + r"the required key engine\.version"
    with pytest.raises(ConfigError, match=expected):
        if plan == "update":
            plan_committed_update(state, lambda config: config)
        else:
            plan_detector_cache_refresh(state, {})


def test_plan_first_config_writes_the_config_alone(tmp_path: Path) -> None:
    (tmp_path / _LOCAL).write_text(_PERSONAL, encoding="utf-8")
    state = FileSystemStateSource(repo_root=tmp_path)
    config = Config.from_dict(tomllib.loads(_COMMITTED))
    rewrite = plan_first_config(state, config)
    assert rewrite.table == config.to_dict()
    assert not (tmp_path / _PRIMARY).exists()


def test_plan_first_config_refuses_to_overwrite_an_existing_committed_file(
    tmp_path: Path,
) -> None:
    """A first-run plan from a ``Config`` built elsewhere (``load_config``'s merge)
    must never replace the committed file: rewrites start from the file itself."""
    state = _state(tmp_path)
    with pytest.raises(FileExistsError, match=r"plan_committed_update"):
        plan_first_config(state, state.load_config())
    assert (tmp_path / _PRIMARY).read_text(encoding="utf-8") == _COMMITTED


def test_detector_cache_table_writes_sets_as_sorted_lists() -> None:
    table = detector_cache_table({"dev_tools": {"ruff", "mypy"}, "has_ci": True})
    assert table == {"dev_tools": ["mypy", "ruff"], "has_ci": True}


#: The committed file's writers (``FileSystemStateSource``) and the ``ConfigRewrite``
#: builders that may call them: production code names them in one module only.
_WRITERS = frozenset({"save_config", "save_config_table"})
_BUILDERS = frozenset({"ConfigRewrite", "_checked_rewrite"})
_HOME = "config/committed.py"
#: ``_HOME`` as a dotted module: what ``check`` and ``init`` import the builders from.
_HOME_MODULE = engine_module(f"coding_agent_playbook.{_HOME.removesuffix('.py').replace('/', '.')}")
#: Where the writers are defined (``save_config`` delegates to ``save_config_table``).
_WRITERS_HOME = "config/files.py"


def _engine_modules() -> Iterator[tuple[str, ast.Module]]:
    """``(path, tree)`` of every engine module; ``resources/`` holds content, not code."""
    package_root = Path(coding_agent_playbook.__file__).parent
    for path in sorted(package_root.rglob("*.py")):
        module = path.relative_to(package_root)
        if module.parts[0] != "resources":
            yield module.as_posix(), ast.parse(path.read_text(encoding="utf-8"))


def _referenced_names(tree: ast.Module) -> Iterator[tuple[int, str]]:
    """``(line, name)`` of every bare name and attribute ``tree`` references."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            yield node.lineno, node.attr
        elif isinstance(node, ast.Name):
            yield node.lineno, node.id


def _called_names(tree: ast.Module) -> Iterator[tuple[int, str]]:
    """``(line, name)`` of every call's callee: ``f`` in ``f(…)`` and ``x.f(…)``.

    Calls, not references: ``init`` names ``ConfigRewrite`` as a return type.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute):
            yield node.lineno, node.func.attr
        elif isinstance(node.func, ast.Name):
            yield node.lineno, node.func.id


def _imports_committed_config(tree: ast.Module) -> bool:
    """Whether ``tree`` imports ``config.committed`` or a name from it.

    Both spellings count: ``from …config.committed import plan_first_config`` and
    ``from …config import committed``.
    """
    imported = (
        [node.module or "", *(f"{node.module}.{alias.name}" for alias in node.names)]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    return any(name == _HOME_MODULE for names in imported for name in names)


def test_only_committed_config_writes_the_committed_file() -> None:
    """SPEC §7.2 invariant: local overrides are never written back to the committed file.

    Pins, by walking the engine's AST: (1) the writers ``save_config`` and
    ``save_config_table`` are referenced only in ``config/committed`` (and where
    they are defined), (2) a ``ConfigRewrite`` — whose ``save`` is the one caller —
    is built only there too, by ``plan_*`` builders that each read the committed
    file itself or require none; and (3) no module importing ``config.committed``
    references ``load_config``, the merged config, which ``init`` and ``check
    --refresh`` each saved before v0.18. It cannot see a merged config reaching a
    plan another way (``SyncContext.config`` returned from an ``update``
    callback); the CLI tests pin both commands' output for that.
    """
    misplaced: list[str] = []
    for module, tree in _engine_modules():
        names = list(_referenced_names(tree))
        if module not in (_HOME, _WRITERS_HOME):
            misplaced += [f"{module}:{line}:{name}" for line, name in names if name in _WRITERS]
        if module != _HOME:
            calls = _called_names(tree)
            misplaced += [f"{module}:{line}:{name}" for line, name in calls if name in _BUILDERS]
        if _imports_committed_config(tree):
            misplaced += [
                f"{module}:{line}:{name}" for line, name in names if name == "load_config"
            ]
    assert misplaced == []


def test_the_writer_pin_sees_the_names_it_guards() -> None:
    """Guard the guard: the walk finds the real writer call and builders in their home."""
    modules = dict(_engine_modules())
    assert "save_config_table" in {name for _, name in _referenced_names(modules[_HOME])}
    assert {"ConfigRewrite", "_checked_rewrite"} <= {
        name for _, name in _called_names(modules[_HOME])
    }
    assert _imports_committed_config(modules["commands/check.py"])
    assert _imports_committed_config(modules["commands/init.py"])
