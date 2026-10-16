"""PEP 503 project names and the names in requirement specs (specs/prK-hook-pack.md §E.4).

Package indexes treat ``Foo_Bar``, ``foo.bar`` and ``FOO-bar`` as one project
(PEP 503: runs of ``-_.`` become ``-``, then lower case). The detector, the
dependency-allowlist-guard and ``playbook check-deps`` all compare names, so
they normalize through :func:`canonical_name` and never disagree. A spec's
name ends at the first character PEP 508 allows after one (``[`` ``(`` ``;``
``@``, a version operator, ``,`` or whitespace); anything else (``git+https``,
``./pkg``) has no name here. Stdlib ``re`` only, no ``packaging``: the hook
runtime imports this on its hot path.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = ["canonical_name", "requirement_name", "requirement_names", "split_requirement"]

_SEPARATOR_RUNS: Final = re.compile(r"[-_.]+")
_NAME: Final = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")
_NAME_ENDS: Final = frozenset(" \t[(;@<>=!~,")
#: pip strips a ``#`` comment at a line start or after whitespace (a URL's ``#egg=`` stays).
_COMMENT: Final = re.compile(r"(?:^|\s)#.*$")
_EGG: Final = re.compile(r"#egg=([A-Za-z0-9._-]+)")
_EDITABLE: Final = ("-e", "--editable")
_SDIST_SUFFIXES: Final = (".tar.gz", ".tar.bz2", ".tgz", ".zip")


def canonical_name(name: str) -> str:
    """``name`` normalized per PEP 503.

    Example::

        >>> canonical_name("Foo_Bar.baz")
        'foo-bar-baz'
    """
    return _SEPARATOR_RUNS.sub("-", name).lower()


def split_requirement(spec: str) -> tuple[str, str]:
    """``(canonical name, the text after the raw name)`` of a PEP 508 spec; ``("", "")`` without one.

    Splitting on the raw name's span keeps the constraint of a name that
    normalization changes (``Foo_Bar>=1.0`` keeps ``>=1.0``).

    Example::

        >>> split_requirement("Foo_Bar>=1.0")
        ('foo-bar', '>=1.0')
    """
    text = spec.lstrip()
    match = _NAME.match(text)
    if match is None:
        return "", ""
    rest = text[match.end() :]
    if rest and rest[0] not in _NAME_ENDS:
        return "", ""
    return canonical_name(match.group()), rest


def requirement_name(spec: str) -> str:
    """The canonical project name of a PEP 508 spec, ``""`` when it names none.

    Example::

        >>> requirement_name("Foo.Bar[extra]>=1; python_version<'3.13'")
        'foo-bar'
    """
    return split_requirement(spec)[0]


def requirement_names(text: str) -> frozenset[str]:
    """The project names a ``requirements*.txt`` file installs.

    Continuations and comments are handled as pip does; option lines
    (``-r``, ``-c``, ``--index-url``) name nothing; ``-e`` and URL or path
    lines yield the ``#egg=`` name or the wheel / sdist file's name.

    Example::

        >>> sorted(requirement_names("-r base.txt\\nFlask==3.0  # web\\n./Local_Pkg-1.0-py3-none-any.whl\\n"))
        ['flask', 'local-pkg']
    """
    names = {_line_name(line) for line in _logical_lines(text)}
    names.discard("")
    return frozenset(names)


def _logical_lines(text: str) -> Iterator[str]:
    """Lines joined at a trailing ``\\``, then stripped of comments and whitespace."""
    pending = ""
    for raw in text.splitlines():
        if raw.endswith("\\"):
            pending += raw[:-1] + " "
            continue
        yield _COMMENT.sub("", pending + raw).strip()
        pending = ""
    if pending:
        yield _COMMENT.sub("", pending).strip()


def _line_name(line: str) -> str:
    if not line:
        return ""
    first, _, rest = line.partition(" ")
    if first in _EDITABLE:
        return _target_name(rest.strip())
    if first.startswith("-"):
        return ""
    if "://" in first or first.startswith((".", "/")) or first.endswith(".whl"):
        return _target_name(first)
    return requirement_name(line)


def _target_name(target: str) -> str:
    """The project an ``-e`` / URL / path target installs: its ``#egg=`` or its file's name."""
    egg = _EGG.search(target)
    if egg is not None:
        return canonical_name(egg[1])
    filename = target.split("#", 1)[0].rstrip("/").rsplit("/", 1)[-1]
    if filename.endswith(".whl"):
        return canonical_name(filename.split("-", 1)[0])
    for suffix in _SDIST_SUFFIXES:
        stem = filename.removesuffix(suffix)
        if stem != filename and "-" in stem:
            return canonical_name(stem.rsplit("-", 1)[0])
    return ""
