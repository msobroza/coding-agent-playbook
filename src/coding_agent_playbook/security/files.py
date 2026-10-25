"""Filesystem-aware secret checks for engine code that walks or copies trees (SPEC §17.3).

:mod:`security.paths` classifies a path *string* and never touches the disk.
Code that walks a real tree needs two more facts: whose home anchors the ``~/``
globs, and where a path really leads, because a symlink can give a credential
file an innocent name (``scripts/notes.txt -> ~/.aws/credentials``). Resolving
a path follows links without opening the file. Stdlib-only.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from coding_agent_playbook.security.paths import is_secret_path

if TYPE_CHECKING:
    from pathlib import Path


def user_home() -> str:
    """The current user's home directory (``"~"`` when it cannot be determined).

    ``os.path.expanduser`` never raises, unlike ``Path.home()``, so an odd
    environment (no ``HOME``, no passwd entry) cannot crash a scan.

    Example::

        >>> user_home()  # doctest: +SKIP
        '/home/dev'
    """
    return os.path.expanduser("~")


def is_secret_file(
    path: Path, *, relative_to: Path, home: str, resolved: Path | None = None
) -> bool:
    """Whether ``path`` is a secret by its spelling below ``relative_to`` or by its target.

    The spelling (``path`` relative to ``relative_to``, or ``path`` itself when
    it lies elsewhere) is the name a reader sees; the resolved target is what a
    read would open. Either one matching the catalog makes the file secret. The
    file is never opened. ``resolved`` is the target when the caller already
    resolved ``path`` (a walk resolving its files in one batch); ``None``
    resolves it here.

    Example::

        >>> is_secret_file(Path("/r/.continue/rules/.env"), relative_to=Path("/r"),
        ...                home="/home/dev")
        True
    """
    try:
        spelled: Path = path.relative_to(relative_to)
    except ValueError:
        spelled = path
    if is_secret_path(spelled, home=home):
        return True
    return is_secret_path(path.resolve() if resolved is None else resolved, home=home)
