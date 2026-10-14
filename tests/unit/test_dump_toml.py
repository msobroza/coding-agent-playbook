"""Tests for the Config/Lockfile TOML document writer (``sources.filesystem._dump_toml``).

P6 makes the writer total over what ``tomllib`` returns, because ``Config`` now
writes back the tables it does not model (``[hooks]``, ``[links]``,
``[metrics]``…): values below two header levels become inline tables, and every
key and header segment is quoted when it is not a bare TOML key. The engine's
own Config/Lockfile shapes must still serialize byte-for-byte as before.
"""

from __future__ import annotations

import datetime
import tomllib

from coding_agent_playbook.config import Config, OutputConfig, ProjectMeta
from coding_agent_playbook.lockfile import LockEntry, Lockfile
from coding_agent_playbook.sources.filesystem import _dump_toml


def test_dump_toml_inline_tables_beyond_depth_two() -> None:
    data = {
        "schema_version": 1,
        "a": {"flat": True, "b": {"c": {"d": 1, "e": {"f": [1.5, "x"]}}}},
        "metrics": {"rows": [{"name": "cc", "fail": 20}, {"name": "mi", "warn": {"min": 0.5}}]},
        "entries": [{"path": "x", "meta": {"deep": {"er": 1}}, "tags": [{"k": "v"}]}],
    }
    text = _dump_toml(data)
    assert tomllib.loads(text) == data
    assert '[a.b]\nc = { d = 1, e = { f = [1.5, "x"] } }\n' in text
    assert 'rows = [{ name = "cc", fail = 20 }, { name = "mi", warn = { min = 0.5 } }]' in text
    assert '[[entries]]\npath = "x"\nmeta = { deep = { er = 1 } }\ntags = [{ k = "v" }]\n' in text


def test_dump_toml_keeps_temporal_values() -> None:
    data = {
        "links": {"checked_on": datetime.date(2026, 10, 14), "at": datetime.time(7, 30)},
        "stamp": datetime.datetime(2026, 10, 14, 9, 0, tzinfo=datetime.UTC),
    }
    assert tomllib.loads(_dump_toml(data)) == data


def test_dump_toml_quotes_non_bare_keys() -> None:
    data = {
        "top key": "v",
        "hooks": {"with space": 1, "a.b": {"enabled": False}, "plain": {"x": 1}},
        "my entries": [{"k.k": 1}],
    }
    text = _dump_toml(data)
    assert tomllib.loads(text) == data
    assert '"top key" = "v"\n' in text
    assert '"with space" = 1\n' in text
    assert '[hooks."a.b"]\nenabled = false\n' in text
    assert "[hooks.plain]\n" in text
    assert '[["my entries"]]\n"k.k" = 1\n' in text


# Captured from the pre-P6 writer: the engine's own shapes must not drift.
_GOLDEN_CONFIG = """\
schema_version = 1
overlays_enabled = ["acme_overlay"]
adapters_enabled = ["continue", "claude_code"]

[project]
name = "my-app"
kind = "python-application"
description = "An \\"app\\""

[engine]
version = "0.1.0a0"

[storage]
artifact_source = "filesystem"
state_source = "filesystem"

[output]
commit = false

[detector_cache]
python_version = "3.12"
has_ci = true

[detector_cache.frameworks]
fastapi = "0.110.0"
scikit-learn = "1.5"

[user_choices]
banking_mode = false
docstring_style = "numpy"
"""

_GOLDEN_LOCKFILE = """\
schema_version = 2
engine_version = "0.1.0a0"
rendered_at = "2026-05-28T12:00:00Z"

[[entries]]
path = "AGENTS.md"
sha256 = "abc"
bytes = 4
kind = "composite"
adapter = "agents_md"

[[entries]]
path = ".claude/settings.json"
sha256 = "def"
bytes = 9
scope = "json:/hooks"
executable = true
"""


def test_dump_toml_without_extra_tables_is_byte_identical() -> None:
    config = Config(
        schema_version=1,
        project=ProjectMeta(name="my-app", kind="python-application", description='An "app"'),
        engine_version="0.1.0a0",
        overlays_enabled=["acme_overlay"],
        adapters_enabled=["continue", "claude_code"],
        detector_cache={
            "python_version": "3.12",
            "has_ci": True,
            "frameworks": {"fastapi": "0.110.0", "scikit-learn": "1.5"},
        },
        user_choices={"banking_mode": False, "docstring_style": "numpy"},
        output=OutputConfig(commit=False),
    )
    lockfile = Lockfile(
        schema_version=2,
        engine_version="0.1.0a0",
        rendered_at="2026-05-28T12:00:00Z",
        entries=[
            LockEntry("AGENTS.md", "abc", 4, kind="composite", adapter="agents_md"),
            LockEntry(".claude/settings.json", "def", 9, scope="json:/hooks", executable=True),
        ],
    )
    assert _dump_toml(config.to_dict()) == _GOLDEN_CONFIG
    assert _dump_toml(lockfile.to_dict()) == _GOLDEN_LOCKFILE
