"""validate-then-sync-on-canonical-edit: report validate failures in-turn (specs/prK-hook-pack.md §E.1).

Every case runs the shipped ``HOOK.md`` through ``playbook-hook simulate
post_tool_use``. ``playbook validate`` / ``playbook sync`` are child processes
on the dispatcher's interpreter (OQ-27), so ``FakeProc`` scripts them by their
``-m coding_agent_playbook.cli <subcommand>`` argv and fails on anything else.
The ``vts_*`` goldens pin the parse, the filtered context and the wire.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.dispatch.event import EventName, Harness
from tests.hook_runtime.fakes import FakeClock, FakeProc
from tests.hook_runtime.handlers.pack_repo import PackRepo, playbook_calls, playbook_child
from tests.import_probe import PROBE_TIMEOUT_S, probe_env

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.diagnostics.simulate import SimulateReport
    from coding_agent_playbook.hook_runtime.proc import SubprocessProc
    from tests.hook_payloads import HookPayloadCase

    type Payload = Callable[[str, str, str], HookPayloadCase]

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "validate-then-sync-on-canonical-edit"
GLOSSARY: Final = "playbook/rules/glossary.md"
_RULE: Final = "---\nid: glossary\nname: Glossary\ndescription: Terms.\nscope: always\n---\n"
_FAIL_GLOSSARY: Final = f"FAIL {GLOSSARY}: link target 'missing.md' does not exist"
_VALIDATE_OUT: Final = (
    f"{_FAIL_GLOSSARY}\n"
    "FAIL playbook/prompts/triage.md: rule() names 'glossary', which is not in includes_rules\n"
    "FAIL playbook/rules/other.md: unrelated failure\n"
    "validation failed with 3 error(s)\n"
)


def _repo(pack_repo: PackRepo, *, auto_sync: bool = False) -> PackRepo:
    pack_repo.write(GLOSSARY, _RULE + "See [missing](missing.md).\n")
    pack_repo.write("playbook/hooks/guard-x/HOOK.md", "---\nid: guard-x\n---\n")
    pack_repo.write(".coding-agent-playbook.toml", '[project]\nname = "demo"\n')
    pack_repo.install_pack([HOOK_ID], auto_sync=auto_sync)
    return pack_repo


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    """A fixture repo with validate-then-sync on and ``[hooks] auto_sync`` off."""
    return _repo(pack_repo)


def _proc(*, validate: bytes = b"OK 3 artifacts validated\n", code: int = 0) -> FakeProc:
    proc = FakeProc()
    proc.script(playbook_child("validate"), stdout=validate, returncode=code)
    proc.script(playbook_child("sync"), stdout=b"Synced.\n")
    return proc


def _edit(repo: PackRepo, deps: RuntimeDeps, rel: str, state: Path | None = None) -> SimulateReport:
    tool_input = {"file_path": str(repo.root / rel), "old_string": "a", "new_string": "b"}
    payload = repo.tool_payload("Edit", tool_input, event=EventName.POST_TOOL_USE)
    return repo.simulate(payload, deps, event=EventName.POST_TOOL_USE, state=state)


def _golden(repo: PackRepo, deps: RuntimeDeps, case: HookPayloadCase) -> SimulateReport:
    report = repo.simulate(
        repo.relocate(case), deps, harness=Harness(case.harness), event=EventName.POST_TOOL_USE
    )
    combined, expected = report.trace.combined, case.expected["result"]
    assert (combined.decision.value, list(combined.context)) == (
        expected["decision"],
        expected.get("context", []),
    )
    assert report.trace.wire == case.wire()
    return report


@pytest.mark.parametrize(
    ("harness", "case"),
    [("claude_code", "vts_write_glossary_rule"), ("opencode", "vts_edit_glossary_rule")],
)
def test_broken_link_in_rule_reports_fail_line_writes_nothing(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    hook_payload: Payload,
    harness: str,
    case: str,
) -> None:
    proc = _proc(validate=_VALIDATE_OUT.encode(), code=1)

    report = _golden(repo, deps(proc=proc), hook_payload(harness, "post_tool_use", case))

    [item] = report.trace.combined.context
    assert _FAIL_GLOSSARY in item
    assert "includes_rules" in item  # the cross-reference the edit broke names its id
    assert "other.md" not in item
    assert playbook_calls(proc) == [("validate", "--repo-root", str(repo.root))]
    assert not (repo.root / ".claude").exists()


def test_child_runs_on_the_dispatcher_interpreter_under_the_hook_timeout(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    proc = _proc()

    _edit(repo, deps(proc=proc), GLOSSARY)

    [call] = proc.calls
    assert call.argv[:5] == (sys.executable, "-I", "-m", "coding_agent_playbook.cli", "validate")
    assert call.timeout <= 8.0 and call.cwd == str(repo.root)


def test_auto_sync_valid_edit_runs_sync_child(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo, proc = _repo(pack_repo, auto_sync=True), _proc()

    report = _edit(repo, deps(proc=proc), GLOSSARY)

    root = str(repo.root)
    assert playbook_calls(proc) == [
        ("validate", "--repo-root", root),
        ("sync", "--repo-root", root),
    ]
    assert report.trace.combined.decision is Decision.NONE


@pytest.mark.parametrize(
    "rel",
    [
        "playbook/hooks/guard-x/HOOK.md",
        ".coding-agent-playbook.toml",
        # The engine checkout's own hooks live in its catalog (SPEC v0.19).
        "catalog/core/hooks/protect/guard-x/HOOK.md",
        "catalog/plugins/demo/hooks/guard-x/HOOK.md",
    ],
)
def test_auto_sync_hooks_table_edit_advises_instead(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], rel: str
) -> None:
    repo, proc = _repo(pack_repo, auto_sync=True), _proc()

    report = _edit(repo, deps(proc=proc), rel)

    assert playbook_calls(proc) == [("validate", "--repo-root", str(repo.root))]
    [item] = report.trace.combined.context
    assert "ask the user to run playbook sync" in item


def test_auto_sync_never_runs_while_validate_fails_elsewhere(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo = _repo(pack_repo, auto_sync=True)
    proc = _proc(validate=b"FAIL playbook/rules/other.md: broken\n", code=1)

    report = _edit(repo, deps(proc=proc), GLOSSARY)

    assert [call[0] for call in playbook_calls(proc)] == ["validate"]
    assert "ask the user to run playbook sync" in report.trace.combined.context[0]


def test_two_edits_within_2s_one_validate_call(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    proc, clock = _proc(), FakeClock()
    shared = deps(proc=proc, clock=clock)
    state = tmp_path / "state"

    _edit(repo, shared, GLOSSARY, state)
    clock.advance(1.5)
    _edit(repo, shared, GLOSSARY, state)
    clock.advance(1.0)
    _edit(repo, shared, GLOSSARY, state)

    assert len(playbook_calls(proc)) == 2


def test_output_filtered_to_edited_file_capped_15(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    lines = [f"FAIL {GLOSSARY}: problem {n}" for n in range(20)]
    noise = ["FAIL playbook/rules/zeta.md: elsewhere", "validation failed with 21 error(s)"]
    proc = _proc(validate="\n".join([*lines, *noise]).encode(), code=1)

    [item] = _edit(repo, deps(proc=proc), GLOSSARY).trace.combined.context

    body = item.splitlines()[1:]
    assert len(body) == 15
    assert body[:14] == [json.dumps(line) for line in lines[:14]]
    assert body[-1].startswith("… 6 more")
    assert "zeta" not in item


@pytest.mark.parametrize(
    "rel",
    [
        "src/acme_rules/resources/prompts/triage.md",
        # The engine checkout's prompts live in its catalog (SPEC v0.19).
        "catalog/core/prompts/triage.md",
        "catalog/plugins/demo/prompts/triage.md",
    ],
)
def test_engine_resource_edit_is_canonical(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], rel: str
) -> None:
    repo.write(rel, "---\nid: triage\n---\nBody.\n")
    proc = _proc(validate=f"FAIL {rel}: unknown applies_if fact 'has_gpu'\n".encode(), code=1)

    report = _edit(repo, deps(proc=proc), rel)

    assert "has_gpu" in report.trace.combined.context[0]


def test_non_canonical_edit_runs_nothing(repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    repo.write("src/app.py", "x = 1\n")

    report = _edit(repo, deps(), "src/app.py")  # FakeProc() would fail on any child

    assert report.trace.combined.decision is Decision.NONE


def test_child_timeout_fails_open_one_note(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    proc, clock = FakeProc(), FakeClock()
    proc.script(playbook_child("validate"), timeout=True)
    shared, state = deps(proc=proc, clock=clock), tmp_path / "state"

    first = _edit(repo, shared, GLOSSARY, state)
    clock.advance(5)
    second = _edit(repo, shared, GLOSSARY, state)

    assert first.trace.combined.decision is Decision.NONE
    [note] = first.trace.combined.user_notes
    assert "playbook validate timed out" in note
    assert second.trace.combined.user_notes == ()
    assert len(proc.calls) == 2


_DISPATCH_SCRIPT: Final = """
import io, json, sys
from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
from coding_agent_playbook.hook_runtime.dispatch.run import run_event
from coding_agent_playbook.hook_runtime.dispatch.event import EventName, Harness
from coding_agent_playbook.hook_runtime.proc import ProcResult

class StubProc:
    def __init__(self):
        self.calls = []
    def run(self, argv, *, timeout, env=None, input=None, cwd=None):
        self.calls.append(list(argv[4:5]))
        return ProcResult(tuple(argv), 1, sys.argv[2].encode(), b"")
    def which(self, name, *, path=None):
        return None

proc = StubProc()
deps = RuntimeDeps(env={"CLAUDE_PROJECT_DIR": sys.argv[1]}, proc=proc,
                   out=io.StringIO(), err=io.StringIO())
wire = run_event(EventName.POST_TOOL_USE, Harness.CLAUDE_CODE, sys.stdin.buffer.read(), deps)
print(json.dumps({"jinja2": "jinja2" in sys.modules, "calls": proc.calls, "out": wire.stdout}))
"""


def test_jinja2_absent_from_dispatcher_after_source_changed_dispatch(
    repo: PackRepo, real_proc: SubprocessProc
) -> None:
    """L3 / Track K5 "done when": a fresh ``-I`` interpreter runs the real pipeline."""
    tool_input = {"file_path": str(repo.root / GLOSSARY), "old_string": "a", "new_string": "b"}
    payload = repo.tool_payload("Edit", tool_input, event=EventName.POST_TOOL_USE)
    argv = [sys.executable, "-I", "-c", _DISPATCH_SCRIPT, str(repo.root), _FAIL_GLOSSARY]

    result = real_proc.run(argv, timeout=PROBE_TIMEOUT_S, env=probe_env(), input=payload)

    assert result.returncode == 0, result.stderr.decode()
    seen = json.loads(result.stdout)
    assert seen["calls"] == [["validate"]]
    assert "missing.md" in seen["out"]
    assert seen["jinja2"] is False


def test_auto_sync_failure_asks_the_user(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo, proc = _repo(pack_repo, auto_sync=True), FakeProc()
    proc.script(playbook_child("validate"), stdout=b"OK 3 artifacts validated\n")
    proc.script(playbook_child("sync"), returncode=1, stderr=b"error: boom\n")

    [item] = _edit(repo, deps(proc=proc), GLOSSARY).trace.combined.context

    assert item.startswith("playbook sync failed (exit 1)")
    assert "ask the user to run playbook sync" in item
