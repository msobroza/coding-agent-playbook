"""The detector's one bounded UTF-8 file read, stdlib-only (a stdlib leaf).

``detector.requirements_files``, ``detector.platform_facts`` and the resync
hook's cheap comparison (``hook_runtime.handlers.protect._detector_inputs``)
all read small repo files the same way: a regular file only (a FIFO named
``pyproject.toml`` would block), at most :data:`DETECTOR_INPUT_MAX_BYTES`, as
UTF-8. Any other outcome is ``None``, because the detector never raises.
"""

from __future__ import annotations

import os
from typing import Final

__all__ = ["DETECTOR_INPUT_MAX_BYTES", "read_bounded_utf8"]

#: A detector input larger than this is skipped (a generated lock with hashes stays well under).
DETECTOR_INPUT_MAX_BYTES: Final = 1024 * 1024


def read_bounded_utf8(
    path: str | os.PathLike[str], max_bytes: int = DETECTOR_INPUT_MAX_BYTES
) -> str | None:
    """``path``'s UTF-8 text, or ``None`` when it is no regular file, too large, unreadable or not UTF-8.

    Example::

        >>> read_bounded_utf8("requirements.txt")  # doctest: +SKIP
        'flask\\n'
    """
    try:
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as handle:
            data = handle.read(max_bytes + 1)
    except OSError:
        return None
    if len(data) > max_bytes:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None
