"""clean-code-metrics-nonregression: the ``quality-metrics`` Stop stage (specs/prK-hook-pack.md §E.2).

Through ``playbook-hook simulate stop`` with the coordinator and this stage
hook on. The real ``evaluators.metrics_gate`` measures the worktree file; its
``git:HEAD`` baseline blob comes from ``FakeGit.head_blobs`` through the
hook's ``GitPort`` (no git binary), and a touched file is one ``FakeGit``
reports as changed. The ``run_tests`` spy drives the stage directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.hook_runtime._git_parse import AddedLine
from coding_agent_playbook.hook_runtime.config import (
    GUARD_CONFIG_REL,
    GuardConfig,
    parse_guard_config,
)
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.escape import EscapeHatches
from coding_agent_playbook.hook_runtime.event import CanonicalEvent, EventName, Harness
from coding_agent_playbook.hook_runtime.handlers.quality_metrics import QualityMetricsStage
from coding_agent_playbook.hook_runtime.registry import HandlerContext, load_builtin
from coding_agent_playbook.hook_runtime.session import SessionState
from coding_agent_playbook.hook_runtime.stop.stages import StopPlan
from tests.hook_runtime.fakes import FakeClock, FakeProc
from tests.hook_runtime.guard_repo import SESSION_ID
from tests.hooks.pack_repo import engine_hook
from tests.hooks.stop_kit import HEAD_TREE, changed_git, reason_lines, stop, stop_payload

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hook_runtime.fakes import FakeGit
    from tests.hooks.pack_repo import PackRepo

HOOK_ID: Final = "clean-code-metrics-nonregression"
GATE_ID: Final = "stop-ci-parity-gate"
SRC: Final = "src/x.py"
BASE: Final = "def parse(x):\n    return x\n"
GROWN: Final = (
    "def parse(x):\n"
    + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(8))
    + "    return x\n"
)
CC_LINE: Final = '"src/x.py"::parse cyclomatic_complexity 1 -> 9 (regression)'
METRICS_PRECOMMIT: Final = (
    "repos:\n  - repo: local\n    hooks:\n      - id: playbook-metrics\n"
    "        name: metrics\n        entry: playbook metrics --baseline git:HEAD\n"
)


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    pack_repo.write(SRC, GROWN)
    return pack_repo


def _install(repo: PackRepo, *, precommit: bool = False, metrics: str = "") -> None:
    if precommit:
        repo.write(".pre-commit-config.yaml", METRICS_PRECOMMIT)
    if metrics:
        repo.write(".coding-agent-playbook.toml", f"[metrics]\n{metrics}")
    repo.install_pack([GATE_ID, HOOK_ID])


def _touched(*paths: str, head: dict[str, bytes] | None = None) -> FakeGit:
    added = tuple(AddedLine(path, 1, "x") for path in paths)
    return changed_git(added=added, head_blobs=head if head is not None else {SRC: BASE.encode()})


def _stop(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], git: FakeGit, state: Path
) -> SimulateReport:
    return stop(repo, deps, stop_payload(repo, message="Done."), git=git, state=state)


def test_cc_growth_with_metrics_precommit_hook_blocks(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    _install(repo, precommit=True)

    report = _stop(repo, deps, _touched(SRC), tmp_path)

    assert report.trace.combined.decision is Decision.DENY
    assert reason_lines(report)[1:] == [f"[quality-metrics] {CC_LINE}"]


def test_cc_growth_without_hook_is_context_line(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    _install(repo)

    report = _stop(repo, deps, _touched(SRC), tmp_path)

    assert report.trace.combined.decision is Decision.NONE
    assert f"[quality-metrics] {CC_LINE}" in report.trace.combined.user_notes


def test_fail_on_breach_false_is_context_line(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    _install(repo, precommit=True, metrics="fail_on_breach = false\n")

    report = _stop(repo, deps, _touched(SRC), tmp_path)

    assert report.trace.combined.decision is Decision.NONE
    assert f"[quality-metrics] {CC_LINE}" in report.trace.combined.user_notes


def test_run_tests_true_config_never_runs_suite(repo: PackRepo) -> None:
    _install(repo, precommit=True, metrics='run_tests = true\ntest_cmd = ["pytest", "-x"]\n')
    requests: list[Any] = []

    def spy(request: Any, gate_deps: Any) -> Any:
        requests.append(request)
        from coding_agent_playbook.evaluators.metrics_gate import run_metrics_gate

        return run_metrics_gate(request, deps=gate_deps)

    stage = QualityMetricsStage(ctx=_ctx(repo, _touched(SRC)), root=str(repo.root), gate=spy)
    plan = _plan(repo, stage)

    result = stage.run(plan, stage.ctx.deadline)

    [request] = requests
    assert request.config.run_tests is True  # the repo asked for it ...
    assert (request.run_tests, request.test_cmd) == (False, None)  # ... the hook never runs it
    assert (request.baseline, result.status, result.lines) == ("git:HEAD", "red", (CC_LINE,))


def test_pathological_nesting_context_line_no_crash(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    _install(repo, precommit=True)
    repo.write("src/deep.py", "x = " + "(" * 400 + "1" + ")" * 400 + "\n")

    report = _stop(repo, deps, _touched("src/deep.py"), tmp_path)

    assert report.trace.combined.decision is Decision.NONE
    [note] = [n for n in report.trace.combined.user_notes if n.startswith("[quality-metrics]")]
    assert note.startswith('[quality-metrics] "src/deep.py" not measured: unparseable')


def test_eval_fixture_files_excluded(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    fixture = "pkg/eval_tasks/t1/setup/app.py"
    repo.write(fixture, GROWN)
    _install(repo, precommit=True)

    report = _stop(repo, deps, _touched(fixture, head={fixture: BASE.encode()}), tmp_path)

    assert report.trace.combined.decision is Decision.NONE


def test_no_py_touched_inactive(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    _install(repo, precommit=True)
    repo.write("README.md", "# x\n")

    report = _stop(repo, deps, _touched("README.md"), tmp_path)

    assert report.trace.combined.decision is Decision.NONE
    assert not [n for n in report.trace.combined.user_notes if "quality-metrics" in n]


def test_without_the_coordinator_the_stage_notes_alone(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    repo.install_pack([HOOK_ID])

    report = _stop(repo, deps, _touched(SRC), tmp_path)

    assert report.trace.combined.decision is Decision.NONE
    assert report.trace.combined.user_notes == (f"[quality-metrics] {CC_LINE}",)


def test_shipped_hook_matches_its_pack_row() -> None:
    fm = engine_hook(HOOK_ID).frontmatter
    assert fm.handler is not None and fm.handler.builtin is not None

    declaration = load_builtin(fm.handler.builtin)

    assert (fm.tier, tuple(fm.events), fm.on_error) == ("default", ("stop",), "open")
    assert fm.handler.config == {"stage": "quality-metrics"}
    assert set(fm.handler.config) <= set(declaration.config_schema)


def _ctx(repo: PackRepo, git: FakeGit) -> HandlerContext:
    cfg = parse_guard_config((repo.root / GUARD_CONFIG_REL).read_bytes(), platform="linux")
    assert isinstance(cfg, GuardConfig)
    clock = FakeClock()
    return HandlerContext(
        hook=cfg.hooks[HOOK_ID],
        config={"stage": "quality-metrics"},
        cfg=cfg,
        git=git,
        session=SessionState(repo.store(), SESSION_ID),
        ledger=None,
        proc=FakeProc(),
        clock=clock,
        deadline=clock.monotonic() + 3.0,
        hatches=EscapeHatches(),
        platform="linux",
    )


def _plan(repo: PackRepo, stage: QualityMetricsStage) -> StopPlan:
    root = str(repo.root)
    event = CanonicalEvent(
        name=EventName.STOP,
        harness=Harness.CLAUDE_CODE,
        session_id=SESSION_ID,
        cwd=root,
        project_dir=root,
    )
    return StopPlan(event=event, stages=(stage,), head_tree=HEAD_TREE)
