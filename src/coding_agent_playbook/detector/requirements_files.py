"""The project names a repo's root ``requirements*.txt`` files install (prU D78(2)), stdlib-only.

``detector.detect()`` adds them to its ``dependencies`` fact, so the
dependency and framework gates (and ``domino_project``) fire in a repo that
declares its packages only there. resync-on-detector-input-change compares
the same names on its cheap path, so it reads them through this module too
and the two can never disagree. Each file is parsed by the one requirement
parser, ``detector.pep503.requirement_names``.

Only the repo root is read (``requirements.txt``, ``requirements-dev.txt``…);
nested files and ``requirements*.in`` are not. Every root file feeds the
runtime ``dependencies`` fact, ``requirements-dev.txt`` included: D78(2) names
no group, and a file name is no reliable group marker (``-r requirements.txt``
chains mix them). A file that cannot be read, is not UTF-8 or is larger than
:data:`REQUIREMENTS_MAX_BYTES` contributes nothing: the detector never raises.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.detector.bounded_read import DETECTOR_INPUT_MAX_BYTES, read_bounded_utf8
from coding_agent_playbook.detector.pep503 import requirement_names

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["REQUIREMENTS_MAX_BYTES", "root_requirement_names"]

#: A requirements file larger than this is skipped.
REQUIREMENTS_MAX_BYTES: Final = DETECTOR_INPUT_MAX_BYTES
_REQUIREMENTS_GLOB: Final = "requirements*.txt"


def root_requirement_names(repo_root: Path) -> frozenset[str]:
    """The PEP 503 names every root ``requirements*.txt`` of ``repo_root`` installs.

    Example::

        >>> root_requirement_names(repo)  # doctest: +SKIP
        frozenset({'dominodatalab', 'flask'})
    """
    names: set[str] = set()
    for path in sorted(repo_root.glob(_REQUIREMENTS_GLOB)):
        text = read_bounded_utf8(path, REQUIREMENTS_MAX_BYTES)
        if text is not None:
            names |= requirement_names(text)
    return frozenset(names)
