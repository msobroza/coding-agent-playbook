"""The ``[forge]`` table parser (specs/prF-forge-adapter.md §5.4)."""

from __future__ import annotations

import pytest

from coding_agent_playbook.config.entries import CONFIG_MANAGED_KEYS
from coding_agent_playbook.config.schema import _TABLE_HINTS
from coding_agent_playbook.config.tables.forge import ForgeTable, parse_forge_table


def test_an_absent_table_maps_no_host() -> None:
    assert parse_forge_table({}) == ForgeTable(hosts={})


def test_hosts_take_a_forge_name_or_a_table_with_an_api_host() -> None:
    hosts = {
        "git.acme.com": "gitlab",
        "ssh.acme.com": {"forge": "gitlab", "api_host": "gitlab.acme.com"},
        "code.acme.com": {"forge": "github"},
    }

    assert parse_forge_table({"hosts": hosts}).hosts == hosts


@pytest.mark.parametrize(
    ("table", "problem"),
    [
        ({"host": {}}, "[forge] unknown key 'host'; allowed: hosts"),
        ({"hosts": "gitlab"}, "[forge] hosts: must be a table of host"),
        ({"hosts": {"x": "svn"}}, "[forge] hosts entry 'x': 'svn' is not a forge"),
        ({"hosts": {"x": {"forge": "gitlab", "token": "t"}}}, "unknown key 'token'"),
        ({"hosts": {"x": {"api_host": "a.b"}}}, "a table entry needs forge"),
        ({"hosts": {"x": {"forge": "gitlab", "api_host": "https://a.b/x"}}}, "api_host must be"),
        ({"hosts": {"x": 3}}, "expected a forge name or a table"),
    ],
)
def test_unknown_keys_and_bad_values_are_refused(table: dict[str, object], problem: str) -> None:
    with pytest.raises(ValueError) as raised:
        parse_forge_table(table)

    assert problem in str(raised.value)


def test_every_problem_is_listed_and_an_api_host_value_is_never_echoed() -> None:
    table = {"extra": 1, "hosts": {"a": "svn", "b": {"forge": "gitlab", "api_host": "tok@x/y"}}}

    with pytest.raises(ValueError) as raised:
        parse_forge_table(table)

    lines = str(raised.value).splitlines()
    assert len(lines) == 3
    assert "tok@x" not in str(raised.value)


def test_forge_is_no_config_managed_table() -> None:
    assert "forge" not in CONFIG_MANAGED_KEYS
    assert "forge" not in _TABLE_HINTS
