"""The repo-marker facts ``domino_project`` (prU D63) and ``playbook_layer`` (D70).

Neither can be written as an ``applies_if`` predicate: predicate keys are
AND-ed, and each fact is true when *any* of several markers (a file, a
dependency, a committed config key) is present.

- ``domino_project``: a reliable Domino marker — ``.dominoignore`` or
  ``.dominoresults`` at the repo root, a committed root ``dominostats.json``,
  or a ``dominodatalab`` / ``dominodatalab-data`` dependency — or the committed
  config key ``platforms = ["domino"]`` (a repo with no marker yet). A Domino
  run writes ``dominostats.json`` as an output, so in a git work tree it counts
  only when git tracks it (an untracked run leftover does not); in a repo
  without ``.git`` (a Domino File System project) every file is committed.
  Weak markers (``app.sh``, ``/mnt/...`` paths) are never read, so they cannot
  count alone.
- ``playbook_layer``: the repo has a ``catalog/`` layer (the engine's own
  repo), a ``playbook/`` directory (a consumer's own layer, even empty), or is
  an overlay: it depends on ``coding-agent-playbook`` and a package of it ships
  catalog content under ``resources/``.

Stdlib plus the config file names and the bounded reader only, so
``config.schema`` can import :data:`KNOWN_PLATFORMS` to validate the
``platforms`` key.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.detector.bounded_read import read_bounded_utf8
from coding_agent_playbook.detector.config_filenames import CONFIG_FILENAME

if TYPE_CHECKING:
    from collections.abc import Iterator, Set
    from pathlib import Path

__all__ = [
    "DOMINO_DEPENDENCIES",
    "DOMINO_MARKER_FILES",
    "DOMINO_PLATFORM",
    "DOMINO_STATS_FILE",
    "KNOWN_PLATFORMS",
    "PLATFORMS_KEY",
    "committed_platforms",
    "has_playbook_layer",
    "is_domino_project",
]

#: The ``platforms`` name that turns ``domino_project`` on (D63).
DOMINO_PLATFORM: Final = "domino"
#: The values the committed ``platforms`` key accepts (D63).
KNOWN_PLATFORMS: Final = frozenset({DOMINO_PLATFORM})
#: The committed config's top-level key that turns a platform's skills on without markers.
PLATFORMS_KEY: Final = "platforms"
#: Reliable Domino markers at the repo root: present is enough (D63).
DOMINO_MARKER_FILES: Final = (".dominoignore", ".dominoresults")
#: A Domino run's output: a reliable marker only when committed (D63).
DOMINO_STATS_FILE: Final = "dominostats.json"
#: Domino's client libraries, PEP 503 names (D63).
DOMINO_DEPENDENCIES: Final = frozenset({"dominodatalab", "dominodatalab-data"})

_GIT_TIMEOUT_SECONDS: Final = 5.0
_ENGINE_DISTRIBUTION: Final = "coding-agent-playbook"
_LAYER_DIRS: Final = ("catalog", "playbook")
#: The artifact kinds a layer's ``resources/`` tree holds (SPEC §5.1, §11).
_CATALOG_KIND_DIRS: Final = ("rules", "skills", "prompts", "hooks", "eval_samples")
_SRC_DIR: Final = "src"


def is_domino_project(repo_root: Path, dependencies: Set[str], platforms: Set[str]) -> bool:
    """Whether ``repo_root`` is a Domino project (D63).

    ``dependencies`` are every PEP 503 dependency name the repo declares, in
    any group; ``platforms`` is :func:`committed_platforms`.

    Example::

        >>> is_domino_project(repo, frozenset({"dominodatalab"}), frozenset())  # doctest: +SKIP
        True
    """
    if DOMINO_PLATFORM in platforms or not DOMINO_DEPENDENCIES.isdisjoint(dependencies):
        return True
    if any((repo_root / name).exists() for name in DOMINO_MARKER_FILES):
        return True
    return _is_committed(repo_root, DOMINO_STATS_FILE)


def has_playbook_layer(repo_root: Path, dependencies: Set[str]) -> bool:
    """Whether ``repo_root`` holds a playbook layer (D70).

    ``dependencies`` are every direct dependency name the repo declares, in any
    group (an overlay usually lists the engine as a runtime dependency).

    Example::

        >>> has_playbook_layer(repo_with_empty_playbook_dir, frozenset())  # doctest: +SKIP
        True
    """
    if any((repo_root / name).is_dir() for name in _LAYER_DIRS):
        return True
    return _ENGINE_DISTRIBUTION in dependencies and _ships_catalog_content(repo_root)


def committed_platforms(repo_root: Path) -> frozenset[str]:
    """The known names the committed config's top-level ``platforms`` list holds.

    An absent, unreadable, oversized or malformed config, or a ``platforms``
    value that is not a list, yields nothing (``config.schema`` reports those
    shapes; the detector never raises). Unknown names are dropped.

    Example::

        >>> committed_platforms(repo_with_platforms_domino)  # doctest: +SKIP
        frozenset({'domino'})
    """
    text = read_bounded_utf8(repo_root / CONFIG_FILENAME)
    if text is None:
        return frozenset()
    try:
        value = tomllib.loads(text).get(PLATFORMS_KEY)
    except tomllib.TOMLDecodeError:
        return frozenset()
    if not isinstance(value, list):
        return frozenset()
    return frozenset(item for item in value if item in KNOWN_PLATFORMS)


def _is_committed(repo_root: Path, name: str) -> bool:
    """Whether the root file ``name`` is committed: git-tracked, or present outside a git work tree."""
    if not (repo_root / name).is_file():
        return False
    if not (repo_root / ".git").exists():
        return True  # no git: a Domino File System project, where every file is committed
    return _git_tracks(repo_root, name)


def _git_tracks(repo_root: Path, name: str) -> bool:
    """Whether git's index holds ``name``; ``False`` when git is missing, fails or times out."""
    import subprocess  # branch-local: only a root dominostats.json with no other marker needs it

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "--error-unmatch", "--", name],
            capture_output=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _ships_catalog_content(repo_root: Path) -> bool:
    """Whether a package of ``repo_root`` (``src/<pkg>/`` or ``<pkg>/``) has a catalog kind under ``resources/``."""
    return any(
        (package / "resources" / kind).is_dir()
        for package in _package_dirs(repo_root)
        for kind in _CATALOG_KIND_DIRS
    )


def _package_dirs(repo_root: Path) -> Iterator[Path]:
    """The candidate package directories: every non-hidden child of the root and of ``src/``."""
    for parent in (repo_root, repo_root / _SRC_DIR):
        try:
            children = sorted(parent.iterdir())
        except OSError:
            continue
        yield from (
            child for child in children if child.is_dir() and not child.name.startswith(".")
        )
