"""The enabled lists are top-level keys; other shapes are refused (SPEC §7.1, §7.2).

``Config`` reads only the top-level ``overlays_enabled`` / ``adapters_enabled``
lists. An ``[overlays]`` / ``[adapters]`` table (or a dotted
``overlays.enabled = …`` key, which TOML parses as the same table) used to be
ignored without a word: ``playbook sync`` then ran with only ``agents_md`` and
settled every other adapter's earlier output as leftovers. A string value
became a list of characters. Both are now a :class:`ConfigError` that names the
file and quotes the offending value.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.config import (
    Config,
    ConfigError,
    OutputConfig,
    ProjectMeta,
    check_enabled_keys,
    parse_output_config,
)
from coding_agent_playbook.sources.filesystem import FileSystemStateSource

if TYPE_CHECKING:
    from pathlib import Path

_BASE = """\
schema_version = 1

[project]
name = "x"
kind = "python-library"

[engine]
version = "0.1.0a0"
"""

_PRIMARY = ".coding-agent-playbook.toml"
_LOCAL = ".coding-agent-playbook.local.toml"

#: Every fix-it hint says where the key goes: TOML nests a key written after a
#: ``[table]`` header inside that table, where it is not read.
_HINT = "use the top-level key instead, at the top of the file, above the first [table] header: "


def _data(*, top: str = "", tables: str = "") -> dict[str, Any]:
    """Parse ``_BASE`` with ``top`` keys before it and ``tables`` after it.

    Top-level keys must precede the first table header in TOML, so they go first.
    """
    return tomllib.loads(top + _BASE + tables)


# --------------------------------------------------------------------------- #
# The legacy table form
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("table", "key"), [("overlays", "overlays_enabled"), ("adapters", "adapters_enabled")]
)
def test_table_form_is_refused_with_the_top_level_replacement(table: str, key: str) -> None:
    data = _data(tables=f'\n[{table}]\nenabled = ["a_pkg", "b_pkg"]\n')
    with pytest.raises(ConfigError) as exc:
        Config.from_dict(data, source=_PRIMARY)
    message = str(exc.value)
    assert message.startswith(f"{_PRIMARY}: the [{table}] table is not read")
    # Quotes the offending value, then shows the line to write instead.
    assert "{'enabled': ['a_pkg', 'b_pkg']}" in message
    assert message.endswith(f'{_HINT}{key} = ["a_pkg", "b_pkg"]')


def test_dotted_key_form_parses_as_the_same_table_and_is_refused() -> None:
    data = _data(top='overlays.enabled = ["coding_agent_playbook.plugins.superpowers"]\n')
    with pytest.raises(ConfigError) as exc:
        check_enabled_keys(data, source="cfg.toml")
    assert str(exc.value).startswith("cfg.toml: the [overlays] table is not read")
    assert 'overlays_enabled = ["coding_agent_playbook.plugins.superpowers"]' in str(exc.value)


def test_fixit_hint_recommends_canonical_name() -> None:
    """The hint never recommends the deprecated ``packs`` spelling (SPEC v0.19);
    the ``found`` part still quotes the file as written."""
    data = _data(tables='\n[overlays]\nenabled = ["coding_agent_playbook.packs.superpowers"]\n')
    with pytest.raises(ConfigError) as exc:
        Config.from_dict(data, source=_PRIMARY)
    found, hint = str(exc.value).split(_HINT, 1)
    assert "coding_agent_playbook.packs.superpowers" in found
    assert hint == 'overlays_enabled = ["coding_agent_playbook.plugins.superpowers"]'
    assert ".packs." not in hint


def test_table_without_an_enabled_list_is_refused_too() -> None:
    data = _data(tables="\n[adapters]\nclaude_code = true\n")
    with pytest.raises(ConfigError) as exc:
        check_enabled_keys(data, source="cfg.toml")
    message = str(exc.value)
    assert "{'claude_code': True}" in message
    assert message.endswith(f"{_HINT}adapters_enabled = [<adapter names>]")


def test_an_empty_table_is_refused() -> None:
    with pytest.raises(ConfigError, match=r"the \[overlays\] table is not read"):
        check_enabled_keys(_data(tables="\n[overlays]\n"), source="cfg.toml")


def test_a_non_table_value_under_the_legacy_name_is_refused() -> None:
    data = _data(top='overlays = ["x_pkg"]\n')
    with pytest.raises(ConfigError) as exc:
        check_enabled_keys(data, source="cfg.toml")
    message = str(exc.value)
    assert message.startswith(
        "cfg.toml: the top-level key 'overlays' is not read (found ['x_pkg'])"
    )
    assert message.endswith(f'{_HINT}overlays_enabled = ["x_pkg"]')


def test_both_tables_are_reported_in_one_error() -> None:
    data = _data(
        tables='\n[overlays]\nenabled = ["o_pkg"]\n\n[adapters]\nenabled = ["claude_code"]\n'
    )
    with pytest.raises(ConfigError) as exc:
        check_enabled_keys(data, source="cfg.toml")
    first, second = str(exc.value).splitlines()
    assert first.startswith("cfg.toml: the [overlays] table is not read")
    assert first.endswith('overlays_enabled = ["o_pkg"]')
    assert second.startswith("cfg.toml: the [adapters] table is not read")
    assert second.endswith('adapters_enabled = ["claude_code"]')


# --------------------------------------------------------------------------- #
# Non-list values
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("key", ["overlays_enabled", "adapters_enabled"])
def test_a_string_value_is_refused_not_split_into_characters(key: str) -> None:
    data = _data(top=f'{key} = "claude_code"\n')
    with pytest.raises(ConfigError) as exc:
        Config.from_dict(data, source="cfg.toml")
    message = str(exc.value)
    assert message.startswith(f"cfg.toml: {key} must be a list of strings, got 'claude_code'")
    assert message.endswith(f'write {key} = ["claude_code"]')


@pytest.mark.parametrize("bad", ['["ok", 1]', "{ a = 1 }", "true", '[["nested"]]', "3"])
def test_a_value_that_is_not_a_list_of_strings_is_refused(bad: str) -> None:
    data = _data(top=f"adapters_enabled = {bad}\n")
    with pytest.raises(ConfigError) as exc:
        Config.from_dict(data)
    message = str(exc.value)
    assert "adapters_enabled must be a list of strings" in message
    assert repr(data["adapters_enabled"]) in message


@pytest.mark.parametrize("key", ["overlays_enabled", "adapters_enabled"])
@pytest.mark.parametrize("bad", ['[""]', '["ok", "  "]'])
def test_an_empty_name_is_refused(key: str, bad: str) -> None:
    """``""`` used to reach ``importlib`` and crash every command with a traceback."""
    data = _data(top=f"{key} = {bad}\n")
    with pytest.raises(ConfigError) as exc:
        check_enabled_keys(data, source="cfg.toml")
    assert str(exc.value) == (
        f"cfg.toml: {key} lists an empty name, got {data[key]!r}; remove the empty entry"
    )


# --------------------------------------------------------------------------- #
# An enabled key nested in a table (written after a [table] header)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("key", ["overlays_enabled", "adapters_enabled"])
@pytest.mark.parametrize(
    ("tables", "where"),
    [
        ("", "engine"),  # right after _BASE's last header: the in-place fix of [overlays]
        ("\n[output]\ncommit = false\n", "output"),
        ('\n[detector_cache]\npython_version = "3.12"\n[detector_cache.frameworks]\n', None),
    ],
)
def test_a_key_nested_in_a_table_is_refused(key: str, tables: str, where: str | None) -> None:
    """TOML puts every key after a ``[table]`` header inside that table, unread."""
    table = where or "detector_cache.frameworks"
    data = _data(tables=f'{tables}{key} = ["claude_code"]\n')
    assert data[table.split(".")[0]]  # the key really is nested, not top-level
    assert key not in data

    with pytest.raises(ConfigError) as exc:
        Config.from_dict(data, source=_PRIMARY)

    assert str(exc.value) == (
        f"{_PRIMARY}: '{key}' in the [{table}] table is not read (found ['claude_code']) "
        "(TOML puts every key written after a [table] header in that table); "
        f'{_HINT}{key} = ["claude_code"]'
    )


def test_a_key_nested_under_project_is_refused() -> None:
    data = tomllib.loads(
        'schema_version = 1\n[project]\nname = "x"\nkind = "python-library"\n'
        'overlays_enabled = ["o_pkg"]\n[engine]\nversion = "0.1.0a0"\n'
    )
    with pytest.raises(ConfigError, match=r"^cfg\.toml: 'overlays_enabled' in the \[project\]"):
        check_enabled_keys(data, source="cfg.toml")


def test_a_dotted_legacy_key_nested_in_a_table_is_refused() -> None:
    data = _data(tables='overlays.enabled = ["o_pkg"]\n')
    assert data["engine"]["overlays"] == {"enabled": ["o_pkg"]}
    with pytest.raises(ConfigError) as exc:
        check_enabled_keys(data, source="cfg.toml")
    message = str(exc.value)
    assert message.startswith("cfg.toml: the [engine.overlays] table is not read")
    assert message.endswith(f'{_HINT}overlays_enabled = ["o_pkg"]')


def test_a_nested_key_is_refused_even_next_to_a_valid_top_level_one() -> None:
    data = _data(
        top='adapters_enabled = ["continue"]\n', tables='adapters_enabled = ["opencode"]\n'
    )
    with pytest.raises(ConfigError, match=r"'adapters_enabled' in the \[engine\] table"):
        check_enabled_keys(data, source="cfg.toml")


def test_framework_names_that_resemble_the_legacy_names_still_load() -> None:
    """A ``detector_cache.frameworks`` entry may be the ``adapters`` library: not a mistake."""
    data = _data(
        tables='\n[detector_cache.frameworks]\nadapters = "1.1.0"\noverlays = "0.2"\n'
        "\n[metrics.thresholds.adapters]\nwarn = 1\n"
    )
    check_enabled_keys(data, source="cfg.toml")
    assert Config.from_dict(data).detector_cache == {
        "frameworks": {"adapters": "1.1.0", "overlays": "0.2"}
    }


# --------------------------------------------------------------------------- #
# A misspelled enabled key
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("typo", "key"),
    [
        ("overlay_enabled", "overlays_enabled"),
        ("adapter_enabled", "adapters_enabled"),
        ("overlays-enabled", "overlays_enabled"),
        ("OVERLAYS_ENABLED", "overlays_enabled"),
        ("enabled_adapters", "adapters_enabled"),
        ("adaptors_enabled", "adapters_enabled"),
    ],
)
def test_a_misspelled_top_level_key_is_refused(typo: str, key: str) -> None:
    data = _data(top=f'{typo} = ["x_pkg"]\n')
    with pytest.raises(ConfigError) as exc:
        Config.from_dict(data, source="cfg.toml")
    assert str(exc.value) == (
        f"cfg.toml: the top-level key {typo!r} is not read (found ['x_pkg']) "
        f'(did you mean {key}?); {_HINT}{key} = ["x_pkg"]'
    )


def test_a_misspelled_key_nested_in_a_table_names_both_mistakes() -> None:
    data = _data(tables='overlay_enabled = ["x_pkg"]\n')
    with pytest.raises(ConfigError) as exc:
        check_enabled_keys(data, source="cfg.toml")
    assert str(exc.value) == (
        "cfg.toml: 'overlay_enabled' in the [engine] table is not read (found ['x_pkg']) "
        "(TOML puts every key written after a [table] header in that table; "
        f'did you mean overlays_enabled?); {_HINT}overlays_enabled = ["x_pkg"]'
    )


@pytest.mark.parametrize("unrelated", ["overlays_note", "enabled", "adapter", "plugins_enabled"])
def test_an_unrelated_key_is_not_taken_for_a_misspelling(unrelated: str) -> None:
    check_enabled_keys(_data(top=f'{unrelated} = ["x"]\n'), source="cfg.toml")


def test_from_dict_names_a_generic_source_by_default() -> None:
    with pytest.raises(ConfigError, match=r"^config: the \[adapters\] table is not read"):
        Config.from_dict(_data(tables="\n[adapters]\nenabled = []\n"))


def test_config_error_is_a_value_error() -> None:
    assert issubclass(ConfigError, ValueError)


def test_output_errors_are_config_errors() -> None:
    """The CLI reports every ConfigError cleanly, so ``[output]`` mistakes use it too."""
    with pytest.raises(ConfigError, match="commit must be a boolean"):
        parse_output_config({"commit": "false"})
    with pytest.raises(ConfigError, match="must be a table"):
        parse_output_config(True)


# --------------------------------------------------------------------------- #
# Valid configs are unchanged
# --------------------------------------------------------------------------- #


def test_top_level_lists_load_unchanged() -> None:
    data = _data(
        top='overlays_enabled = ["o_pkg"]\nadapters_enabled = ["claude_code", "opencode"]\n'
    )
    check_enabled_keys(data, source="cfg.toml")
    config = Config.from_dict(data)
    assert config.overlays_enabled == ["o_pkg"]
    assert config.adapters_enabled == ["claude_code", "opencode"]


def test_empty_lists_and_absent_keys_are_valid() -> None:
    assert Config.from_dict(_data(top="overlays_enabled = []\n")).overlays_enabled == []
    assert Config.from_dict(_data()).adapters_enabled == []


def test_to_dict_passes_the_check_and_round_trips() -> None:
    config = Config(
        schema_version=1,
        project=ProjectMeta(name="x", kind="python-library"),
        engine_version="0.1.0a0",
        overlays_enabled=["coding_agent_playbook.plugins.superpowers"],
        adapters_enabled=["continue", "claude_code"],
        output=OutputConfig(commit=False),
    )
    data = config.to_dict()
    check_enabled_keys(data, source="cfg.toml")
    assert Config.from_dict(data) == config


# --------------------------------------------------------------------------- #
# FileSystemStateSource: each file is checked on its own, before the merge
# --------------------------------------------------------------------------- #


def _write_primary(repo: Path, *, top: str = "", tables: str = "") -> None:
    (repo / _PRIMARY).write_text(top + _BASE + tables, encoding="utf-8")


def test_load_config_names_the_primary_file(tmp_path: Path) -> None:
    _write_primary(tmp_path, tables='\n[overlays]\nenabled = ["o_pkg"]\n')
    with pytest.raises(ConfigError) as exc:
        FileSystemStateSource(repo_root=tmp_path).load_config()
    assert str(exc.value).startswith(f"{_PRIMARY}: the [overlays] table is not read")


def test_load_config_names_the_local_file(tmp_path: Path) -> None:
    _write_primary(tmp_path, top='adapters_enabled = ["continue", "claude_code"]\n')
    (tmp_path / _LOCAL).write_text('[adapters]\nenabled = ["claude_code"]\n', encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        FileSystemStateSource(repo_root=tmp_path).load_config()
    message = str(exc.value)
    assert message.startswith(f"{_LOCAL}: the [adapters] table is not read")
    assert message.endswith('adapters_enabled = ["claude_code"]')


def test_load_config_refuses_a_key_appended_after_the_init_written_local_table(
    tmp_path: Path,
) -> None:
    """``playbook init`` writes the local file as ``[user_choices]`` only, so an
    appended ``adapters_enabled`` lands in that table: refused, naming the local file."""
    _write_primary(tmp_path, top='adapters_enabled = ["continue", "claude_code"]\n')
    (tmp_path / _LOCAL).write_text(
        '[user_choices]\nadapters_enabled = ["claude_code"]\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError) as exc:
        FileSystemStateSource(repo_root=tmp_path).load_config()
    message = str(exc.value)
    assert message.startswith(f"{_LOCAL}: 'adapters_enabled' in the [user_choices] table")
    assert message.endswith(f'{_HINT}adapters_enabled = ["claude_code"]')


def test_load_config_names_the_primary_file_for_a_nested_key(tmp_path: Path) -> None:
    _write_primary(tmp_path, tables='\n[output]\ncommit = false\noverlays_enabled = ["o"]\n')
    with pytest.raises(ConfigError, match=rf"^{_PRIMARY}: 'overlays_enabled' in the \[output\]"):
        FileSystemStateSource(repo_root=tmp_path).load_config()


def test_load_config_refuses_a_string_list_in_the_local_file(tmp_path: Path) -> None:
    _write_primary(tmp_path)
    (tmp_path / _LOCAL).write_text('adapters_enabled = "claude_code"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match=rf"^{_LOCAL}: adapters_enabled must be a list"):
        FileSystemStateSource(repo_root=tmp_path).load_config()


def test_a_local_list_replaces_the_primary_list(tmp_path: Path) -> None:
    """SPEC §7.2: lists are replaced by the local file, not merged."""
    _write_primary(tmp_path, top='adapters_enabled = ["continue", "claude_code", "opencode"]\n')
    (tmp_path / _LOCAL).write_text('adapters_enabled = ["claude_code"]\n', encoding="utf-8")
    config = FileSystemStateSource(repo_root=tmp_path).load_config()
    assert config.adapters_enabled == ["claude_code"]


def test_load_local_overrides_reads_and_checks_the_local_file(tmp_path: Path) -> None:
    source = FileSystemStateSource(repo_root=tmp_path)
    assert source.load_local_overrides() == {}
    (tmp_path / _LOCAL).write_text('[user_choices]\nstyle = "google"\n', encoding="utf-8")
    assert source.load_local_overrides() == {"user_choices": {"style": "google"}}
    (tmp_path / _LOCAL).write_text("[overlays]\nenabled = []\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=rf"^{_LOCAL}: the \[overlays\] table is not read"):
        source.load_local_overrides()
