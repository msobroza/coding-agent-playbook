"""Did a tool call change a detector input? Decided from ``guard_config.facts`` alone (specs/prK-hook-pack.md §E.1).

The cheap half of resync-on-detector-input-change, about 5 ms:

- which inputs the call touched: ``pyproject.toml`` and ``requirements*``
  (dependencies), ``Dockerfile`` / ``docker/`` (``has_dockerfile``), CI files
  (``has_ci``), a notebook (``has_notebooks``), or a successful ``uv
  add|remove``, ``poetry add|remove`` or ``pip install`` segment;
- whether they changed: one ``tomllib`` read of ``pyproject.toml`` whose
  dependency names (``detector.pyproject_deps``, the detector's own parser) are
  compared with the names sync baked, and the presence of a file whose flag
  was false at sync. An ordinary ``[tool.*]`` edit stays silent.

``requirements*`` files trigger the comparison but never change it: the
detector reads only ``pyproject.toml``. A private module: it registers no
handler, and ``tomllib`` loads only once a dependency input was touched.
"""

from __future__ import annotations

import os
import posixpath
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from coding_agent_playbook.hook_runtime.dispatch.event import ToolCall
    from coding_agent_playbook.hook_runtime.dispatch.paths import NormalizedPath

__all__ = ["DEPENDENCIES", "FLAGS", "INSTALL_PROGRAMS", "detector_triggers", "inputs_changed"]

DEPENDENCIES: Final = "dependencies"
FLAGS: Final = ("has_dockerfile", "has_ci", "has_notebooks")
#: Dependency-changing commands, by ``(program, subcommand)`` (``uv pip install`` too).
_INSTALLS: Final = frozenset(
    {
        ("uv", "add"),
        ("uv", "remove"),
        ("uv", "pip"),
        ("poetry", "add"),
        ("poetry", "remove"),
        ("pip", "install"),
        ("pip3", "install"),
    }
)
#: The argv0s of :data:`_INSTALLS`: the dispatcher's prefilter skips any other shell call.
INSTALL_PROGRAMS: Final = frozenset(program for program, _ in _INSTALLS)
#: The detector's ignored dirs: a notebook there never sets ``has_notebooks``.
_IGNORED: Final = frozenset({".venv", "venv", "node_modules", ".git", "__pycache__", ".tox"})
_PYPROJECT_MAX_BYTES: Final = 1024 * 1024


def _is_requirements(rel: str) -> bool:
    name = posixpath.basename(rel)
    return "/" not in rel and name.startswith("requirements") and name.endswith((".txt", ".in"))


def _is_notebook(rel: str) -> bool:
    return rel.endswith(".ipynb") and not _IGNORED.intersection(rel.split("/")[:-1])


#: Which input a repo-relative (folded) path is, in the detector's own terms.
_PATH_INPUTS: Final[Mapping[str, Callable[[str], bool]]] = {
    DEPENDENCIES: lambda rel: rel == "pyproject.toml" or _is_requirements(rel),
    "has_dockerfile": lambda rel: rel == "dockerfile" or rel.startswith("docker/"),
    "has_ci": lambda rel: (
        rel.startswith((".github/workflows/", ".circleci/"))
        or rel in (".gitlab-ci.yml", "jenkinsfile")
    ),
    "has_notebooks": _is_notebook,
}


def detector_triggers(tool: ToolCall) -> frozenset[str]:
    """The detector inputs ``tool`` wrote (``DEPENDENCIES`` or a flag name).

    Names compare lower-cased on every platform: an over-match only costs the
    comparison (or one ``detect()``), never a wrong report.

    Example::

        >>> detector_triggers(edit_of_pyproject)  # doctest: +SKIP
        frozenset({'dependencies'})
    """
    found = {
        name
        for path in tool.write_paths
        if path.repo_rel is not None
        for name, matches in _PATH_INPUTS.items()
        if matches(path.repo_rel.lower())
    }
    command = tool.command
    if command is not None and any(_is_install(s.argv) for s in command.segments):
        found.add(DEPENDENCIES)
    return frozenset(found)


def inputs_changed(
    triggers: Iterable[str],
    facts: Mapping[str, Any],
    repo_root: str,
    written: Sequence[NormalizedPath],
) -> bool:
    """Whether a triggered input differs from what sync baked into ``facts``.

    Example::

        >>> inputs_changed({"dependencies"}, {"dependencies": []}, "/r", [])  # doctest: +SKIP
        True
    """
    wanted = set(triggers)
    if DEPENDENCIES in wanted and _dependencies_changed(facts, repo_root):
        return True
    return any(
        flag in wanted and facts.get(flag) is False and _written_now(flag, written)
        for flag in FLAGS
    )


def _is_install(argv: Sequence[str]) -> bool:
    return len(argv) >= 2 and (posixpath.basename(argv[0]), argv[1]) in _INSTALLS


def _written_now(flag: str, written: Sequence[NormalizedPath]) -> bool:
    """Whether a path of ``flag``'s kind was written and exists: the flag is true now."""
    matches = _PATH_INPUTS[flag]
    return any(
        p.repo_rel is not None and matches(p.repo_rel.lower()) and os.path.exists(p.path)
        for p in written
    )


def _dependencies_changed(facts: Mapping[str, Any], repo_root: str) -> bool:
    """Whether ``pyproject.toml``'s dependency names differ from the baked ones.

    A pyproject that does not parse (an edit in progress) counts as unchanged.
    """
    names = _current_names(repo_root)
    if names is None:
        return False
    runtime, dev = names
    return runtime != _baked(facts, "dependencies") or dev != _baked(facts, "dev_dependencies")


def _current_names(repo_root: str) -> tuple[frozenset[str], frozenset[str]] | None:
    import tomllib  # branch-local (§D.1): only after a dependency input was touched

    from coding_agent_playbook.detector.pyproject_deps import dependency_names

    try:
        with open(os.path.join(repo_root, "pyproject.toml"), "rb") as handle:
            data = handle.read(_PYPROJECT_MAX_BYTES + 1)
    except FileNotFoundError:
        return frozenset(), frozenset()
    except OSError:
        return None
    if len(data) > _PYPROJECT_MAX_BYTES:
        return None
    try:
        return dependency_names(tomllib.loads(data.decode("utf-8")))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return None


def _baked(facts: Mapping[str, Any], key: str) -> frozenset[str]:
    value = facts.get(key, [])
    return (
        frozenset(v for v in value if isinstance(v, str))
        if isinstance(value, list)
        else frozenset()
    )
