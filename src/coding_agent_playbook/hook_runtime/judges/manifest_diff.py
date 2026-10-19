"""The dependency names a manifest edit adds, read from the simulated file (specs/prK-hook-pack.md §E.4).

dependency-allowlist-guard compares a manifest before and after an Edit or
Write (``edit_preview``); only NEWLY declared names count, so reformatting or
re-pinning an existing dependency is silent (the metrics non-regression
stance). One reader per manifest kind:

- ``pyproject.toml``: ``tomllib`` (imported here only, the §D.1 branch-local
  row) over ``[project].dependencies``, every optional-dependency and
  ``[dependency-groups]`` group and Poetry's tables (``detector.pyproject_deps``);
- ``requirements*.txt`` / ``requirements*.in``: pip's line grammar (``detector.pep503``);
- ``setup.cfg``: the ``install_requires`` / ``setup_requires`` /
  ``tests_require`` values and ``[options.extras_require]``;
- ``environment.yml``: the list items (conda specs and the nested ``pip:`` list).

:func:`added_indexes` reads the package indexes a manifest names (pip's
``--index-url`` / ``--extra-index-url`` lines, ``[tool.uv]`` indexes, Poetry
sources), so index mixing written into a file is caught like a command flag.
``uv.lock`` and ``poetry.lock`` are :data:`LOCKFILES`: generated, never
hand-edited. Stdlib only.
"""

from __future__ import annotations

import fnmatch
import re
from typing import TYPE_CHECKING, Any, Final, Literal

from coding_agent_playbook.detector.pep503 import (
    canonical_name,
    requirement_name,
    requirement_names,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from coding_agent_playbook.hook_runtime.judges.install_commands import Index

__all__ = ["LOCKFILES", "ManifestKind", "added_indexes", "added_names", "manifest_kind"]

type ManifestKind = Literal["pyproject", "requirements", "setup_cfg", "conda_env"]

#: Lockfile -> the command that regenerates it.
LOCKFILES: Final = {"uv.lock": "uv lock", "poetry.lock": "poetry lock"}
_KINDS: Final[tuple[tuple[str, ManifestKind], ...]] = (
    ("pyproject.toml", "pyproject"),
    ("requirements*.txt", "requirements"),
    ("requirements*.in", "requirements"),
    ("setup.cfg", "setup_cfg"),
    ("environment.yml", "conda_env"),
    ("environment.yaml", "conda_env"),
)
_SETUP_KEYS: Final = frozenset({"install_requires", "setup_requires", "tests_require"})
_SECTION: Final = re.compile(r"^\[([^\]]+)\]\s*$")
_KEY: Final = re.compile(r"^([A-Za-z0-9_.-]+)\s*[=:](.*)$")
_LIST_ITEM: Final = re.compile(r"^\s*-\s+(['\"]?)([^'\"#\s][^'\"#]*)\1\s*(?:#.*)?$")
_CONDA_NAME_END: Final = re.compile(r"[=<>!~\s\[]")
_NOT_PACKAGES: Final = frozenset({"pip", "python"})
_REQ_INDEX: Final = re.compile(r"^\s*(-i|--index-url|--extra-index-url)(?:\s*=\s*|\s+)(\S+)")


def manifest_kind(basename: str) -> ManifestKind | None:
    """Which manifest a file named ``basename`` is, else ``None``.

    Example::

        >>> manifest_kind("requirements-dev.in"), manifest_kind("README.md")
        ('requirements', None)
    """
    name = basename.lower()
    return next((kind for glob, kind in _KINDS if fnmatch.fnmatchcase(name, glob)), None)


def added_names(kind: ManifestKind, before: str | None, after: str) -> frozenset[str] | None:
    """The names ``after`` declares that ``before`` (``None``: a new file) did not.

    ``None`` when ``after`` cannot be read (a ``pyproject.toml`` that no longer
    parses): the caller cannot tell what it adds.

    Example::

        >>> sorted(added_names("requirements", "flask==3\\n", "Flask==3.1\\nrich\\n"))
        ['rich']
    """
    new = _names(kind, after)
    if new is None:
        return None
    old = _names(kind, before) if before is not None else frozenset()
    return new - (old or frozenset())


def added_indexes(kind: ManifestKind, before: str | None, after: str) -> list[Index]:
    """The package indexes ``after`` names that ``before`` did not, in file order.

    Example::

        >>> added_indexes("requirements", "torch\n", "--extra-index-url https://x/s\ntorch\n")
        [('extra', 'https://x/s')]
    """
    old = _indexes(kind, before)
    return [index for index in _indexes(kind, after) if index not in old]


def _names(kind: ManifestKind, text: str) -> frozenset[str] | None:
    if kind == "pyproject":
        return _pyproject_names(text)
    if kind == "requirements":
        return requirement_names(text)
    if kind == "setup_cfg":
        return frozenset(filter(None, map(requirement_name, _setup_cfg_specs(text))))
    return frozenset(_conda_env_names(text))


def _pyproject_names(text: str) -> frozenset[str] | None:
    import tomllib  # branch-local (§D.1): only a pyproject.toml edit pays ~19 ms

    from coding_agent_playbook.detector.pyproject_deps import manifest_dependency_names

    try:
        return manifest_dependency_names(tomllib.loads(text))
    except tomllib.TOMLDecodeError:
        return None


def _setup_cfg_specs(text: str) -> Iterator[str]:
    """The requirement specs of a ``setup.cfg``: its dependency keys' values, one per line."""
    section, key = "", ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped[0] in "#;":
            continue
        header = _SECTION.match(stripped)
        if header is not None:
            section, key = header.group(1).strip().lower(), ""
            continue
        value = stripped
        if not raw[0].isspace():  # a key line; an indented one continues the last key
            found = _KEY.match(stripped)
            key, value = (found.group(1).lower(), found.group(2)) if found else ("", "")
        if key in _SETUP_KEYS or (section == "options.extras_require" and key):
            yield value.strip()


def _conda_env_names(text: str) -> Iterator[str]:
    """The packages of an ``environment.yml``: the ``dependencies:`` items, ``pip:`` ones too."""
    top = ""
    for line in text.splitlines():
        if line[:1].isalpha():  # a top-level key: channels, dependencies, name, ...
            top = line.split(":", 1)[0].strip()
            continue
        item = _LIST_ITEM.match(line)
        if item is None or top != "dependencies":
            continue
        spec = item.group(2).strip().rpartition("::")[2]
        name = canonical_name(_CONDA_NAME_END.split(spec, maxsplit=1)[0])
        if name and not name.endswith(":") and name not in _NOT_PACKAGES:
            yield name


def _indexes(kind: ManifestKind, text: str | None) -> list[Index]:
    """The package indexes a manifest names: pip options, ``[tool.uv]``, Poetry sources."""
    if not text:
        return []
    if kind == "requirements":
        found = (_REQ_INDEX.match(line) for line in text.splitlines())
        return [("extra" if m[1] == "--extra-index-url" else "primary", m[2]) for m in found if m]
    if kind != "pyproject":
        return []
    import tomllib  # branch-local (§D.1), as for the names

    try:
        tool = _table(tomllib.loads(text).get("tool"))
    except tomllib.TOMLDecodeError:
        return []
    return [*_uv_indexes(_table(tool.get("uv"))), *_poetry_sources(_table(tool.get("poetry")))]


def _uv_indexes(uv: dict[str, Any]) -> list[Index]:
    found: list[Index] = [("primary", u) for u in [uv.get("index-url")] if isinstance(u, str)]
    found.extend(("extra", u) for u in _list(uv.get("extra-index-url")) if isinstance(u, str))
    for row in _list(uv.get("index")):
        url = row.get("url") if isinstance(row, dict) else None
        if isinstance(url, str):
            found.append(("primary" if row.get("default") is True else "extra", url))
    return found


def _poetry_sources(poetry: dict[str, Any]) -> list[Index]:
    rows = (row for row in _list(poetry.get("source")) if isinstance(row, dict))
    return [("extra", row["url"]) for row in rows if isinstance(row.get("url"), str)]


def _table(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []
