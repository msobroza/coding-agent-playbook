"""prompt-write-scope-guard and the active-prompt record (specs/prK-hook-pack.md §E.3, OQ-45).

The engine's five scoped prompts are rendered into the guard's ``scopes``
through the real ``render_guard_config``. Each test drives the exact dispatch
pipeline: a ``user_prompt_submit`` (or a model-invoked ``Skill`` call) records
the active prompt in a shared ``--state`` dir, then a ``pre_tool_use`` is judged
against its scope.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.hook_runtime.active_prompt import (
    ActivePrompt,
    active_prompt_document,
    read_active_prompt,
    record_active_prompt,
)
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.handlers.prompt_scope import (
    READ_ONLY_REASON,
    TESTS_ONLY_REASON,
)
from coding_agent_playbook.hook_runtime.registry import load_builtin
from coding_agent_playbook.hook_runtime.state import STATE_DIR_NAME, StateStore
from tests.hook_runtime.guard_repo import SESSION_ID, hook_record
from tests.hooks.pack_repo import engine_hook, engine_hook_paths, engine_prompts

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hook_payloads import HookPayloadCase
    from tests.hooks.pack_repo import PackRepo

    type Payload = Callable[[str, str, str], HookPayloadCase]

HOOK_ID: Final = "prompt-write-scope-guard"
GOLDEN_SESSION: Final = "9b2c4e1a-7f3d-4a8e-b1c2-3d4e5f6a7b8c"


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    pack_repo.write("src/app.py", "import pickle\n")
    pack_repo.install_pack([HOOK_ID], prompts=engine_prompts())
    return pack_repo


@pytest.fixture
def state(tmp_path: Path) -> Path:
    return tmp_path / "state"


def _prompt(repo: PackRepo, deps: RuntimeDeps, state: Path, text: str) -> SimulateReport:
    payload = repo.payload(EventName.USER_PROMPT_SUBMIT, prompt=text)
    return repo.simulate(payload, deps, event=EventName.USER_PROMPT_SUBMIT, state=state)


def _tool(
    repo: PackRepo, deps: RuntimeDeps, state: Path, tool: str, tool_input: dict[str, Any]
) -> SimulateReport:
    return repo.simulate(repo.tool_payload(tool, tool_input), deps, state=state)


def _edit(repo: PackRepo, deps: RuntimeDeps, state: Path, rel: str = "src/app.py") -> Decision:
    edit = {"file_path": str(repo.root / rel), "old_string": "a", "new_string": "b"}
    return _tool(repo, deps, state, "Edit", edit).trace.combined.decision


def _golden(
    repo: PackRepo, deps: RuntimeDeps, state: Path, case: HookPayloadCase
) -> SimulateReport:
    return repo.simulate(repo.relocate(case), deps, event=case.event_name, state=state)


def _stored(state: Path, session_id: str = SESSION_ID) -> ActivePrompt | None:
    return read_active_prompt(StateStore(state / STATE_DIR_NAME), session_id)


def test_security_review_then_edit_denied(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], hook_payload: Payload, state: Path
) -> None:
    prompt = hook_payload("claude_code", "user_prompt_submit", "pwsg_security_review")
    edit = hook_payload("claude_code", "pre_tool_use", "pwsg_edit_app")

    submitted = _golden(repo, deps(), state, prompt)
    report = _golden(repo, deps(), state, edit)

    combined, expected = report.trace.combined, edit.expected["result"]
    assert submitted.trace.wire == prompt.wire()  # the record is silent
    assert _stored(state, GOLDEN_SESSION) == ActivePrompt("security-review", "prompt", "pr_21")
    assert (combined.decision.value, combined.reason) == (expected["decision"], expected["reason"])
    assert report.trace.wire == edit.wire()


def test_model_invoked_skill_review_then_edit_denied(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], hook_payload: Payload, state: Path
) -> None:
    skill = hook_payload("claude_code", "pre_tool_use", "pwsg_skill_review")
    edit = hook_payload("claude_code", "pre_tool_use", "pwsg_edit_app")

    invoked = _golden(repo, deps(), state, skill)
    report = _golden(repo, deps(), state, edit)

    assert invoked.trace.wire == skill.wire()  # Skill itself is no write
    assert _stored(state, GOLDEN_SESSION) == ActivePrompt("review", "skill", "pr_23")
    assert report.trace.combined.decision is Decision.DENY
    assert report.trace.combined.reason == f"/review is read-only: {READ_ONLY_REASON}"


@pytest.mark.parametrize(
    ("command", "expected", "named"),
    [
        ("sed -i s/x/y/ src/app.py", Decision.ASK, '"src/app.py"'),
        ("echo x > src/out.txt", Decision.ASK, '"src/out.txt"'),
        ("cp /tmp/patched.py src/app.py", Decision.ASK, '"src/app.py"'),
        ("git apply fix.diff", Decision.ASK, "changes the repository"),
        ("git commit -am wip", Decision.ASK, "changes the repository"),
        ("patch -p1 < fix.diff", Decision.ASK, "changes the repository"),
        ("grep -rn pickle src > /tmp/hits.txt", Decision.NONE, ""),
        ("ls -la src", Decision.NONE, ""),
    ],
)
def test_sed_i_under_read_only_asks(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    state: Path,
    command: str,
    expected: Decision,
    named: str,
) -> None:
    _prompt(repo, deps(), state, "/review src/app.py")

    report = _tool(repo, deps(), state, "Bash", {"command": command})

    assert report.trace.combined.decision is expected
    if expected is Decision.ASK:
        assert report.trace.combined.reason.startswith("/review is read-only and this command")
        assert named in report.trace.combined.reason


def test_next_prompt_clears_scope(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path
) -> None:
    _prompt(repo, deps(), state, "/security-review src/app.py")
    during = _edit(repo, deps(), state)

    _prompt(repo, deps(), state, "fix it")
    after = _edit(repo, deps(), state)

    assert during is Decision.DENY
    assert after is Decision.NONE
    assert _stored(state) is None
    assert not (state / STATE_DIR_NAME / active_prompt_document(SESSION_ID)).exists()


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("tests/test_app.py", Decision.NONE),
        ("tests/unit/conftest.py", Decision.NONE),
        ("conftest.py", Decision.NONE),
        ("src/app.py", Decision.ASK),
    ],
)
def test_generate_tests_write_in_globs_none_outside_asks(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path, rel: str, expected: Decision
) -> None:
    _prompt(repo, deps(), state, "/generate-tests src/app.py")

    report = _tool(repo, deps(), state, "Write", {"file_path": str(repo.root / rel), "content": ""})

    assert report.trace.combined.decision is expected
    if expected is Decision.ASK:
        reason = report.trace.combined.reason
        assert reason.startswith("/generate-tests writes only tests/**, **/conftest.py; this")
        assert '"src/app.py"' in reason
        assert reason.endswith(TESTS_ONLY_REASON)


def test_read_only_scratch_file_outside_repo_passes(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path, tmp_path: Path
) -> None:
    _prompt(repo, deps(), state, "/explain src/app.py")

    report = _tool(repo, deps(), state, "Write", {"file_path": str(tmp_path / "notes.md")})

    assert report.trace.combined.decision is Decision.NONE


@pytest.mark.parametrize(
    "text",
    [
        "<command-foo>/review</command-foo>",
        "please /review src/app.py",
        "/refactor src/app.py",  # a playbook prompt without a write scope
        "/unknown-command",
    ],
)
def test_unrecognized_wrapper_records_no_scope(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path, text: str
) -> None:
    _prompt(repo, deps(), state, text)

    assert _stored(state) is None
    assert _edit(repo, deps(), state) is Decision.NONE


def test_command_wrapper_records_scope(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], hook_payload: Payload, state: Path
) -> None:
    wrapped = hook_payload("claude_code", "user_prompt_submit", "pwsg_command_wrapper")

    _golden(repo, deps(), state, wrapped)

    assert _stored(state, GOLDEN_SESSION) == ActivePrompt("review", "prompt", "pr_22")


class CountingStore(StateStore):
    """A real ``StateStore`` that counts document reads (the one-stat spy)."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.reads: list[str] = []

    def read_json(self, rel: str) -> dict[str, Any]:
        self.reads.append(rel)
        return super().read_json(rel)


def test_no_active_scope_costs_one_stat(tmp_path: Path) -> None:
    store = CountingStore(tmp_path / STATE_DIR_NAME)

    absent = read_active_prompt(store, SESSION_ID)
    record_active_prompt(store, SESSION_ID, ActivePrompt("review", "prompt"))
    present = read_active_prompt(store, SESSION_ID)

    assert absent is None
    assert present == ActivePrompt("review", "prompt")
    assert store.reads == [active_prompt_document(SESSION_ID)]  # only once a record exists


def test_record_kept_while_only_the_output_contract_consumer_is_enabled(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path
) -> None:
    """OQ-45: the record is a dispatcher branch, so the guard being off never disables it."""
    contract = hook_record("prompt-output-contract-on-stop", events=["stop"], on_error="open")
    verdict = r"(?im)^\W*(approve|request changes)\W*$"
    pack_repo.install(contract, prompts={"review": {"id": "review", "output_contract": [verdict]}})

    _prompt(pack_repo, deps(), state, "/review src/app.py")

    assert _stored(state) == ActivePrompt("review", "prompt")


def test_hook_md_matches_its_pack_row_and_handler(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """§E.0.6 row: default, pre_tool_use, deny/ask, guard-class; Claude only; Skill in the matcher."""
    fm = engine_hook(HOOK_ID).frontmatter
    declaration = load_builtin("prompt_scope_guard")

    rc = _validate.run(argparse.Namespace(repo_root=str(tmp_path)))

    assert (fm.tier, fm.events, fm.decisions, fm.on_error) == (
        "default",
        ["pre_tool_use"],
        ["deny", "ask", "none"],
        "ask",
    )
    assert fm.supports == ["claude_code"]
    assert fm.matcher["pre_tool_use"].tool_names == ["Skill"]
    assert {d.value for d in declaration.decisions} >= set(fm.decisions)
    assert declaration.mutates_input is False and dict(declaration.config_schema) == {}
    assert rc == 0
    assert str(engine_hook_paths()[HOOK_ID]) not in capsys.readouterr().err


def test_no_consumer_enabled_records_nothing(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path
) -> None:
    pack_repo.install_pack(["guard-generated-outputs"], prompts=engine_prompts())

    _prompt(pack_repo, deps(), state, "/review src/app.py")

    assert _stored(state) is None
