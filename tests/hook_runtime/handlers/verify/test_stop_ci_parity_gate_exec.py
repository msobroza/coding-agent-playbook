"""stop-ci-parity-gate's execution stages, ``typecheck`` and ``tests`` (specs/prK-hook-pack.md §E.2, §B.4).

Opted in through ``[hooks.stop-ci-parity-gate] stages``. They run repo code,
so the coordinator runs them only with a user-local approval of this exact
stage list (``FakeTrustStore.executions`` holds the digest sync would have
recorded). ``FakeStageRunner`` stands in for the pinned project interpreter.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.hook_runtime.config.guard_tables import GuardTables
from coding_agent_playbook.hook_runtime.config.schema import GUARD_CONFIG_REL
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.handlers._exec_stages import PLUGINS_CHANGED
from coding_agent_playbook.hook_runtime.stop.coordinator import GatePolicy
from coding_agent_playbook.hook_runtime.stop.runner import ToolRun
from tests.hook_runtime.fakes import FakeStageRunner, FakeTrustStore
from tests.hook_runtime.handlers.stop_kit import (
    NO_CLAIM,
    changed_git,
    py_edit,
    reason_lines,
    script_ruff,
    seed_ledger,
    session_of,
    stop,
    stop_payload,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
    from tests.hook_runtime.handlers.pack_repo import PackRepo

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "stop-ci-parity-gate"
MYPY: Final = ("-m", "mypy")
PYTEST: Final = ("-m", "pytest", "-q")
PLUGIN_PYPROJECT: Final = '[tool.mypy]\nstrict = true\nplugins = ["pydantic.mypy"]\n'


def _install(repo: PackRepo, **config: Any) -> FakeTrustStore:
    """The coordinator with ``config``; a trust store approving its rendered stage list."""
    repo.install_pack([HOOK_ID], per_hook={HOOK_ID: config})
    table = json.loads((repo.root / GUARD_CONFIG_REL).read_bytes())["stop_gate"]
    gate = GuardTables({"stop_gate": table}).stop_gate()
    return FakeTrustStore(executions={GatePolicy.from_gate(gate).stages_sha256()})


def _runner(**python: Any) -> FakeStageRunner:
    runner = FakeStageRunner()
    script_ruff(runner)
    runner.script("project_python", **python)
    return runner


def _python_args(runner: FakeStageRunner) -> list[tuple[str, ...]]:
    return [call.args for call in runner.calls if call.tool == "project_python"]


def test_untrusted_repo_mypy_pytest_never_invoked(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    _install(pack_repo, stages=["typecheck", "tests"])
    runner = _runner()

    report = stop(
        pack_repo, deps, stop_payload(pack_repo), git=changed_git(), state=tmp_path, runner=runner
    )

    assert _python_args(runner) == []
    assert report.trace.combined.decision is Decision.NONE
    assert report.trace.combined.user_notes == (
        "Playbook execution stages (typecheck, tests) skipped: not approved on this machine; "
        "ask the user to run playbook sync in a terminal.",
        "verified locally (lint); the CI matrix is authoritative",
    )


def test_trusted_stages_run_and_a_failure_blocks(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    trust = _install(pack_repo, stages=["typecheck", "tests"])
    failed = b"tests/test_a.py::test_x FAILED\nFAILED tests/test_a.py::test_x - assert 1 == 2\n"
    runner = _runner()
    runner.answer(
        "project_python",
        lambda call: (
            ToolRun("project_python", 0, b"Success: no issues found\n")
            if call.args == MYPY
            else ToolRun("project_python", 1, failed + b"1 failed in 0.1s\n")
        ),
    )

    report = stop(
        pack_repo,
        deps,
        stop_payload(pack_repo),
        git=changed_git(),
        state=tmp_path,
        runner=runner,
        trust=trust,
    )

    assert _python_args(runner) == [MYPY, PYTEST]
    assert report.trace.combined.decision is Decision.DENY
    assert reason_lines(report)[1:] == [
        "[tests] FAILED tests/test_a.py::test_x - assert 1 == 2",
        "[tests] 1 failed in 0.1s",
    ]


def test_trusted_mypy_plugin_added_vs_head_skips_mypy(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    trust = _install(pack_repo, stages=["typecheck"])
    pack_repo.write("pyproject.toml", PLUGIN_PYPROJECT)
    head = {"pyproject.toml": b"[tool.mypy]\nstrict = true\n"}
    runner = _runner()

    report = stop(
        pack_repo,
        deps,
        stop_payload(pack_repo),
        git=changed_git(head_blobs=head),
        state=tmp_path,
        runner=runner,
        trust=trust,
    )

    assert _python_args(runner) == []
    assert report.trace.combined.user_notes == (
        PLUGINS_CHANGED,
        "NOT verified: typecheck skipped (tool_changed)",
    )


def test_pytest_only_when_completion_claimed(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    trust = _install(pack_repo, stages=["tests"])
    quiet, claimed = _runner(), _runner()

    stop(
        pack_repo,
        deps,
        stop_payload(pack_repo, message=NO_CLAIM),
        git=changed_git(),
        state=tmp_path,
        runner=quiet,
        trust=trust,
    )
    stop(
        pack_repo,
        deps,
        stop_payload(pack_repo),
        git=changed_git("d" * 40),
        state=tmp_path,
        runner=claimed,
        trust=trust,
    )

    assert _python_args(quiet) == []
    assert _python_args(claimed) == [PYTEST]


@pytest.mark.parametrize(
    ("touched", "expected"),
    [
        (("tests/test_x.py",), (*PYTEST, "--no-cov", "tests/test_x.py")),
        ((), PYTEST),  # no test file edited: the whole suite, with its coverage gate
    ],
)
def test_touched_scope_passes_no_cov(
    pack_repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    tmp_path: Path,
    touched: tuple[str, ...],
    expected: tuple[str, ...],
) -> None:
    trust = _install(pack_repo, stages=["tests"], tests_scope="touched")
    pack_repo.write("tests/test_x.py", "def test_x() -> None: ...\n")
    payload = stop_payload(pack_repo)
    seed_ledger(tmp_path, session_of(payload), py_edit("src/x.py", *touched, cats=("py", "test")))
    runner = _runner()

    stop(pack_repo, deps, payload, git=changed_git(), state=tmp_path, runner=runner, trust=trust)

    assert _python_args(runner) == [expected]
