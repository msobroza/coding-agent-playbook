"""The one metrics pass the ``quality-metrics`` and ``docstrings`` Stop stages share (specs/prK-hook-pack.md §F.2.2).

Both stages read findings of the same in-process ``run_metrics_gate`` call,
memoized on the event, so each touched file is parsed and ruff-checked once per
Stop whichever stage asks first:

- **what**: the touched ``.py`` files (the ledger, ``git diff HEAD`` and
  untracked files, minus the ``eval_fixture`` path class), at most
  :data:`MAX_FILES`, against ``git:HEAD`` through the hook's hardened
  ``SafeGit``; ``run_tests`` is **always** ``False`` (a repo's
  ``[metrics] run_tests = true`` never runs its suite from a hook, §B.4);
- **which metrics**: ``[metrics]`` (read live, like the pre-commit twin)
  restricted to the ``quality`` and ``docstrings`` families, plus
  ``ruff_violations`` by name (``policy.stop_stage_selection``);
- **tools**: each picked metric's tool (ruff, complexipy) runs through its
  ``machine.json`` pin and ``ctx.proc``, bounded by the stage deadline; without
  a usable pin its metric measures nothing, and a consumer who selected the
  metric gets a line saying so;
- **severity** (:meth:`MetricsPass.deny_eligible`): a fail-level finding may
  block only when ``[metrics] fail_on_breach`` is true **and** the consumer's
  own selection includes the metric. Under the stage hook's default
  ``block = "auto"``, ``.pre-commit-config.yaml`` must also declare a playbook
  metrics hook, so a stage is never stricter than its twin; ``block =
  "always"`` (:func:`block_policy`) drops that condition, for repos whose
  commits and CI may not run the gate.

A private module: it registers no handler.
"""

from __future__ import annotations

import dataclasses
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.artifacts.path_globs import fold_key
from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
from coding_agent_playbook.hook_runtime.dispatch.caps import clean_text, clip, quote_data
from coding_agent_playbook.hook_runtime.dispatch.event import EventName
from coding_agent_playbook.hook_runtime.dispatch.proc import ProcTimeout
from coding_agent_playbook.hook_runtime.dispatch.registry import ConfigKey
from coding_agent_playbook.hook_runtime.stop.tools import edited_py

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from coding_agent_playbook.grading.metric import Metric
    from coding_agent_playbook.grading.static_metrics.ruff_violations import RuffHit
    from coding_agent_playbook.grading.tool_runner import ToolRunner
    from coding_agent_playbook.grading.types import ScopeDetail, ToolSetup
    from coding_agent_playbook.hook_runtime.dispatch.deps import Clock, ProcPort
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.git.safe_git import GitPort
    from coding_agent_playbook.hook_runtime.stop.stages import StopPlan

    type Gate = Callable[[Any, Any], Any]  # (MetricsGateRequest, MetricsGateDeps) -> result

__all__ = [
    "BLOCK_ALWAYS",
    "BLOCK_AUTO",
    "BLOCK_KEY",
    "MAX_FILES",
    "METRICS_HOOK_IDS",
    "MORE_HINT",
    "MetricsPass",
    "PortBaselineGit",
    "ProcToolRunner",
    "block_policy",
    "capped",
    "finding_line",
    "is_test_path",
    "metrics_gated",
    "ruff_detail",
    "ruff_line",
    "shared_pass",
    "touched_py",
]

#: The pre-commit ids that make a metrics regression fail the commit (§E.2).
METRICS_HOOK_IDS: Final = frozenset({"playbook-metrics", "coding-agent-playbook-metrics"})
#: ``[hooks.<stage hook>] block``: ``auto`` blocks only where pre-commit gates metrics,
#: ``always`` also without it. ``strictest``: an overlay's ``always`` is never loosened.
BLOCK_AUTO: Final = "auto"
BLOCK_ALWAYS: Final = "always"
BLOCK_KEY: Final = ConfigKey("string", "strictest", (BLOCK_AUTO, BLOCK_ALWAYS))
MAX_FILES: Final = 50
#: Where the full list is, once a stage has shown its lines (§F.2.2).
MORE_HINT: Final = "playbook metrics --changed --baseline git:HEAD"
_PRECOMMIT: Final = ".pre-commit-config.yaml"
_PRECOMMIT_MAX_BYTES: Final = 1024 * 1024
#: What a hostile source, a bad ``[metrics]`` table or a git failure can raise.
_MEASURE_ERRORS: Final = (SyntaxError, RecursionError, MemoryError, ValueError, OSError)
_DEF_LINE: Final = re.compile(r"\s*(?:async\s+def|def|class)\s+(\w+)")
_DETAIL_HITS: Final = 2


# --- what the pass measures ----------------------------------------------------------------------


def touched_py(plan: StopPlan, ctx: HandlerContext, root: str) -> list[str]:
    """Ledger ``.py`` edits, then ``git diff HEAD`` and untracked ``.py`` files; no eval fixtures.

    Repo-relative and existing, once per event.
    Example: ``touched_py(plan, ctx, root) == ["src/x.py"]`` after an edit of ``src/x.py``.
    """

    def compute() -> list[str]:
        found = dict.fromkeys(edited_py(plan.ledger))
        found.update(dict.fromkeys(line.path for line in ctx.git.diff_added()))
        found.update(dict.fromkeys(ctx.git.ls_untracked()))
        fixtures = ctx.cfg.path_classes.get("eval_fixture")
        return [
            rel
            for rel in found
            if rel.endswith(".py")
            and not (fixtures is not None and fixtures.matches(fold_key(rel, ctx.platform)))
            and os.path.isfile(os.path.join(root, rel))
        ]

    touched: list[str] = ctx.memo.get_or_compute(("metrics-touched", root), compute)
    return touched


def is_test_path(rel: str, ctx: HandlerContext) -> bool:
    """Whether ``rel`` is in the ``test`` path class (``tests/``, ``test_*.py``, ``conftest.py``).

    Example: ``is_test_path("tests/test_x.py", ctx) is True``.
    """
    tests = ctx.cfg.path_classes.get("test")
    return tests is not None and tests.matches(fold_key(rel, ctx.platform))


# --- the pass ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricsPass:
    """One Stop's shared gate pass: the graded result, or the line saying why there is none.

    ``own`` is the consumer's ``[metrics]`` selection; ``fail_on_breach`` is
    its ``[metrics]`` key; ``gated`` says ``.pre-commit-config.yaml`` declares a
    playbook metrics hook; ``setup`` and ``tool_paths`` re-ask the pass's ruff
    memo for a finding's details; ``tools_missing`` says which selected metrics
    had no usable tool pin.

    Example::

        >>> shared_pass(plan, ctx, root, deadline).deny_eligible("wmc", BLOCK_AUTO)
        ... # doctest: +SKIP
        True
    """

    result: Any | None = None
    error: str = ""
    own: frozenset[str] = frozenset()
    fail_on_breach: bool = False
    gated: bool = False
    tool_paths: Mapping[str, str] = field(default_factory=dict)
    setup: ToolSetup | None = None
    tools_missing: tuple[str, ...] = ()

    def fails(self) -> list[ScopeDetail]:
        """The fail-level findings, in report order."""
        findings = [] if self.result is None else self.result.report.findings
        return [finding for finding in findings if finding.level == "fail"]

    def fix_note(self, finding: ScopeDetail) -> str:
        """What ``finding`` needs to pass and how (``metrics_gate.targets.fix_note``); ``""`` unknown.

        Example: ``found.fix_note(cc_regression) == "passes at <= 5: split branches into helpers"``.
        """
        if self.result is None:
            return ""
        from coding_agent_playbook.metrics_gate.targets import fix_note

        note: str = fix_note(finding, self.result.config)
        return note

    def deny_eligible(self, evaluator: str, block: str) -> bool:
        """Whether a fail of ``evaluator`` may block under the stage's ``block`` policy.

        Never without ``fail_on_breach`` or for a metric the consumer does not
        select; under :data:`BLOCK_AUTO` the repo must also gate metrics in
        pre-commit, under :data:`BLOCK_ALWAYS` not.
        """
        if not self.fail_on_breach or evaluator not in self.own:
            return False
        return block == BLOCK_ALWAYS or self.gated


def shared_pass(
    plan: StopPlan,
    ctx: HandlerContext,
    root: str,
    deadline: float,
    *,
    git_dir: str | None = None,
    gate: Gate | None = None,
) -> MetricsPass:
    """The pass over this Stop's touched files, computed once per event (whichever stage asks first).

    ``gate`` replaces ``run_metrics_gate`` (a test spy).
    Example: ``shared_pass(plan, ctx, root, deadline, git_dir=repo.git_dir).fails()``.
    """
    key = ("metrics-pass", root)
    found: MetricsPass = ctx.memo.get_or_compute(
        key, lambda: _run_pass(plan, ctx, root, deadline, git_dir=git_dir, gate=gate)
    )
    return found


def _run_pass(
    plan: StopPlan,
    ctx: HandlerContext,
    root: str,
    deadline: float,
    *,
    git_dir: str | None,
    gate: Gate | None,
) -> MetricsPass:
    from coding_agent_playbook.grading.metric import static_metrics
    from coding_agent_playbook.metrics_gate import run as gates  # the stage runs
    from coding_agent_playbook.metrics_gate.policy import stop_stage_selection

    targets = touched_py(plan, ctx, root)[:MAX_FILES]
    try:
        config = gates.load_metrics_config(Path(root))
        picked, own = stop_stage_selection(static_metrics(), config)
    except (gates.MetricsGateUsageError, ValueError) as exc:
        return MetricsPass(error=f"metrics not measured: {clip(clean_text(str(exc)), 120)}")
    tool_paths, runner, missing = _pinned_tools(ctx, git_dir, deadline, picked)
    request = gates.MetricsGateRequest(
        repo_root=Path(root),
        config=config,
        paths=tuple(os.path.join(root, rel) for rel in targets),
        baseline="git:HEAD",
        run_tests=False,  # never the suite from a hook, whatever [metrics] run_tests says
        tool_paths=tool_paths,
        select=tuple(metric.name for metric in picked),
        extend_select=(),
        ignore=(),
    )
    git = ctx.git
    deps = gates.MetricsGateDeps(git_factory=lambda _timeout: PortBaselineGit(git))
    if runner is not None:
        deps = dataclasses.replace(deps, tool_runner=runner)
    try:
        if gate is not None:
            result = gate(request, deps)
        else:
            result = gates.run_metrics_gate(request, deps=deps)
    except _MEASURE_ERRORS as exc:
        return MetricsPass(error=f"metrics not measured ({type(exc).__name__})")
    except Exception as exc:  # MetricsGateUsageError: a bad [metrics] table or git ref
        return MetricsPass(error=f"metrics not measured: {clip(clean_text(str(exc)), 120)}")
    return MetricsPass(
        result=result,
        own=own,
        fail_on_breach=bool(result.config.fail_on_breach),
        gated=metrics_gated(ctx, root),
        tool_paths=tool_paths,
        setup=gates.tool_setup(request, deps),
        tools_missing=tuple(line for metric, line in missing if metric in own),
    )


# --- the metrics' tools through their pins -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProcToolRunner:
    """An evaluator ``ToolRunner`` over the dispatch's ``ProcPort`` that runs only pinned programs.

    ``pins`` maps each ``tool_paths`` value to its pin's argv, which replaces
    the metric's program name; any other program is never run. No call
    outlives ``deadline`` (the stage's, on ``clock.monotonic()``).

    Example::

        >>> pins = {"/v/bin/ruff": ("/v/bin/ruff",)}
        >>> ProcToolRunner(ctx.proc, pins, ctx.clock, deadline)(argv, b"", None, 10.0)
        ... # doctest: +SKIP
        (0, b'[]')
    """

    proc: ProcPort
    pins: Mapping[str, tuple[str, ...]]
    clock: Clock
    deadline: float

    def __call__(
        self, argv: Sequence[str], stdin: bytes, cwd: Path | None, timeout_s: float
    ) -> tuple[int, bytes]:
        from coding_agent_playbook.grading.tool_runner import ToolRunError

        program = argv[0] if argv else ""
        name = os.path.basename(program)
        pinned = self.pins.get(program)
        if pinned is None:
            raise ToolRunError(f"{name}: not pinned")
        left = self.deadline - self.clock.monotonic()
        if left <= 0:
            raise ToolRunError(f"{name}: no time left in the Stop stage")
        try:
            done = self.proc.run(
                [*pinned, *argv[1:]],
                timeout=min(timeout_s, left),
                input=stdin,
                cwd=None if cwd is None else str(cwd),
            )
        except (ProcTimeout, OSError) as exc:
            raise ToolRunError(f"{name}: {exc}") from None
        return done.returncode, done.stdout


def _pinned_tools(
    ctx: HandlerContext, git_dir: str | None, deadline: float, picked: Sequence[Metric]
) -> tuple[dict[str, str], ToolRunner | None, list[tuple[str, str]]]:
    """``(tool_paths, memoized runner, [(metric, why not measured)])`` from the picked pins."""
    from coding_agent_playbook.grading.tool_runner import MemoToolRunner

    tool_paths: dict[str, str] = {}
    pins: dict[str, tuple[str, ...]] = {}
    missing: list[tuple[str, str]] = []
    for metric in picked:
        if metric.tool is None:
            continue
        pin = _tool_pin(ctx, git_dir, metric.tool)
        if isinstance(pin, str):
            why = f"{metric.name} not measured: {metric.tool} pin {pin} (run playbook sync)"
            missing.append((metric.name, why))
            continue
        tool_paths[metric.tool] = pin[0]
        pins[pin[0]] = pin
    if not pins:
        return {}, None, missing
    runner = MemoToolRunner(ProcToolRunner(ctx.proc, pins, ctx.clock, deadline))
    return tool_paths, runner, missing


def _tool_pin(ctx: HandlerContext, git_dir: str | None, tool: str) -> tuple[str, ...] | str:
    """``tool``'s pinned argv, or ``"missing"`` / ``"changed"``; ruff shares the post-edit memo."""
    from coding_agent_playbook.hook_runtime.config.pin import read_machine_pins
    from coding_agent_playbook.hook_runtime.handlers._shared.ruff_pipeline import event_ruff_pin

    if git_dir is None:
        return "missing"
    if tool == "ruff":
        ruff = event_ruff_pin(ctx, git_dir)
        return ruff if isinstance(ruff, str) else ruff.argv

    def load() -> tuple[str, ...] | str:
        found = read_machine_pins(git_dir=git_dir)
        pin = None if found is None else found.tool(tool)
        if pin is None:
            return "missing"
        return pin.argv if pin.unchanged() else "changed"

    argv: tuple[str, ...] | str = ctx.memo.get_or_compute(("tool-pin", tool, git_dir), load)
    return argv


class PortBaselineGit:
    """``grading.baseline_git.BaselineGit`` over the hook's hardened ``GitPort``.

    Only ``HEAD`` blobs are read (the stages never run a suite, so no worktree).
    Example: ``PortBaselineGit(ctx.git).read_sources(root, "HEAD", ["src/a.py"])``.
    """

    def __init__(self, git: GitPort) -> None:
        self._git = git

    def is_commit(self, repo_root: Path, ref: str) -> bool:
        """Only ``HEAD`` on a born branch."""
        return ref == "HEAD" and self._git.head_tree() is not None

    def read_sources(self, repo_root: Path, ref: str, rel_paths: Sequence[str]) -> dict[str, bytes]:
        """Each path's ``HEAD`` blob; paths absent there are left out."""
        blobs = {rel: self._git.cat_head(rel) for rel in rel_paths}
        return {rel: blob for rel, blob in blobs.items() if blob is not None}

    def add_worktree(self, repo_root: Path, worktree: Path, ref: str) -> None:
        """Never needed: the hook never measures a suite baseline."""
        raise NotImplementedError("the metrics Stop stages never run a suite")

    def remove_worktree(self, repo_root: Path, worktree: Path) -> None:
        """Nothing to remove."""


# --- severity --------------------------------------------------------------------------------------


def block_policy(ctx: HandlerContext, hook_id: str) -> str:
    """``hook_id``'s own ``block`` key (:data:`BLOCK_AUTO` or :data:`BLOCK_ALWAYS`), from its record.

    Read from the hook's ``guard_config`` record, not ``ctx.config``: the
    coordinator, subagent-stop-verify and the stage run alone then agree. A
    missing record or value reads as :data:`BLOCK_AUTO`.
    Example: ``block_policy(ctx, "clean-code-metrics-nonregression") == "always"``.
    """
    record = ctx.cfg.hooks.get(hook_id)
    handler = None if record is None else record.handlers.get(EventName.STOP)
    if handler is None:
        return BLOCK_AUTO
    return HookConfig(handler.config, {"block": BLOCK_KEY}).choice("block", BLOCK_AUTO)


def metrics_gated(ctx: HandlerContext, root: str) -> bool:
    """The repo gates metrics in pre-commit: the rendered snapshot or a live scan says so.

    Example: ``metrics_gated(ctx, root)`` is ``True`` with ``playbook-metrics`` configured.
    """
    if METRICS_HOOK_IDS.intersection(ctx.cfg.tables.precommit_hook_ids()):
        return True
    return bool(METRICS_HOOK_IDS.intersection(_live_precommit_ids(root)))


def _live_precommit_ids(root: str) -> Iterable[str]:
    from coding_agent_playbook.hook_runtime.config.schema import (
        playbook_precommit_ids,
    )

    try:
        with open(os.path.join(root, _PRECOMMIT), "rb") as handle:
            data = handle.read(_PRECOMMIT_MAX_BYTES)
    except OSError:
        return ()
    return playbook_precommit_ids(data.decode("utf-8", errors="replace"))


# --- lines -----------------------------------------------------------------------------------------


def finding_line(finding: ScopeDetail, note: str = "") -> str:
    """``"src/x.py"::parse cyclomatic_complexity 6 -> 9 (regression; <note>)``.

    ``note`` is the fix note (:meth:`MetricsPass.fix_note`): what the scope
    needs to pass and how, so the agent knows how far to refactor.
    Example: ``finding_line(detail, "passes at <= 6: split branches into helpers")``.
    """
    path, _, scope = str(finding.scope_key).partition("::")
    where = f"{quote_data(path)}::{clip(clean_text(scope), 60)}" if scope else quote_data(path)
    return f"{where} {finding.evaluator} {_change(finding)} ({_joined(finding.kind, note)})"


def ruff_line(finding: ScopeDetail, family: str, detail: str, note: str = "") -> str:
    """``"src/x.py" ruff:quality 1 -> 2 (C901 parse; passes at <= 1)``; no ``detail``: the kind.

    Example: ``ruff_line(detail, "docstrings", "D103 load", "passes at <= 0")``.
    """
    path = str(finding.scope_key).partition("::")[0]
    why = _joined(detail or finding.kind, note)
    return f"{quote_data(path)} ruff:{family} {_change(finding)} ({why})"


def _joined(head: str, note: str) -> str:
    return f"{head}; {note}" if note else head


def _change(finding: ScopeDetail) -> str:
    if finding.baseline is not None:
        return f"{finding.baseline:g} -> {finding.value:g}"
    return f"= {finding.value:g}"


def capped(lines: Sequence[str], limit: int) -> list[str]:
    """At most ``limit`` lines, the last one ``+N more (<MORE_HINT>)`` when some were cut.

    Example::

        >>> capped(["a", "b", "c"], 2)
        ['a', '+2 more (playbook metrics --changed --baseline git:HEAD)']
    """
    if len(lines) <= limit:
        return list(lines)
    shown = max(limit - 1, 0)
    return [*lines[:shown], f"+{len(lines) - shown} more ({MORE_HINT})"]


def ruff_detail(found: MetricsPass, ctx: HandlerContext, root: str, rel: str, family: str) -> str:
    """The family's hits ``rel`` gained since ``HEAD``: ``"C901 parse"`` (``""`` when unknown).

    Re-asks the pass's ruff memo for the exact texts it measured, so no ruff
    runs twice. A hit names its ``def``/``class`` when it sits on one, else
    quotes ruff's message as data.
    Example: ``ruff_detail(found, ctx, root, "src/x.py", "docstrings") == "D103 load"``.
    """
    if found.setup is None or not found.tool_paths:
        return ""
    codes = found.setup.ruff.families.get(family, ())
    after = _family_hits(found, rel, _read_text(root, rel), codes)
    before = _family_hits(found, rel, _head_text(ctx, rel), codes)
    gained = list((Counter(after) - Counter(before)).elements())
    return ", ".join(f"{code} {where}" for code, where in gained[:_DETAIL_HITS])


def _family_hits(
    found: MetricsPass, rel: str, text: str | None, codes: Sequence[str]
) -> list[tuple[str, str]]:
    """``(code, where)`` of each hit of ``codes`` ruff reports for ``text`` (``[]`` when unknown)."""
    if text is None or found.setup is None:
        return []
    hits = _hits(found, rel, text)
    lines = text.splitlines()
    return [
        (hit.code, _where(hit, lines))
        for hit in hits
        if any(hit.code.startswith(code) for code in codes)
    ]


def _hits(found: MetricsPass, rel: str, text: str) -> tuple[RuffHit, ...]:
    from coding_agent_playbook.grading.static_metrics.ruff_violations import ruff_hits
    from coding_agent_playbook.grading.types import EvalContext

    assert found.setup is not None
    ctx = EvalContext(
        module=None, source=text, label=rel, tool_paths=found.tool_paths, tool_setup=found.setup
    )
    return ruff_hits(ctx) or ()


def _where(hit: RuffHit, lines: Sequence[str]) -> str:
    line = lines[hit.row - 1] if 0 < hit.row <= len(lines) else ""
    named = _DEF_LINE.match(line)
    return named.group(1) if named else quote_data(clean_text(hit.message), 60)


def _read_text(root: str, rel: str) -> str | None:
    try:
        return Path(root, rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _head_text(ctx: HandlerContext, rel: str) -> str | None:
    from coding_agent_playbook.grading.measuring import decode_source_blob

    blob = ctx.git.cat_head(rel)
    return None if blob is None else decode_source_blob(blob)
