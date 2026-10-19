"""``playbook check-notebooks [PATHS]`` — notebook-output-hygiene's off-workstation twin (specs/prK-hook-pack.md §E.3).

SPEC §13.2 keeps nbstripout and nbqa out of the air-gapped starter, so this
stdlib check is what the ``playbook-notebooks`` pre-commit entry
(``types: [jupyter]``) runs: every cell of each notebook named (pre-commit
passes the staged ones), or of every tracked ``.ipynb`` file without PATHS,
must keep no outputs. The check is the hook's own
(``judges.notebook_check.check_cells``), with a larger parse cap: a CLI may take
the time a hook may not.

Exit codes: 0 clean, 1 a notebook keeps outputs or is not valid notebook
JSON, 2 a path that does not exist or no git repository to list.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands._git_base import open_git
from coding_agent_playbook.hook_runtime.caps import quote_data
from coding_agent_playbook.hook_runtime.git import GitError
from coding_agent_playbook.hook_runtime.judges.notebook_check import (
    NotebookLimits,
    Oversized,
    check_cells,
    notebook_line,
    read_notebook,
)

if TYPE_CHECKING:
    import argparse

__all__ = ["CLI_MAX_BYTES", "check_notebook_file", "run", "tracked_notebooks"]

#: A notebook larger than this is reported unparsed even here.
CLI_MAX_BYTES: Final = 256 * 1024 * 1024
_LIMITS: Final = NotebookLimits(max_bytes=CLI_MAX_BYTES)


def run(args: argparse.Namespace) -> int:
    """Check ``args.paths`` (default: every tracked notebook); print one line per finding.

    Example::

        >>> run(build_parser().parse_args(["check-notebooks", "nb/a.ipynb"]))  # doctest: +SKIP
        1
    """
    root = Path(args.repo_root or ".").resolve()
    try:
        paths = [Path(p) for p in args.paths] if args.paths else tracked_notebooks(root)
    except (GitError, ValueError) as exc:  # GitBaseError is a ValueError
        print(f"error: {exc}", file=sys.stderr)
        return 2
    missing = [str(path) for path in paths if not _resolved(path, root).is_file()]
    if missing:
        print(f"error: no such notebook: {', '.join(missing)}", file=sys.stderr)
        return 2
    lines = [line for path in paths if (line := check_notebook_file(path, root)) is not None]
    print("\n".join([*lines, _summary(len(lines), len(paths))]))
    return 1 if lines else 0


def tracked_notebooks(root: Path) -> list[Path]:
    """Every ``.ipynb`` file git tracks under ``root``, repo-relative."""
    from coding_agent_playbook.hook_runtime._git_parse import split_z

    listed = open_git(root).run(["ls-files", "-z", "--", "*.ipynb"])
    return [Path(rel) for rel in split_z(listed.stdout)]


def check_notebook_file(path: Path, root: Path) -> str | None:
    """The finding line for notebook ``path`` (relative to ``root`` or absolute), else ``None``.

    Example::

        >>> check_notebook_file(Path("nb/clean.ipynb"), Path("."))  # doctest: +SKIP
        None
    """
    found = read_notebook(str(_resolved(path, root)), _LIMITS)
    label = path.as_posix()
    if found is None:
        return f"{quote_data(label)}: not a valid notebook (JSON with a cells list)."
    if isinstance(found, Oversized):
        return notebook_line(label, found, _LIMITS)
    return notebook_line(label, check_cells(found, None), _LIMITS)


def _resolved(path: Path, root: Path) -> Path:
    return path if path.is_absolute() else root / path


def _summary(flagged: int, total: int) -> str:
    if flagged:
        return f"check-notebooks: {flagged} of {total} notebooks need their outputs stripped"
    return f"check-notebooks: {total} notebooks clean"
