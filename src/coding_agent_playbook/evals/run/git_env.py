"""Environment for a ``git`` child that must act on its own repository, not the caller's.

Git exports absolute ``GIT_DIR``/``GIT_INDEX_FILE`` to hooks run in a linked
worktree, and pre-commit passes them on to ``language: system`` hooks. A child
``git`` that inherits them ignores its ``cwd`` and acts on the caller's gitdir and
index, so ``git init``/``add``/``commit`` in an eval scratch repo would commit onto
the developer's branch and overwrite their index.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

#: The variables that pin a repository location: git's own list
#: (``git rev-parse --local-env-vars``, git 2.39) plus ``GIT_NAMESPACE``. Git
#: clears the same list itself before running a command in another repository
#: (a submodule).
REPO_LOCATION_GIT_VARS: frozenset[str] = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_CONFIG",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_PARAMETERS",
        "GIT_DIR",
        "GIT_GRAFT_FILE",
        "GIT_IMPLICIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_INTERNAL_SUPER_PREFIX",
        "GIT_NAMESPACE",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_REPLACE_REF_BASE",
        "GIT_SHALLOW_FILE",
        "GIT_WORK_TREE",
    }
)


def without_repo_location(environ: Mapping[str, str]) -> dict[str, str]:
    """Return a copy of ``environ`` without :data:`REPO_LOCATION_GIT_VARS`.

    Every other variable (``PATH``, ``HOME``, ``GIT_CONFIG_GLOBAL``, identity)
    passes through unchanged.

    Example::

        >>> without_repo_location({"GIT_DIR": "/repo/.git", "PATH": "/bin"})
        {'PATH': '/bin'}
    """
    return {name: value for name, value in environ.items() if name not in REPO_LOCATION_GIT_VARS}
