"""The committed ``platforms`` key (prU D63): a top-level list of known platform names.

``platforms = ["domino"]`` turns the Domino skills on in a repo with no Domino
marker yet (the detector's ``domino_project`` fact). A shape the detector would
silently ignore is refused when the config loads, like the enabled lists.
"""

from __future__ import annotations

import tomllib
from typing import Any

import pytest

from coding_agent_playbook.config.model import Config
from coding_agent_playbook.config.schema import ConfigError

_PRIMARY = ".coding-agent-playbook.toml"
_BASE = """\
schema_version = 1

[project]
name = "x"
kind = "python-library"

[engine]
version = "0.1.0a0"
"""


def _data(*, top: str = "", tables: str = "") -> dict[str, Any]:
    return tomllib.loads(top + _BASE + tables)


def test_a_top_level_platforms_list_loads_and_is_written_back() -> None:
    config = Config.from_dict(_data(top='platforms = ["domino"]\n'), source=_PRIMARY)

    assert config.to_dict()["platforms"] == ["domino"]


def test_a_string_value_is_refused_with_the_list_to_write() -> None:
    with pytest.raises(ConfigError) as exc:
        Config.from_dict(_data(top='platforms = "domino"\n'), source=_PRIMARY)

    assert str(exc.value) == (
        f"{_PRIMARY}: platforms must be a list of platform names, got 'domino'; "
        'write platforms = ["domino"]'
    )


def test_an_unknown_platform_is_refused_with_the_known_ones() -> None:
    with pytest.raises(ConfigError) as exc:
        Config.from_dict(_data(top='platforms = ["domino", "aws"]\n'), source=_PRIMARY)

    assert str(exc.value) == (
        f"{_PRIMARY}: platforms names unknown platform(s) ['aws']; known platforms: ['domino']"
    )


def test_a_platforms_key_nested_in_a_table_is_refused() -> None:
    data = _data(tables='\n[output]\ncommit = false\nplatforms = ["domino"]\n')
    assert "platforms" not in data  # TOML nested it in [output]

    with pytest.raises(ConfigError) as exc:
        Config.from_dict(data, source=_PRIMARY)

    assert str(exc.value) == (
        f"{_PRIMARY}: 'platforms' in the [output] table is not read (found ['domino']) "
        "(TOML puts every key written after a [table] header in that table); "
        "use the top-level key instead, at the top of the file, above the first [table] "
        'header: platforms = ["domino"]'
    )


def test_a_top_level_platforms_table_is_refused() -> None:
    """Regression: a ``[platforms]`` table loaded silently, and the detector ignores it."""
    data = _data(tables="\n[platforms]\ndomino = true\n")

    with pytest.raises(ConfigError) as exc:
        Config.from_dict(data, source=_PRIMARY)

    assert str(exc.value) == (
        f"{_PRIMARY}: platforms must be a list of platform names, got {{'domino': True}}; "
        'write platforms = ["domino"]'
    )
