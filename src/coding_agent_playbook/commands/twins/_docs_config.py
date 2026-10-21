"""Which docs tools a repository configures, read from its own files (D69, D78(10)).

Readers only, never a tool run: each answers from the committed config files,
and a file that does not parse counts as not configuring anything (the tool
that owns it reports it in its own run, never docs-check).
"""

from __future__ import annotations

import configparser
import shlex
import tomllib
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

__all__ = [
    "doc8_configured",
    "docs_group_hint",
    "doctest_globs",
    "first_existing",
    "markdownlint_configured",
]

#: The group or extra name that holds a repository's docs toolchain.
DOCS_GROUP: Final = "docs"
_MARKDOWNLINT_CONFIGS: Final = (
    ".markdownlint.json",
    ".markdownlint.jsonc",
    ".markdownlint.yaml",
    ".markdownlint.yml",
    ".markdownlintrc",
)
_DOC8_FILES: Final = (".doc8.ini", "doc8.ini")
#: pytest's own config-file precedence, with the section that holds ``addopts``.
_PYTEST_INI_FILES: Final = (
    ("pytest.ini", "pytest"),
    ("tox.ini", "pytest"),
    ("setup.cfg", "tool:pytest"),
)
_DOCTEST_GLOB: Final = "--doctest-glob"


def first_existing(root: Path, candidates: Iterable[str]) -> str | None:
    """The first of ``candidates`` (repo-relative) that is a file under ``root``.

    Example: ``first_existing(root, ("mkdocs.yml", "mkdocs.yaml")) == "mkdocs.yaml"``.
    """
    return next((rel for rel in candidates if (root / rel).is_file()), None)


def markdownlint_configured(root: Path) -> bool:
    """Whether a markdownlint config file sits at the repository root.

    Example: ``markdownlint_configured(root)`` after writing ``.markdownlint.yaml``.
    """
    return first_existing(root, _MARKDOWNLINT_CONFIGS) is not None


def doc8_configured(root: Path) -> bool:
    """Whether doc8 is configured: its own ini file, a ``[doc8]`` section or ``[tool.doc8]``.

    Example: ``doc8_configured(root)`` after writing ``.doc8.ini``.
    """
    if first_existing(root, _DOC8_FILES) is not None:
        return True
    if any("doc8" in _ini_sections(root / name) for name in ("setup.cfg", "tox.ini")):
        return True
    return bool(_table(_table(_pyproject(root), "tool"), "doc8"))


def doctest_globs(root: Path) -> tuple[str, ...]:
    """The ``--doctest-glob`` patterns of the pytest config pytest itself would read.

    Example: ``doctest_globs(root) == ("*.md",)`` for ``addopts = "--doctest-glob=*.md"``.
    """
    try:
        words = shlex.split(_addopts(root))
    except ValueError:  # unbalanced quotes: pytest reports its own config, not docs-check
        return ()
    globs: list[str] = []
    for index, word in enumerate(words):
        if word.startswith(f"{_DOCTEST_GLOB}="):
            globs.append(word.split("=", 1)[1])
        elif word == _DOCTEST_GLOB and index + 1 < len(words):
            globs.append(words[index + 1])
    return tuple(globs)


def docs_group_hint(root: Path) -> str:
    """How to install the ``docs`` dependency group or extra, or ``""`` without one.

    Example: ``docs_group_hint(root) == "uv sync --group docs"`` with a PEP 735 ``docs`` group.
    """
    pyproject = _pyproject(root)
    if DOCS_GROUP in _table(pyproject, "dependency-groups"):
        return f"uv sync --group {DOCS_GROUP}"
    if DOCS_GROUP in _table(_table(pyproject, "project"), "optional-dependencies"):
        return f'pip install -e ".[{DOCS_GROUP}]"'
    return ""


def _addopts(root: Path) -> str:
    """``addopts`` of the first pytest config file found, in pytest's order."""
    ini = root / "pytest.ini"
    if ini.is_file():
        return _ini_addopts(ini, "pytest")
    options = _table(_table(_pyproject(root), "tool"), "pytest")
    if "ini_options" in options:
        value = _table(options, "ini_options").get("addopts", "")
        return " ".join(value) if isinstance(value, list) else str(value)
    for name, section in _PYTEST_INI_FILES[1:]:
        path = root / name
        if section in _ini_sections(path):
            return _ini_addopts(path, section)
    return ""


def _ini_addopts(path: Path, section: str) -> str:
    parser = _ini(path)
    return parser.get(section, "addopts", fallback="") if parser.has_section(section) else ""


def _ini_sections(path: Path) -> list[str]:
    return _ini(path).sections() if path.is_file() else []


def _ini(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, UnicodeDecodeError):
        return configparser.ConfigParser(interpolation=None)
    return parser


def _pyproject(root: Path) -> dict[str, Any]:
    try:
        with (root / "pyproject.toml").open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return {}


def _table(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    return value if isinstance(value, dict) else {}
