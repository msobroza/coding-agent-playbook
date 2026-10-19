"""Every engine module's syntax tree, for the config package's source pins.

The SPEC §7.2 writer pin (``test_committed.py``), the one-spelling pin of the
two config filenames (``test_files_committed_table.py``) and the
``FileSystemStateSource`` importer pin (``test_files_state_source.py``) walk the
same trees, and name the modules they pin dotted (:func:`engine_module_file`).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING, Final

import coding_agent_playbook
from tests.engine_modules import ENGINE, engine_module

if TYPE_CHECKING:
    from collections.abc import Iterator

#: The engine package directory: :func:`engine_module_trees` keys are relative to it.
PACKAGE_ROOT: Final = Path(coding_agent_playbook.__file__).parent


def engine_module_trees() -> Iterator[tuple[str, ast.Module]]:
    """``(path, tree)`` of every engine module, the path relative to the package.

    ``resources/`` holds content, not code.

    Example: ``dict(engine_module_trees())["config/files.py"]`` is that module's tree.
    """
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        module = path.relative_to(PACKAGE_ROOT)
        if module.parts[0] != "resources":
            yield module.as_posix(), ast.parse(path.read_text(encoding="utf-8"))


def engine_module_file(dotted: str) -> str:
    """The :func:`engine_module_trees` key of the engine module ``dotted``, once it resolves.

    A pin keyed on these paths spells its modules dotted and converts them here:
    ``python -m tests.architecture.module_moves apply`` rewrites a stale dotted
    name in a string, never a package-relative path, so a raw path broke the
    importer pin when A9 moved the prior-output module; ``engine_module`` raises
    ``StaleModulePin`` for a name that no longer resolves. For a module, not a
    package (a package's key is its ``__init__.py``).

    Example: ``engine_module_file("coding_agent_playbook.config.files")`` is ``"config/files.py"``.
    """
    return f"{engine_module(dotted).removeprefix(f'{ENGINE}.').replace('.', '/')}.py"
