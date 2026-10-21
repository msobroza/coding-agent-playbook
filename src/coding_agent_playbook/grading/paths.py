"""Path classes the metrics tools share: test code and frozen eval fixtures (prK §F.0.3, §F.1.1).

:data:`TEST_PATH_GLOBS` says what counts as test code (``diff_coverage`` and the
docstring stage leave it out) and :data:`EVAL_FIXTURE_GLOBS` names the frozen
eval ``setup/`` trees, the default of ``[metrics] exclude``: intentionally bad
needle code there must never gate a commit or a Stop.

Both constants are *re-exported*, not redefined. The stdlib leaf
``artifacts.path_classes`` owns the definitions (gate-weakening-guard's test
classes, the ``eval_fixture`` path class) because the dispatcher hot path must
not import this module: the hook-runtime-stack import contract keeps
``grading`` off the dispatch path. Hooks receive the globs through
``guard_config.json``; only sync-time and CLI code imports them from here.

:func:`matches_any_glob` reuses the hook glob grammar
(:mod:`coding_agent_playbook.artifacts.path_globs`), so a glob means the same thing
to a hook and to its CLI twin. Python 3.12 has no ``PurePath.full_match``, and
``fnmatch`` lets ``*`` cross ``/``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.artifacts.path_classes import FIXTURE_GLOBS, TEST_PATH_GLOBS
from coding_agent_playbook.artifacts.path_globs import compile_globs

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.artifacts.path_globs import GlobSet

__all__ = ["EVAL_FIXTURE_GLOBS", "TEST_PATH_GLOBS", "is_test_path", "matches_any_glob"]

#: The frozen eval-sample fixtures (``**/eval_samples/*/setup/**``): ``[metrics] exclude``'s default.
EVAL_FIXTURE_GLOBS: Final = FIXTURE_GLOBS

#: Repo-relative paths are exact (git and the gate report them as written), so
#: match without the darwin/win32 case folding the hook paths get.
_GLOB_PLATFORM: Final = "linux"


def matches_any_glob(rel_posix: str, globs: Iterable[str]) -> bool:
    """Whether the repo-relative POSIX path ``rel_posix`` matches one of ``globs``.

    ``**`` crosses ``/`` and a leading ``**/`` also matches zero directories;
    ``*`` and ``?`` stay inside one segment; a glob without ``/`` matches the
    basename at any depth.

    Example::

        >>> matches_any_glob("eval_samples/t1/setup/app.py", EVAL_FIXTURE_GLOBS)
        True
    """
    return _compiled(tuple(globs)).matches(rel_posix)


def is_test_path(rel_posix: str) -> bool:
    """Whether ``rel_posix`` is test code under :data:`TEST_PATH_GLOBS`.

    Example::

        >>> is_test_path("pkg/tests/test_api.py"), is_test_path("src/pkg/api.py")
        (True, False)
    """
    return matches_any_glob(rel_posix, TEST_PATH_GLOBS)


@lru_cache(maxsize=32)
def _compiled(globs: tuple[str, ...]) -> GlobSet:
    """Compile each distinct glob tuple once per process (the gate matches every target)."""
    return compile_globs(globs, platform=_GLOB_PLATFORM)
