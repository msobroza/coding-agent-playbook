"""``playbook validate``'s check of the ``[forge]`` table (specs/prF-forge-adapter.md §5.4).

Only ``playbook forge`` reads ``[forge] hosts``; validate reports its unknown
keys and values from the committed file, one finding per problem, through the
same parser (:mod:`coding_agent_playbook.config.tables.forge`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.config.files import ConfigFiles
from coding_agent_playbook.config.schema import ConfigError
from coding_agent_playbook.config.tables.forge import checked_forge_table
from coding_agent_playbook.validation.findings import ValidationError

if TYPE_CHECKING:
    from pathlib import Path


def check_forge_table(repo_root: Path) -> list[ValidationError]:
    """One :class:`ValidationError` per problem of the committed ``[forge]`` table.

    Example::

        >>> check_forge_table(Path("/no/such/repo"))
        []
    """
    files = ConfigFiles(repo_root)
    where = str(files.committed_path)
    try:
        table = files.committed_table("forge")
    except ConfigError as error:
        return [ValidationError(path=where, message=str(error))]
    _, problems = checked_forge_table(table)
    return [ValidationError(path=where, message=problem) for problem in problems]
