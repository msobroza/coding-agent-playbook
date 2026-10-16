"""The files a shell segment reads as data, for sensitive-data-read-guard (prK-hook-pack.md §E.5).

Path-only, like the guard: a word is a candidate, never opened here.

- readers (``cat``, ``head``, ``tail``, ``less``, ``more``, ``sed``, ``awk``,
  ``cut``, ``sqlite3``, ``duckdb``): every non-option operand and every input
  redirect target. The caller keeps a word only when it names an existing
  file, so an ``awk`` program or a ``sed`` script passes;
- ``sqlite3`` / ``duckdb`` SQL and ``python -c`` code (and a ``python``
  heredoc): every quoted data-file literal (``pd.read_csv("data/raw/x.csv")``,
  ``from 'exports/x.parquet'``).

A word holding shell glob characters (``cat data/raw/*.csv``) is a pattern the
shell expands: :func:`is_pattern` tells the caller to match it as a glob.

A private module: it registers no handler.
"""

from __future__ import annotations

import posixpath
import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterator

    from coding_agent_playbook.hook_runtime.shell import Segment

__all__ = ["READER_ARGV0S", "is_pattern", "read_candidates"]

READER_ARGV0S: Final = frozenset(
    {"cat", "head", "tail", "less", "more", "sed", "awk", "gawk", "cut", "sqlite3", "duckdb"}
)
_SQL_READERS: Final = frozenset({"sqlite3", "duckdb"})
_PYTHON: Final = re.compile(r"^python(?:\d+(?:\.\d+)?)?$")
#: A quoted data-file literal inside code or SQL.
_QUOTED_FILE: Final = re.compile(
    r"""['"]([^'"\s]{1,4096}\.(?:csv|tsv|parquet|xlsx|xls|feather|jsonl?|db|sqlite3?|ipynb))['"]""",
    re.IGNORECASE,
)
_INPUT_REDIRECTS: Final = frozenset({"<", "<>"})
_GLOB_CHARS: Final = re.compile(r"[*?\[]")


def read_candidates(segment: Segment) -> Iterator[str]:
    """Every word of ``segment`` that may name a file it reads as data, in order.

    Example::

        >>> list(read_candidates(parse("head -n 5 data/raw/x.csv")[0]))  # doctest: +SKIP
        ['5', 'data/raw/x.csv']
    """
    program = posixpath.basename(segment.argv[0]) if segment.argv else ""
    if program in READER_ARGV0S:
        yield from (word for word in segment.argv[1:] if word and not word.startswith("-"))
        yield from _input_redirects(segment)
        if program in _SQL_READERS:
            yield from _quoted(segment.argv[1:])
    elif _PYTHON.match(program):
        yield from _quoted(_python_code(segment))


def is_pattern(word: str) -> bool:
    """Whether ``word`` is a shell glob the shell expands (``data/raw/*.csv``).

    Example::

        >>> is_pattern("data/raw/*.csv"), is_pattern("data/raw/x.csv")
        (True, False)
    """
    return _GLOB_CHARS.search(word) is not None


def _input_redirects(segment: Segment) -> Iterator[str]:
    for redirect in segment.redirects:
        if redirect.op in _INPUT_REDIRECTS and redirect.target and not redirect.target.isdigit():
            yield redirect.target


def _python_code(segment: Segment) -> list[str]:
    """``python -c`` code and the body of a ``python - <<EOF`` heredoc."""
    argv = list(segment.argv)
    code = [argv[i + 1] for i, word in enumerate(argv[:-1]) if word == "-c"]
    return [*code, *segment.heredoc_bodies]


def _quoted(texts: list[str] | tuple[str, ...]) -> Iterator[str]:
    for text in texts:
        yield from (match.group(1) for match in _QUOTED_FILE.finditer(text))
