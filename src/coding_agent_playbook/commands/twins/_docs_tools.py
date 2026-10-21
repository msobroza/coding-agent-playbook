"""The repository's own docs tools that ``playbook docs-check`` runs (D69, D78(10)).

A tool runs only where the repository already configures it, so docs-check
never imposes one:

- MkDocs, ``mkdocs build --strict``, where ``mkdocs.yml`` or ``mkdocs.yaml`` exists;
- Sphinx, ``sphinx-build -W --keep-going``, where ``docs/conf.py``,
  ``docs/source/conf.py`` or ``doc/conf.py`` exists;
- doctests, ``pytest <files>``, on the changed files a ``--doctest-glob`` of the
  repo's pytest ``addopts`` collects (the suite itself never runs);
- markdownlint on the changed Markdown and doc8 on the changed reStructuredText,
  where their config file exists (:mod:`._docs_config`).

Both builds write to a temporary directory, never into the repository. A tool
that is not on ``PATH`` fails open: one ``skipped`` line whose install hint is
the repository's ``docs`` dependency group or extra when it declares one (that
group is the docs toolchain), else the tool's own package.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands.twins._docs_config import (
    doc8_configured,
    docs_group_hint,
    doctest_globs,
    first_existing,
    markdownlint_configured,
)
from coding_agent_playbook.commands.twins._docs_markdown import MARKDOWN_SUFFIXES
from coding_agent_playbook.hook_runtime.dispatch.proc import ProcTimeout

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime.dispatch.deps import ProcPort

__all__ = ["MKDOCS_CONFIGS", "SPHINX_CONFS", "TOOL_TIMEOUT_S", "ToolReport", "tool_report"]

MKDOCS_CONFIGS: Final = ("mkdocs.yml", "mkdocs.yaml")
SPHINX_CONFS: Final = ("docs/conf.py", "docs/source/conf.py", "doc/conf.py")
#: Per tool: a docs build of a large project takes minutes, not the hooks' seconds.
TOOL_TIMEOUT_S: Final = 600.0
_OUTPUT_TAIL: Final = 20


@dataclass(frozen=True, slots=True)
class ToolReport:
    """What the docs tools reported: printable lines and how many tools failed.

    Example: ``ToolReport(("docs-check: `mkdocs build --strict` failed (exit 1)",), 1)``.
    """

    lines: tuple[str, ...] = ()
    failures: int = 0


@dataclass(frozen=True, slots=True)
class _ToolRun:
    """One planned tool call: its label, program, arguments and default install hint."""

    label: str
    program: str
    args: tuple[str, ...]
    hint: str
    python_tool: bool = True


def tool_report(root: Path, paths: list[str], proc: ProcPort) -> ToolReport:
    """Run every docs tool ``root`` configures over the changed ``paths`` (repo-relative).

    Example::

        >>> tool_report(Path("."), ["README.md"], SubprocessProc())  # doctest: +SKIP
        ToolReport(lines=(), failures=0)
    """
    with tempfile.TemporaryDirectory(prefix="playbook-docs-") as out:
        runs = _planned(root, paths, Path(out))
        results = [_run_one(run, root, proc) for run in runs]
    lines = tuple(line for _, found in results for line in found)
    return ToolReport(lines, sum(1 for failed, _ in results if failed))


def _planned(root: Path, paths: list[str], out: Path) -> list[_ToolRun]:
    return [
        *_builds(root, out),
        *_doctests(root, paths),
        *_linters(root, paths),
    ]


def _builds(root: Path, out: Path) -> list[_ToolRun]:
    planned = (_mkdocs(root, out / "mkdocs"), _sphinx(root, out / "sphinx"))
    return [run for run in planned if run is not None]


def _mkdocs(root: Path, site: Path) -> _ToolRun | None:
    config = first_existing(root, MKDOCS_CONFIGS)
    if config is None:
        return None
    args = ("build", "--strict", "--config-file", config, "--site-dir", str(site))
    return _ToolRun("mkdocs build --strict", "mkdocs", args, "pip install mkdocs")


def _sphinx(root: Path, build: Path) -> _ToolRun | None:
    conf = first_existing(root, SPHINX_CONFS)
    if conf is None:
        return None
    source = str(PurePosixPath(conf).parent)
    args = ("-W", "--keep-going", "-q", "-b", "html", source, str(build))
    return _ToolRun("sphinx-build -W --keep-going", "sphinx-build", args, "pip install sphinx")


def _doctests(root: Path, paths: list[str]) -> list[_ToolRun]:
    globs = doctest_globs(root)
    files = tuple(p for p in paths if any(PurePosixPath(p).match(glob) for glob in globs))
    if not files:
        return []
    return [_ToolRun("pytest (doctests)", "pytest", files, "pip install pytest")]


def _linters(root: Path, paths: list[str]) -> list[_ToolRun]:
    runs: list[_ToolRun] = []
    markdown = tuple(p for p in paths if PurePosixPath(p).suffix.lower() in MARKDOWN_SUFFIXES)
    if markdown and markdownlint_configured(root):
        hint = "npm install --global markdownlint-cli"
        runs.append(_ToolRun("markdownlint", "markdownlint", markdown, hint, python_tool=False))
    rst = tuple(p for p in paths if PurePosixPath(p).suffix.lower() == ".rst")
    if rst and doc8_configured(root):
        runs.append(_ToolRun("doc8", "doc8", rst, "pip install doc8"))
    return runs


def _run_one(run: _ToolRun, root: Path, proc: ProcPort) -> tuple[bool, list[str]]:
    """``(failed, lines)`` for one tool; a missing program is skipped, not failed."""
    found = proc.which(run.program)
    if found is None:
        hint = (docs_group_hint(root) if run.python_tool else "") or run.hint
        skipped = f"docs-check: skipped `{run.label}`: {run.program} is not installed"
        return False, [f"{skipped} (install it: {hint})"]
    try:
        result = proc.run([found, *run.args], timeout=TOOL_TIMEOUT_S, cwd=str(root))
    except (ProcTimeout, OSError) as exc:
        return True, [f"docs-check: `{run.label}` failed: {exc}"]
    if result.ok:
        return False, []
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace").splitlines()
    tail = [f"  {line}" for line in output[-_OUTPUT_TAIL:]]
    return True, [f"docs-check: `{run.label}` failed (exit {result.returncode})", *tail]
