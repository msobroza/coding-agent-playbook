"""``playbook scan-sinks`` — ml-unsafe-deserialization-guard's off-workstation twin (specs/prK-hook-pack.md §E.3).

Counts the unsafe sink calls a change adds with the guard's own visitor
(``judges.sink_scan.new_sink_calls``) and the sink table the engine ships in the guard's
``HOOK.md``, so the hook and its twin never disagree on a row:

- ``--staged``: the index against ``HEAD`` (the ``playbook-scan-sinks``
  pre-commit entry);
- ``--range A..B`` / ``A...B``: as ``playbook gate-scan``; with neither,
  ``<merge base with the default branch>..HEAD``.

Python files and the code cells of notebooks are scanned. A block sink under
a ``# playbook: trusted-artifact`` comment that the base already had passes;
under a new one it is a note (a reviewer confirms the provenance, as the
hook's ``ask`` would). Warn rows are notes. git runs through the stateless
``SafeGit`` of ``_git_scope``.

Exit codes: 0 clean (notes only), 1 a new block sink, 2 a usage or git error.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook.commands.twins._git_scope import open_git, resolve_range
from coding_agent_playbook.hook_runtime.git import GitError
from coding_agent_playbook.hook_runtime.judges.notebook_cells import notebook_code
from coding_agent_playbook.hook_runtime.judges.sink_scan import (
    SinkTable,
    new_sink_calls,
    trusted_artifact_line,
)

if TYPE_CHECKING:
    import argparse

    from coding_agent_playbook.hook_runtime.git import GitPort, SafeGit
    from coding_agent_playbook.hook_runtime.judges.sink_scan import SinkHit

__all__ = ["SinkChange", "SinkFinding", "range_changes", "run", "scan_changes", "shipped_table"]

HOOK_ID: Final = "ml-unsafe-deserialization-guard"
_HOOK_MD: Final = ("hooks", "feedback", HOOK_ID, "HOOK.md")
_SUFFIXES: Final = (".py", ".ipynb")

type Status = Literal["blocking", "warn", "new_pragma"]


@dataclass(frozen=True, slots=True)
class SinkChange:
    """One changed file: its text at the base (``None``: added) and after the change."""

    rel: str
    before: str | None
    after: str


@dataclass(frozen=True, slots=True)
class SinkFinding:
    """One new sink call and how the twin counts it (``line`` 0: a notebook's cells)."""

    rel: str
    line: int
    callee: str
    status: Status
    advice: str

    def text(self) -> str:
        """``path:line: callee: advice``, prefixed ``note:`` unless blocking."""
        where = self.rel if self.line == 0 else f"{self.rel}:{self.line}"
        prefix = "" if self.status == "blocking" else "note: "
        return f"{prefix}{where}: {self.callee}: {self.advice}"

    def to_json(self) -> dict[str, object]:
        return {
            "path": self.rel,
            "line": self.line,
            "call": self.callee,
            "status": self.status,
            "advice": self.advice,
        }


def run(args: argparse.Namespace, *, git: SafeGit | None = None) -> int:
    """Scan the staged change or ``args.rev_range`` and print the findings; returns 0, 1 or 2.

    Example::

        >>> run(build_parser().parse_args(["scan-sinks", "--staged"]))  # doctest: +SKIP
        1
    """
    repo_root = Path(args.repo_root or ".").resolve()
    try:
        port = git if git is not None else open_git(repo_root)
        label, changes = _changes(port, args)
        findings = scan_changes(changes, shipped_table())
    except (GitError, ValueError) as exc:  # GitBaseError and a bad --range are ValueErrors
        print(f"error: {exc}", file=sys.stderr)
        return 2
    code = 1 if any(f.status == "blocking" for f in findings) else 0
    print(_json(findings, label, code) if args.format == "json" else _text(findings, label))
    return code


def shipped_table() -> SinkTable:
    """The sink table of the engine's own ``HOOK.md`` (its ``handler.config``).

    The ``HOOK.md`` is in the engine's catalog (``catalog/core/hooks/``), found
    through the ``catalog.roots`` module; a broken install raises ``CatalogMissingError``.
    """
    from coding_agent_playbook.artifacts.hook import Hook
    from coding_agent_playbook.catalog.roots import ENGINE_PACKAGE, engine_layer_root

    path = engine_layer_root().joinpath(*_HOOK_MD)
    handler = Hook.from_markdown(path, ENGINE_PACKAGE).frontmatter.handler
    return SinkTable.from_config({} if handler is None else handler.config)


def _changes(git: SafeGit, args: argparse.Namespace) -> tuple[str, list[SinkChange]]:
    if args.staged:
        return "staged", staged_changes(git)
    span = resolve_range(git, args.rev_range)
    return span.label, range_changes(git, span.base, span.head)


def range_changes(git: GitPort, base: str, head: str) -> list[SinkChange]:
    """The Python files and notebooks the diff from ``base`` to ``head`` changes or adds.

    Example::

        >>> [c.rel for c in range_changes(git, "HEAD~1", "HEAD")]  # doctest: +SKIP
        ['src/app/io.py']
    """
    changes: list[SinkChange] = []
    for rel in git.diff_range(base, head).paths:
        after = git.show(head, rel) if rel.endswith(_SUFFIXES) else None
        if after is not None:
            changes.append(
                SinkChange(rel, _decoded(git.show(base, rel)), after.decode("utf-8", "replace"))
            )
    return changes


def staged_changes(git: SafeGit) -> list[SinkChange]:
    """The staged Python files and notebooks (added, copied, modified, renamed) against ``HEAD``."""
    from coding_agent_playbook.hook_runtime._git_parse import parse_batch_blob, split_z

    listed = git.run(["diff", "--cached", "--name-only", "-z", "--no-renames", "--diff-filter=ACM"])
    changes: list[SinkChange] = []
    for rel in split_z(listed.stdout):
        if not rel.endswith(_SUFFIXES) or "\n" in rel:
            continue
        staged = parse_batch_blob(
            git.run(["cat-file", "--batch"], input=f":{rel}\n".encode()).stdout
        )
        if staged is not None:
            changes.append(
                SinkChange(rel, _decoded(git.cat_head(rel)), staged.decode("utf-8", "replace"))
            )
    return changes


def scan_changes(changes: list[SinkChange], table: SinkTable) -> list[SinkFinding]:
    """Every new sink call of ``changes``, judged as the hook judges it (module docstring).

    Example::

        >>> scan_changes([SinkChange("a.py", None, "import pickle\\npickle.loads(b)\\n")],
        ...              SinkTable.from_config({"block": [{"call": "pickle.loads"}]}))[0].status
        'blocking'
    """
    findings: list[SinkFinding] = []
    for change in changes:
        notebook = change.rel.endswith(".ipynb")
        before, after = _code(change.before, notebook), _code(change.after, notebook) or ""
        for hit in new_sink_calls(before, after, table):
            status = _status(hit, before, after)
            if status is not None:
                line = 0 if notebook else hit.line
                findings.append(
                    SinkFinding(change.rel, line, hit.callee, status, _advice(hit, status))
                )
    return findings


def _status(hit: SinkHit, before: str | None, after: str) -> Status | None:
    pragma = trusted_artifact_line(after, hit.line)
    if pragma is not None and pragma in {line.strip() for line in (before or "").splitlines()}:
        return None  # vouched for before this change
    if hit.kind == "warn":
        return "warn"
    return "blocking" if pragma is None else "new_pragma"


def _advice(hit: SinkHit, status: Status) -> str:
    if status == "new_pragma":
        return "under a new trusted-artifact comment: confirm the artifact's provenance"
    return hit.row.advice or "new unsafe deserialization sink"


def _code(text: str | None, notebook: bool) -> str | None:
    if text is None or not notebook:
        return text
    return notebook_code(text) or text


def _decoded(raw: bytes | None) -> str | None:
    return None if raw is None else raw.decode("utf-8", errors="replace")


def _text(findings: list[SinkFinding], label: str) -> str:
    blocking = [f for f in findings if f.status == "blocking"]
    lines = [f.text() for f in findings]
    noted = len(findings) - len(blocking)
    if blocking:
        lines.append(f"scan-sinks {label}: {len(blocking)} blocking, {noted} noted")
    else:
        lines.append(f"scan-sinks {label}: clean ({noted} noted)")
    return "\n".join(lines)


def _json(findings: list[SinkFinding], label: str, code: int) -> str:
    document = {
        "range": label,
        "findings": [finding.to_json() for finding in findings],
        "blocking": sum(f.status == "blocking" for f in findings),
        "exit": code,
    }
    return json.dumps(document, indent=2, ensure_ascii=False)
