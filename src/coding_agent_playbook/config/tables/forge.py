"""The ``[forge]`` table of ``.coding-agent-playbook.toml`` (specs/prF-forge-adapter.md §5.4).

Only ``playbook forge`` reads it, to map a remote host the §5.2 rules cannot
name to its forge; the guards never do (Q48), and it is not in ``Config``,
``CONFIG_MANAGED_KEYS`` or ``schema._TABLE_HINTS``::

    [forge]
    hosts = { "git.acme.com" = "gitlab", "ssh.acme.com" = { forge = "gitlab", api_host = "gitlab.acme.com" } }

Keys are checked through the table-shape reader; each ``hosts`` value through
:func:`coding_agent_playbook.forge.hosts.host_entry`, so ``playbook validate``
and ``playbook forge`` reject the same values. Stdlib-only, like its siblings.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from coding_agent_playbook.config.tables._table_shapes import TableShape, read_table
from coding_agent_playbook.forge.hosts import host_entry

__all__ = ["ForgeTable", "checked_forge_table", "parse_forge_table"]

_LABEL: Final = "[forge]"
_SHAPES: Final = {
    "hosts": TableShape(
        'a table of host = "github" | "gitlab" | { forge = ..., api_host = ... }',
        lambda value: isinstance(value, Mapping),
        dict,
    ),
}


@dataclass(frozen=True)
class ForgeTable:
    """A checked ``[forge]`` table: ``hosts`` maps each host to its raw, valid entry.

    The entries stay raw (``"gitlab"`` or ``{forge, api_host}``) because
    :func:`coding_agent_playbook.forge.hosts.forge_for_host` reads them as written.

    Example: ``ForgeTable(hosts={"git.acme.com": "gitlab"})``.
    """

    hosts: Mapping[str, object] = field(default_factory=dict)


def checked_forge_table(data: Mapping[str, Any]) -> tuple[ForgeTable, list[str]]:
    """The valid part of the ``[forge]`` table ``data``, and one line per unknown key or bad value.

    Example::

        >>> checked_forge_table({"hosts": {"git.acme.com": "svn"}})[1]
        ["[forge] hosts entry 'git.acme.com': 'svn' is not a forge (expected one of github, gitlab)"]
    """
    problems: list[str] = []
    values = read_table(data, _SHAPES, label=_LABEL, problems=problems)
    hosts: dict[str, object] = {}
    for host, value in values.get("hosts", {}).items():
        try:
            host_entry(value)
        except ValueError as error:
            problems.append(f"{_LABEL} hosts entry {host!r}: {error}")
        else:
            hosts[str(host)] = value
    return ForgeTable(hosts=hosts), problems


def parse_forge_table(data: object) -> ForgeTable:
    """The checked ``[forge]`` table, or a ``ValueError`` listing every problem, one per line.

    ``data`` is the decoded ``forge`` entry of the file (``{}`` when absent).

    Example::

        >>> parse_forge_table({"hosts": {"git.acme.com": "gitlab"}}).hosts
        {'git.acme.com': 'gitlab'}
    """
    if not isinstance(data, Mapping):
        raise ValueError(f"{_LABEL} must be a table, got {data!r}")
    table, problems = checked_forge_table(data)
    if problems:
        raise ValueError("\n".join(problems))
    return table
