#!/usr/bin/env python3
"""List design-smell candidates in Python source, using only the standard library.

Usage:
    python3 detect_smells.py [PATH ...]

Each PATH is a file or a directory; the default is the current directory.
Directories are searched recursively for ``*.py`` files, skipping dot
directories, ``__pycache__``, ``venv``/``.venv``, ``node_modules`` and
``site-packages``.

stdout is a JSON array of ``{"smell", "file", "line", "evidence"}`` objects,
sorted by (file, line, smell). Every entry is a candidate for a reviewer to
judge, never a verdict: a boolean parameter may be a deliberate public API and
a long parameter list may mirror an external schema.

Smell ids:
    mutable-default-argument   a list/dict/set literal, comprehension or factory
                               call used as a parameter default
    isinstance-ladder          3+ isinstance() tests in one if/elif chain
    long-parameter-list        more than 5 parameters, not counting self/cls
    boolean-flag-parameter     a bool-annotated or True/False-defaulted
                               parameter that an ``if`` branches on
    bare-except                ``except:`` with no exception type
    swallowed-exception        ``except Exception``/``BaseException`` whose
                               body is only pass, ``...`` or continue
    deep-nesting               a block nested more than 3 levels in a function
                               (an elif sits beside its if, not inside it)
    long-function              more than 50 lines that start a statement
    method-could-be-function   an instance method that never uses self; skips
                               methods that override a scanned base class or
                               are overridden by a scanned subclass, every
                               method of a class with an unscanned base (it
                               might be an override), Protocols, ``Test*``
                               classes, dunders, stub bodies, and methods
                               decorated with staticmethod, classmethod,
                               property, a setter/getter/deleter,
                               abstractmethod, override or overload
    namespace-class            a class whose methods are all staticmethods and
                               that has no base, metaclass, class decorator or
                               annotated field
    type-in-name               a parameter or assigned name ending in _str,
                               _int, _list, _dict, _set, _tuple or _bool, or
                               starting with str_, list_ or dict_ (first
                               binding per scope only)
    module-level-mutable-global-rebound
                               a ``global`` statement

Exit status: 0 after a scan, with or without candidates; 2 on a usage error or
a PATH that does not exist or cannot be read. A file that fails to parse, or
that nests too deeply to analyse, is named on stderr and skipped; the other
files are still reported.

Example:
    python3 detect_smells.py src/ tests/ > smell-candidates.json

The detectors live in ``_smell_detectors.py`` and their shared records in
``_smell_model.py``, beside this script; ``_pyscan_common.py`` holds the file
walk and AST helpers this script shares with ``lcom4_clusters.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

# The helper modules sit beside this script: find them even under ``python -I`` (no script dir),
# and write no __pycache__ into the synced skill directory.
sys.dont_write_bytecode = True
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _pyscan_common import load_modules, report_unreadable  # noqa: E402
from _smell_detectors import DETECTORS  # noqa: E402
from _smell_model import Candidate, ClassIndex, ModuleScan  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

PROG = "detect_smells.py"


def module_candidates(
    name: str,
    module: ModuleScan,
    detectors: Sequence[Callable[[ModuleScan], Iterator[Candidate]]],
) -> list[Candidate]:
    """Every detector's candidates for one module, or none when it nests too deeply.

    A module that exhausts the call stack is named on stderr and skipped, like an
    unparseable one, so it cannot abort the scan of every other file.
    """
    try:
        return [candidate for detector in detectors for candidate in detector(module)]
    except RecursionError as error:
        print(f"{PROG}: skipped {name}: {error}", file=sys.stderr)
        return []


def scan(
    paths: Sequence[Path],
    detectors: Sequence[Callable[[ModuleScan], Iterator[Candidate]]] = DETECTORS,
) -> list[dict[str, object]]:
    """Run ``detectors`` over ``paths`` and return the sorted JSON-ready candidates.

    >>> scan([Path("pkg")])  # doctest: +SKIP
    [{'smell': 'bare-except', 'file': 'pkg/io.py', 'line': 12, 'evidence': "bare 'except:' ..."}]
    """
    modules = load_modules(paths, PROG)
    index = ClassIndex.from_trees(tree for _, tree in modules)
    found = {
        (name, candidate.line, candidate.smell, candidate.evidence)
        for name, tree in modules
        for candidate in module_candidates(name, ModuleScan(tree, index), detectors)
    }
    return [
        {"smell": smell, "file": name, "line": line, "evidence": text}
        for name, line, smell, text in sorted(found)
    ]


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Command-line interface; argparse exits with status 2 on a usage error."""
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Print design-smell candidates in Python files as a JSON array.",
    )
    parser.add_argument(
        "paths", nargs="*", default=["."], metavar="PATH", help="file or directory (default: .)"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: scan the given paths and print JSON; returns the exit status."""
    paths = [Path(raw) for raw in parse_args(argv).paths]
    if report_unreadable(paths, PROG):
        return 2
    print(json.dumps(scan(paths), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
