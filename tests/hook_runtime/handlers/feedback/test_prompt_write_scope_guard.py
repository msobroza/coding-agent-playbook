"""prompt-write-scope-guard and the per-turn active prompt (specs/prK-hook-pack.md §E.3, OQ-45).

The engine's five scoped prompts are rendered into the guard's ``scopes``
through the real ``render_guard_config``. Each test drives the exact dispatch
pipeline with no ``user_prompt_submit`` dispatch at all (review finding #6):
the user's turn is written to a Claude transcript (``SessionTranscript``),
or a model-invoked ``Skill`` call records the prompt, and a ``pre_tool_use``
pointing at that transcript and turn is judged against the scope.
"""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.hook_runtime.active_prompt import (
    TurnRecord,
    active_prompt_document,
    read_turn_record,
    write_turn_record,
)
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.handlers.prompt_scope import (
    READ_ONLY_REASON,
    TESTS_ONLY_REASON,
)
from coding_agent_playbook.hook_runtime.registry import load_builtin
from coding_agent_playbook.hook_runtime.state import STATE_DIR_NAME, StateStore
from tests.hook_runtime.guard_repo import SESSION_ID, hook_record
from tests.hook_runtime.handlers.pack_repo import engine_hook, engine_hook_paths, engine_prompts
from tests.hook_runtime.transcript_kit import SessionTranscript

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hook_payloads import HookPayloadCase
    from tests.hook_runtime.handlers.pack_repo import PackRepo

    type Payload = Callable[[str, str, str], HookPayloadCase]

pytestmark = pytest.mark.catalog

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


@pytest.fixture
def transcript(tmp_path: Path) -> SessionTranscript:
    return SessionTranscript(tmp_path / "session.jsonl")


def _tool(
    repo: PackRepo,
    deps: RuntimeDeps,
    state: Path,
    transcript: SessionTranscript,
    tool: str,
    tool_input: dict[str, Any],
) -> SimulateReport:
    payload = _pointed(repo.tool_payload(tool, tool_input), transcript.fields())
    return repo.simulate(payload, deps, state=state)


def _pointed(payload: bytes, fields: dict[str, str]) -> bytes:
    """``payload`` with ``fields`` (the transcript path, the turn's ``prompt_id``) set."""
    body = json.loads(payload)
    body.update(fields)
    return json.dumps(body).encode("utf-8")


def _edit(
    repo: PackRepo,
    deps: RuntimeDeps,
    state: Path,
    transcript: SessionTranscript,
    rel: str = "src/app.py",
) -> Decision:
    edit = {"file_path": str(repo.root / rel), "old_string": "a", "new_string": "b"}
    return _tool(repo, deps, state, transcript, "Edit", edit).trace.combined.decision


def _golden(
    repo: PackRepo,
    deps: RuntimeDeps,
    state: Path,
    case: HookPayloadCase,
    transcript: SessionTranscript,
) -> SimulateReport:
    """``case`` relocated into ``repo`` and pointed at ``transcript``'s file and current turn."""
    payload = _pointed(repo.relocate(case), transcript.fields())
    return repo.simulate(payload, deps, event=case.event_name, state=state)


def _stored(state: Path, session_id: str = SESSION_ID) -> TurnRecord | None:
    return read_turn_record(StateStore(state / STATE_DIR_NAME), session_id)


def test_security_review_then_edit_denied(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    hook_payload: Payload,
    state: Path,
    transcript: SessionTranscript,
) -> None:
    edit = hook_payload("claude_code", "pre_tool_use", "pwsg_edit_app")
    transcript.command("security-review", "src/app.py")
    transcript.tool_round()

    report = _golden(repo, deps(), state, edit, transcript)

    combined, expected = report.trace.combined, edit.expected["result"]
    assert (combined.decision.value, combined.reason) == (expected["decision"], expected["reason"])
    assert report.trace.wire == edit.wire()
    assert _stored(state, GOLDEN_SESSION) == TurnRecord("security-review", "prompt", "pr_1")


def test_model_invoked_skill_review_then_edit_denied(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    hook_payload: Payload,
    state: Path,
    transcript: SessionTranscript,
) -> None:
    skill = hook_payload("claude_code", "pre_tool_use", "pwsg_skill_review")
    edit = hook_payload("claude_code", "pre_tool_use", "pwsg_edit_app")
    transcript.typed("look at src/app.py for me")

    invoked = _golden(repo, deps(), state, skill, transcript)
    report = _golden(repo, deps(), state, edit, transcript)

    assert invoked.trace.wire == skill.wire()  # Skill itself is no write
    assert _stored(state, GOLDEN_SESSION) == TurnRecord("review", "skill", "pr_1")
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
    transcript: SessionTranscript,
    command: str,
    expected: Decision,
    named: str,
) -> None:
    transcript.command("review", "src/app.py")

    report = _tool(repo, deps(), state, transcript, "Bash", {"command": command})

    assert report.trace.combined.decision is expected
    if expected is Decision.ASK:
        assert report.trace.combined.reason.startswith("/review is read-only and this command")
        assert named in report.trace.combined.reason


def test_next_prompt_clears_scope(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path, transcript: SessionTranscript
) -> None:
    transcript.command("security-review", "src/app.py")
    during = _edit(repo, deps(), state, transcript)

    transcript.typed("fix it")
    after = _edit(repo, deps(), state, transcript)

    assert during is Decision.DENY
    assert after is Decision.NONE
    assert _stored(state) == TurnRecord(None, "prompt", "pr_2")


def test_typed_raw_slash_records_scope(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path, transcript: SessionTranscript
) -> None:
    transcript.typed("/explain src/app.py")

    assert _edit(repo, deps(), state, transcript) is Decision.DENY


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
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    state: Path,
    transcript: SessionTranscript,
    rel: str,
    expected: Decision,
) -> None:
    transcript.command("generate-tests", "src/app.py")
    write = {"file_path": str(repo.root / rel), "content": ""}

    report = _tool(repo, deps(), state, transcript, "Write", write)

    assert report.trace.combined.decision is expected
    if expected is Decision.ASK:
        reason = report.trace.combined.reason
        assert reason.startswith("/generate-tests writes only tests/**, **/conftest.py; this")
        assert '"src/app.py"' in reason
        assert reason.endswith(TESTS_ONLY_REASON)


def test_read_only_scratch_file_outside_repo_passes(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    state: Path,
    transcript: SessionTranscript,
    tmp_path: Path,
) -> None:
    transcript.command("explain", "src/app.py")
    write = {"file_path": str(tmp_path / "notes.md")}

    report = _tool(repo, deps(), state, transcript, "Write", write)

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
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    state: Path,
    transcript: SessionTranscript,
    text: str,
) -> None:
    transcript.typed(text)

    assert _edit(repo, deps(), state, transcript) is Decision.NONE
    assert _stored(state) == TurnRecord(None, "prompt", "pr_1")


def test_command_wrapper_records_scope(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    hook_payload: Payload,
    state: Path,
    transcript: SessionTranscript,
) -> None:
    """The ``pwsg_command_wrapper`` golden's prompt, as the transcript entry Claude writes."""
    wrapped = hook_payload("claude_code", "user_prompt_submit", "pwsg_command_wrapper")
    transcript.typed(json.loads(wrapped.raw)["prompt"])

    assert _edit(repo, deps(), state, transcript) is Decision.DENY
    assert _stored(state) == TurnRecord("review", "prompt", "pr_1")


def test_turn_is_resolved_once_then_read_from_state(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path, transcript: SessionTranscript
) -> None:
    """Later calls of the turn never reopen the transcript; a new turn does (and fails open)."""
    transcript.command("review", "src/app.py")
    first = _edit(repo, deps(), state, transcript)
    transcript.path.unlink()

    same_turn = _edit(repo, deps(), state, transcript)
    transcript.turns += 1  # a new prompt_id whose transcript cannot be read
    new_turn = _edit(repo, deps(), state, transcript)

    assert (first, same_turn, new_turn) == (Decision.DENY, Decision.DENY, Decision.NONE)


def test_without_turn_ids_a_skill_lasts_until_the_next_prompt(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path, transcript: SessionTranscript
) -> None:
    """A harness without ``prompt_id``: the Skill record is anchored to the turn's entry."""
    transcript.typed("check the module")
    path = {"transcript_path": str(transcript.path)}
    skill = _pointed(repo.tool_payload("Skill", {"skill": "review"}), path)
    edit = {"file_path": str(repo.root / "src/app.py"), "old_string": "a", "new_string": "b"}
    edit_payload = _pointed(repo.tool_payload("Edit", edit), path)

    repo.simulate(skill, deps(), state=state)
    during = repo.simulate(edit_payload, deps(), state=state)
    transcript.typed("now fix it")
    after = repo.simulate(edit_payload, deps(), state=state)

    assert _stored(state) == TurnRecord("review", "skill", None, "u-0000")
    assert during.trace.combined.decision is Decision.DENY
    assert after.trace.combined.decision is Decision.NONE


def test_unreadable_transcript_fails_open(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path, transcript: SessionTranscript
) -> None:
    transcript.command("review", "src/app.py")
    transcript.append('{"type":"user","uuid":"u-x","message":"no longer a message"}')

    assert _edit(repo, deps(), state, transcript) is Decision.NONE


class CountingStore(StateStore):
    """A real ``StateStore`` that counts document reads (the one-stat spy)."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.reads: list[str] = []

    def read_json(self, rel: str) -> dict[str, Any]:
        self.reads.append(rel)
        return super().read_json(rel)


def test_no_record_costs_one_stat(tmp_path: Path) -> None:
    store = CountingStore(tmp_path / STATE_DIR_NAME)

    absent = read_turn_record(store, SESSION_ID)
    write_turn_record(store, SESSION_ID, TurnRecord("review", "prompt", "pr_1"))
    present = read_turn_record(store, SESSION_ID)

    assert absent is None
    assert present == TurnRecord("review", "prompt", "pr_1")
    assert store.reads == [active_prompt_document(SESSION_ID)]  # only once a record exists


@pytest.mark.parametrize(
    "document",
    [
        {"v": 1, "slash": "review", "via": "prompt", "turn_id": "pr_1"},  # the old shape
        {"v": 2, "slash": "", "via": "prompt"},
        {"v": 2, "slash": "review", "via": "typed"},
        {"v": 2, "slash": "review", "via": "skill", "anchor": 7},
    ],
)
def test_malformed_or_old_record_reads_as_none(tmp_path: Path, document: dict[str, Any]) -> None:
    store = StateStore(tmp_path / STATE_DIR_NAME)
    store.write_json(active_prompt_document(SESSION_ID), document)

    assert read_turn_record(store, SESSION_ID) is None


def test_skill_recorded_while_only_the_output_contract_consumer_is_enabled(
    pack_repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    state: Path,
    transcript: SessionTranscript,
) -> None:
    """OQ-45: the Skill branch is the dispatcher's, so the guard being off never disables it."""
    contract = hook_record("prompt-output-contract-on-stop", events=["stop"], on_error="open")
    verdict = r"(?im)^\W*(approve|request changes)\W*$"
    pack_repo.install(contract, prompts={"review": {"id": "review", "output_contract": [verdict]}})
    transcript.typed("have a look")

    _tool(pack_repo, deps(), state, transcript, "Skill", {"skill": "review"})

    assert _stored(state) == TurnRecord("review", "skill", "pr_1")


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
    pack_repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    state: Path,
    transcript: SessionTranscript,
) -> None:
    pack_repo.install_pack(["guard-generated-outputs"], prompts=engine_prompts())
    transcript.command("review", "src/app.py")

    _tool(pack_repo, deps(), state, transcript, "Skill", {"skill": "review"})
    _edit(pack_repo, deps(), state, transcript)

    assert _stored(state) is None
