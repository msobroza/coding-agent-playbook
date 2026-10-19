"""Every engine module's syntax tree, for the config package's source pins.

The SPEC §7.2 writer pin (``test_committed.py``), the one-spelling pin of the
two config filenames (``test_files_committed_table.py``) and the
``FileSystemStateSource`` importer pin (``test_files_state_source.py``) walk the
same trees.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

import coding_agent_playbook

if TYPE_CHECKING:
    from collections.abc import Iterator


def engine_module_trees() -> Iterator[tuple[str, ast.Module]]:
    """``(path, tree)`` of every engine module, the path relative to the package.

    ``resources/`` holds content, not code.

    Example: ``dict(engine_module_trees())["config/files.py"]`` is that module's tree.
    """
    package_root = Path(coding_agent_playbook.__file__).parent
    for path in sorted(package_root.rglob("*.py")):
        module = path.relative_to(package_root)
        if module.parts[0] != "resources":
            yield module.as_posix(), ast.parse(path.read_text(encoding="utf-8"))
