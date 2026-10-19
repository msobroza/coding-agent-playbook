"""Tests for FileSystemStateSource (SPEC §20.3)."""

from __future__ import annotations

import re
import textwrap
import tomllib
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.config.model import Config, ProjectMeta
from coding_agent_playbook.config.schema import ConfigError
from tests.toml_equality import assert_toml_identical

if TYPE_CHECKING:
    from pathlib import Path


CONFIG_PRIMARY = """\
schema_version = 1

[project]
name = "my-app"
kind = "python-application"

[engine]
version = "0.1.0a0"

[storage]
artifact_source = "filesystem"
state_source = "filesystem"

[user_choices]
banking_mode = false
"""

CONFIG_LOCAL_OVERRIDE = """\
[user_choices]
banking_mode = true
extra_dev_choice = "yes"
"""


def test_load_config_reads_primary_toml(tmp_path: Path) -> None:
    (tmp_path / ".coding-agent-playbook.toml").write_text(CONFIG_PRIMARY)
    source = FileSystemStateSource(repo_root=tmp_path)
    config = source.load_config()
    assert config.schema_version == 1
    assert config.project.name == "my-app"
    assert config.project.kind == "python-application"
    assert config.engine_version == "0.1.0a0"
    assert config.user_choices == {"banking_mode": False}


def test_load_config_merges_local_overrides(tmp_path: Path) -> None:
    (tmp_path / ".coding-agent-playbook.toml").write_text(CONFIG_PRIMARY)
    (tmp_path / ".coding-agent-playbook.local.toml").write_text(CONFIG_LOCAL_OVERRIDE)
    source = FileSystemStateSource(repo_root=tmp_path)
    config = source.load_config()
    assert config.user_choices == {
        "banking_mode": True,
        "extra_dev_choice": "yes",
    }


def test_load_config_deep_merges_nested_dicts(tmp_path: Path) -> None:
    """Primary's detector_cache.frameworks is merged with override's, not
    replaced wholesale (code-quality review I3, coupled with C1's nested
    support)."""
    (tmp_path / ".coding-agent-playbook.toml").write_text(
        textwrap.dedent("""
            schema_version = 1
            [project]
            name = "r"
            kind = "python-application"
            [engine]
            version = "0.1.0a0"
            [detector_cache]
            python_version = "3.12"
            [detector_cache.frameworks]
            fastapi = "0.110.0"
            pydantic = "2.9.2"
        """).strip()
    )
    (tmp_path / ".coding-agent-playbook.local.toml").write_text(
        textwrap.dedent("""
            [detector_cache.frameworks]
            pydantic = "2.10.0"
            sqlalchemy = "2.0.40"
        """).strip()
    )
    config = FileSystemStateSource(repo_root=tmp_path).load_config()
    assert config.detector_cache["frameworks"] == {
        "fastapi": "0.110.0",  # from primary, preserved
        "pydantic": "2.10.0",  # overridden by local
        "sqlalchemy": "2.0.40",  # added by local
    }


def test_load_config_missing_raises_fnf(tmp_path: Path) -> None:
    source = FileSystemStateSource(repo_root=tmp_path)
    with pytest.raises(FileNotFoundError, match=r"\.coding-agent-playbook\.toml"):
        source.load_config()


def test_load_primary_config_ignores_local_overrides(tmp_path: Path) -> None:
    """The hook policy reads its tables from this (``load_policy_tables``), so
    ``.local.toml`` values must never reach it (P6); unmodelled tables do."""
    (tmp_path / ".coding-agent-playbook.toml").write_text(
        CONFIG_PRIMARY + '\n[links]\nallowed_domains = ["example.com"]\n'
    )
    (tmp_path / ".coding-agent-playbook.local.toml").write_text(
        CONFIG_LOCAL_OVERRIDE + '\n[links]\nallowed_domains = ["personal.dev"]\n'
    )
    source = FileSystemStateSource(repo_root=tmp_path)
    primary = source.load_primary_config()
    assert primary.user_choices == {"banking_mode": False}
    assert primary.extra_tables == {"links": {"allowed_domains": ["example.com"]}}
    assert source.load_config().user_choices["banking_mode"] is True


def test_load_primary_config_checks_the_committed_file(tmp_path: Path) -> None:
    source = FileSystemStateSource(repo_root=tmp_path)
    with pytest.raises(FileNotFoundError, match=r"\.coding-agent-playbook\.toml"):
        source.load_primary_config()
    (tmp_path / ".coding-agent-playbook.toml").write_text(
        CONFIG_PRIMARY + '\n[adapters]\nenabled = ["claude_code"]\n'
    )
    with pytest.raises(ConfigError, match=r"^\.coding-agent-playbook\.toml: the \[adapters\]"):
        source.load_primary_config()


def test_save_config_emits_valid_toml(tmp_path: Path) -> None:
    source = FileSystemStateSource(repo_root=tmp_path)
    config = Config(
        schema_version=1,
        project=ProjectMeta(name="my-app", kind="python-application"),
        engine_version="0.1.0a0",
        user_choices={"banking_mode": True},
    )
    source.save_config(config)
    written = tmp_path / ".coding-agent-playbook.toml"
    assert written.is_file()
    with written.open("rb") as f:
        parsed = tomllib.load(f)
    assert parsed["schema_version"] == 1
    assert parsed["project"]["name"] == "my-app"
    assert parsed["engine"]["version"] == "0.1.0a0"
    assert parsed["user_choices"]["banking_mode"] is True


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


def test_save_then_load_config_roundtrip_with_nested_detector_cache(tmp_path: Path) -> None:
    """Config with a 2-level nested detector_cache.frameworks dict (the
    canonical SPEC §8.2 shape) must round-trip through TOML
    (code-quality review C1)."""
    config = Config(
        schema_version=1,
        project=ProjectMeta(name="r", kind="python-application"),
        engine_version="0.1.0a0",
        detector_cache={
            "python_version": "3.12",
            "frameworks": {"fastapi": "0.110.0", "pydantic": "2.9.2"},
        },
    )
    source = FileSystemStateSource(repo_root=tmp_path)
    source.save_config(config)
    assert source.load_config() == config


def test_save_then_load_config_roundtrip(tmp_path: Path) -> None:
    source = FileSystemStateSource(repo_root=tmp_path)
    original = Config(
        schema_version=1,
        project=ProjectMeta(
            name="my-app",
            kind="python-application",
            description="An example app",
        ),
        engine_version="0.1.0a0",
        overlays_enabled=["playbook-rules-bnp"],
        adapters_enabled=["continue", "claude_code"],
        detector_cache={"python_version": "3.12"},
        user_choices={"banking_mode": True},
    )
    source.save_config(original)
    restored = source.load_config()
    assert restored == original


def test_entry_point_registers_filesystem_state_source() -> None:
    from importlib import metadata

    eps = metadata.entry_points(group="coding_agent_playbook.state_sources")
    by_name = {ep.name: ep for ep in eps}
    assert "filesystem" in by_name
    loaded = by_name["filesystem"].load()
    assert loaded is FileSystemStateSource


# --------------------------------------------------------------------------- #
# Committed-only reads + save_config_table — what `playbook init` and
# `check --refresh` rewrite, so personal .local.toml overrides never reach the
# committed file — and the per-file checks that name the file at fault
# --------------------------------------------------------------------------- #

CONFIG_WITH_UNMANAGED_TABLES = (
    CONFIG_PRIMARY
    + """
[links]
allowed_domains = ["example.com"]

[metrics]
mode = "absolute"

[metrics.thresholds.cyclomatic_complexity]
warn = 10
fail = 20.5

[metrics.weights]
coverage = 1.0
"""
)

#: A local file whose every key would leak into a committed rewrite of the merge.
CONFIG_LOCAL_EVERYTHING = """\
adapters_enabled = ["claude_code"]
overlays_enabled = ["some_overlay"]

[user_choices]
banking_mode = true

[output]
commit = true
"""


def test_read_committed_config_table_ignores_the_local_file(tmp_path: Path) -> None:
    (tmp_path / ".coding-agent-playbook.toml").write_text(CONFIG_WITH_UNMANAGED_TABLES)
    (tmp_path / ".coding-agent-playbook.local.toml").write_text(CONFIG_LOCAL_EVERYTHING)
    table = FileSystemStateSource(repo_root=tmp_path).read_committed_config_table()
    assert table == tomllib.loads(CONFIG_WITH_UNMANAGED_TABLES)


def test_read_committed_config_table_missing_raises_fnf(tmp_path: Path) -> None:
    source = FileSystemStateSource(repo_root=tmp_path)
    with pytest.raises(FileNotFoundError, match=r"missing \.coding-agent-playbook\.toml"):
        source.read_committed_config_table()


def test_read_committed_config_table_error_names_the_committed_file(tmp_path: Path) -> None:
    from coding_agent_playbook.config.schema import ConfigError

    (tmp_path / ".coding-agent-playbook.toml").write_text(
        CONFIG_PRIMARY.replace("[project]", '[adapters]\nenabled = ["continue"]\n\n[project]')
    )
    source = FileSystemStateSource(repo_root=tmp_path)
    with pytest.raises(ConfigError, match=r"^\.coding-agent-playbook\.toml: the \[adapters\]"):
        source.read_committed_config_table()


def test_read_committed_config_table_never_reads_a_broken_local_file(tmp_path: Path) -> None:
    """The local file is not read at all, so even one load_config refuses is ignored."""
    (tmp_path / ".coding-agent-playbook.toml").write_text(CONFIG_PRIMARY)
    (tmp_path / ".coding-agent-playbook.local.toml").write_text('[adapters]\nenabled = ["x"]\n')
    source = FileSystemStateSource(repo_root=tmp_path)
    assert source.read_committed_config_table()["project"]["name"] == "my-app"


def test_has_committed_config(tmp_path: Path) -> None:
    source = FileSystemStateSource(repo_root=tmp_path)
    (tmp_path / ".coding-agent-playbook.local.toml").write_text("")
    assert source.has_committed_config() is False
    (tmp_path / ".coding-agent-playbook.toml").write_text(CONFIG_PRIMARY)
    assert source.has_committed_config() is True


_PRIMARY_NAME = ".coding-agent-playbook.toml"
_LOCAL_NAME = ".coding-agent-playbook.local.toml"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        pytest.param(b"broken = [\n", "invalid TOML: Invalid value", id="syntax"),
        pytest.param(b'x = "\xff"\n', "not UTF-8 text (invalid start byte at byte 5)", id="utf8"),
        pytest.param(
            b"x = " + b"[" * 3000 + b"1" + b"]" * 3000 + b"\n",
            "inline arrays/tables nested too deeply for Python's TOML reader",
            id="deep-inline",
        ),
    ],
)
@pytest.mark.parametrize("name", [_PRIMARY_NAME, _LOCAL_NAME])
def test_a_file_tomllib_cannot_read_is_a_config_error_naming_it(
    tmp_path: Path, name: str, content: bytes, message: str
) -> None:
    """Regression: a syntax error, a non-UTF-8 byte or inline values nested past the
    recursion limit escaped as ``TOMLDecodeError``/``UnicodeDecodeError``/
    ``RecursionError`` — a traceback, exit 1 — from every command."""
    from coding_agent_playbook.config.schema import ConfigError

    (tmp_path / _PRIMARY_NAME).write_text(CONFIG_PRIMARY)
    (tmp_path / name).write_bytes(content)
    with pytest.raises(ConfigError, match=f"^{re.escape(f'{name}: {message}')}"):
        FileSystemStateSource(repo_root=tmp_path).load_config()


def test_a_table_header_a_thousand_levels_deep_loads(tmp_path: Path) -> None:
    """Regression: the recursive enabled-key walk raised ``RecursionError`` past
    ~990 levels although ``tomllib`` builds headers iteratively, with no limit."""
    header = ".".join(f"d{i}" for i in range(1000))
    (tmp_path / _PRIMARY_NAME).write_text(f"{CONFIG_PRIMARY}\n[{header}]\nleaf = 1\n")
    source = FileSystemStateSource(repo_root=tmp_path)
    assert source.load_config().project.name == "my-app"
    assert "d0" in source.read_committed_config_table()


def test_save_config_table_writes_every_entry_back_verbatim(tmp_path: Path) -> None:
    (tmp_path / _PRIMARY_NAME).write_text(CONFIG_WITH_UNMANAGED_TABLES)
    source = FileSystemStateSource(repo_root=tmp_path)
    table = source.read_committed_config_table()
    source.save_config_table(table)
    assert_toml_identical(source.read_committed_config_table(), table)


def test_save_config_writes_exactly_config_to_dict(tmp_path: Path) -> None:
    """The ``StateSource`` method writes ``config.to_dict()`` and nothing else —
    ``extra_tables`` (``[links]``/``[metrics]``) included. No command calls it:
    rewrites go through ``commands/_committed_config`` (§7.2)."""
    (tmp_path / _PRIMARY_NAME).write_text(CONFIG_WITH_UNMANAGED_TABLES)
    source = FileSystemStateSource(repo_root=tmp_path)
    config = Config.from_dict(source.read_committed_config_table())
    source.save_config(config)
    assert_toml_identical(source.read_committed_config_table(), config.to_dict())


CONFIG_WITH_UNKNOWN_SUB_KEYS = CONFIG_PRIMARY.replace(
    "[engine]\n", '[engine]\nchannel = "beta"\n', 1
).replace('kind = "python-application"\n', 'kind = "python-application"\nhomepage = "h"\n', 1)


def test_a_config_rewrite_keeps_unknown_keys_of_managed_tables(tmp_path: Path) -> None:
    from coding_agent_playbook.config.entries import (
        unmanaged_config_entries,
        with_unmanaged_entries,
    )

    assert CONFIG_WITH_UNKNOWN_SUB_KEYS.count("homepage") == 1  # the fixture took
    assert CONFIG_WITH_UNKNOWN_SUB_KEYS.count("channel") == 1
    (tmp_path / _PRIMARY_NAME).write_text(CONFIG_WITH_UNKNOWN_SUB_KEYS)
    source = FileSystemStateSource(repo_root=tmp_path)
    table = source.read_committed_config_table()
    config = Config.from_dict(table)
    source.save_config_table(
        with_unmanaged_entries(config.to_dict(), unmanaged_config_entries(table))
    )
    assert_toml_identical(source.read_committed_config_table(), table)


def test_preview_config_is_load_config_after_the_save_and_writes_nothing(tmp_path: Path) -> None:
    (tmp_path / ".coding-agent-playbook.local.toml").write_text(CONFIG_LOCAL_EVERYTHING)
    source = FileSystemStateSource(repo_root=tmp_path)
    config = Config(1, ProjectMeta("x", "python-library"), "0.1.0a0", adapters_enabled=["a"])

    table = {**config.to_dict(), "links": {"allowed_domains": []}}

    preview = source.preview_config(table)

    assert sorted(path.name for path in tmp_path.iterdir()) == [_LOCAL_NAME]
    source.save_config_table(table)
    assert preview == source.load_config()
    assert preview.adapters_enabled == ["claude_code"]  # the local list replaces the committed one
    assert preview.commit_output is True


#: Shapes ``Config`` would misread, each with the start of the error naming the table.
_MISREAD_SHAPES = [
    pytest.param(
        '[output]\ncommit = "yes"\n',
        "[output] commit must be a boolean (true or false), got 'yes'",
        id="output-commit",
    ),
    pytest.param('project = "x"\n', "[project] must be a table, got 'x'", id="project"),
    pytest.param('engine = "x"\n', "[engine] must be a table, got 'x'", id="engine"),
    pytest.param('storage = "x"\n', "[storage] must be a table, got 'x'", id="storage"),
    pytest.param('output = "x"\n', "[output] must be a table, got 'x'", id="output"),
    pytest.param('user_choices = "x"\n', "[user_choices] must be a table, got 'x'", id="uc"),
    pytest.param('detector_cache = ["x"]\n', "[detector_cache] must be a table", id="cache"),
]


@pytest.mark.parametrize(("local", "message"), _MISREAD_SHAPES)
def test_every_read_of_a_misread_local_file_names_the_local_file(
    tmp_path: Path, local: str, message: str
) -> None:
    """Regression: these shapes passed the per-file check and failed only merged,
    blamed on the committed file by ``load_config`` (``sync``, ``check``,
    ``validate``…) while ``init``'s preview named the local one."""
    from coding_agent_playbook.config.schema import ConfigError

    (tmp_path / _LOCAL_NAME).write_text(local)
    (tmp_path / _PRIMARY_NAME).write_text(CONFIG_PRIMARY)
    source = FileSystemStateSource(repo_root=tmp_path)
    expected = f"^{re.escape(f'{_LOCAL_NAME}: {message}')}"
    for read in (source.load_local_overrides, source.load_config):
        with pytest.raises(ConfigError, match=expected):
            read()
    with pytest.raises(ConfigError, match=expected):
        source.preview_config(Config(1, ProjectMeta("x", "python-library"), "0.1.0a0").to_dict())


@pytest.mark.parametrize(("shape", "message"), _MISREAD_SHAPES)
def test_a_misread_committed_table_is_refused_even_when_the_local_file_hides_it(
    tmp_path: Path, shape: str, message: str
) -> None:
    """Regression: a local ``[user_choices]`` (the file ``init`` creates) replaced a
    committed ``user_choices = "x"`` in the merge, so ``sync`` ran while ``init``
    and ``check --refresh``, reading the committed file alone, crashed with a
    traceback; teammates without a local file crashed too. Now every read of the
    committed file refuses it, naming it."""
    from coding_agent_playbook.config.schema import ConfigError
    from coding_agent_playbook.toml_writer import dump_toml

    # The shape replaces the fixture's own entry (a second `project` would not parse).
    (tmp_path / _PRIMARY_NAME).write_text(
        dump_toml({**tomllib.loads(CONFIG_PRIMARY), **tomllib.loads(shape)})
    )
    hiding = "".join(f"[{key}]\n" for key in ("project", "engine", "storage", "output"))
    (tmp_path / _LOCAL_NAME).write_text(f"{hiding}[user_choices]\n[detector_cache]\n")
    source = FileSystemStateSource(repo_root=tmp_path)
    expected = f"^{re.escape(f'{_PRIMARY_NAME}: {message}')}"
    for read in (source.read_committed_config_table, source.load_config):
        with pytest.raises(ConfigError, match=expected):
            read()


def test_save_then_load_config_keeps_keys_that_need_quotes(tmp_path: Path) -> None:
    """Regression: ``_dump_toml`` wrote keys raw, so every ``save_config`` (an
    ``init`` re-run, ``check --refresh``) turned a committed ``"docs.style"``
    choice into a ``docs`` table and a detected ``ruamel.yaml`` dependency into a
    ``ruamel`` table — valid TOML that ``tomllib`` read back as other keys."""
    config = Config(
        1,
        ProjectMeta("x", "python-library"),
        "0.1.0a0",
        detector_cache={"dependencies": {"ruamel.yaml": ">=0.17", "zope.interface": ""}},
        user_choices={"docs.style": "google", '"q"': 1},
    )
    source = FileSystemStateSource(repo_root=tmp_path)
    source.save_config(config)
    loaded = source.load_config()
    assert loaded == config
    assert_toml_identical(loaded.user_choices, {"docs.style": "google", '"q"': 1})
    assert list(loaded.detector_cache["dependencies"]) == ["ruamel.yaml", "zope.interface"]
