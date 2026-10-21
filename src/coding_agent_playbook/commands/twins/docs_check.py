"""``playbook docs-check [PATHS]`` — the documentation guard twin (specs/prU-core-python-skills.md D69).

It checks committed documentation with the repository's own tools only. Always,
in engine stdlib code: the relative links and the Python code blocks of each
changed Markdown file. Then, only where the repository configures them: the
docs build and the doctests and linters (:mod:`._docs_tools`). A configured
tool that is not installed fails open: one ``skipped`` line with an install hint.

The ``playbook-docs`` pre-commit hook runs it on the staged files that match
:data:`DOCS_FILES_PATTERN` (``*.md``, ``*.rst``, ``docs/**``, ``mkdocs.yml``,
``mkdocs.yaml``, ``doc/conf.py``), so a commit of Python files alone never runs
it. Without PATHS it checks the files changed since ``--base`` (default: the
default branch, through its merge base with ``HEAD``) plus the untracked ones,
which is how CI runs it. ``[guardrails.docs] mode`` switches it: ``block`` (the
default) fails on a finding, ``warn`` prints and passes, ``off`` checks nothing.

Exit codes: 0 clean (or warn/off), 1 a finding, 2 a named path that does not
exist, a git error or a config that does not load.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands.twins._docs_markdown import (
    MARKDOWN_SUFFIXES,
    markdown_findings,
)
from coding_agent_playbook.commands.twins._docs_tools import tool_report
from coding_agent_playbook.commands.twins._git_scope import (
    BASE_FLAG_HELP,
    open_git,
    resolve_merge_base,
)
from coding_agent_playbook.commands.twins._runner import TWIN_ERRORS, TwinOutcome, run_twin
from coding_agent_playbook.config.files import ConfigFiles
from coding_agent_playbook.config.tables.hooks import parse_guardrails_config
from coding_agent_playbook.hook_runtime.dispatch.proc import SubprocessProc

if TYPE_CHECKING:
    import argparse

    from coding_agent_playbook.hook_runtime.dispatch.deps import ProcPort
    from coding_agent_playbook.hook_runtime.git.safe_git import GitPort

__all__ = ["DOCS_FILES_PATTERN", "HELP", "NAME", "configure", "docs_paths", "run"]

NAME: Final = "docs-check"
HELP: Final = "check changed documentation: links, code blocks, the repo's docs tools (D69)"

#: The documentation paths, as the pre-commit hooks' ``files:`` regex (D69, D78(10)).
DOCS_FILES_PATTERN: Final = r"(\.(md|markdown|rst)$|^docs/|^mkdocs\.ya?ml$|^doc/conf\.py$)"
_DOCS_FILES: Final = re.compile(DOCS_FILES_PATTERN)


def configure(parser: argparse.ArgumentParser) -> None:
    """Declare ``playbook docs-check [PATHS] [--base REF]`` (D69).

    Example::

        >>> configure(argparse.ArgumentParser(prog="playbook docs-check"))  # doctest: +SKIP
    """
    parser.add_argument(
        "paths", nargs="*", help="documentation files to check (default: changed since --base)"
    )
    parser.add_argument("--base", help=BASE_FLAG_HELP)
    parser.add_argument("--repo-root", help="repo the paths are relative to (defaults to cwd)")


def run(
    args: argparse.Namespace, *, proc: ProcPort | None = None, git: GitPort | None = None
) -> int:
    """Check ``args.paths`` (default: the docs changed since the base); returns 0, 1 or 2.

    Example::

        >>> run(build_parser().parse_args(["docs-check", "README.md"]))  # doctest: +SKIP
        1
    """
    port = proc if proc is not None else SubprocessProc()
    return run_twin(
        args.repo_root,
        lambda root: _outcome(args.paths, args.base, root, port, git),
        errors=(*TWIN_ERRORS, OSError),
    )


def docs_paths(paths: list[str]) -> list[str]:
    """The paths among ``paths`` (repo-relative, ``/``-separated) that are documentation.

    Example::

        >>> docs_paths(["src/a.py", "README.md", "docs/conf.py"])
        ['README.md', 'docs/conf.py']
    """
    return [path for path in paths if _DOCS_FILES.search(path)]


def _outcome(
    named: list[str], base: str | None, root: Path, proc: ProcPort, git: GitPort | None
) -> TwinOutcome:
    mode = _mode(root)
    if mode == "off":
        return TwinOutcome(0, 'docs-check: off ([guardrails.docs] mode = "off")')
    paths = _checked_named(named, root) if named else _changed(base, root, git)
    if not paths:
        return TwinOutcome(0, "docs-check: no documentation changed")
    lines = [
        line
        for rel in paths
        if Path(rel).suffix.lower() in MARKDOWN_SUFFIXES
        for line in markdown_findings(root / rel, rel)
    ]
    tools = tool_report(root, paths, proc)
    failed = len(lines) + tools.failures
    summary = (
        f"docs-check: {failed} finding(s) in {len(paths)} file(s)"
        if failed
        else (f"docs-check: {len(paths)} file(s) clean")
    )
    code = 1 if failed and mode == "block" else 0
    return TwinOutcome(code, "\n".join([*lines, *tools.lines, summary]))


def _mode(root: Path) -> str:
    table = ConfigFiles(root).committed_table("guardrails")
    return parse_guardrails_config(dict(table) if table else None).docs.mode


def _checked_named(named: list[str], root: Path) -> list[str]:
    missing = [path for path in named if not (root / path).is_file()]
    if missing:
        raise ValueError(f"no such file: {', '.join(missing)}")
    return [Path(path).as_posix() for path in named]


def _changed(base: str | None, root: Path, git: GitPort | None) -> list[str]:
    port = git if git is not None else open_git(root)
    sha = resolve_merge_base(port, base).sha
    changed = sorted({*port.diff_worktree(sha).paths, *port.ls_untracked()})
    return [rel for rel in docs_paths(changed) if (root / rel).is_file()]
