"""guard-eval-fixtures: protect frozen eval ``setup/`` fixtures (specs/prK-hook-pack.md §E.1).

The fixture repo mirrors the engine checkout: a committed task under
``src/coding_agent_playbook/resources/eval_tasks/<id>/`` (``FakeGit`` answers
``cat_head(task.toml)``). Session evidence (the task created this session, an
approved earlier write) comes from the real ledger, written by real
``post_tool_use`` dispatches into a shared ``--state`` dir.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.dispatch.event import EventName, Harness
from coding_agent_playbook.hook_runtime.dispatch.policy import UNATTENDED_ENV_VAR
from coding_agent_playbook.hook_runtime.git.safe_git import GitError
from tests.hook_runtime.fakes import FakeGit

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.diagnostics.simulate import SimulateReport
    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
    from tests.hook_payloads import HookPayloadCase
    from tests.hook_runtime.handlers.pack_repo import PackRepo

    type Payload = Callable[[str, str, str], HookPayloadCase]

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "guard-eval-fixtures"
TASK: Final = "src/coding_agent_playbook/resources/eval_tasks/find-injected-vuln-pytorch-deserial"
LOADER: Final = f"{TASK}/setup/app/loader.py"
FROZEN: Final = "setup/ is the frozen starting state"
_COMMITTED: Final = {f"{TASK}/task.toml": b'id = "find-injected-vuln-pytorch-deserial"\n'}


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    pack_repo.write(f"{TASK}/task.toml", 'id = "find-injected-vuln-pytorch-deserial"\n')
    pack_repo.write(LOADER, "import torch\n\ndef load(p):\n    return torch.load(p)\n")
    pack_repo.write(f"{TASK}/setup/app/registry.py", "MODELS = {}\n")
    pack_repo.install_pack([HOOK_ID])
    return pack_repo


def _committed(deps: Callable[..., RuntimeDeps], **overrides: object) -> RuntimeDeps:
    return deps(git=FakeGit(head_blobs=dict(_COMMITTED)), **overrides)


def _edit(
    repo: PackRepo,
    deps: RuntimeDeps,
    rel: str = LOADER,
    *,
    event: EventName = EventName.PRE_TOOL_USE,
    state: Path | None = None,
    env: dict[str, str] | None = None,
) -> SimulateReport:
    tool_input = {"file_path": str(repo.root / rel), "old_string": "a", "new_string": "b"}
    payload = repo.tool_payload("Edit", tool_input, event=event)
    return repo.simulate(payload, deps, event=event, state=state, env=env)


def _bash(repo: PackRepo, deps: RuntimeDeps, command: str) -> SimulateReport:
    return repo.simulate(repo.tool_payload("Bash", {"command": command}), deps)


def _decision(report: SimulateReport) -> Decision:
    return report.trace.combined.decision


@pytest.mark.parametrize(
    ("harness", "case"),
    [("claude_code", "gef_edit_pytorch_loader"), ("opencode", "gef_edit_pytorch_loader")],
)
def test_frozen_pytorch_deserial_fixture_edit_asks(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    hook_payload: Payload,
    harness: str,
    case: str,
) -> None:
    golden = hook_payload(harness, "pre_tool_use", case)

    report = repo.simulate(repo.relocate(golden), _committed(deps), harness=Harness(harness))

    combined, expected = report.trace.combined, golden.expected["result"]
    assert (combined.decision.value, combined.reason) == (expected["decision"], expected["reason"])
    assert report.trace.wire == golden.wire()
    assert FROZEN in combined.reason
    # OpenCode has no ask primitive: the shim's deny carries the same reason.
    assert combined.decision is (Decision.ASK if harness == "claude_code" else Decision.DENY)


def test_task_created_this_session_passes(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    untracked = _edit(repo, deps(git=FakeGit()))
    state = tmp_path / "state"
    toml = {"file_path": str(repo.root / TASK / "task.toml"), "content": 'id = "x"\n'}
    created = repo.tool_payload("Write", toml, event=EventName.POST_TOOL_USE)
    repo.simulate(created, _committed(deps), event=EventName.POST_TOOL_USE, state=state)

    after = _edit(repo, _committed(deps), state=state)

    assert _decision(untracked) is Decision.NONE  # task.toml absent at HEAD: being authored
    assert _decision(after) is Decision.NONE  # tracked, but written this session


def test_second_edit_after_approval_passes(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    state = tmp_path / "state"

    first = _edit(repo, _committed(deps), state=state)
    _edit(repo, _committed(deps), event=EventName.POST_TOOL_USE, state=state)  # the user said yes
    second = _edit(repo, _committed(deps), f"{TASK}/setup/app/registry.py", state=state)
    other_task = _edit(repo, _committed(deps), "pkg/eval_tasks/other/setup/x.py", state=state)

    assert _decision(first) is Decision.ASK
    assert _decision(second) is Decision.NONE
    assert _decision(other_task) is Decision.NONE  # no task.toml at HEAD there: authoring


def test_headless_denies(repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    report = _edit(repo, _committed(deps), env={UNATTENDED_ENV_VAR: "1"})

    assert _decision(report) is Decision.DENY
    assert FROZEN in report.trace.combined.reason


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (f"ruff format {TASK}/setup/app", Decision.ASK),
        (f"uv run ruff check --fix {TASK}/setup", Decision.ASK),
        (f"black {LOADER}", Decision.ASK),
        (f"isort {LOADER}", Decision.ASK),
        (f"sed -i s/torch.load/safe_load/ {LOADER}", Decision.ASK),
        (f"ruff check {LOADER}", Decision.NONE),
        ("ruff format src/app.py", Decision.NONE),
    ],
)
def test_ruff_format_on_setup_dir_asks(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], command: str, expected: Decision
) -> None:
    assert _decision(_bash(repo, _committed(deps), command)) is expected


def test_internal_error_fails_open(repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    broken = deps(git=FakeGit(errors={"cat_head": GitError("git cat-file failed")}))

    report = _edit(repo, broken)

    assert _decision(report) is Decision.NONE
    assert report.to_json()["decisions"][0]["degraded"] is True
