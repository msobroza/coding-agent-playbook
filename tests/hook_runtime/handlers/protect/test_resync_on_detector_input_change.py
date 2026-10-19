"""resync-on-detector-input-change: surface newly activated rules mid-session (specs/prK-hook-pack.md §E.1).

The fixture repo is "synced" the way ``playbook sync`` renders it: ``facts``
from the real ``detect()`` and ``applicability`` rows from the engine's real
rules and prompts (plus a repo-local Docker rule). Each case then edits a
detector input and dispatches ``post_tool_use`` through ``playbook-hook
simulate``. ``detect`` is spied on its module attribute: the cheap ``tomllib``
comparison must decide alone whenever the dependency names did not change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.artifacts.rule import Rule
from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.detector import facts as detector
from coding_agent_playbook.guard_config import DetectInputs, applicability_rows
from coding_agent_playbook.hook_policy import EffectiveHooks
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.event import EventName, Harness
from coding_agent_playbook.hook_runtime.handlers import resync_on_detector_input_change as resync
from coding_agent_playbook.hook_runtime.handlers._detector_inputs import detector_triggers
from tests.hook_runtime.fakes import FakeProc
from tests.hook_runtime.handlers.pack_repo import PackRepo, playbook_calls, playbook_child

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.detector.facts import Facts
    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.event import ToolCall
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hook_payloads import HookPayloadCase

    type Payload = Callable[[str, str, str], HookPayloadCase]

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "resync-on-detector-input-change"
ML_RULE: Final = "ml-serialization-security"
_BASE: Final = '[project]\nname = "demo"\ndependencies = ["fastapi>=0.110"]\n'
_WITH_TORCH: Final = '[project]\nname = "demo"\ndependencies = ["fastapi>=0.110", "torch>=2"]\n'
_DOCKER_RULE: Final = (
    "---\nid: docker-hygiene\nname: Docker hygiene\ndescription: Pin base images.\n"
    "scope: always\napplies_if:\n  has_dockerfile: true\n---\nPin base images.\n"
)


class DetectSpy:
    """Counts ``detector.detect`` calls and forwards to the real one."""

    def __init__(self) -> None:
        self.calls = 0
        self._real = detector.detect

    def __call__(self, repo_root: Path) -> Facts:
        self.calls += 1
        return self._real(repo_root)


class TriggerSpy:
    """Counts the handler's ``detector_triggers`` calls: the handler body ran."""

    def __init__(self) -> None:
        self.calls = 0
        self._real = detector_triggers

    def __call__(self, tool: ToolCall) -> frozenset[str]:
        self.calls += 1
        return self._real(tool)


@pytest.fixture
def trigger_spy(monkeypatch: pytest.MonkeyPatch) -> TriggerSpy:
    spy = TriggerSpy()
    monkeypatch.setattr(resync, "detector_triggers", spy)
    return spy


@pytest.fixture
def detect_spy(monkeypatch: pytest.MonkeyPatch) -> DetectSpy:
    spy = DetectSpy()
    monkeypatch.setattr(detector, "detect", spy)
    return spy


def _synced(repo: PackRepo, pyproject: str = _BASE, *, auto_sync: bool = False) -> PackRepo:
    """Write ``pyproject`` and render facts + rows exactly as sync would from it."""
    repo.write("pyproject.toml", pyproject)
    docker_rule = repo.write("playbook/rules/docker-hygiene.md", _DOCKER_RULE)
    source = FileSystemArtifactSource(repo_root=repo.root)
    rules = [*source.list_rules(), Rule.from_markdown(docker_rule, "<repo-local>")]
    facts = detector.detect(repo.root)
    rows = applicability_rows(
        rules=rules,
        prompts=source.list_prompts(),
        hooks=[],
        view=EffectiveHooks([], [], []),
        facts=facts,
        repo_root=repo.root,
    )
    repo.install_pack([HOOK_ID], auto_sync=auto_sync, detect=DetectInputs(facts, rows))
    return repo


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    return _synced(pack_repo)


def _post(
    repo: PackRepo,
    deps: RuntimeDeps,
    tool: str,
    tool_input: dict[str, str],
    *,
    event: EventName = EventName.POST_TOOL_USE,
    state: Path | None = None,
) -> SimulateReport:
    payload = repo.tool_payload(tool, tool_input, event=event)
    return repo.simulate(payload, deps, event=event, state=state)


def _edit_pyproject(
    repo: PackRepo, deps: RuntimeDeps, text: str, state: Path | None = None
) -> SimulateReport:
    repo.write("pyproject.toml", text)
    tool_input = {
        "file_path": str(repo.root / "pyproject.toml"),
        "old_string": "a",
        "new_string": "b",
    }
    return _post(repo, deps, "Edit", tool_input, state=state)


@pytest.mark.parametrize(
    ("harness", "case"),
    [("claude_code", "rdc_edit_pyproject_add_torch"), ("opencode", "rdc_edit_pyproject_add_torch")],
)
def test_adding_torch_names_ml_serialization_security(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    hook_payload: Payload,
    detect_spy: DetectSpy,
    harness: str,
    case: str,
) -> None:
    repo.write("pyproject.toml", _WITH_TORCH)
    golden = hook_payload(harness, "post_tool_use", case)

    report = repo.simulate(
        repo.relocate(golden), deps(), harness=Harness(harness), event=EventName.POST_TOOL_USE
    )

    combined = report.trace.combined
    assert (combined.decision.value, list(combined.context)) == (
        golden.expected["result"]["decision"],
        golden.expected["result"]["context"],
    )
    assert report.trace.wire == golden.wire()
    [item] = combined.context
    assert f'rule "{ML_RULE}"' in item and 'prompt "security-review"' in item
    assert "ask the user to run playbook validate && playbook sync" in item
    assert detect_spy.calls == 1


def test_tool_ruff_only_edit_never_calls_detect(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], detect_spy: DetectSpy
) -> None:
    report = _edit_pyproject(repo, deps(), _BASE + "\n[tool.ruff]\nline-length = 100\n")

    assert report.trace.combined.decision is Decision.NONE
    assert detect_spy.calls == 0


def test_removing_torch_with_auto_sync_reports_never_syncs(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo = _synced(pack_repo, _WITH_TORCH, auto_sync=True)
    proc = FakeProc()  # any child (a sync) fails the test

    report = _edit_pyproject(repo, deps(proc=proc), _BASE)

    [item] = report.trace.combined.context
    assert item.startswith("This change would turn off: ")
    assert f'rule "{ML_RULE}"' in item.splitlines()[0]
    assert "add-only" in item and "ask the user" in item
    assert proc.calls == []


def test_auto_sync_applies_an_add_only_change(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo = _synced(pack_repo, auto_sync=True)
    proc = FakeProc()
    proc.script(playbook_child("sync"), stdout=b"Synced.\n")

    report = _edit_pyproject(repo, deps(proc=proc), _WITH_TORCH)

    assert playbook_calls(proc) == [("sync", "--repo-root", str(repo.root))]
    [item] = report.trace.combined.context
    assert ML_RULE in item and "playbook sync ran ([hooks] auto_sync)" in item


def test_failed_uv_add_on_post_tool_use_failure_silent(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], detect_spy: DetectSpy
) -> None:
    repo.write("pyproject.toml", _WITH_TORCH)

    failed = _post(
        repo,
        deps(),
        "Bash",
        {"command": "uv add torch"},
        event=EventName.POST_TOOL_USE_FAILURE,
    )

    assert failed.trace.combined.decision is Decision.NONE
    assert failed.trace.wire.stdout == ""
    assert detect_spy.calls == 0


def test_successful_uv_add_reports(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], detect_spy: DetectSpy
) -> None:
    repo.write("pyproject.toml", _WITH_TORCH)

    report = _post(repo, deps(), "Bash", {"command": "uv add 'torch>=2'"})

    assert ML_RULE in report.trace.combined.context[0]
    assert detect_spy.calls == 1


@pytest.mark.parametrize("command", ["ls -la", "pytest -q", "git status", "python -c 'import x'"])
def test_non_install_command_never_runs_the_handler(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], trigger_spy: TriggerSpy, command: str
) -> None:
    """Finding #7: the argv0 prefilter skips every shell call that runs no install program."""
    repo.write("pyproject.toml", _WITH_TORCH)  # a change the handler would report if it ran

    report = _post(repo, deps(), "Bash", {"command": command})

    assert report.trace.combined.decision is Decision.NONE
    assert trigger_spy.calls == 0


@pytest.mark.parametrize(
    "command", ["uv add torch", "cd sub && poetry add torch", "pip3 install x"]
)
def test_install_command_passes_the_prefilter(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], trigger_spy: TriggerSpy, command: str
) -> None:
    _post(repo, deps(), "Bash", {"command": command})

    assert trigger_spy.calls == 1


def test_newly_active_id_injected_once_per_session(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    state = tmp_path / "state"

    first = _edit_pyproject(repo, deps(), _WITH_TORCH, state)
    second = _edit_pyproject(repo, deps(), _WITH_TORCH + "# again\n", state)

    assert ML_RULE in first.trace.combined.context[0]
    assert second.trace.combined.decision is Decision.NONE


def test_new_dockerfile_flips_the_presence_flag(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo.write("Dockerfile", "FROM python:3.12\n")
    tool_input = {"file_path": str(repo.root / "Dockerfile"), "content": "FROM python:3.12\n"}

    report = _post(repo, deps(), "Write", tool_input)

    [item] = report.trace.combined.context
    assert 'rule "docker-hygiene" (source "<repo-local>")' in item
    assert ML_RULE not in item


def test_requirements_edit_is_inert(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], detect_spy: DetectSpy
) -> None:
    """The detector reads no requirements file, so the comparison stays on pyproject."""
    repo.write("requirements.txt", "torch>=2\n")
    tool_input = {"file_path": str(repo.root / "requirements.txt"), "content": "torch>=2\n"}

    report = _post(repo, deps(), "Write", tool_input)

    assert report.trace.combined.decision is Decision.NONE
    assert detect_spy.calls == 0


def test_malformed_pyproject_mid_edit_is_silent(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], detect_spy: DetectSpy
) -> None:
    report = _edit_pyproject(repo, deps(), '[project]\ndependencies = ["torch"\n')

    assert report.trace.combined.decision is Decision.NONE
    assert detect_spy.calls == 0


def test_auto_sync_failure_falls_back_to_asking(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo, proc = _synced(pack_repo, auto_sync=True), FakeProc()
    proc.script(playbook_child("sync"), timeout=True)

    [item] = _edit_pyproject(repo, deps(proc=proc), _WITH_TORCH).trace.combined.context

    assert "playbook sync did not complete; ask the user" in item
