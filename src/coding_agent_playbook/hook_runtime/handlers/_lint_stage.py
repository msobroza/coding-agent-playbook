"""stop-ci-parity-gate's ``lint`` stage: CI-parity ruff, blocking only on what this work added (specs/prK-hook-pack.md §E.2).

It runs ``ruff check --output-format=json .`` (the ``stop_gate.stages`` record)
and ``ruff format --check .`` at the worktree root, with no path arguments,
exactly as CI does. Legacy red must never fail every turn, so it blocks only on:

- a new ``(file, code, message)`` tuple; line numbers are ignored, so moving
  code does not make an old finding new;
- a file that newly needs reformatting.

"New" is measured against a baseline: the same two commands run over a
``git archive HEAD`` export in a temp dir (secret paths never extracted), cached
per ``HEAD^{tree}`` at ``stop/lint-baseline-<tree>.json``, so it is computed
once per commit. A clean tree never needs the baseline. A ruff that cannot run
(no pin, changed binary, timeout, exit 2) is ``skipped``: NOT verified, never green.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.artifacts.path_globs import fold_key
from coding_agent_playbook.hook_runtime.dispatch.caps import clean_text, clip, quote_data
from coding_agent_playbook.hook_runtime.state.store import StateUnavailable
from coding_agent_playbook.hook_runtime.stop.stages import StageCost, StageResult
from coding_agent_playbook.hook_runtime.stop.tools import runner_of, seconds_left, stage_command

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from coding_agent_playbook.hook_runtime.deps import Clock
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.git.safe_git import GitPort
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.state.store import StateStore
    from coding_agent_playbook.hook_runtime.stop.runner import StageRunner, ToolRun
    from coding_agent_playbook.hook_runtime.stop.stages import StopPlan

    type Finding = tuple[str, str, str]  # (file, code, message)

__all__ = ["FORMAT_ARGS", "STAGE_NAME", "LintSnapshot", "LintStage", "baseline_doc", "lint_stage"]

STAGE_NAME: Final = "lint"
FORMAT_ARGS: Final = ("format", "--check", ".")
_BASELINE_DOC: Final = "stop/lint-baseline-{tree}.json"
_TREE_ID: Final = re.compile(r"[0-9a-f]{40,64}")
_WOULD_REFORMAT: Final = re.compile(r"^Would reformat: (.+)$", re.MULTILINE)
#: ruff exits 1 when it found something; anything else is a broken run.
_RUFF_OK: Final = frozenset({0, 1})
_MESSAGE_CHARS: Final = 100


@dataclass(frozen=True, slots=True)
class LintSnapshot:
    """What ruff reported for one tree: findings (first row each) and unformatted files.

    Example: ``LintSnapshot({("a.py", "F401", "x"): 3}, frozenset()).clean`` is ``False``.
    """

    findings: Mapping[Finding, int]
    unformatted: frozenset[str]

    @property
    def clean(self) -> bool:
        """Nothing to attribute: no finding and no unformatted file."""
        return not self.findings and not self.unformatted

    def restricted(self, paths: frozenset[str]) -> LintSnapshot:
        """Only what ruff reported about ``paths`` (a subagent's edited files, §D.5.6)."""
        findings = {key: row for key, row in self.findings.items() if key[0] in paths}
        return LintSnapshot(findings, self.unformatted & paths)

    def to_json(self) -> dict[str, Any]:
        """The cached baseline document."""
        rows = [[*key, row] for key, row in sorted(self.findings.items())]
        return {"v": 1, "check": rows, "unformatted": sorted(self.unformatted)}

    @classmethod
    def from_json(cls, document: Mapping[str, Any]) -> LintSnapshot | None:
        """A cached baseline, or ``None`` when absent or malformed (it is then recomputed)."""
        rows, unformatted = document.get("check"), document.get("unformatted")
        if document.get("v") != 1 or not isinstance(rows, list):
            return None
        if not isinstance(unformatted, list):
            return None
        findings = {
            (str(r[0]), str(r[1]), str(r[2])): r[3]
            for r in rows
            if isinstance(r, list) and len(r) == 4 and type(r[3]) is int
        }
        return cls(findings, frozenset(str(path) for path in unformatted))


def baseline_doc(head_tree: str) -> str | None:
    """The state document caching ``head_tree``'s baseline; ``None`` for a malformed id.

    Example: ``baseline_doc("ab" * 20) == "stop/lint-baseline-abab...ab.json"``.
    """
    return _BASELINE_DOC.format(tree=head_tree) if _TREE_ID.fullmatch(head_tree) else None


@dataclass(frozen=True, slots=True, kw_only=True)
class LintStage:
    """The ``lint`` stage of one Stop; every collaborator is injected.

    ``only`` scopes the verdict to those repo paths (subagent-stop-verify);
    ruff still runs over the whole tree, exactly as CI does.

    Example::

        >>> stage = lint_stage(stop_event, ctx)  # doctest: +SKIP
        >>> stage.run(plan, deadline).status
        'red'
    """

    runner: StageRunner
    git: GitPort
    store: StateStore
    clock: Clock
    root: str
    tool: str
    check_args: tuple[str, ...]
    skip_path: Callable[[str], bool]
    only: frozenset[str] | None = None
    name: str = STAGE_NAME
    cost: StageCost = StageCost.DETERMINISTIC
    needs_diff: bool = True
    mode: str = "block"

    def applies(self, plan: StopPlan) -> bool:
        """Every changed tree is linted."""
        return True

    def run(self, plan: StopPlan, deadline: float) -> StageResult:
        """Red with one line per new finding or newly unformatted file; else green."""
        current = self._snapshot(None, deadline)
        if isinstance(current, StageResult):
            return current
        if self.only is not None:
            current = current.restricted(self.only)
        if current.clean:  # nothing to attribute: the baseline is never needed
            return _green()
        baseline = self._baseline(plan.head_tree, deadline)
        if isinstance(baseline, StageResult):
            return baseline
        return _verdict(current, baseline)

    def _snapshot(self, cwd: str | None, deadline: float) -> LintSnapshot | StageResult:
        """Both ruff commands in ``cwd`` (``None``: the worktree), parsed."""
        check = self._ruff(self.check_args, cwd, deadline)
        if not isinstance(check, bytes):
            return check
        formatted = self._ruff(FORMAT_ARGS, cwd, deadline)
        if not isinstance(formatted, bytes):
            return formatted
        base = cwd or self.root
        return LintSnapshot(parse_check(check, base), parse_unformatted(formatted, base))

    def _ruff(self, args: tuple[str, ...], cwd: str | None, deadline: float) -> bytes | StageResult:
        left = seconds_left(self.clock, deadline)
        if left <= 0:
            return StageResult(STAGE_NAME, "skipped", skip_category="timeout")
        run: ToolRun = self.runner.run(self.tool, args, timeout=left, cwd=cwd)
        if run.skip_category:
            return run.skipped(STAGE_NAME)
        if run.returncode not in _RUFF_OK:
            return StageResult(STAGE_NAME, "skipped", skip_category="crash")
        return run.stdout + b"\n" + run.stderr if args == FORMAT_ARGS else run.stdout

    def _baseline(self, head_tree: str | None, deadline: float) -> LintSnapshot | StageResult:
        """``HEAD``'s snapshot: cached per tree, else measured over a ``git archive`` export."""
        if head_tree is None:  # unborn branch: everything is new
            return LintSnapshot({}, frozenset())
        doc = baseline_doc(head_tree)
        cached = self._cached(doc)
        if cached is not None:
            return cached
        with tempfile.TemporaryDirectory(prefix="playbook-lint-") as export:
            self.git.archive_to("HEAD", export, skip=self.skip_path)
            measured = self._snapshot(export, deadline)
        if isinstance(measured, LintSnapshot) and doc is not None:
            with suppress(StateUnavailable, OSError):  # stateless: measured again next Stop
                self.store.write_json(doc, measured.to_json())
        return measured

    def _cached(self, doc: str | None) -> LintSnapshot | None:
        if doc is None:
            return None
        try:
            return LintSnapshot.from_json(self.store.read_json(doc))
        except (StateUnavailable, OSError):
            return None


def parse_check(stdout: bytes, base: str) -> dict[Finding, int]:
    """``ruff check --output-format=json`` rows as ``{(file, code, message): first row}``.

    Example::

        >>> parse_check(b'[{"filename": "/r/a.py", "code": "F401", "message": "m",'
        ...             b' "location": {"row": 3}}]', "/r")
        {('a.py', 'F401', 'm'): 3}
    """
    found: dict[Finding, int] = {}
    for row in json.loads(stdout or b"[]"):
        if not isinstance(row, dict) or not isinstance(row.get("filename"), str):
            continue
        location = row.get("location")
        line = location.get("row", 0) if isinstance(location, dict) else 0
        key = (_relative(row["filename"], base), str(row.get("code") or "syntax"), _msg(row))
        found.setdefault(key, line if isinstance(line, int) else 0)
    return found


def parse_unformatted(output: bytes, base: str) -> frozenset[str]:
    """The files ``ruff format --check`` would reformat, repo-relative.

    Example: ``parse_unformatted(b"Would reformat: src/a.py\\n", "/r") == {"src/a.py"}``.
    """
    text = output.decode("utf-8", errors="replace")
    return frozenset(_relative(m.group(1).strip(), base) for m in _WOULD_REFORMAT.finditer(text))


def lint_stage(ev: CanonicalEvent, ctx: HandlerContext) -> LintStage | None:
    """The ``lint`` stage for ``ev``'s repository, from its rendered record: the factory.

    Example: ``lint_stage(stop_event, ctx).check_args[0] == "check"``.
    """
    command = stage_command(ctx.cfg, STAGE_NAME)
    if ev.repo is None or command is None:
        return None
    secrets, platform = ctx.cfg.secret_paths, ctx.platform
    return LintStage(
        runner=runner_of(ctx, ev.repo),
        git=ctx.git,
        store=ctx.session.store,
        clock=ctx.clock,
        root=ev.repo.worktree_root,
        tool=command[0],
        check_args=command[1],
        skip_path=lambda rel: secrets.matches(fold_key(rel, platform)),
    )


def _verdict(current: LintSnapshot, baseline: LintSnapshot) -> StageResult:
    new = sorted(key for key in current.findings if key not in baseline.findings)
    reformat = sorted(current.unformatted - baseline.unformatted)
    if not new and not reformat:
        return _green()
    lines = [
        f"{quote_data(path)}:{current.findings[(path, code, message)]} {code} {message}"
        for path, code, message in new
    ]
    lines += [f"{quote_data(path)} needs reformatting (ruff format)" for path in reformat]
    old = len(current.findings) - len(new) + len(current.unformatted) - len(reformat)
    if old:
        lines[0] += f" ({len(new) + len(reformat)} new; {old} pre-existing ignored)"
    return StageResult(STAGE_NAME, "red", lines=tuple(lines))


def _relative(path: str, base: str) -> str:
    """``path`` relative to ``base``, POSIX; both resolved, as ruff may print a realpath."""
    if not os.path.isabs(path):
        return path.replace(os.sep, "/")
    rel = os.path.relpath(os.path.realpath(path), os.path.realpath(base))
    return rel.replace(os.sep, "/")


def _msg(row: Mapping[str, Any]) -> str:
    return clip(clean_text(str(row.get("message") or "")), _MESSAGE_CHARS)


def _green() -> StageResult:
    return StageResult(STAGE_NAME, "green")
