"""The StateSource ABC (PR 1) and FileSystemStateSource, the ``state_sources`` entry (SPEC §20.3).

``FileSystemStateSource`` delegates its config half to ``ConfigFiles``
(``test_files.py`` pins the reads and writes); its lockfile half is
``test_files_lockfile.py``'s.
"""

from __future__ import annotations

import ast
import inspect
import tomllib
from pathlib import Path

import pytest

from coding_agent_playbook.config.files import (
    CONFIG_FILENAME,
    CONFIG_LOCAL_FILENAME,
    ConfigFiles,
    FileSystemStateSource,
    StateSource,
)
from coding_agent_playbook.config.model import Config, ProjectMeta
from coding_agent_playbook.config.tables.hooks import PolicyTables
from tests.config._engine_trees import PACKAGE_ROOT, engine_module_file, engine_module_trees
from tests.engine_modules import StaleModulePin


class _DummyStateSource(StateSource):
    name = "dummy"

    def load_config(self):
        return {}

    def save_config(self, config):
        return None

    def load_lockfile(self):
        return None

    def save_lockfile(self, lockfile):
        return None


@pytest.mark.parametrize("abc", [StateSource])
def test_source_abc_cannot_be_instantiated(abc):
    with pytest.raises(TypeError):
        abc()


def test_state_source_subclass_can_be_instantiated():
    assert isinstance(_DummyStateSource(), StateSource)


def test_state_source_load_primary_config_defaults_to_load_config():
    """A third-party source written before ``load_primary_config`` existed
    keeps working: the concrete default returns whatever ``load_config`` does."""
    loaded = object()

    class _OldStyleStateSource(_DummyStateSource):
        def load_config(self):
            return loaded

    assert _OldStyleStateSource().load_primary_config() is loaded


def test_state_source_load_local_overrides_defaults_to_empty():
    """A source with no per-developer file has no local overrides to ignore."""
    assert _DummyStateSource().load_local_overrides() == {}


def test_state_source_load_policy_tables_reads_the_primary_config():
    """The concrete default (prK §B.1): the committed config's extension
    tables, with the local overrides only recorded."""
    config = Config(1, ProjectMeta("x", "python-library"), "0.1")
    config.extra_tables = {"hooks": {"enabled": True}, "links": {}}

    class _OneConfigSource(_DummyStateSource):
        def load_config(self):
            return config

        def load_local_overrides(self):
            return {"guardrails": {"git": {}}}

    assert _OneConfigSource().load_policy_tables() == PolicyTables(
        hooks={"enabled": True}, local_keys=("guardrails.git",)
    )


_COMMITTED = """\
schema_version = 1
adapters_enabled = ["continue"]

[project]
name = "x"
kind = "python-library"

[engine]
version = "0.1"

[hooks]
enabled = true
"""


def test_filesystem_state_source_delegates_its_config_half(tmp_path: Path) -> None:
    """The ``state_sources`` entry reads and writes the two files as ``ConfigFiles`` does."""
    (tmp_path / CONFIG_FILENAME).write_text(_COMMITTED, encoding="utf-8")
    (tmp_path / CONFIG_LOCAL_FILENAME).write_text('adapters_enabled = ["opencode"]\n', "utf-8")
    source, files = FileSystemStateSource(repo_root=tmp_path), ConfigFiles(tmp_path)

    assert source.load_config() == files.load()
    assert source.load_config().adapters_enabled == ["opencode"]
    assert source.load_primary_config() == files.load_committed()
    assert source.load_local_overrides() == files.local_overrides()
    assert files.local_overrides() == {"adapters_enabled": ["opencode"]}
    assert source.load_policy_tables().hooks == {"enabled": True}
    source.save_config(source.load_primary_config())
    assert files.load_committed() == source.load_primary_config()
    # validation/context.py reads these two (spec B.5.3), so they stay class attributes.
    assert (source._CONFIG_FILENAME, source._CONFIG_LOCAL_FILENAME) == (
        ".coding-agent-playbook.toml",
        ".coding-agent-playbook.local.toml",
    )


def test_filesystem_state_source_keeps_its_committed_file_methods(tmp_path: Path) -> None:
    """Spec B.5.3: the entry's other config methods stay too, each a ``ConfigFiles`` call,
    so out-of-tree code that reads or rewrites the committed file through it still runs."""
    (tmp_path / CONFIG_LOCAL_FILENAME).write_text('adapters_enabled = ["opencode"]\n', "utf-8")
    source, files = FileSystemStateSource(repo_root=tmp_path), ConfigFiles(tmp_path)
    table = tomllib.loads(_COMMITTED)
    with pytest.raises(FileNotFoundError, match=r"; run `playbook init`$"):
        source.read_committed_config_table()

    assert (source.has_committed_config(), files.has_committed()) == (False, False)
    assert source.preview_config(table) == files.preview(table)
    assert source.preview_config(table).adapters_enabled == ["opencode"]
    assert not files.has_committed()  # a preview writes nothing
    source.save_config_table(table)

    assert (source.has_committed_config(), files.has_committed()) == (True, True)
    committed = source.read_committed_config_table()
    assert isinstance(committed, dict)  # a copy the caller may change, as before B2
    assert committed == dict(files.committed().data) == table


def test_dump_toml_escapes_control_characters(tmp_path: Path) -> None:
    """Strings with control chars (\\x00, \\x08) must be \\uXXXX-escaped so
    the emitted TOML is valid (code-quality review I1)."""
    config = Config(
        schema_version=1,
        project=ProjectMeta(name="r", kind="x", description="weird:\x00\x08"),
        engine_version="0.1.0a0",
    )
    source = FileSystemStateSource(repo_root=tmp_path)
    source.save_config(config)
    # Must round-trip
    loaded = source.load_config()
    assert loaded.project.description == "weird:\x00\x08"


def test_entry_point_registers_filesystem_state_source() -> None:
    from importlib import metadata

    eps = metadata.entry_points(group="coding_agent_playbook.state_sources")
    by_name = {ep.name: ep for ep in eps}
    assert "filesystem" in by_name
    loaded = by_name["filesystem"].load()
    assert loaded is FileSystemStateSource


#: The engine modules outside ``config/`` that may import ``FileSystemStateSource``
#: (spec B.5.8); everything else reads the config files through ``ConfigFiles``.
#: Named dotted, so ``module_moves apply`` follows a move (``engine_module_file``).
_STATE_SOURCE_USERS = frozenset(
    {
        # builds the sync context's state source (moved from orchestrator.py by A5)
        engine_module_file("coding_agent_playbook.validation.context"),
        # reads the lockfile through it
        engine_module_file("coding_agent_playbook.adapters.skill_dirs.ownership"),
    }
)


def _imported_names(tree: ast.Module) -> set[str]:
    """Every name a ``from … import`` of ``tree`` binds (the original name, not an alias)."""
    return {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }


def _state_source_importers() -> set[str]:
    """Engine modules outside ``config/`` that import ``FileSystemStateSource``."""
    return {
        module
        for module, tree in engine_module_trees()
        if not module.startswith("config/") and "FileSystemStateSource" in _imported_names(tree)
    }


def test_only_the_state_source_users_import_filesystem_state_source() -> None:
    """The allowlist is exact, so it only shrinks: a module that stops importing it
    must leave the list too."""
    assert _state_source_importers() == _STATE_SOURCE_USERS


@pytest.mark.parametrize("defined", [ConfigFiles, PolicyTables])
def test_engine_module_file_is_the_trees_key_of_the_module(defined: type) -> None:
    """Guard the guard: a dotted name becomes the path the pins compare (no raw path
    here either, so a later move cannot strand this test)."""
    expected = Path(inspect.getfile(defined)).relative_to(PACKAGE_ROOT).as_posix()

    assert engine_module_file(defined.__module__) == expected


def test_engine_module_file_refuses_a_stale_name() -> None:
    """A name that no longer resolves fails, instead of leaving an allowlist entry
    that matches no module."""
    with pytest.raises(StaleModulePin, match="no longer resolves"):
        engine_module_file("coding_agent_playbook.config.no_such_module")
