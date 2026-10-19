"""``ConfigFiles``: the committed config and the local overrides of one consumer repo (SPEC §7.2).

Each file is read and checked on its own, then deep-merged with the local file
on top; the committed file has one writer, ``write_committed``, and the local
file is never written back. Ported from the ``FileSystemStateSource`` cases,
which now delegate here (``test_files_state_source.py``).
"""

from __future__ import annotations

import re
import textwrap
import tomllib
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.config.files import ConfigFiles
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


def test_load_reads_the_committed_file(tmp_path: Path) -> None:
    (tmp_path / ".coding-agent-playbook.toml").write_text(CONFIG_PRIMARY)
    config = ConfigFiles(tmp_path).load()
    assert config.schema_version == 1
    assert config.project.name == "my-app"
    assert config.project.kind == "python-application"
    assert config.engine_version == "0.1.0a0"
    assert config.user_choices == {"banking_mode": False}


def test_load_merges_the_local_overrides_on_top(tmp_path: Path) -> None:
    (tmp_path / ".coding-agent-playbook.toml").write_text(CONFIG_PRIMARY)
    (tmp_path / ".coding-agent-playbook.local.toml").write_text(CONFIG_LOCAL_OVERRIDE)
    config = ConfigFiles(tmp_path).load()
    assert config.user_choices == {
        "banking_mode": True,
        "extra_dev_choice": "yes",
    }


def test_load_deep_merges_nested_tables(tmp_path: Path) -> None:
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
    config = ConfigFiles(tmp_path).load()
    assert config.detector_cache["frameworks"] == {
        "fastapi": "0.110.0",  # from primary, preserved
        "pydantic": "2.10.0",  # overridden by local
        "sqlalchemy": "2.0.40",  # added by local
    }


def test_load_without_the_committed_file_says_run_init(tmp_path: Path) -> None:
    (tmp_path / ".coding-agent-playbook.local.toml").write_text(CONFIG_LOCAL_OVERRIDE)
    with pytest.raises(FileNotFoundError) as excinfo:
        ConfigFiles(tmp_path).load()
    assert str(excinfo.value) == "missing .coding-agent-playbook.toml; run `playbook init`"


def test_load_committed_ignores_the_local_file(tmp_path: Path) -> None:
    """The hook policy reads its tables from this (``load_policy_tables``), so
    ``.local.toml`` values must never reach it (P6); unmodelled tables do."""
    (tmp_path / ".coding-agent-playbook.toml").write_text(
        CONFIG_PRIMARY + '\n[links]\nallowed_domains = ["example.com"]\n'
    )
    (tmp_path / ".coding-agent-playbook.local.toml").write_text(
        CONFIG_LOCAL_OVERRIDE + '\n[links]\nallowed_domains = ["personal.dev"]\n'
    )
    files = ConfigFiles(tmp_path)
    committed = files.load_committed()
    assert committed.user_choices == {"banking_mode": False}
    assert committed.extra_tables == {"links": {"allowed_domains": ["example.com"]}}
    assert files.load().user_choices["banking_mode"] is True


def test_load_committed_checks_the_committed_file(tmp_path: Path) -> None:
    files = ConfigFiles(tmp_path)
    with pytest.raises(FileNotFoundError, match=r"\.coding-agent-playbook\.toml"):
        files.load_committed()
    (tmp_path / ".coding-agent-playbook.toml").write_text(
        CONFIG_PRIMARY + '\n[adapters]\nenabled = ["claude_code"]\n'
    )
    with pytest.raises(ConfigError, match=r"^\.coding-agent-playbook\.toml: the \[adapters\]"):
        files.load_committed()


def test_write_committed_of_a_config_round_trips(tmp_path: Path) -> None:
    """The file holds exactly the document written (``extra_tables`` included), and
    ``load`` gives the config back."""
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
        extra_tables={"links": {"allowed_domains": ["example.com"]}},
    )
    files = ConfigFiles(tmp_path)
    files.write_committed(original.to_dict())
    written = tomllib.loads((tmp_path / ".coding-agent-playbook.toml").read_text("utf-8"))
    assert written["project"] == {
        "name": "my-app",
        "kind": "python-application",
        "description": "An example app",
    }
    assert written["links"] == {"allowed_domains": ["example.com"]}
    assert_toml_identical(written, original.to_dict())
    assert files.load() == original


def test_write_then_load_keeps_a_nested_detector_cache(tmp_path: Path) -> None:
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
    files = ConfigFiles(tmp_path)
    files.write_committed(config.to_dict())
    assert files.load() == config


# --------------------------------------------------------------------------- #
# Committed-only reads + write_committed — what `playbook init` and
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


def test_committed_ignores_the_local_file(tmp_path: Path) -> None:
    (tmp_path / ".coding-agent-playbook.toml").write_text(CONFIG_WITH_UNMANAGED_TABLES)
    (tmp_path / ".coding-agent-playbook.local.toml").write_text(CONFIG_LOCAL_EVERYTHING)
    document = ConfigFiles(tmp_path).committed()
    assert document.where == ".coding-agent-playbook.toml"
    assert document.data == tomllib.loads(CONFIG_WITH_UNMANAGED_TABLES)


def test_committed_without_the_file_says_run_init(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError) as excinfo:
        ConfigFiles(tmp_path).committed()
    assert str(excinfo.value) == "missing .coding-agent-playbook.toml; run `playbook init`"


def test_committed_error_names_the_committed_file(tmp_path: Path) -> None:
    (tmp_path / ".coding-agent-playbook.toml").write_text(
        CONFIG_PRIMARY.replace("[project]", '[adapters]\nenabled = ["continue"]\n\n[project]')
    )
    with pytest.raises(ConfigError, match=r"^\.coding-agent-playbook\.toml: the \[adapters\]"):
        ConfigFiles(tmp_path).committed()


def test_committed_never_reads_a_broken_local_file(tmp_path: Path) -> None:
    """The local file is not read at all, so even one ``load`` refuses is ignored."""
    (tmp_path / ".coding-agent-playbook.toml").write_text(CONFIG_PRIMARY)
    (tmp_path / ".coding-agent-playbook.local.toml").write_text('[adapters]\nenabled = ["x"]\n')
    project = ConfigFiles(tmp_path).committed().table("project")
    assert project["name"] == "my-app"


def test_has_committed(tmp_path: Path) -> None:
    files = ConfigFiles(tmp_path)
    (tmp_path / ".coding-agent-playbook.local.toml").write_text("")
    assert files.has_committed() is False
    (tmp_path / ".coding-agent-playbook.toml").write_text(CONFIG_PRIMARY)
    assert files.has_committed() is True
    assert files.committed_path == tmp_path / ".coding-agent-playbook.toml"
    assert files.local_path == tmp_path / ".coding-agent-playbook.local.toml"


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
    (tmp_path / _PRIMARY_NAME).write_text(CONFIG_PRIMARY)
    (tmp_path / name).write_bytes(content)
    with pytest.raises(ConfigError, match=f"^{re.escape(f'{name}: {message}')}"):
        ConfigFiles(tmp_path).load()


def test_a_table_header_a_thousand_levels_deep_loads(tmp_path: Path) -> None:
    """Regression: the recursive enabled-key walk raised ``RecursionError`` past
    ~990 levels although ``tomllib`` builds headers iteratively, with no limit."""
    header = ".".join(f"d{i}" for i in range(1000))
    (tmp_path / _PRIMARY_NAME).write_text(f"{CONFIG_PRIMARY}\n[{header}]\nleaf = 1\n")
    files = ConfigFiles(tmp_path)
    assert files.load().project.name == "my-app"
    assert "d0" in files.committed().data


def test_write_committed_writes_every_entry_back_verbatim(tmp_path: Path) -> None:
    (tmp_path / _PRIMARY_NAME).write_text(CONFIG_WITH_UNMANAGED_TABLES)
    files = ConfigFiles(tmp_path)
    document = dict(files.committed().data)
    files.write_committed(document)
    assert_toml_identical(dict(files.committed().data), document)
    assert_toml_identical(document, tomllib.loads(CONFIG_WITH_UNMANAGED_TABLES))


CONFIG_WITH_UNKNOWN_SUB_KEYS = CONFIG_PRIMARY.replace(
    "[engine]\n", '[engine]\nchannel = "beta"\n', 1
).replace('kind = "python-application"\n', 'kind = "python-application"\nhomepage = "h"\n', 1)


def test_a_rewrite_keeps_unknown_keys_of_managed_tables(tmp_path: Path) -> None:
    from coding_agent_playbook.config.entries import (
        unmanaged_config_entries,
        with_unmanaged_entries,
    )

    assert CONFIG_WITH_UNKNOWN_SUB_KEYS.count("homepage") == 1  # the fixture took
    assert CONFIG_WITH_UNKNOWN_SUB_KEYS.count("channel") == 1
    (tmp_path / _PRIMARY_NAME).write_text(CONFIG_WITH_UNKNOWN_SUB_KEYS)
    files = ConfigFiles(tmp_path)
    table = dict(files.committed().data)
    config = Config.from_dict(table)
    files.write_committed(with_unmanaged_entries(config.to_dict(), unmanaged_config_entries(table)))
    assert_toml_identical(dict(files.committed().data), table)


def test_preview_is_load_after_the_write_and_writes_nothing(tmp_path: Path) -> None:
    (tmp_path / ".coding-agent-playbook.local.toml").write_text(CONFIG_LOCAL_EVERYTHING)
    files = ConfigFiles(tmp_path)
    config = Config(1, ProjectMeta("x", "python-library"), "0.1.0a0", adapters_enabled=["a"])

    table = {**config.to_dict(), "links": {"allowed_domains": []}}

    preview = files.preview(table)

    assert sorted(path.name for path in tmp_path.iterdir()) == [_LOCAL_NAME]
    files.write_committed(table)
    assert preview == files.load()
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
    blamed on the committed file by ``load`` (``sync``, ``check``, ``validate``…)
    while ``init``'s preview named the local one."""
    (tmp_path / _LOCAL_NAME).write_text(local)
    (tmp_path / _PRIMARY_NAME).write_text(CONFIG_PRIMARY)
    files = ConfigFiles(tmp_path)
    expected = f"^{re.escape(f'{_LOCAL_NAME}: {message}')}"
    for read in (files.local_overrides, files.load):
        with pytest.raises(ConfigError, match=expected):
            read()
    with pytest.raises(ConfigError, match=expected):
        files.preview(Config(1, ProjectMeta("x", "python-library"), "0.1.0a0").to_dict())


@pytest.mark.parametrize(("shape", "message"), _MISREAD_SHAPES)
def test_a_misread_committed_table_is_refused_even_when_the_local_file_hides_it(
    tmp_path: Path, shape: str, message: str
) -> None:
    """Regression: a local ``[user_choices]`` (the file ``init`` creates) replaced a
    committed ``user_choices = "x"`` in the merge, so ``sync`` ran while ``init``
    and ``check --refresh``, reading the committed file alone, crashed with a
    traceback; teammates without a local file crashed too. Now every read of the
    committed file refuses it, naming it."""
    from coding_agent_playbook.toml_writer import dump_toml

    # The shape replaces the fixture's own entry (a second `project` would not parse).
    (tmp_path / _PRIMARY_NAME).write_text(
        dump_toml({**tomllib.loads(CONFIG_PRIMARY), **tomllib.loads(shape)})
    )
    hiding = "".join(f"[{key}]\n" for key in ("project", "engine", "storage", "output"))
    (tmp_path / _LOCAL_NAME).write_text(f"{hiding}[user_choices]\n[detector_cache]\n")
    files = ConfigFiles(tmp_path)
    expected = f"^{re.escape(f'{_PRIMARY_NAME}: {message}')}"
    for read in (files.committed, files.load_committed, files.load):
        with pytest.raises(ConfigError, match=expected):
            read()


def test_write_then_load_keeps_keys_that_need_quotes(tmp_path: Path) -> None:
    """Regression: ``_dump_toml`` wrote keys raw, so every committed rewrite (an
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
    files = ConfigFiles(tmp_path)
    files.write_committed(config.to_dict())
    loaded = files.load()
    assert loaded == config
    assert_toml_identical(loaded.user_choices, {"docs.style": "google", '"q"': 1})
    assert list(loaded.detector_cache["dependencies"]) == ["ruamel.yaml", "zope.interface"]
