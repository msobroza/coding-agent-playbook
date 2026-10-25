#!/usr/bin/env python3
"""Build the documentation site the way CI does: strictly, any warning fails (ADR 0009).

Run it from the repository root, inside an environment with the ``docs`` extra::

    uv sync --extra dev --extra docs
    uv run scripts/build_docs.py            # writes docs/_build/html
    uv run scripts/build_docs.py --clean    # wipes docs/_build first
    uv run scripts/build_docs.py --serve    # then previews it on http://127.0.0.1:8000/

It installs nothing: without the ``docs`` extra it names the fix and exits 2. It
exits 1 when the build fails, else 0. ``.github/workflows/docs.yml`` runs it too,
so the build command lives here only.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import importlib.util
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

#: The strict, offline build: warnings are errors, and every page is checked.
SPHINX_OPTIONS: Final = ("-W", "--keep-going", "-b", "html")
DEFAULT_PORT: Final = 8000
USAGE_EXIT: Final = 2
INSTALL_HINT: Final = (
    "build_docs: Sphinx is not installed in this environment. "
    "Run `uv sync --extra dev --extra docs`, then `uv run scripts/build_docs.py`."
)


@dataclass(frozen=True)
class DocsLayout:
    """Where the site's sources are and where the build goes."""

    source_dir: Path
    build_dir: Path

    @property
    def html_dir(self) -> Path:
        """The built site: ``<build_dir>/html``."""
        return self.build_dir / "html"

    @classmethod
    def of_repo(cls, repo_root: Path) -> DocsLayout:
        """The layout of a checkout: ``docs/`` built into ``docs/_build/``.

        Example: ``DocsLayout.of_repo(Path("/repo")).html_dir`` -> ``Path("/repo/docs/_build/html")``.
        """
        return cls(source_dir=repo_root / "docs", build_dir=repo_root / "docs" / "_build")


def build_parser() -> argparse.ArgumentParser:
    """The ``build_docs.py`` options.

    Example: ``build_parser().parse_args(["--serve"]).serve`` -> ``8000``.
    """
    parser = argparse.ArgumentParser(
        prog="build_docs.py", description="Build the documentation site strictly, as CI does."
    )
    parser.add_argument("--clean", action="store_true", help="delete docs/_build first")
    parser.add_argument(
        "--serve",
        nargs="?",
        const=DEFAULT_PORT,
        type=int,
        metavar="PORT",
        help=f"after a good build, serve it on 127.0.0.1 (default port {DEFAULT_PORT})",
    )
    return parser


def sphinx_command(layout: DocsLayout, python: str = sys.executable) -> list[str]:
    """The ``sphinx-build`` call, run through ``python`` so it uses this environment.

    Example: ``sphinx_command(layout)[1:3]`` -> ``["-m", "sphinx"]``.
    """
    return [python, "-m", "sphinx", *SPHINX_OPTIONS, str(layout.source_dir), str(layout.html_dir)]


def main(
    argv: Sequence[str] | None = None,
    *,
    layout: DocsLayout | None = None,
    run: Callable[[list[str]], int] | None = None,
    serve: Callable[[Path, int], None] | None = None,
    has_sphinx: Callable[[], bool] | None = None,
) -> int:
    """Build the site and, with ``--serve``, preview it; return the exit code.

    The keyword arguments replace the real filesystem layout, process runner,
    server and Sphinx check, so tests run without Sphinx and touch nothing.

    Example: ``main(["--clean"])`` rebuilds ``docs/_build/html`` from scratch.
    """
    args = build_parser().parse_args(argv)
    layout = layout or DocsLayout.of_repo(Path(__file__).resolve().parent.parent)
    if not (has_sphinx or _has_sphinx)():
        print(INSTALL_HINT, file=sys.stderr)
        return USAGE_EXIT
    if args.clean:
        shutil.rmtree(layout.build_dir, ignore_errors=True)
    code = (run or _run)(sphinx_command(layout))
    if code != 0 or args.serve is None:
        return code
    (serve or serve_html)(layout.html_dir, args.serve)
    return 0


def serve_html(directory: Path, port: int) -> None:  # pragma: no cover - blocks until Ctrl+C
    """Serve ``directory`` on ``127.0.0.1:port`` until interrupted."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"Serving {directory} at http://127.0.0.1:{port}/ (Ctrl+C to stop)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print()


def _run(command: list[str]) -> int:
    return subprocess.run(command, check=False).returncode


def _has_sphinx() -> bool:
    return importlib.util.find_spec("sphinx") is not None


if __name__ == "__main__":
    sys.exit(main())
